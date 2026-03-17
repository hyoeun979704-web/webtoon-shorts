"""Typecast 웹(typecast.ai)을 사용한 음성 생성 모듈

Typecast Pro 구독의 웹 인터페이스를 Playwright로 자동화합니다.
"""

import os
from playwright.sync_api import Page
import config
from browser_manager import ensure_login
from utils import log


def _is_on_editor(page: Page) -> bool:
    """이미 Typecast 에디터 페이지에 있는지 확인합니다."""
    return "/editor" in page.url and "typecast" in page.url.lower()


def generate_voice(page: Page, text: str, output_path: str, actor_name: str = "") -> str:
    """Typecast 웹에서 음성을 생성하고 다운로드합니다."""
    if not actor_name:
        raise ValueError("성우 이름이 지정되지 않았습니다. 시트 [설정] 탭의 '성우 이름'을 입력하세요.")

    # 이미 에디터에 있으면 로그인/네비게이션 건너뜀
    if not _is_on_editor(page):
        ensure_login(page, config.TYPECAST_URL, "Typecast")
        page.goto(f"{config.TYPECAST_URL}/editor", wait_until="domcontentloaded")
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

    # 텍스트 입력
    text_input = page.locator(
        'textarea, [contenteditable="true"], [role="textbox"]'
    ).first
    text_input.wait_for(timeout=10000)
    text_input.click()
    text_input.press("Control+a")
    text_input.fill(text)
    page.wait_for_timeout(500)

    # 음성 합성
    generate_btn = page.locator(
        'button:has-text("합성"), button:has-text("생성"), '
        'button:has-text("Generate"), button:has-text("Play")'
    ).first
    generate_btn.wait_for(timeout=5000)
    generate_btn.click()

    # 합성 완료 대기
    log.info("    음성 합성 대기 중...")
    download_btn = None
    for _ in range(120):
        page.wait_for_timeout(1000)
        btn = page.locator(
            'button:has-text("다운로드"), button:has-text("Download"), '
            'button:has-text("내보내기"), button:has-text("Export"), '
            'a[download]'
        ).first
        if btn.is_visible():
            download_btn = btn
            break
    else:
        raise TimeoutError("Typecast 음성 합성 타임아웃 (2분)")

    # 다운로드
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with page.expect_download(timeout=30000) as download_info:
        download_btn.click()
    download = download_info.value
    download.save_as(output_path)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"음성 파일 다운로드 실패: {output_path}")

    return output_path
