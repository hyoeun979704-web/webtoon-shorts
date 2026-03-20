"""Typecast 웹(typecast.ai)을 사용한 음성 생성 모듈

Typecast Pro 구독의 웹 인터페이스를 Playwright로 자동화합니다.
장면별로 개별 음성 파일을 생성하여 컷 타이밍 동기화를 지원합니다.
"""

import os
from playwright.sync_api import Page
import config
from utils import log, _safe_goto


def _is_on_editor(page: Page) -> bool:
    """이미 Typecast 에디터 페이지에 있는지 확인합니다."""
    url = page.url.lower()
    return "typecast" in url and ("/text-to-speech" in url or "/editor" in url)


def _check_typecast_logged_in(page: Page) -> bool:
    """Typecast에 로그인되어 있는지 확인합니다.

    에디터 페이지 접근 가능 여부 또는 로그인/랜딩 페이지 리다이렉트로 판단합니다.
    """
    url = page.url.lower()
    # 로그인/회원가입 페이지로 리다이렉트된 경우
    if any(kw in url for kw in ("login", "signin", "sign-in", "auth", "signup")):
        return False
    # 에디터 페이지에 있으면 로그인 상태
    if "/text-to-speech" in url or "/editor" in url:
        return True
    # 메인/랜딩 페이지에서 로그인 버튼이 보이면 미로그인
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


