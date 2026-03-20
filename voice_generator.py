"""Typecast 웹(typecast.ai)을 사용한 음성 생성 모듈

Typecast Pro 구독의 웹 인터페이스를 Playwright로 자동화합니다.
장면별로 개별 음성 파일을 생성하여 컷 타이밍 동기화를 지원합니다.

실제 UI 흐름:
  1. /text-to-speech 대시보드 → "새 프로젝트" 클릭
  2. 프로젝트 만들기 다이얼로그 → 한국어 선택 → 확인
  3. 에디터: 성우 이름 클릭 → 캐릭터 목록에서 선택
  4. 스크립트 입력 → 하단 재생(▶) → 우측 상단 "다운로드"
"""

import os
from playwright.sync_api import Page
import config
from utils import log, _safe_goto


def _take_debug_screenshot(page: Page, label: str) -> None:
    """디버깅용 스크린샷을 저장합니다."""
    debug_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, f"typecast_debug_{label}.png")
    try:
        page.screenshot(path=path, full_page=True)
        log.info("    디버그 스크린샷: %s", path)
    except Exception as e:
        log.warning("    스크린샷 저장 실패: %s", e)


def _is_on_dashboard(page: Page) -> bool:
    """Typecast 대시보드(프로젝트 목록)에 있는지 확인합니다."""
    url = page.url.lower()
    return "typecast" in url and "/text-to-speech" in url and "/editor" not in url


def _is_on_project_editor(page: Page) -> bool:
    """Typecast 프로젝트 에디터에 있는지 확인합니다.

    에디터 URL 예: /text-to-speech/editor/xxx 또는 /editor/xxx
    """
    url = page.url.lower()
    if "typecast" not in url:
        return False
    # 에디터 페이지 판별: "스크립트를 입력해 주세요" placeholder 또는 URL에 editor 포함
    if "/editor" in url:
        return True
    # 대시보드가 아니면서 typecast URL이면 에디터일 가능성
    return False


def _check_typecast_logged_in(page: Page) -> bool:
    """Typecast에 로그인되어 있는지 확인합니다."""
    url = page.url.lower()
    if any(kw in url for kw in ("login", "signin", "sign-in", "auth", "signup")):
        return False
    # 대시보드나 에디터에 있으면 로그인 상태
    if "/text-to-speech" in url or "/editor" in url:
        return True
    # 메인 페이지에서 로그인 버튼 확인
    login_btn = page.locator(
        'a:has-text("로그인"), a:has-text("Login"), a:has-text("Sign in"), '
        'button:has-text("로그인"), button:has-text("Login"), button:has-text("Sign in")'
    ).first
    try:
        if login_btn.is_visible(timeout=3000):
            return False
    except Exception:
        pass
    return True


def _wait_for_login(page: Page, editor_url: str) -> None:
    """로그인 대기 (최대 60초, 1초마다 확인)."""
    log.info("")
    log.info("=" * 50)
    log.info("  Typecast 로그인이 필요합니다!")
    log.info("  브라우저 창에서 직접 로그인해주세요.")
    log.info("  60초 대기 후 자동으로 진행합니다.")
    log.info("=" * 50)

    for elapsed in range(60):
        page.wait_for_timeout(1000)
        if _check_typecast_logged_in(page):
            log.info("  Typecast 로그인 확인! (%d초 경과)", elapsed + 1)
            break
    else:
        log.warning("  60초 대기 완료. 로그인 상태를 확인할 수 없지만 계속 진행합니다.")

    # 로그인 후 대시보드로 이동
    if not _is_on_dashboard(page) and not _is_on_project_editor(page):
        _safe_goto(page, editor_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)


def _dismiss_restore_banner(page: Page) -> None:
    """'이전에 작업하던 내용이 있습니다' 배너의 무시하기 버튼 클릭."""
    try:
        dismiss_btn = page.locator('button:has-text("무시하기")').first
        if dismiss_btn.is_visible(timeout=2000):
            dismiss_btn.click()
            page.wait_for_timeout(500)
            log.info("    복원 배너 무시함")
    except Exception:
        pass


