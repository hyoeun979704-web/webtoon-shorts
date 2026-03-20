"""Typecast 웹(typecast.ai)을 사용한 음성 생성 모듈

Typecast Pro 구독의 웹 인터페이스를 Playwright로 자동화합니다.
장면별로 개별 음성 파일을 생성하여 컷 타이밍 동기화를 지원합니다.

사용법:
  시트 [설정] 탭의 'Typecast 에디터 URL'에 프로젝트 에디터 URL을 설정하세요.
  예: https://typecast.ai/text-to-speech/editor/xxxxxxxx
  (브라우저에서 프로젝트를 열고 주소창 URL을 복사)

에디터 UI 흐름:
  1. 에디터 URL로 직접 진입 (로그인 필요 시 60초 대기)
  2. 성우 이름(예: "박창수 ▸") 클릭 → 캐릭터 패널 → 대상 성우 선택
  3. 스크립트 입력 영역에 나레이션 텍스트 입력
  4. 하단 재생(▶) 클릭 → 합성 완료 대기
  5. 우측 상단 "다운로드" 클릭 → 파일 저장
"""

import os
from playwright.sync_api import Page
import config
from utils import log, _safe_goto


# ──────────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────────

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


def _check_typecast_logged_in(page: Page) -> bool:
    """Typecast에 로그인되어 있는지 확인합니다."""
    url = page.url.lower()
    if any(kw in url for kw in ("login", "signin", "sign-in", "auth", "signup")):
        return False
    if "/text-to-speech" in url or "/editor" in url:
        return True
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


def _wait_for_login(page: Page) -> None:
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
            return
    log.warning("  60초 대기 완료. 계속 진행합니다.")


def _wait_for_editor_load(page: Page) -> None:
    """에디터 페이지가 완전히 로드될 때까지 대기합니다.

    "스크립트를 입력해 주세요" placeholder가 보이면 로드 완료.
    """
    for _ in range(30):
        page.wait_for_timeout(1000)
        # 스크립트 입력 영역의 placeholder 텍스트 확인
        placeholder = page.locator('text="스크립트를 입력해 주세요."').first
        try:
            if placeholder.is_visible():
                log.info("    에디터 로드 완료")
                return
        except Exception:
            pass
        # contenteditable 영역이 보여도 OK
        ce = page.locator('[contenteditable="true"]').first
        try:
            if ce.is_visible():
                log.info("    에디터 로드 완료 (contenteditable)")
                return
        except Exception:
            pass
    log.warning("    에디터 로드 확인 실패, 계속 진행합니다.")


# ──────────────────────────────────────────────
# 대시보드 → 에디터 진입
# ──────────────────────────────────────────────

def _is_on_editor(page: Page) -> bool:
    """에디터 페이지에 있는지 확인 (/editor/ 가 URL에 포함)."""
    url = page.url.lower()
    return "typecast" in url and "/editor/" in url


def _open_first_project(page: Page) -> None:
    """대시보드의 '내 스튜디오'에서 첫 번째 프로젝트를 엽니다."""
    # "이전에 작업하던 내용이 있습니다" 배너 → 복원하기
    try:
        restore_btn = page.locator('button:has-text("복원하기")').first
        if restore_btn.is_visible(timeout=2000):
            restore_btn.click()
            page.wait_for_timeout(3000)
            if _is_on_editor(page):
                log.info("    이전 프로젝트 복원 완료")
                return
    except Exception:
        pass

    # 내 스튜디오 프로젝트 목록에서 첫 번째 클릭
    try:
        # 테이블 행 (제목 | 내용 | 최종 수정 시각) 중 첫 번째
        first_row = page.locator('table tbody tr, [class*="project-item"], [class*="studio"] a').first
        if first_row.is_visible(timeout=3000):
            first_row.click()
            page.wait_for_timeout(3000)
            if _is_on_editor(page):
                log.info("    기존 프로젝트 열기 완료")
                return
    except Exception:
        pass

    # 둘 다 실패하면 새 프로젝트 생성
    log.info("    기존 프로젝트를 못 찾아 새 프로젝트를 생성합니다...")
    try:
        new_btn = page.locator('text="새 프로젝트"').first
        if new_btn.is_visible(timeout=5000):
            new_btn.click()
            page.wait_for_timeout(1000)
            # 다이얼로그: 하나의 언어 선택 → 확인
            single_lang = page.locator('text="하나의 언어 선택"').first
            try:
                if single_lang.is_visible(timeout=2000):
                    single_lang.click()
                    page.wait_for_timeout(500)
            except Exception:
                pass
            confirm = page.locator('button:has-text("확인")').first
            if confirm.is_visible(timeout=3000):
                confirm.click()
                page.wait_for_timeout(3000)
                log.info("    새 프로젝트 생성 완료")
                return
    except Exception:
        pass

    _take_debug_screenshot(page, "cannot_enter_editor")
    raise RuntimeError("Typecast 에디터에 진입할 수 없습니다. temp/typecast_debug_cannot_enter_editor.png 확인")


