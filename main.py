"""웹툰 숏폼 자동 생성 파이프라인 (Google Sheets + 브라우저 자동화)

Google Sheets를 컨트롤 패널로 사용합니다:
  [설정] 탭 - 카테고리, 프로젝트 URL, 성우, 스타일 등
  [작업목록] 탭 - '대기' 상태 작업을 순서대로 처리
  [대본] 탭 - 생성된 대본 확인/수정

사용법:
    python main.py                 # 전체 자동 실행 (키워드 발굴 → 영상 생성)
    python main.py --login         # 각 서비스 로그인만 수행 (최초 1회)
"""

import argparse
import json
import os
import time

import config
import sheet_manager
from browser_manager import BrowserManager, ensure_login
from keyword_generator import generate_keywords
from script_generator import generate_script
from image_generator import generate_image
from voice_generator import generate_voice
from video_editor import assemble_video
from utils import log


def login_all(browser: BrowserManager, settings: dict = None):
    """모든 서비스에 미리 로그인합니다.

    settings에 서비스별 계정 정보가 있으면 로그인 시 안내합니다.
    """
    services = [
        (config.CLAUDE_URL, "Claude", "Claude 계정"),
        (config.CHATGPT_URL, "ChatGPT", "ChatGPT 계정"),
        (config.TYPECAST_URL, "Typecast", "Typecast 계정"),
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
    missing = []
    if not settings.get("카테고리", "").strip():
        missing.append("카테고리")
    if not settings.get("성우 이름", "").strip():
        missing.append("성우 이름")
    if missing:
        raise ValueError(
            f"시트 [설정] 탭에 다음 항목을 입력해주세요: {', '.join(missing)}"
        )


def _auto_discover_keywords(browser: BrowserManager, spreadsheet, settings: dict) -> None:
    """대기 작업이 없으면 자동으로 키워드를 발굴합니다."""
    category = settings.get("카테고리", "").strip()
    count = int(settings.get("키워드 개수", "5") or "5")
    keyword_project = settings.get("Claude 키워드 프로젝트 URL", "").strip()

    log.info("카테고리 [%s]에서 토픽 %d개 자동 발굴 중...", category, count)

    claude_page = browser.new_page()
    try:
        keywords = generate_keywords(
            claude_page,
            category=category,
            count=count,
            project_url=keyword_project,
        )
    finally:
        claude_page.close()

    added = sheet_manager.append_tasks(spreadsheet, keywords)
    log.info("[작업목록]에 %d건 자동 추가 완료", added)


def process_task(browser: BrowserManager, spreadsheet, task: dict, settings: dict):
    """하나의 작업(주제)을 처리합니다."""
    topic = task["주제"]
    task_num = task["번호"]
    row = sheet_manager.find_task_row(spreadsheet, task_num)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = os.path.join(config.OUTPUT_DIR, f"project_{timestamp}")
    images_dir = os.path.join(project_dir, "images")
    voices_dir = os.path.join(project_dir, "voices")
    os.makedirs(project_dir, exist_ok=True)

    # 설정 읽기
    actor_name = settings.get("성우 이름", "").strip()
    edit_mode = settings.get("편집 모드", "capcut").strip().lower()
    review_script = settings.get("대본 검토", "Y").strip().upper() == "Y"
    review_edit = settings.get("편집 검토", "Y").strip().upper() == "Y"
    script_project = settings.get("Claude 대본 프로젝트 URL", "").strip()
    chatgpt_project = settings.get("ChatGPT 프로젝트 URL", "").strip()

    sheet_manager.update_task_status(
        spreadsheet, row, "진행중",
        시작시간=time.strftime("%Y-%m-%d %H:%M:%S"),
    )

    try:
        # ===== 1단계: 대본 생성 =====
        log.info("[1/4] 대본 생성 중 (Claude) - '%s'", topic)
        sheet_manager.update_task_status(spreadsheet, row, "1/4 대본 생성중")

        claude_page = browser.new_page()
        try:
            script = generate_script(
                claude_page,
                topic=topic,
                project_url=script_project,
            )
        finally:
            claude_page.close()

        total_cuts = sum(len(s.get("cuts", [])) for s in script["scenes"])

        sheet_manager.write_script_to_sheet(spreadsheet, script)
        sheet_manager.update_task_status(
            spreadsheet, row, "1/4 대본 생성완료",
            제목=script["title"],
            장면수=f"{len(script['scenes'])}장면/{total_cuts}컷",
        )

        script_path = os.path.join(project_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        log.info("  제목: %s (%d장면, %d컷)", script["title"], len(script["scenes"]), total_cuts)

        # ===== 검토 포인트 1: 대본 검토 =====
        if review_script:
            sheet_manager.update_task_status(spreadsheet, row, "대본 검토 대기")
            log.info("")
            log.info("=" * 50)
            log.info("  [대본 검토] Google Sheets [대본] 탭을 확인하세요.")
            log.info("")
            log.info("  수정 가능 항목:")
            log.info("    - 나레이션 텍스트")
            log.info("    - 이미지 프롬프트")
            log.info("    - 자막 (컷별 자유 수정)")
            log.info("    - 효과음 (CapCut 이름으로 수정)")
            log.info("    - 장면전환 (CapCut 이름으로 수정)")
            log.info("")
            log.info("  수정 완료 후 Enter를 눌러주세요.")
            log.info("  (수정 없이 바로 진행하려면 그냥 Enter)")
            log.info("=" * 50)
            input("  → Enter: ")

            edited = sheet_manager.read_script_from_sheet(spreadsheet)
            if edited and edited["scenes"]:
                edited["title"] = script["title"]
                script = edited
                with open(script_path, "w", encoding="utf-8") as f:
                    json.dump(script, f, ensure_ascii=False, indent=2)
                log.info("  시트에서 수정된 대본을 반영했습니다.")
                total_cuts = sum(len(s.get("cuts", [])) for s in script["scenes"])

        # ===== 2단계: 이미지 생성 =====
        log.info("[2/4] 이미지 생성 중 (ChatGPT DALL-E)...")
        sheet_manager.update_task_status(spreadsheet, row, "2/4 이미지 생성중")

        gpt_page = browser.new_page()
        try:
            ensure_login(gpt_page, config.CHATGPT_URL, "ChatGPT")

            image_paths = []  # cut 순서와 1:1 매칭 (빈 프롬프트는 빈 문자열)
            os.makedirs(images_dir, exist_ok=True)

            sheet_row = 2
            for scene in script["scenes"]:
                scene_num = scene["scene_number"]
                cuts = scene.get("cuts", [])
                if not cuts:
                    cuts = [{"cut_number": 1, "image_prompt": scene.get("image_prompt", "")}]

                for cut in cuts:
                    cut_num = cut["cut_number"]
                    prompt = cut.get("image_prompt", "").strip()
                    if not prompt:
                        log.warning("  장면 %d 컷 %d: 이미지 프롬프트가 비어있어 건너뜁니다", scene_num, cut_num)
                        image_paths.append("")  # 빈 슬롯 유지 (인덱스 정합성)
                        sheet_row += 1
                        continue

                    output_path = os.path.join(
                        images_dir, f"scene_{scene_num:02d}_cut_{cut_num:02d}.png"
                    )

                    log.info("  장면 %d 컷 %d 이미지 생성 중...", scene_num, cut_num)
                    generate_image(gpt_page, prompt, output_path, chatgpt_project)
                    image_paths.append(output_path)

                    sheet_manager.update_script_cut_status(
                        spreadsheet, sheet_row, image_status="완료"
                    )
                    log.info("  장면 %d 컷 %d 이미지 완료", scene_num, cut_num)
                    sheet_row += 1
        finally:
            gpt_page.close()

        valid_image_paths = [p for p in image_paths if p]
        log.info("  총 %d장 이미지 생성 완료", len(valid_image_paths))

        if not valid_image_paths:
            raise RuntimeError("생성된 이미지가 없습니다. 대본의 이미지 프롬프트를 확인하세요.")

        # ===== 3단계: 음성 생성 =====
        log.info("[3/4] 음성 생성 중 (Typecast)...")
        sheet_manager.update_task_status(spreadsheet, row, "3/4 음성 생성중")

        tc_page = browser.new_page()
        try:
            voice_paths = []
            os.makedirs(voices_dir, exist_ok=True)

            scene_first_row = {}
            current_row = 2
            for scene in script["scenes"]:
                scene_num = scene["scene_number"]
                scene_first_row[scene_num] = current_row
                num_cuts = len(scene.get("cuts", [{"cut_number": 1}]))
                current_row += num_cuts

            for scene in script["scenes"]:
                scene_num = scene["scene_number"]
                narration = scene.get("narration", "").strip()
                if not narration:
                    log.warning("  장면 %d: 나레이션이 비어있어 건너뜁니다", scene_num)
                    continue

                output_path = os.path.join(voices_dir, f"voice_{scene_num:02d}.wav")

                log.info("  장면 %d 음성 생성 중...", scene_num)
                generate_voice(tc_page, narration, output_path, actor_name)
                voice_paths.append(output_path)

                sheet_manager.update_script_cut_status(
                    spreadsheet, scene_first_row[scene_num], voice_status="완료"
                )
                log.info("  장면 %d 음성 완료", scene_num)
        finally:
            tc_page.close()

        # ===== 4단계: 영상 편집 =====
        if edit_mode == "skip":
            sheet_manager.update_task_status(
                spreadsheet, row, "완료 (에셋만)",
                완료시간=time.strftime("%Y-%m-%d %H:%M:%S"),
                출력경로=project_dir,
            )
            log.info("에셋 생성 완료! 폴더: %s", project_dir)
        else:
            log.info("[4/4] 영상 편집 중 (CapCut)...")
            sheet_manager.update_task_status(spreadsheet, row, "4/4 편집중")

            capcut_page = browser.new_page()
            try:
                output_video = os.path.join(project_dir, f"{script['title']}.mp4")

                if review_edit:
                    sheet_manager.update_task_status(spreadsheet, row, "4/4 편집 배치중")

                assemble_video(
                    capcut_page,
                    script,
                    valid_image_paths,
                    voice_paths,
                    output_video,
                    auto_export=not review_edit,
                )

                if review_edit:
                    sheet_manager.update_task_status(spreadsheet, row, "4/4 내보내기중")
            finally:
                capcut_page.close()

            sheet_manager.update_task_status(
                spreadsheet, row, "완료",
                완료시간=time.strftime("%Y-%m-%d %H:%M:%S"),
                출력경로=output_video,
            )
            log.info("완료! 최종 영상: %s", output_video)

    except Exception as e:
        sheet_manager.update_task_status(
            spreadsheet, row, "오류",
            비고=str(e)[:200],
        )
        log.error("오류 발생: %s", e)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="웹툰 숏폼 자동 생성기 (Google Sheets 기반)"
    )
    parser.add_argument("--login", action="store_true", help="서비스 로그인만 수행 (최초 1회)")
    parser.add_argument("--headless", action="store_true", help="브라우저 숨김")
    args = parser.parse_args()

    if args.headless:
        config.HEADLESS = True

    # ===== Google Sheets 연결 =====
    log.info("Google Sheets 연결 중...")
    spreadsheet = sheet_manager.connect(config.GOOGLE_SHEET_URL)
    log.info("  시트 연결 완료: %s", spreadsheet.title)

    # ===== 시트 자동 초기화 (탭이 없으면 생성) =====
    sheet_manager.init_sheet(spreadsheet)

    # ===== 설정 읽기 =====
    settings = sheet_manager.read_settings(spreadsheet)
    log.info("  카테고리: %s", settings.get("카테고리", "(미지정)") or "(미지정)")
    log.info("  성우: %s", settings.get("성우 이름", "(미지정)") or "(미지정)")

    with BrowserManager() as browser:
        # ===== 로그인 (항상 확인) =====
        login_all(browser, settings)

        # ===== 로그인 전용 모드 =====
        if args.login:
            log.info("로그인 전용 모드 - 작업 없이 종료합니다.")
            return

        # ===== 필수 설정 검증 =====
        _validate_settings(settings)

        # 대기 작업 확인 → 없으면 자동으로 키워드 발굴
        pending = sheet_manager.get_pending_tasks(spreadsheet)
        if not pending:
            log.info("대기 작업이 없어 키워드를 자동 발굴합니다...")
            _auto_discover_keywords(browser, spreadsheet, settings)
            pending = sheet_manager.get_pending_tasks(spreadsheet)

        if not pending:
            log.error("키워드 발굴 후에도 대기 작업이 없습니다. 시트를 확인해주세요.")
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