def _create_new_project(page: Page) -> None:
    """대시보드에서 새 프로젝트를 생성하고 에디터에 진입합니다."""
    # "새 프로젝트" 클릭
    new_proj_btn = page.locator('text="새 프로젝트"').first
    new_proj_btn.wait_for(timeout=10000)
    new_proj_btn.click()
    page.wait_for_timeout(1000)

    # 프로젝트 만들기 다이얼로그
    dialog = page.locator('text="프로젝트 만들기"').first
    dialog.wait_for(timeout=5000)

    # "하나의 언어 선택" 라디오 클릭
    single_lang = page.locator('text="하나의 언어 선택"').first
    try:
        if single_lang.is_visible(timeout=2000):
            single_lang.click()
            page.wait_for_timeout(500)
    except Exception:
        pass

    # "확인" 버튼 클릭
    confirm_btn = page.locator('button:has-text("확인")').first
    confirm_btn.wait_for(timeout=3000)
    confirm_btn.click()

    # 에디터 로드 대기
    page.wait_for_timeout(3000)
    log.info("    새 프로젝트 생성 완료")


def _select_actor(page: Page, actor_name: str) -> None:
    """에디터에서 성우(캐릭터)를 선택합니다.

    현재 성우 이름 영역을 클릭 → 캐릭터 패널 열림 → 이름으로 선택
    """
    # 현재 성우 이름 영역 클릭 (예: "박창수 ▸")
    # 성우 이름 옆의 ▸ 기호가 있는 버튼 또는 성우 프로필 영역
    actor_btn = page.locator('[class*="actor"], [class*="character"], [class*="speaker"]').first
    try:
        if not actor_btn.is_visible(timeout=2000):
            # 클래스로 못 찾으면 ▸ 기호가 있는 요소 시도
            actor_btn = page.locator('button:has-text("▸"), button:has-text("►")').first
    except Exception:
        actor_btn = page.locator('button:has-text("▸"), button:has-text("►")').first

    try:
        if actor_btn.is_visible(timeout=2000):
            actor_btn.click()
            page.wait_for_timeout(1000)
        else:
            # 성우 프로필 아바타 영역 시도
            log.info("    성우 버튼을 찾는 중...")
            _take_debug_screenshot(page, "actor_search")
    except Exception:
        pass

    # 캐릭터 패널이 열린 상태 - 목록에서 성우 이름 클릭
    actor_item = page.locator(f'text="{actor_name}"').first
    try:
        if actor_item.is_visible(timeout=3000):
            actor_item.click()
            page.wait_for_timeout(1000)
            log.info("    성우 '%s' 선택 완료", actor_name)

            # 패널 닫기 - 에디터 빈 영역 클릭
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            return
    except Exception:
        pass

    # 직접 이름이 안 보이면 검색 시도
    search_input = page.locator(
        'input[placeholder*="검색"], input[placeholder*="찾기"], input[type="search"]'
    ).first
    try:
        if search_input.is_visible(timeout=2000):
            search_input.click()
            search_input.fill(actor_name)
            page.wait_for_timeout(1000)

            actor_result = page.locator(f'text="{actor_name}"').first
            if actor_result.is_visible(timeout=3000):
                actor_result.click()
                page.wait_for_timeout(500)
                log.info("    성우 '%s' 검색+선택 완료", actor_name)
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                return
    except Exception:
        pass

    log.warning("    성우 '%s'를 찾을 수 없습니다. 기본 성우로 진행합니다.", actor_name)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)