# ──────────────────────────────────────────────
# 에디터 조작: 성우 선택
# ──────────────────────────────────────────────

def _select_actor(page: Page, actor_name: str) -> None:
    """에디터에서 성우(캐릭터)를 선택합니다.

    스크린샷 기준 UI:
      - 에디터 좌측 상단에 "박창수 ▸" 같은 성우 프로필 영역
      - 클릭하면 캐릭터 선택 패널 (찾기/찜 탭, 카테고리 태그, 캐릭터 목록)
      - "최근 사용 캐릭터"에 소진, 설화, 이겸 등 표시
    """
    # 1) 먼저 이미 원하는 성우가 선택되어 있는지 확인
    current_actor = page.locator(f'text="{actor_name}"').first
    try:
        if current_actor.is_visible(timeout=1000):
            # 성우 이름이 에디터에 이미 보이면 → 이미 선택된 상태
            # (캐릭터 패널이 아닌 에디터 본문에서 보이는 경우)
            pass
    except Exception:
        pass

    # 2) 성우 프로필 영역 클릭 → 캐릭터 패널 열기
    #    "박창수 ▸" 패턴: 이름 + 화살표가 포함된 클릭 가능 영역
    #    ▸(U+25B8) 또는 ►(U+25BA) 기호가 있는 요소
    actor_opened = False

    # 방법A: ▸ 기호가 포함된 요소 클릭
    arrow_el = page.locator('text=/.*[▸►▶].*/').first
    try:
        if arrow_el.is_visible(timeout=2000):
            arrow_el.click()
            page.wait_for_timeout(1500)
            actor_opened = True
            log.info("    캐릭터 패널 열림 (화살표 클릭)")
    except Exception:
        pass

    if not actor_opened:
        _take_debug_screenshot(page, "no_actor_panel")
        log.warning("    캐릭터 패널을 열 수 없습니다. 기본 성우로 진행합니다.")
        return

    # 3) 캐릭터 패널에서 대상 성우 찾기
    #    "최근 사용 캐릭터 (6)" 목록에 이름이 바로 보일 수 있음
    actor_item = page.locator(f'text="{actor_name}"').first
    try:
        if actor_item.is_visible(timeout=3000):
            actor_item.click()
            page.wait_for_timeout(1000)
            log.info("    성우 '%s' 선택 완료", actor_name)
            # 패널이 자동으로 닫히지 않으면 Escape
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            return
    except Exception:
        pass

    # 4) 검색으로 찾기
    log.info("    성우 '%s' 검색 중...", actor_name)
    search_icon = page.locator('svg, button').filter(has=page.locator('[class*="search"]')).first
    try:
        if search_icon.is_visible(timeout=1000):
            search_icon.click()
            page.wait_for_timeout(500)
    except Exception:
        pass

    search_input = page.locator('input[placeholder*="검색"], input[type="search"]').first
    try:
        if search_input.is_visible(timeout=2000):
            search_input.click()
            search_input.fill(actor_name)
            page.wait_for_timeout(1500)

            result = page.locator(f'text="{actor_name}"').first
            if result.is_visible(timeout=3000):
                result.click()
                page.wait_for_timeout(1000)
                log.info("    성우 '%s' 검색+선택 완료", actor_name)
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                return
    except Exception:
        pass

    log.warning("    성우 '%s'를 찾을 수 없습니다. 기본 성우로 진행합니다.", actor_name)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)


# ──────────────────────────────────────────────
# 에디터 조작: 스크립트 입력 → 합성 → 다운로드
# ──────────────────────────────────────────────

def _enter_script(page: Page, text: str) -> None:
    """스크립트 입력 영역에 텍스트를 입력합니다.

    placeholder: "스크립트를 입력해 주세요."
    """
    _TEXT_SELECTORS = [
        'text="스크립트를 입력해 주세요."',
        '[data-placeholder*="스크립트"]',
        '[placeholder*="스크립트"]',
        '[contenteditable="true"]',
        '[role="textbox"]',
        'textarea',
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
            "temp/typecast_debug_no_text_input.png 확인"
        )

    text_input.click()
    page.wait_for_timeout(300)
    page.keyboard.press("Control+a")
    page.wait_for_timeout(200)

    try:
        text_input.fill(text)
    except Exception:
        page.keyboard.type(text, delay=10)
    page.wait_for_timeout(500)
    log.info("    스크립트 입력 완료 (%d자)", len(text))


