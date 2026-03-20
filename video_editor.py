"""CapCut 웹(capcut.com)을 사용한 영상 편집 모듈

CapCut Pro 구독의 웹 에디터를 Playwright로 자동화합니다.
이미지, 자막, 효과음, 장면전환을 타임라인에 배치하고 최종 영상을 내보냅니다.

효과음/전환 이름은 CapCut에 있는 이름을 시트에 그대로 적으면 됩니다.
"""

import os
from playwright.sync_api import Page
import config
from browser_manager import ensure_login
from utils import log, _safe_goto


def create_project(page: Page, title: str) -> None:
    """CapCut 웹에서 새 프로젝트를 생성합니다."""
    ensure_login(page, config.CAPCUT_URL, "CapCut")

    _safe_goto(page, f"{config.CAPCUT_URL}/editor", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    new_project_btn = page.locator(
        'button:has-text("새 프로젝트"), button:has-text("New Project"), '
        'button:has-text("Create"), [data-testid="new-project"]'
    ).first
    if new_project_btn.is_visible():
        new_project_btn.click()
        page.wait_for_timeout(3000)

    ratio_btn = page.locator(
        'button:has-text("9:16"), [data-testid="ratio-9-16"]'
    ).first
    if ratio_btn.is_visible():
        ratio_btn.click()
        page.wait_for_timeout(1000)


def upload_assets(page: Page, file_paths: list[str]) -> None:
    """에셋 파일들을 CapCut에 업로드합니다."""
    upload_input = page.locator('input[type="file"]').first

    valid_files = []
    for file_path in file_paths:
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            log.warning("파일을 찾을 수 없어 건너뜁니다: %s", file_path)
            continue
        valid_files.append(abs_path)

    if not valid_files:
        raise FileNotFoundError("업로드할 에셋 파일이 없습니다")

    # 한 번에 모든 파일을 선택하여 업로드 (set_input_files는 매번 선택을 교체하므로)
    upload_input.set_input_files(valid_files)
    log.info("    %d개 파일 업로드 시작", len(valid_files))

    # 업로드 완료 대기 (파일 수에 비례)
    wait_sec = max(10, len(valid_files) * 3)
    page.wait_for_timeout(wait_sec * 1000)
    log.info("    업로드 완료 대기 (%d초)", wait_sec)


def add_to_timeline(page: Page, asset_index: int) -> None:
    """업로드된 에셋을 타임라인에 추가합니다."""
    media_items = page.locator(
        '.media-item, [data-testid="media-item"], .asset-item'
    ).all()
    if asset_index < len(media_items):
        media_items[asset_index].dblclick()
        page.wait_for_timeout(1000)
    else:
        log.warning("에셋 인덱스 %d가 범위를 벗어났습니다 (총 %d개)", asset_index, len(media_items))


def add_subtitle(page: Page, text: str) -> None:
    """자막을 추가합니다."""
    if not text:
        return

    text_btn = page.locator(
        'button:has-text("텍스트"), button:has-text("Text"), '
        '[data-testid="text-tool"]'
    ).first
    if text_btn.is_visible():
        text_btn.click()
        page.wait_for_timeout(1000)

    default_text = page.locator(
        'button:has-text("기본 텍스트"), button:has-text("Default text"), '
        'button:has-text("Add text")'
    ).first
    if default_text.is_visible():
        default_text.click()
        page.wait_for_timeout(1000)

    text_editor = page.locator(
        '[contenteditable="true"], textarea'
    ).last
    if text_editor.is_visible():
        text_editor.click()
        text_editor.press("Control+a")
        text_editor.fill(text)
        page.wait_for_timeout(500)


def add_transition(page: Page, name: str) -> None:
    """두 클립 사이에 장면 전환 효과를 추가합니다.

    name: CapCut에 있는 전환 효과 이름 그대로 (예: "페이드", "Fade", "글리치" 등)
    """
    if not name:
        return

    transition_btn = page.locator(
        'button:has-text("전환"), button:has-text("Transition"), '
        '[data-testid="transition-tab"]'
    ).first
    if not transition_btn.is_visible():
        log.warning("전환 효과 버튼을 찾을 수 없습니다")
        return
    transition_btn.click()
    page.wait_for_timeout(1000)

    search_input = page.locator(
        'input[placeholder*="검색"], input[placeholder*="Search"], '
        'input[type="search"]'
    ).first
    if search_input.is_visible():
        search_input.click()
        search_input.fill(name)
        page.wait_for_timeout(1500)

    transition_items = page.locator(
        '.transition-item, [data-testid="transition-item"]'
    ).all()
    if transition_items:
        transition_items[0].dblclick()
        page.wait_for_timeout(500)
        log.info("      전환: %s", name)
    else:
        log.warning("      전환 '%s' 검색 결과 없음", name)


def add_sfx(page: Page, name: str) -> None:
    """현재 타임라인 위치에 효과음을 추가합니다.

    name: CapCut에 있는 효과음 이름 그대로 (예: "타격", "우쉬", "Whoosh" 등)
    """
    if not name:
        return

    audio_btn = page.locator(
        'button:has-text("오디오"), button:has-text("Audio"), '
        '[data-testid="audio-tab"]'
    ).first
    if not audio_btn.is_visible():
        log.warning("오디오 버튼을 찾을 수 없습니다")
        return
    audio_btn.click()
    page.wait_for_timeout(1000)

    sfx_tab = page.locator(
        'button:has-text("효과음"), button:has-text("Sound effects"), '
        'button:has-text("SFX")'
    ).first
    if sfx_tab.is_visible():
        sfx_tab.click()
        page.wait_for_timeout(1000)

    search_input = page.locator(
        'input[placeholder*="검색"], input[placeholder*="Search"], '
        'input[type="search"]'
    ).first
    if search_input.is_visible():
        search_input.click()
        search_input.fill(name)
        page.wait_for_timeout(1500)

    sfx_items = page.locator(
        '.audio-item, [data-testid="audio-item"], .sound-item'
    ).all()
    if sfx_items:
        sfx_items[0].dblclick()
        page.wait_for_timeout(500)
        log.info("      효과음: %s", name)
    else:
        log.warning("      효과음 '%s' 검색 결과 없음", name)


def export_video(page: Page, output_path: str) -> str:
    """최종 영상을 내보냅니다."""
    export_btn = page.locator(
        'button:has-text("내보내기"), button:has-text("Export"), '
        'button:has-text("다운로드")'
    ).first
    export_btn.wait_for(timeout=10000)
    export_btn.click()
    page.wait_for_timeout(2000)

    resolution = page.locator('text="1080p"').first
    if resolution.is_visible():
        resolution.click()
        page.wait_for_timeout(500)

    confirm_btn = page.locator(
        'button:has-text("내보내기"), button:has-text("Export")'
    ).last
    confirm_btn.click()

    log.info("    영상 내보내기 중...")
    for elapsed in range(300):
        page.wait_for_timeout(1000)
        done = page.locator(
            'text="완료", text="Done", text="100%", '
            'button:has-text("다운로드"), button:has-text("Download")'
        ).first
        if done.is_visible():
            break
    else:
        raise TimeoutError("CapCut 내보내기 타임아웃 (5분)")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    download_btn = page.locator(
        'button:has-text("다운로드"), button:has-text("Download"), a[download]'
    ).first
    if download_btn.is_visible():
        with page.expect_download(timeout=60000) as download_info:
            download_btn.click()
        download = download_info.value
        download.save_as(output_path)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"영상 파일 다운로드 실패: {output_path}")

    return output_path


