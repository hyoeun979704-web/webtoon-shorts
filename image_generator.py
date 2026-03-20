"""ChatGPT 프로젝트/GPT를 사용한 이미지 생성 모듈

지정된 ChatGPT 프로젝트 또는 커스텀 GPT 내에서
DALL-E로 고퀄리티 웹툰 이미지를 생성합니다.
프로젝트에 설정된 지침이 이미지 스타일에 적용됩니다.

같은 대화에서 연속 생성하면 스타일 일관성이 유지됩니다.
"""

import os

import requests
from playwright.sync_api import Page

import config
from browser_manager import ensure_login
from utils import log, navigate_to_project


# 이미지 탐색용 셀렉터 (우선순위 순)
_IMAGE_SELECTORS = [
    'img[alt*="Generated"]',
    'img[src*="oaidalleapi"]',
    'img[src*="dall-e"]',
    '.dalle-image img',
    '[data-message-author-role="assistant"] img[src*="https"]',
]


def _count_existing_images(page: Page) -> int:
    """현재 페이지에 이미 존재하는 이미지 수를 셉니다."""
    for sel in _IMAGE_SELECTORS:
        imgs = page.locator(sel).all()
        if imgs:
            return len(imgs)
    return 0


def _wait_for_image(page: Page, timeout_sec: int = 180, prev_count: int = 0) -> str:
    """ChatGPT에서 새 이미지가 생성될 때까지 대기하고 src URL을 반환합니다.

    prev_count: 이전까지 존재하던 이미지 수. 이보다 많아지면 새 이미지로 판단.
    """
    for elapsed in range(timeout_sec):
        page.wait_for_timeout(1000)
        for sel in _IMAGE_SELECTORS:
            imgs = page.locator(sel).all()
            if imgs and len(imgs) > prev_count:
                page.wait_for_timeout(3000)  # 이미지 렌더링 안정화
                src = imgs[-1].get_attribute("src")
                if src:
                    return src

    raise TimeoutError(f"ChatGPT 이미지 생성 타임아웃 ({timeout_sec}초)")


def _download_image(page: Page, img_src: str, output_path: str) -> None:
    """이미지 URL에서 파일을 다운로드합니다."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if img_src.startswith("http"):
        resp = requests.get(img_src, timeout=60)
        resp.raise_for_status()
        if len(resp.content) < 1000:
            raise RuntimeError(f"다운로드된 이미지가 너무 작습니다 ({len(resp.content)} bytes)")
        with open(output_path, "wb") as f:
            f.write(resp.content)
    else:
        # data URL이나 blob인 경우 스크린샷으로 대체
        log.warning("이미지 URL이 HTTP가 아닙니다 (%s...). 스크린샷으로 대체합니다.", img_src[:50])
        for sel in _IMAGE_SELECTORS:
            imgs = page.locator(sel).all()
            if imgs and imgs[-1].is_visible():
                imgs[-1].screenshot(path=output_path)
                return
        raise RuntimeError("이미지 요소를 찾을 수 없어 스크린샷을 저장할 수 없습니다")


def _send_image_prompt(page: Page, prompt: str) -> None:
    """ChatGPT 입력창에 이미지 프롬프트를 전송합니다."""
    full_prompt = (
        f"Generate a single image with the following description. "
        f"Make it cinematic, high detail, professional quality:\n\n"
        f"{prompt}\n\n"
        f"IMPORTANT: No text, letters, words, or speech bubbles in the image. "
        f"Vertical portrait orientation (9:16 aspect ratio)."
    )

    editor = page.locator("#prompt-textarea, [contenteditable='true']").first
    editor.wait_for(timeout=10000)
    editor.click()
    editor.fill(full_prompt)
    page.wait_for_timeout(500)

    send_btn = page.locator('[data-testid="send-button"]').first
    if send_btn.is_visible():
        send_btn.click()
    else:
        editor.press("Enter")


def init_image_session(page: Page, project_url: str = "") -> None:
    """ChatGPT 이미지 생성 세션을 시작합니다 (프로젝트 이동 + 로그인).

    이후 generate_image_in_session()으로 같은 대화에서 연속 생성합니다.
    """
    ensure_login(page, config.CHATGPT_URL, "ChatGPT")
    navigate_to_project(page, config.CHATGPT_URL, project_url)


def generate_image_in_session(
    page: Page,
    prompt: str,
    output_path: str,
) -> str:
    """이미 열린 ChatGPT 대화에서 이미지를 생성합니다.

    같은 대화를 유지하므로 스타일 일관성이 보장됩니다.
    """
    prev_count = _count_existing_images(page)

    _send_image_prompt(page, prompt)

    log.info("    이미지 생성 대기 중...")
    img_src = _wait_for_image(page, prev_count=prev_count)
    _download_image(page, img_src, output_path)

    return output_path


def generate_image(
    page: Page,
    prompt: str,
    output_path: str,
    project_url: str = "",
) -> str:
    """ChatGPT 프로젝트에서 DALL-E로 이미지를 생성합니다 (단건용)."""
    init_image_session(page, project_url)
    return generate_image_in_session(page, prompt, output_path)