def _ensure_editor(page: Page, actor_name: str, editor_url: str = "") -> None:
    """Typecast 에디터 진입 + 로그인 확인 + 성우 선택.

    Args:
        editor_url: 시트 [설정]의 'Typecast 에디터 URL' (예: https://typecast.ai/text-to-speech)
    """
    # 에디터 URL 결정: 시트 설정 > 기본값
    if not editor_url:
        editor_url = f"{config.TYPECAST_URL}/text-to-speech"

    if not _is_on_editor(page):
        _safe_goto(page, editor_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        if not _check_typecast_logged_in(page):
            log.info("")
            log.info("=" * 50)
            log.info("  Typecast 로그인이 필요합니다!")
            log.info("  브라우저 창에서 직접 로그인해주세요.")
            log.info("  60초 대기 후 자동으로 진행합니다.")
            log.info("=" * 50)

            # 60초 동안 1초마다 로그인 상태 확인
            for elapsed in range(60):
                page.wait_for_timeout(1000)
                if _check_typecast_logged_in(page):
                    log.info("  Typecast 로그인 확인! (%d초 경과)", elapsed + 1)
                    break
            else:
                log.warning("  60초 대기 완료. 로그인 상태를 확인할 수 없지만 계속 진행합니다.")

            # 로그인 후 에디터 페이지로 다시 이동
            if not _is_on_editor(page):
                _safe_goto(page, editor_url, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

    # 성우 선택
    actor_search = page.locator(
        'input[placeholder*="검색"], input[placeholder*="search"], input[type="search"]'
    ).first
    if actor_search.is_visible():
        actor_search.click()
        actor_search.fill(actor_name)
        page.wait_for_timeout(1000)
        actor_item = page.locator(f'text="{actor_name}"').first
        if actor_item.is_visible():
            actor_item.click()
            page.wait_for_timeout(500)
        else:
            log.warning("성우 '%s'를 검색 결과에서 찾을 수 없습니다. 기본 성우로 진행합니다.", actor_name)


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


def _synthesize_and_download(page: Page, text: str, output_path: str) -> str:
    """현재 에디터에서 텍스트를 합성하고 다운로드합니다."""
    # 텍스트 입력 - 다양한 셀렉터 시도
    _TEXT_SELECTORS = [
        'textarea',
        '[contenteditable="true"]',
        '[role="textbox"]',
        '.text-area',
        '#text-input',
        'div[data-placeholder]',
    ]
    text_input = None
    for sel in _TEXT_SELECTORS:
        loc = page.locator(sel).first
        try:
            if loc.is_visible(timeout=2000):
                text_input = loc
                break
        except Exception:
            continue

    if not text_input:
        _take_debug_screenshot(page, "no_text_input")
        raise RuntimeError(
            "Typecast 텍스트 입력창을 찾을 수 없습니다. "
            "temp/typecast_debug_no_text_input.png 스크린샷을 확인하세요."
        )

    text_input.click()
    text_input.press("Control+a")
    page.wait_for_timeout(300)

    # fill()이 안 되는 contenteditable 대비
    try:
        text_input.fill(text)
    except Exception:
        text_input.press("Control+a")
        page.keyboard.type(text, delay=10)
    page.wait_for_timeout(500)

    # 음성 합성 버튼 - 다양한 텍스트/셀렉터 시도
    _GEN_SELECTORS = [
        'button:has-text("합성")',
        'button:has-text("생성")',
        'button:has-text("재생")',
        'button:has-text("변환")',
        'button:has-text("듣기")',
        'button:has-text("Play")',
        'button:has-text("Generate")',
        'button:has-text("Convert")',
        'button:has-text("Listen")',
        'button:has-text("TTS")',
        # 아이콘 전용 버튼 (재생/합성 아이콘)
        'button[aria-label*="play"]',
        'button[aria-label*="Play"]',
        'button[aria-label*="생성"]',
        'button[aria-label*="합성"]',
        'button[aria-label*="재생"]',
    ]
    generate_btn = None
    for sel in _GEN_SELECTORS:
        loc = page.locator(sel).first
        try:
            if loc.is_visible(timeout=1000):
                generate_btn = loc
                log.info("    합성 버튼 발견: %s", sel)
                break
        except Exception:
            continue

    if not generate_btn:
        _take_debug_screenshot(page, "no_generate_btn")
        raise RuntimeError(
            "Typecast 합성 버튼을 찾을 수 없습니다. "
            "temp/typecast_debug_no_generate_btn.png 스크린샷을 확인하세요."
        )

    generate_btn.click()

    # 합성 완료 대기
    log.info("    음성 합성 대기 중...")
    _DL_SELECTORS = [
        'button:has-text("다운로드")',
        'button:has-text("Download")',
        'button:has-text("내보내기")',
        'button:has-text("Export")',
        'button:has-text("저장")',
        'button:has-text("Save")',
        'a[download]',
        'button[aria-label*="download"]',
        'button[aria-label*="Download"]',
        'button[aria-label*="다운로드"]',
    ]
    download_btn = None
    for _ in range(120):
        page.wait_for_timeout(1000)
        for sel in _DL_SELECTORS:
            loc = page.locator(sel).first
            try:
                if loc.is_visible():
                    download_btn = loc
                    break
            except Exception:
                continue
        if download_btn:
            break
    else:
        _take_debug_screenshot(page, "no_download_btn")
        raise TimeoutError(
            "Typecast 음성 합성 타임아웃 (2분). "
            "temp/typecast_debug_no_download_btn.png 스크린샷을 확인하세요."
        )

    # 다운로드
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with page.expect_download(timeout=30000) as download_info:
        download_btn.click()
    download = download_info.value
    download.save_as(output_path)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"음성 파일 다운로드 실패: {output_path}")

    return output_path


def generate_voice(
    page: Page, text: str, output_path: str,
    actor_name: str = "", editor_url: str = "",
) -> str:
    """Typecast 웹에서 음성을 생성하고 다운로드합니다 (단건)."""
    if not actor_name:
        raise ValueError("성우 이름이 지정되지 않았습니다. 시트 [설정] 탭의 '성우 이름'을 입력하세요.")

    _ensure_editor(page, actor_name, editor_url)
    return _synthesize_and_download(page, text, output_path)


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
    _ensure_editor(page, actor_name, editor_url)

    voice_paths = []
    for scene in scenes:
        scene_num = scene["scene_number"]
        narration = scene.get("narration", "").strip()
        if not narration:
            log.warning("  장면%d: 나레이션 없음, 건너뜀", scene_num)
            continue

        output_path = os.path.join(voices_dir, f"voice_s{scene_num:02d}.wav")
        log.info("  장면%d 음성 생성 중 (%d자)...", scene_num, len(narration))

        _synthesize_and_download(page, narration, output_path)
        voice_paths.append(output_path)

        log.info("    장면%d 음성 완료: %s", scene_num, os.path.basename(output_path))

    return voice_paths