def _enter_script(page: Page, text: str) -> None:
    """에디터의 스크립트 입력 영역에 텍스트를 입력합니다.

    placeholder: "스크립트를 입력해 주세요."
    """
    # 스크립트 입력 영역 찾기
    _TEXT_SELECTORS = [
        '[data-placeholder*="스크립트"]',
        '[placeholder*="스크립트"]',
        '[contenteditable="true"]',
        '[role="textbox"]',
        'textarea',
        'div[data-placeholder]',
    ]

    text_input = None
    for sel in _TEXT_SELECTORS:
        loc = page.locator(sel).first
        try:
            if loc.is_visible(timeout=2000):
                text_input = loc
                log.info("    텍스트 입력 발견: %s", sel)
                break
        except Exception:
            continue

    if not text_input:
        _take_debug_screenshot(page, "no_text_input")
        raise RuntimeError(
            "Typecast 텍스트 입력창을 찾을 수 없습니다. "
            "temp/typecast_debug_no_text_input.png 확인"
        )

    text_input.click()
    page.wait_for_timeout(300)

    # 기존 텍스트 전체 선택 후 교체
    page.keyboard.press("Control+a")
    page.wait_for_timeout(200)

    # fill() 시도 → 실패하면 keyboard.type()
    try:
        text_input.fill(text)
    except Exception:
        page.keyboard.type(text, delay=10)
    page.wait_for_timeout(500)


def _click_play_and_wait(page: Page) -> None:
    """하단 재생(▶) 버튼을 클릭하고 합성 완료를 대기합니다.

    재생 버튼: 하단 중앙의 큰 주황색 원형 버튼
    합성 완료: 재생 시간이 0:00이 아닌 값으로 변경되면 완료
    """
    # 재생 버튼 찾기 - 하단 플레이어의 SVG 재생 아이콘 또는 aria-label
    _PLAY_SELECTORS = [
        'button[aria-label*="play"]',
        'button[aria-label*="Play"]',
        'button[aria-label*="재생"]',
        'button:has-text("▶")',
        # SVG play 아이콘이 들어있는 버튼 (원형 주황 버튼)
        'button svg polygon',
        'button svg path',
    ]

    play_btn = None

    # 먼저 페이지 하단 영역에서 큰 원형 버튼 찾기
    # Typecast 플레이어: 하단에 재생/이전/다음 버튼이 있음
    all_buttons = page.locator('button').all()
    for btn in all_buttons:
        try:
            # SVG가 포함된 버튼 중 하단에 위치한 것
            bbox = btn.bounding_box()
            if bbox and bbox['y'] > 600 and bbox['width'] > 30:
                # 큰 원형 버튼 (재생 버튼은 보통 40px 이상)
                if bbox['width'] > 40 and bbox['height'] > 40:
                    play_btn = btn
                    break
        except Exception:
            continue

    if not play_btn:
        for sel in _PLAY_SELECTORS:
            loc = page.locator(sel).first
            try:
                if loc.is_visible(timeout=1000):
                    play_btn = loc
                    break
            except Exception:
                continue

    if not play_btn:
        _take_debug_screenshot(page, "no_play_btn")
        raise RuntimeError(
            "Typecast 재생 버튼을 찾을 수 없습니다. "
            "temp/typecast_debug_no_play_btn.png 확인"
        )

    play_btn.click()
    log.info("    음성 합성 중...")

    # 합성 완료 대기: 재생 시간이 0:00 / 0:00에서 변경되면 완료
    for elapsed in range(180):
        page.wait_for_timeout(1000)
        # 시간 표시 텍스트 확인 (예: "0:05 / 0:30")
        time_text = page.locator('text=/\\d+:\\d+ \\/ \\d+:\\d+/').first
        try:
            if time_text.is_visible():
                content = time_text.text_content()
                if content and "/ 0:00" not in content:
                    log.info("    합성 완료: %s", content.strip())
                    page.wait_for_timeout(1000)
                    return
        except Exception:
            pass

        # 진행률 표시가 있을 수 있음
        if elapsed > 0 and elapsed % 30 == 0:
            log.info("    아직 합성 중... (%d초 경과)", elapsed)

    _take_debug_screenshot(page, "synthesis_timeout")
    raise TimeoutError("Typecast 음성 합성 타임아웃 (3분)")


