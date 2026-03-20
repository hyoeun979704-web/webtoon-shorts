"""웹툰 숏폼 자동 생성 파이프라인 (Google Sheets + 브라우저 자동화)

Google Sheets를 컨트롤 패널로 사용합니다:
  [설정] 탭 - 카테고리, 프로젝트 URL, 스타일 등
  [작업목록] 탭 - 작업 큐 (상태: 대기/대본완료)
  [대본] 탭 - 생성된 대본 확인/수정

작업 상태별 동작:
  '대기'     → 1단계(대본 생성)부터 전체 파이프라인 실행
  '대본완료' → 시트 [대본] 탭의 대본을 사용, 이미지 생성부터 실행

사용법:
    python main.py           → 실행 (키워드 발굴 → 영상 생성)
    python main.py --login   → 계정 로그인만 수행
"""

import argparse
import os
import time

import config
import sheet_manager
from browser_manager import BrowserManager, ensure_login
from keyword_generator import generate_keywords, select_keyword
from script_generator import generate_script, structure_script
from image_generator import init_image_session, generate_image_in_session
from video_editor import assemble_video
from utils import log


def login_all(browser: BrowserManager, settings: dict = None):
    """모든 서비스에 미리 로그인합니다."""
    services = [
        (config.CLAUDE_URL, "Claude", "Claude 계정"),
        (config.CHATGPT_URL, "ChatGPT", "ChatGPT 계정"),
        (config.CAPCUT_URL, "CapCut", "CapCut 계정"),
    ]
    page = browser.new_page()
    for url, name, account_key in services:
        account = (settings or {}).get(account_key, "").strip()
        if account:
            log.info("%s 로그인 확인 중... (계정: %s)", name, account)
        else:
            log.info("%s 로그인 확인 중...", name)
        ensure_login(page, url, name, account_hint=account)
        log.info("  %s 로그인 완료!", name)
    page.close()
    log.info("모든 서비스 로그인 완료!")


def _validate_settings(settings: dict) -> None:
    """필수 설정값이 있는지 검증합니다."""
    if not settings.get("카테고리", "").strip():
        raise ValueError("시트 [설정] 탭에 '카테고리'를 입력해주세요.")


def _discover_and_select_keyword(browser: BrowserManager, settings: dict) -> dict:
    """키워드 프로젝트 실행 → 응답 파싱 → 1개 선택."""
    category = settings.get("카테고리", "").strip()
    count = int(settings.get("키워드 개수", "6") or "6")
    keyword_project = settings.get("Claude 키워드 프로젝트 URL", "").strip()

    log.info("카테고리 [%s]에서 키워드 %d개 발굴 중...", category, count)

    claude_page = browser.new_page()
    try:
        items = generate_keywords(
            claude_page,
            category=category,
            count=count,
            project_url=keyword_project,
        )
    finally:
        claude_page.close()

    selected = select_keyword(items)
    return selected


def _build_script_prompt(keyword_item: dict) -> str:
    """선택된 키워드 항목으로 대본 프롬프트를 구성합니다."""
    title = keyword_item["title"]
    parts = [title]
    # 타이틀에 이미 키워드/CTA가 포함되어 있으면 중복 추가하지 않음
    if keyword_item.get("keywords") and "키워드:" not in title:
        parts.append(f"키워드: {', '.join(keyword_item['keywords'])}")
    if keyword_item.get("cta") and "CTA" not in title:
        parts.append(f"CTA 유형: {keyword_item['cta']}")
    return "\n".join(parts)


def _dedup_topic(text: str) -> str:
    """topic 텍스트에서 중복된 줄을 제거합니다."""
    lines = text.strip().split("\n")
    seen = []
    for line in lines:
        line = line.strip()
        if line and line not in seen:
            seen.append(line)
    return "\n".join(seen)