def assemble_video(
    page: Page,
    script: dict,
    image_paths: list[str],
    output_path: str,
    auto_export: bool = False,
) -> str:
    """CapCut 웹에서 전체 영상을 조합합니다."""
    log.info("  CapCut 프로젝트 생성...")
    create_project(page, script["title"])

    log.info("  에셋 업로드 중...")
    upload_assets(page, image_paths)

    # ===== 타임라인에 컷 배치 + 자막 + 전환 + 효과음 =====
    log.info("  타임라인 구성 중... (이미지 %d장)", len(image_paths))
    media_index = 0  # CapCut 미디어 패널에서의 에셋 인덱스
    for scene_idx, scene in enumerate(script["scenes"]):
        scene_num = scene["scene_number"]
        cuts = scene.get("cuts", [{"cut_number": 1, "sfx": "", "subtitle": ""}])
        transition = scene.get("transition", "")

        if scene_idx > 0 and transition:
            add_transition(page, transition)

        for cut in cuts:
            cut_num = cut.get("cut_number", 1)
            sfx = cut.get("sfx", "")
            subtitle = cut.get("subtitle", "")

            if media_index >= len(image_paths):
                log.warning("    이미지 부족: 장면 %d 컷 %d 건너뜀", scene_num, cut_num)
                continue

            log.info("    장면 %d 컷 %d 배치...", scene_num, cut_num)
            add_to_timeline(page, media_index)
            page.wait_for_timeout(500)

            if subtitle:
                add_subtitle(page, subtitle)

            if sfx:
                add_sfx(page, sfx)

            media_index += 1

    # ===== 검토 포인트 =====
    if not auto_export:
        log.info("")
        log.info("=" * 50)
        log.info("  CapCut 타임라인 배치가 완료되었습니다.")
        log.info("  브라우저에서 직접 확인하고 수정하세요:")
        log.info("    - 컷 길이/순서 조정")
        log.info("    - 전환 효과 변경 또는 추가")
        log.info("    - 효과음 타이밍 미세 조정")
        log.info("    - 자막 위치/크기/스타일 수정")
        log.info("    - 배경음악 추가")
        log.info("")
        log.info("  수정 완료 후 Enter를 눌러주세요. (내보내기 진행)")
        log.info("=" * 50)
        input("  → Enter: ")

    log.info("  영상 내보내기 중...")
    export_video(page, output_path)

    return output_path