def _download_audio(page: Page, output_path: str) -> str:
    """우측 상단 '다운로드' 버튼으로 음성 파일을 저장합니다."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    dl_btn = page.locator(
        'button:has-text("다운로드"), '
        'a:has-text("다운로드"), '
        'button:has-text("Download"), '
        'a:has-text("Download"), '
        'a[download]'
    ).first

    if not dl_btn.is_visible(timeout=5000):
        _take_debug_screenshot(page, "no_download_btn")
        raise RuntimeError(
            "Typecast 다운로드 버튼을 찾을 수 없습니다. "
            "temp/typecast_debug_no_download_btn.png 확인"
        )

    with page.expect_download(timeout=30000) as download_info:
        dl_btn.click()
    download = download_info.value
    download.save_as(output_path)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"음성 파일 다운로드 실패: {output_path}")

    return output_path


def _ensure_editor_ready(page: Page, actor_name: str, editor_url: str = "") -> None:
    """Typecast 에디터 진입 (로그인 확인 → 새 프로젝트 생성 → 성우 선택).

    이미 에디터에 있으면 성우 선택만 수행합니다.
    """
    if not editor_url:
        editor_url = f"{config.TYPECAST_URL}/text-to-speech"

    # 1. 대시보드 또는 에디터가 아니면 이동
    if not _is_on_dashboard(page) and not _is_on_project_editor(page):
        _safe_goto(page, editor_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

    # 2. 로그인 확인
    if not _check_typecast_logged_in(page):
        _wait_for_login(page, editor_url)

    # 3. 대시보드에 있으면 새 프로젝트 생성
    if _is_on_dashboard(page):
        _dismiss_restore_banner(page)
        _create_new_project(page)

    # 4. 에디터에서 성우 선택
    _select_actor(page, actor_name)


def _synthesize_one(page: Page, text: str, output_path: str) -> str:
    """에디터에서 텍스트 합성 → 다운로드 (1건)."""
    _enter_script(page, text)
    _click_play_and_wait(page)
    return _download_audio(page, output_path)


def generate_voice(
    page: Page, text: str, output_path: str,
    actor_name: str = "", editor_url: str = "",
) -> str:
    """Typecast 웹에서 음성을 생성하고 다운로드합니다 (단건)."""
    if not actor_name:
        raise ValueError("성우 이름이 지정되지 않았습니다. 시트 [설정] 탭의 '성우 이름'을 입력하세요.")

    _ensure_editor_ready(page, actor_name, editor_url)
    return _synthesize_one(page, text, output_path)


def generate_voices_per_scene(
    page: Page,
    scenes: list[dict],
    voices_dir: str,
    actor_name: str = "",
    editor_url: str = "",
) -> list[str]:
    """장면별로 개별 음성 파일을 생성합니다.

    Args:
        scenes: 구조화된 장면 목록 (scene_number, narration 포함)
        voices_dir: 음성 파일 저장 디렉토리
        actor_name: Typecast 성우 이름
        editor_url: 시트 [설정]의 'Typecast 에디터 URL'

    Returns:
        생성된 음성 파일 경로 목록 (장면 순서대로)
    """
    if not actor_name:
        raise ValueError("성우 이름이 지정되지 않았습니다. 시트 [설정] 탭의 '성우 이름'을 입력하세요.")

    os.makedirs(voices_dir, exist_ok=True)
    _ensure_editor_ready(page, actor_name, editor_url)

    voice_paths = []
    for scene in scenes:
        scene_num = scene["scene_number"]
        narration = scene.get("narration", "").strip()
        if not narration:
            log.warning("  장면%d: 나레이션 없음, 건너뜀", scene_num)
            continue

        output_path = os.path.join(voices_dir, f"voice_s{scene_num:02d}.wav")
        log.info("  장면%d 음성 생성 중 (%d자)...", scene_num, len(narration))

        _synthesize_one(page, narration, output_path)
        voice_paths.append(output_path)

        log.info("    장면%d 음성 완료: %s", scene_num, os.path.basename(output_path))

    return voice_paths
