"""CapCut 웹(capcut.com)을 사용한 영상 편집 모듈

CapCut Pro 구독의 웹 에디터를 Playwright로 자동화합니다.
이미지, 음성, 자막을 타임라인에 배치하고 최종 영상을 내보냅니다.
"""

import os
from playwright.sync_api import Page
import config
from browser_manager import ensure_login


def create_project(page: Page, title: str) -> None:
    """CapCut 웹에서 새 프로젝트를 생성합니다."""
    ensure_login(page, config.CAPCUT_URL, "CapCut")

    # 에디터 페이지로 이동
    page.goto(f"{config.CAPCUT_URL}/editor", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    # 새 프로젝트 생성 (세로형 9:16)
    new_project_btn = page.locator(
        'button:has-text("새 프로젝트"), button:has-text("New Project"), '
        'button:has-text("Create"), [data-testid="new-project"]'
    ).first
    if new_project_btn.is_visible():
        new_project_btn.click()
        page.wait_for_timeout(3000)

    # 비율 설정 (9:16 세로)
    ratio_btn = page.locator(
        'button:has-text("9:16"), [data-testid="ratio-9-16"]'
    ).first
    if ratio_btn.is_visible():
        ratio_btn.click()
        page.wait_for_timeout(1000)


def upload_assets(page: Page, file_paths: list[str]) -> None:
    """에셋 파일들을 CapCut에 업로드합니다."""
    # 미디어 업로드 영역 찾기
    upload_input = page.locator('input[type="file"]').first

    for file_path in file_paths:
        abs_path = os.path.abspath(file_path)
        if os.path.exists(abs_path):
            upload_input.set_input_files(abs_path)
            page.wait_for_timeout(2000)
            print(f"    업로드: {os.path.basename(file_path)}")

    # 모든 업로드 완료 대기
    page.wait_for_timeout(5000)


def add_to_timeline(page: Page, asset_index: int) -> None:
    """업로드된 에셋을 타임라인에 추가합니다."""
    # 미디어 패널에서 에셋을 더블클릭하여 타임라인에 추가
    media_items = page.locator(
        '.media-item, [data-testid="media-item"], .asset-item'
    ).all()
    if asset_index < len(media_items):
        media_items[asset_index].dblclick()
        page.wait_for_timeout(1000)


def add_subtitle(page: Page, text: str) -> None:
    """자막을 추가합니다."""
    # 텍스트 도구 선택
    text_btn = page.locator(
        'button:has-text("텍스트"), button:has-text("Text"), '
        '[data-testid="text-tool"]'
    ).first
    if text_btn.is_visible():
        text_btn.click()
        page.wait_for_timeout(1000)

    # 기본 텍스트 추가
    default_text = page.locator(
        'button:has-text("기본 텍스트"), button:has-text("Default text"), '
        'button:has-text("Add text")'
    ).first
    if default_text.is_visible():
        default_text.click()
        page.wait_for_timeout(1000)

    # 텍스트 내용 입력
    text_editor = page.locator(
        '[contenteditable="true"], textarea'
    ).last
    if text_editor.is_visible():
        text_editor.click()
        text_editor.press("Control+a")
        text_editor.fill(text)
        page.wait_for_timeout(500)


def export_video(page: Page, output_path: str) -> str:
    """최종 영상을 내보냅니다."""
    # 내보내기 버튼 클릭
    export_btn = page.locator(
        'button:has-text("내보내기"), button:has-text("Export"), '
        'button:has-text("다운로드")'
    ).first
    export_btn.wait_for(timeout=10000)
    export_btn.click()
    page.wait_for_timeout(2000)

    # 해상도 설정 (1080p)
    resolution = page.locator('text="1080p"').first
    if resolution.is_visible():
        resolution.click()
        page.wait_for_timeout(500)

    # 내보내기 실행
    confirm_btn = page.locator(
        'button:has-text("내보내기"), button:has-text("Export")'
    ).last
    confirm_btn.click()

    # 내보내기 완료 대기 (최대 5분)
    print("    영상 내보내기 중...")
    for _ in range(300):
        page.wait_for_timeout(1000)
        # 완료 표시 확인
        done = page.locator(
            'text="완료", text="Done", text="100%", '
            'button:has-text("다운로드"), button:has-text("Download")'
        ).first
        if done.is_visible():
            break
    else:
        raise TimeoutError("CapCut 내보내기 타임아웃 (5분)")

    # 다운로드
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
) -> str:
    """CapCut 웹에서 전체 영상을 조합합니다.

    1. 새 프로젝트 생성 (9:16)
    2. 모든 이미지, 음성 파일 업로드
    3. 타임라인에 순서대로 배치
    4. 자막 추가
    5. 내보내기
    """
    print("  CapCut 프로젝트 생성...")
    create_project(page, script["title"])

    # 모든 에셋 업로드
    print("  에셋 업로드 중...")
    all_files = image_paths + voice_paths
    upload_assets(page, all_files)

    # 타임라인에 장면 배치
    print("  타임라인 구성 중...")
    for i, scene in enumerate(script["scenes"]):
        print(f"    장면 {scene['scene_number']} 배치...")
        # 이미지 추가
        add_to_timeline(page, i)
        page.wait_for_timeout(500)

        # 자막 추가
        subtitle = scene.get("subtitle", "")
        if subtitle:
            add_subtitle(page, subtitle)
        page.wait_for_timeout(500)

    # 음성 트랙 추가
    print("  음성 트랙 배치 중...")
    for i in range(len(voice_paths)):
        add_to_timeline(page, len(image_paths) + i)
        page.wait_for_timeout(500)

    # 내보내기
    print("  영상 내보내기 중...")
    export_video(page, output_path)

    return output_path