def process_task(browser: BrowserManager, spreadsheet, task: dict, settings: dict):
    """하나의 작업(주제)을 처리합니다.

    작업 상태에 따라 시작 단계가 달라집니다:
      '대기'     → 1단계(대본 생성)부터 시작
      '대본완료' → 시트 [대본] 탭의 대본을 사용, 이미지 생성부터 시작
    """
    # 비고에 키워드+CTA 포함 프롬프트가 있으면 그것을 사용
    topic = _dedup_topic(str(task.get("비고", "")).strip() or task["주제"])
    task_num = task["번호"]
    task_status = str(task.get("상태", "")).strip()
    row = sheet_manager.find_task_row(spreadsheet, task_num)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = os.path.join(config.OUTPUT_DIR, f"project_{timestamp}")
    images_dir = os.path.join(project_dir, "images")
    os.makedirs(project_dir, exist_ok=True)

    # 설정 읽기
    review_script = settings.get("대본 검토", "Y").strip().upper() == "Y"
    script_project = settings.get("Claude 대본 프로젝트 URL", "").strip()
    chatgpt_project = settings.get("ChatGPT 프로젝트 URL", "").strip()

    sheet_manager.update_task_status(
        spreadsheet, row, "진행중",
        시작시간=time.strftime("%Y-%m-%d %H:%M:%S"),
    )

    edit_mode = settings.get("편집 모드", "capcut").strip().lower()
    review_edit = settings.get("편집 검토", "Y").strip().upper() == "Y"

    # 시트 대본 기반 실행 여부 판단
    skip_script_gen = task_status == "대본완료"

    try:
        if skip_script_gen:
            # ===== 시트 대본 읽기 (1~2단계 건너뜀) =====
            log.info("[대본완료] 시트 [대본] 탭에서 대본을 읽습니다...")
            script_data = sheet_manager.read_script_from_sheet(spreadsheet)
            if not script_data or not script_data.get("scenes"):
                raise ValueError(
                    "시트 [대본] 탭에 대본이 없습니다. "
                    "장면번호/컷번호/나레이션/이미지 프롬프트를 입력해주세요."
                )

            script_data["title"] = task["주제"]
            structured = script_data

            total_cuts = sum(len(s.get("cuts", [])) for s in structured["scenes"])
            log.info("  시트 대본 로드: %d장면, %d컷", len(structured["scenes"]), total_cuts)

            sheet_manager.update_task_status(
                spreadsheet, row, "2/4 구조화완료",
                제목=task["주제"],
                장면수=len(structured["scenes"]),
            )

        else:
            # ===== 1단계: 대본 생성 + 구조화 =====
            log.info("[1/4] 대본 생성 중 (Claude) - '%s'", topic)
            sheet_manager.update_task_status(spreadsheet, row, "1/4 대본 생성중")

            claude_page = browser.new_page()
            try:
                script_text = generate_script(
                    claude_page,
                    topic=topic,
                    project_url=script_project,
                )

                script_path = os.path.join(project_dir, "script.txt")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(script_text)

                log.info("  대본 (%d자): %s...", len(script_text), script_text[:100])

                # ===== 검토 포인트 1: 대본 검토 =====
                if review_script:
                    sheet_manager.update_task_status(spreadsheet, row, "대본 검토 대기")
                    log.info("")
                    log.info("=" * 50)
                    log.info("  [대본 검토] 추출된 대본:")
                    log.info("")
                    log.info("  %s", script_text)
                    log.info("")
                    log.info("  수정하려면 새 대본을 입력, 그대로 진행하려면 Enter")
                    log.info("=" * 50)
                    user_input = input("  → 대본 수정 (Enter=유지): ").strip()
                    if user_input:
                        script_text = user_input
                        with open(script_path, "w", encoding="utf-8") as f:
                            f.write(script_text)
                        log.info("  대본이 수정되었습니다.")

                # ===== 구조화: 같은 Claude 대화에서 장면/컷/이미지 프롬프트 생성 =====
                log.info("[2/4] 대본 구조화 중 (장면/컷/이미지 프롬프트)...")
                sheet_manager.update_task_status(spreadsheet, row, "2/4 구조화중")

                structured = structure_script(claude_page, script_text, settings)
            finally:
                claude_page.close()

            # 구조화된 대본을 시트에 반영
            script_data = {"title": task["주제"], "scenes": structured["scenes"]}
            sheet_manager.write_script_to_sheet(spreadsheet, script_data)

            total_cuts = sum(len(s.get("cuts", [])) for s in structured["scenes"])
            log.info("  시트 반영 완료: %d장면, %d컷", len(structured["scenes"]), total_cuts)

            sheet_manager.update_task_status(
                spreadsheet, row, "2/4 구조화완료",
                제목=task["주제"],
                장면수=len(structured["scenes"]),
            )

        # ===== 3단계: 이미지 생성 (컷별, 같은 대화 유지) =====
        log.info("[3/4] 이미지 생성 중 (ChatGPT DALL-E) - %d컷...", total_cuts)
        sheet_manager.update_task_status(spreadsheet, row, "3/4 이미지 생성중")

        gpt_page = browser.new_page()
        image_paths = []
        try:
            init_image_session(gpt_page, chatgpt_project)
            os.makedirs(images_dir, exist_ok=True)

            img_idx = 0
            for scene in structured["scenes"]:
                for cut in scene.get("cuts", []):
                    img_idx += 1
                    prompt = cut.get("image_prompt", "").strip()
                    if not prompt:
                        log.warning("  장면%d-컷%d: 이미지 프롬프트 없음, 건너뜀",
                                    scene["scene_number"], cut["cut_number"])
                        continue

                    output_path = os.path.join(
                        images_dir,
                        f"s{scene['scene_number']:02d}_c{cut['cut_number']:02d}.png",
                    )
                    log.info("  [%d/%d] 장면%d-컷%d 이미지 생성 중...",
                             img_idx, total_cuts,
                             scene["scene_number"], cut["cut_number"])

                    generate_image_in_session(gpt_page, prompt, output_path)
                    image_paths.append(output_path)

                    # 시트에 이미지 상태 업데이트
                    sheet_row = 1 + img_idx  # 헤더(1) + 컷 순서
                    sheet_manager.update_script_cut_status(
                        spreadsheet, sheet_row, image_status="완료"
                    )

            log.info("  이미지 생성 완료 (%d컷)", len(image_paths))
        finally:
            gpt_page.close()

        # ===== 4단계: CapCut 영상 편집 =====
        if edit_mode == "skip":
            log.info("[4/4] 편집 건너뜀 (편집 모드: skip)")
        else:
            log.info("[4/4] 영상 편집 중 (CapCut)...")
            sheet_manager.update_task_status(spreadsheet, row, "4/4 편집중")

            video_path = os.path.join(project_dir, "final.mp4")
            capcut_page = browser.new_page()
            try:
                assemble_video(
                    capcut_page,
                    script=script_data,
                    image_paths=image_paths,
                    output_path=video_path,
                    auto_export=not review_edit,
                )
                log.info("  영상 내보내기 완료: %s", video_path)
            finally:
                capcut_page.close()

        # ===== 완료 =====
        sheet_manager.update_task_status(
            spreadsheet, row, "완료",
            완료시간=time.strftime("%Y-%m-%d %H:%M:%S"),
            출력경로=project_dir,
        )
        log.info("완료! 출력 폴더: %s", project_dir)

    except Exception as e:
        sheet_manager.update_task_status(
            spreadsheet, row, "오류",
            비고=str(e)[:200],
        )
        log.error("오류 발생: %s", e)
        raise


