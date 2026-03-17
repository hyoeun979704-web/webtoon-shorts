"""CapCut 웹(capcut.com)을 사용한 영상 편집 모듈

CapCut Pro 구독의 웹 에디터를 Playwright로 자동화합니다.
이미지, 음성, 자막, 효과음, 장면전환을 타임라인에 배치하고 최종 영상을 내보냅니다.

효과음/전환 이름은 CapCut에 있는 이름을 시트에 그대로 적으면 됩니다.
"""

import os
from playwright.sync_api import Page
import config
from browser_manager import ensure_login


def create_project(page: Page, title: str) -> None:
    """CapCut 웹에서 새 프로젝트를 생성합니다."""
    ensure_login(page, config.CAPCUT_URL, "CapCut")

    page.goto(f"{config.CAPCUT_URL}/editor", wait_until="domcontentloaded")
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

    for file_path in file_paths:
        abs_path = os.path.abspath(file_path)
        if os.path.exists(abs_path):
            upload_input.set_input_files(abs_path)
            page.wait_for_timeout(2000)
            print(f"    업로드: {os.path.basename(file_path)}")

    page.wait_for_timeout(5000)


def add_to_timeline(page: Page, asset_index: int) -> None:
    """업로드된 에셋을 타임라인에 추가합니다."""
    media_items = page.locator(
        '.media-item, [data-testid="media-item"], .asset-item'
    ).all()
    if asset_index < len(media_items):
        media_items[asset_index].dblclick()
        page.wait_for_timeout(1000)


def add_subtitle(page: Page, text: str) -> None:
    """자막을 추가합니다."""
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

    # 전환 효과 패널 열기
    transition_btn = page.locator(
        'button:has-text("전환"), button:has-text("Transition"), '
        '[data-testid="transition-tab"]'
    ).first
    if not transition_btn.is_visible():
        return
    transition_btn.click()
    page.wait_for_timeout(1000)

    # CapCut에서 이름 그대로 검색
    search_input = page.locator(
        'input[placeholder*="검색"], input[placeholder*="Search"], '
        'input[type="search"]'
    ).first
    if search_input.is_visible():
        search_input.click()
        search_input.fill(name)
        page.wait_for_timeout(1500)

    # 첫 번째 결과 적용
    transition_items = page.locator(
        '.transition-item, [data-testid="transition-item"]'
    ).all()
    if transition_items:
        transition_items[0].dblclick()
        page.wait_for_timeout(500)
        print(f"      전환: {name}")


def add_sfx(page: Page, name: str) -> None:
    """현재 타임라인 위치에 효과음을 추가합니다.

    name: CapCut에 있는 효과음 이름 그대로 (예: "타격", "우쉬", "Whoosh" 등)
    """
    if not name:
        return

    # 오디오 패널 열기
    audio_btn = page.locator(
        'button:has-text("오디오"), button:has-text("Audio"), '
        '[data-testid="audio-tab"]'
    ).first
    if not audio_btn.is_visible():
        return
    audio_btn.click()
    page.wait_for_timeout(1000)

    # 효과음 카테고리 선택
    sfx_tab = page.locator(
        'button:has-text("효과음"), button:has-text("Sound effects"), '
        'button:has-text("SFX")'
    ).first
    if sfx_tab.is_visible():
        sfx_tab.click()
        page.wait_for_timeout(1000)

    # CapCut에서 이름 그대로 검색
    search_input = page.locator(
        'input[placeholder*="검색"], input[placeholder*="Search"], '
        'input[type="search"]'
    ).first
    if search_input.is_visible():
        search_input.click()
        search_input.fill(name)
        page.wait_for_timeout(1500)

    # 첫 번째 결과 적용
    sfx_items = page.locator(
        '.audio-item, [data-testid="audio-item"], .sound-item'
    ).all()
    if sfx_items:
        sfx_items[0].dblclick()
        page.wait_for_timeout(500)
        print(f"      효과음: {name}")


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

    print("    영상 내보내기 중...")
    for _ in range(300):
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

    return output_path


def assemble_video(
    page: Page,
    script: dict,
    image_paths: list[str],
    voice_paths: list[str],
    output_path: str,
    auto_export: bool = False,
) -> str:
    """CapCut 웹에서 전체 영상을 조합합니다."""
    print("  CapCut 프로젝트 생성...")
    create_project(page, script["title"])

    # 모든 에셋 업로드
    print("  에셋 업로드 중...")
    all_files = image_paths + voice_paths
    upload_assets(page, all_files)

    # ===== 타임라인에 컷 배치 + 자막 + 전환 + 효과음 =====
    print(f"  타임라인 구성 중... (이미지 {len(image_paths)}장)")
    cut_index = 0
    for scene_idx, scene in enumerate(script["scenes"]):
        scene_num = scene["scene_number"]
        cuts = scene.get("cuts", [{"cut_number": 1, "sfx": "", "subtitle": ""}])
        transition = scene.get("transition", "")

        # 장면 전환 효과 (첫 장면 제외, 이름이 있을 때만)
        if scene_idx > 0 and transition:
            add_transition(page, transition)

        for cut in cuts:
            cut_num = cut.get("cut_number", 1)
            sfx = cut.get("sfx", "")
            subtitle = cut.get("subtitle", "")

            print(f"    장면 {scene_num} 컷 {cut_num} 배치...")
            add_to_timeline(page, cut_index)
            page.wait_for_timeout(500)

            # 자막 (컷에 자막이 있으면 추가)
            if subtitle:
                add_subtitle(page, subtitle)

            # 효과음 (이름이 있으면 CapCut에서 검색하여 추가)
            if sfx:
                add_sfx(page, sfx)

            cut_index += 1

    # 음성 트랙 추가 (장면당 1개)
    print(f"  음성 트랙 배치 중... ({len(voice_paths)}개)")
    for i in range(len(voice_paths)):
        add_to_timeline(page, len(image_paths) + i)
        page.wait_for_timeout(500)

    # ===== 검토 포인트: CapCut에서 직접 확인/수정 =====
    if not auto_export:
        print("\n" + "=" * 50)
        print("  CapCut 타임라인 배치가 완료되었습니다.")
        print("  브라우저에서 직접 확인하고 수정하세요:")
        print("    - 컷 길이/순서 조정")
        print("    - 전환 효과 변경 또는 추가")
        print("    - 효과음 타이밍 미세 조정")
        print("    - 자막 위치/크기/스타일 수정")
        print("    - 배경음악 추가")
        print("")
        print("  수정 완료 후 Enter를 눌러주세요. (내보내기 진행)")
        print("=" * 50)
        input("  → Enter: ")

    # 내보내기
    print("  영상 내보내기 중...")
    export_video(page, output_path)

    return output_path
