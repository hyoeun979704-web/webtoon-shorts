"""Typecast 웹(typecast.ai)을 사용한 음성 생성 모듈

Typecast Pro 구독의 웹 인터페이스를 Playwright로 자동화합니다.
"""

import os
from playwright.sync_api import Page
import config
from browser_manager import ensure_login


def generate_voice(page: Page, text: str, output_path: str, actor_name: str = "") -> str:
    """Typecast 웹에서 음성을 생성하고 다운로드합니다."""
    actor_name = actor_name or config.TYPECAST_ACTOR_NAME
    ensure_login(page, config.TYPECAST_URL, "Typecast")

    # 새 프로젝트 또는 에디터 페이지로 이동
    page.goto(f"{config.TYPECAST_URL}/editor", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 성우 선택 (actor_name이 지정된 경우)
    if actor_name:
        # 성우 목록에서 검색
        actor_search = page.locator('input[placeholder*="검색"], input[placeholder*="search"], input[type="search"]').first
        if actor_search.is_visible():
            actor_search.click()
            actor_search.fill(actor_name)
            page.wait_for_timeout(1000)
            # 검색 결과에서 첫 번째 성우 선택
            actor_item = page.locator(f'text="{actor_name}"').first
            if actor_item.is_visible():
                actor_item.click()
                page.wait_for_timeout(500)

    # 텍스트 입력 영역 찾기
    text_input = page.locator(
        'textarea, [contenteditable="true"], [role="textbox"]'
    ).first
    text_input.wait_for(timeout=10000)
    text_input.click()

    # 기존 텍스트 비우고 새 텍스트 입력
    text_input.press("Control+a")
    text_input.fill(text)
    page.wait_for_timeout(500)

    # 음성 합성 버튼 클릭
    generate_btn = page.locator(
        'button:has-text("합성"), button:has-text("생성"), '
        'button:has-text("Generate"), button:has-text("Play")'
    ).first
    generate_btn.wait_for(timeout=5000)
    generate_btn.click()

    # 합성 완료 대기
    print("    음성 합성 대기 중...")
    for _ in range(120):
        page.wait_for_timeout(1000)
        # 다운로드 버튼이 나타나면 합성 완료
        download_btn = page.locator(
            'button:has-text("다운로드"), button:has-text("Download"), '
            'button:has-text("내보내기"), button:has-text("Export"), '
            'a[download]'
        ).first
        if download_btn.is_visible():
            break
    else:
        raise TimeoutError("Typecast 음성 합성 타임아웃 (2분)")

    # 다운로드
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with page.expect_download(timeout=30000) as download_info:
        download_btn.click()
    download = download_info.value
    download.save_as(output_path)

    return output_path


def generate_scene_voices(
    page: Page, script: dict, output_dir: str, actor_name: str = ""
) -> list[str]:
    """대본의 모든 장면에 대해 음성을 생성합니다."""
    voice_paths = []
    os.makedirs(output_dir, exist_ok=True)

    for scene in script["scenes"]:
        scene_num = scene["scene_number"]
        output_path = os.path.join(output_dir, f"voice_{scene_num:02d}.wav")

        print(f"  장면 {scene_num} 음성 생성 중...")
        generate_voice(page, scene["narration"], output_path, actor_name)
        voice_paths.append(output_path)
        print(f"  장면 {scene_num} 음성 완료: {output_path}")

    return voice_paths