def _click_play_and_wait(page: Page) -> None:
    """하단 재생(▶) 버튼을 클릭하고 합성 완료를 대기합니다.

    스크린샷 기준: 하단 중앙에 주황색 큰 원형 재생 버튼.
    좌우에 이전(◁)/다음(▷) 작은 버튼.
    시간 표시: "0:00 / 0:00"
    """
    play_btn = None

    # 방법1: 하단 영역(y > 600)에서 가장 큰 버튼 찾기 (주황 재생 버튼)
    all_buttons = page.locator('button').all()
    best_btn = None
    best_size = 0
    for btn in all_buttons:
        try:
            bbox = btn.bounding_box()
            if not bbox:
                continue
            # 하단 영역 (페이지 높이의 70% 이하)
            if bbox['y'] < 500:
                continue
            size = bbox['width'] * bbox['height']
            if size > best_size:
                best_size = size
                best_btn = btn
        except Exception:
            continue

    if best_btn and best_size > 1000:  # 최소 ~32x32
        play_btn = best_btn

    if not play_btn:
        # 방법2: aria-label로 찾기
        for sel in ['button[aria-label*="play"]', 'button[aria-label*="재생"]']:
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
    log.info("    재생 클릭 → 합성 대기 중...")

    # 합성 완료 대기: 총 시간이 0:00이 아닌 값으로 변경되면 완료
    for elapsed in range(180):
        page.wait_for_timeout(1000)

        # "0:00 / 0:15" 같은 시간 표시에서 총 길이가 0:00이 아닌지 확인
        time_el = page.locator('text=/\\d+:\\d+\\s*\\/\\s*\\d+:\\d+/').first
        try:
            if time_el.is_visible():
                txt = time_el.text_content() or ""
                # "/ 0:00"이 아니면 합성 완료
                parts = txt.split("/")
                if len(parts) == 2:
                    total = parts[1].strip()
                    if total != "0:00":
                        log.info("    합성 완료 (길이: %s)", total)
                        page.wait_for_timeout(1000)
                        return
        except Exception:
            pass

        if elapsed > 0 and elapsed % 15 == 0:
            log.info("    합성 대기 중... (%d초)", elapsed)

    _take_debug_screenshot(page, "synthesis_timeout")
    raise TimeoutError("Typecast 음성 합성 타임아웃 (3분)")


def _download_audio(page: Page, output_path: str) -> str:
    """우측 상단 '다운로드' 버튼으로 음성 파일을 저장합니다."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 우측 상단 "다운로드" 버튼 (주황색 배경)
    dl_btn = page.locator(
        'button:has-text("다운로드"), '
        'a:has-text("다운로드"), '
        'button:has-text("Download"), '
        'a:has-text("Download")'
    ).first

    try:
        dl_btn.wait_for(timeout=5000)
    except Exception:
        _take_debug_screenshot(page, "no_download_btn")
        raise RuntimeError(
            "Typecast 다운로드 버튼을 찾을 수 없습니다. "
            "temp/typecast_debug_no_download_btn.png 확인"
        )

    with page.expect_download(timeout=60000) as download_info:
        dl_btn.click()

    download = download_info.value
    download.save_as(output_path)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"음성 파일 다운로드 실패: {output_path}")

    log.info("    다운로드 완료: %s", os.path.basename(output_path))
    return output_path


# ──────────────────────────────────────────────
# 메인: 에디터 진입 + 합성
# ──────────────────────────────────────────────

def _ensure_editor_ready(page: Page, actor_name: str, editor_url: str = "") -> None:
    """Typecast 에디터에 진입하고 성우를 선택합니다.

    1. editor_url(에디터 직접 URL)로 이동
    2. 로그인 안 되어 있으면 60초 대기
    3. 대시보드에 있으면 첫 번째 기존 프로젝트 열기
    4. 에디터 로드 대기
    5. 성우 선택
    """
    if not editor_url:
        editor_url = f"{config.TYPECAST_URL}/text-to-speech"

    # 1. 에디터 URL로 이동
    if not _is_on_editor(page):
        log.info("    Typecast 에디터로 이동: %s", editor_url[:80])
        _safe_goto(page, editor_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

    # 2. 로그인 확인
    if not _check_typecast_logged_in(page):
        _wait_for_login(page)
        # 로그인 후 다시 에디터 URL로 이동
        _safe_goto(page, editor_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

    # 3. 대시보드에 있으면 (editor_url이 대시보드인 경우) 프로젝트 열기
    if not _is_on_editor(page):
        log.info("    대시보드 → 프로젝트 열기")
        _open_first_project(page)

    # 4. 에디터 로드 대기
    _wait_for_editor_load(page)

    # 5. 성우 선택
    _select_actor(page, actor_name)


def _synthesize_one(page: Page, text: str, output_path: str) -> str:
    """에디터에서 텍스트 입력 → 재생(합성) → 다운로드 (1건)."""
    _enter_script(page, text)
    _click_play_and_wait(page)
    return _download_audio(page, output_path)


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

def generate_voice(
    page: Page, text: str, output_path: str,
    actor_name: str = "", editor_url: str = "",
) -> str:
    """Typecast 웹에서 음성을 생성하고 다운로드합니다 (단건)."""
    if not actor_name:
        raise ValueError("성우 이름이 지정되지 않았습니다.")

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
        raise ValueError("성우 이름이 지정되지 않았습니다.")

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

    return voice_paths