def main():
    parser = argparse.ArgumentParser(description="웹툰 숏폼 자동 생성기")
    parser.add_argument("--login", action="store_true", help="계정 로그인만 수행 (최초 1회)")
    args = parser.parse_args()

    # ===== Google Sheets 연결 =====
    log.info("Google Sheets 연결 중...")
    spreadsheet = sheet_manager.connect(config.GOOGLE_SHEET_URL)
    log.info("  시트 연결 완료: %s", spreadsheet.title)

    sheet_manager.init_sheet(spreadsheet)

    settings = sheet_manager.read_settings(spreadsheet)
    log.info("  카테고리: %s", settings.get("카테고리", "(미지정)") or "(미지정)")

    with BrowserManager() as browser:

        # ===== 로그인 전용 모드 =====
        if args.login:
            login_all(browser, settings)
            log.info("로그인 완료 - 종료합니다.")
            return

        # ===== 실행 모드 (로그인 건너뜀) =====
        _validate_settings(settings)

        # 대기 작업 확인
        pending = sheet_manager.get_pending_tasks(spreadsheet)

        if not pending:
            # 키워드 프로젝트 실행 → 파싱 → 1개 선택 → 작업 추가
            log.info("대기 작업이 없어 키워드를 발굴합니다...")
            selected = _discover_and_select_keyword(browser, settings)

            # 선택된 키워드의 제목+키워드+CTA를 주제로 작업 추가
            topic_text = _build_script_prompt(selected)
            added = sheet_manager.append_tasks(spreadsheet, [
                {"topic": selected["title"], "hook": topic_text}
            ])
            log.info("[작업목록]에 %d건 추가 완료", added)

            pending = sheet_manager.get_pending_tasks(spreadsheet)

        if not pending:
            log.error("대기 작업이 없습니다. 시트를 확인해주세요.")
            return

        log.info("처리할 작업: %d건", len(pending))
        for t in pending:
            log.info("  #%s %s", t["번호"], t["주제"])

        # 작업 순서대로 처리
        failed = 0
        for task in pending:
            log.info("")
            log.info("=" * 50)
            log.info("  작업 #%s: %s", task["번호"], task["주제"])
            log.info("=" * 50)
            try:
                process_task(browser, spreadsheet, task, settings)
            except Exception as e:
                log.error("작업 #%s 실패: %s", task["번호"], e)
                failed += 1
                continue

    if failed:
        log.warning("완료! (성공 %d건 / 실패 %d건)", len(pending) - failed, failed)
    else:
        log.info("모든 작업 완료! (%d건)", len(pending))


if __name__ == "__main__":
    main()
