"""웹툰 숏폼 자동 생성 파이프라인 (Google Sheets + 브라우저 자동화)

Google Sheets를 컨트롤 패널로 사용합니다:
  [설정] 탭 - 카테고리, 프로젝트 URL, 성우, 스타일 등
  [작업목록] 탭 - '대기' 상태 작업을 순서대로 처리
  [대본] 탭 - 생성된 대본 확인/수정

사용법:
    python main.py    → 메뉴 선택 (1: 실행, 2: 계정 로그인)
"""

import os
import time

import config
import sheet_manager
from browser_manager import BrowserManager, ensure_login
from keyword_generator import generate_keywords, select_keyword
from script_generator import generate_script
from image_generator import generate_image
from voice_generator import generate_voice
from utils import log


def login_all(browser: BrowserManager, settings: dict = None):
    """모든 서비스에 미리 로그인합니다."""
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


def _discover_and_select_keyword(browser: BrowserManager, settings: dict) -> dict:
    """키워드 프로젝트 실행 → 응답 파싱 → 6개 중 1개 선택.

    Returns:
        선택된 키워드 항목 {"number", "title", "keywords", "cta"}
    """
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
    parts = [keyword_item["title"]]
    if keyword_item.get("keywords"):
        parts.append(f"키워드: {', '.join(keyword_item['keywords'])}")
    if keyword_item.get("cta"):
        parts.append(f"CTA 유형: {keyword_item['cta']}")
    return "\n".join(parts)


def process_task(browser: BrowserManager, spreadsheet, task: dict, settings: dict):
    """하나의 작업(주제)을 처리합니다."""
    # 비고에 키워드+CTA 포함 프롬프트가 있으면 그것을 사용
    topic = str(task.get("비고", "")).strip() or task["주제"]
    task_num = task["번호"]
    row = sheet_manager.find_task_row(spreadsheet, task_num)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = os.path.join(config.OUTPUT_DIR, f"project_{timestamp}")
    images_dir = os.path.join(project_dir, "images")
    voices_dir = os.path.join(project_dir, "voices")
    os.makedirs(project_dir, exist_ok=True)

    # 설정 읽기
    actor_name = settings.get("성우 이름", "").strip()
    review_script = settings.get("대본 검토", "Y").strip().upper() == "Y"
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
            script_text = generate_script(
                claude_page,
                topic=topic,
                project_url=script_project,
            )
        finally:
            claude_page.close()

        sheet_manager.update_task_status(
            spreadsheet, row, "1/4 대본 생성완료",
            제목=task["주제"],
            비고=f"대본 {len(script_text)}자",
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

        # ===== 2단계: 음성 생성 =====
        log.info("[2/3] 음성 생성 중 (Typecast)...")
        sheet_manager.update_task_status(spreadsheet, row, "2/3 음성 생성중")

        tc_page = browser.new_page()
        try:
            os.makedirs(voices_dir, exist_ok=True)
            voice_path = os.path.join(voices_dir, "voice_01.wav")

            log.info("  나레이션 음성 생성 중...")
            generate_voice(tc_page, script_text, voice_path, actor_name)
            voice_paths = [voice_path]
            log.info("  음성 생성 완료")
        finally:
            tc_page.close()

        # ===== 3단계: 이미지 생성 =====
        log.info("[3/3] 이미지 생성 중 (ChatGPT DALL-E)...")
        sheet_manager.update_task_status(spreadsheet, row, "3/3 이미지 생성중")

        gpt_page = browser.new_page()
        try:
            ensure_login(gpt_page, config.CHATGPT_URL, "ChatGPT")
            os.makedirs(images_dir, exist_ok=True)

            image_prompt = f"유튜브 쇼츠 썸네일 이미지: {task['주제']}"
            output_path = os.path.join(images_dir, "thumbnail.png")

            log.info("  썸네일 이미지 생성 중...")
            generate_image(gpt_page, image_prompt, output_path, chatgpt_project)
            valid_image_paths = [output_path]
            log.info("  이미지 생성 완료")
        finally:
            gpt_page.close()

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


def _show_menu() -> str:
    """메인 메뉴를 표시하고 선택을 반환합니다."""
    print()
    print("=" * 50)
    print("  웹툰 숏폼 자동 생성기")
    print("=" * 50)
    print("  1. 실행 (키워드 발굴 → 영상 생성)")
    print("  2. 계정 로그인 (최초 1회)")
    print("=" * 50)

    while True:
        choice = input("  선택 (1-2): ").strip()
        if choice in ("1", "2"):
            return choice
        print("  1 또는 2를 입력해주세요.")


def main():
    choice = _show_menu()

    # ===== Google Sheets 연결 =====
    log.info("Google Sheets 연결 중...")
    spreadsheet = sheet_manager.connect(config.GOOGLE_SHEET_URL)
    log.info("  시트 연결 완료: %s", spreadsheet.title)

    sheet_manager.init_sheet(spreadsheet)

    settings = sheet_manager.read_settings(spreadsheet)
    log.info("  카테고리: %s", settings.get("카테고리", "(미지정)") or "(미지정)")
    log.info("  성우: %s", settings.get("성우 이름", "(미지정)") or "(미지정)")

    with BrowserManager() as browser:

        # ===== 2번: 계정 로그인만 =====
        if choice == "2":
            login_all(browser, settings)
            log.info("로그인 전용 모드 - 작업 없이 종료합니다.")
            return

        # ===== 1번: 실행 (로그인 건너뜀) =====
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
