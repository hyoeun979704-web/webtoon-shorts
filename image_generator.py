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
from utils import log, navigate_to_project, wait_for_response_complete


# 이미지 탐색용 셀렉터 (우선순위 순)
_IMAGE_SELECTORS = [
    'img[alt*="Generated"]',
    'img[alt*="generated"]',
    'img[src*="oaidalleapi"]',
    'img[src*="dall-e"]',
    '[data-message-author-role="assistant"] img[src*="https"]',
    '.dalle-image img',
]


def _find_all_images(page: Page) -> list:
    """페이지에서 DALL-E 이미지 요소를 모두 찾습니다.

    여러 셀렉터를 합산하여 중복 없이 반환합니다.
    """
    seen_srcs = set()
    result = []

    for sel in _IMAGE_SELECTORS:
        try:
            for img in page.locator(sel).all():
                src = img.get_attribute("src") or ""
                if src and src not in seen_srcs:
                    seen_srcs.add(src)
                    result.append(img)
        except Exception:
            continue

    # 폴백: 어시스턴트 메시지 내 모든 img 태그 (작은 아이콘 제외)
    if not result:
        try:
            for img in page.locator('[data-message-author-role="assistant"] img').all():
                src = img.get_attribute("src") or ""
                if not src or src in seen_srcs:
                    continue
                # 작은 아이콘/아바타 제외 (30px 이하)
                bbox = img.bounding_box()
                if bbox and bbox["width"] > 50 and bbox["height"] > 50:
                    seen_srcs.add(src)
                    result.append(img)
        except Exception:
            pass

    return result


def _wait_for_new_image(
    page: Page,
    prev_count: int,
    timeout_sec: int = 300,
) -> tuple:
    """ChatGPT 응답 완료 후 새 이미지를 찾아 반환합니다.

    Returns:
        (img_src, img_element) 튜플. src가 없으면 element로 스크린샷 대체.
    """
    # 1단계: 응답 완료 대기 (이미지 생성은 오래 걸리므로 넉넉하게)
    wait_for_response_complete(page, timeout_sec=timeout_sec)

    # 2단계: 응답 완료 후 이미지 탐색 (최대 60초 추가 대기)
    for retry in range(60):
        images = _find_all_images(page)
        if len(images) > prev_count:
            new_img = images[-1]
            page.wait_for_timeout(2000)  # 렌더링 안정화
            src = new_img.get_attribute("src") or ""
            return src, new_img

        page.wait_for_timeout(1000)
        if retry > 0 and retry % 10 == 0:
            log.info("    이미지 렌더링 대기 중... (%d초)", retry)

    # 3단계: 셀렉터로 못 찾으면 마지막 어시스턴트 메시지에서 img 탐색
    try:
        last_msg = page.locator('[data-message-author-role="assistant"]').last
        img = last_msg.locator("img").last
        if img.is_visible():
            src = img.get_attribute("src") or ""
            return src, img
    except Exception:
        pass

    raise TimeoutError(
        f"ChatGPT 이미지를 찾을 수 없습니다. "
        f"이전 이미지 수: {prev_count}, 현재: {len(_find_all_images(page))}"
    )


def _download_image(page: Page, img_src: str, img_element, output_path: str) -> None:
    """이미지를 다운로드합니다. URL 다운로드 실패 시 스크린샷으로 대체합니다."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 방법 1: HTTP URL 직접 다운로드
    if img_src.startswith("http"):
        try:
            resp = requests.get(img_src, timeout=60)
            resp.raise_for_status()
            if len(resp.content) > 1000:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                log.info("    다운로드 완료: %s (%d bytes)", os.path.basename(output_path), len(resp.content))
                return
            log.warning("    다운로드된 이미지가 너무 작습니다 (%d bytes). 스크린샷으로 대체합니다.", len(resp.content))
        except Exception as e:
            log.warning("    URL 다운로드 실패: %s. 스크린샷으로 대체합니다.", e)

    # 방법 2: 이미지 요소 스크린샷
    try:
        if img_element.is_visible():
            img_element.screenshot(path=output_path)
            log.info("    스크린샷 저장 완료: %s", os.path.basename(output_path))
            return
    except Exception as e:
        log.warning("    이미지 요소 스크린샷 실패: %s", e)

    # 방법 3: 마지막 어시스턴트 메시지 전체 스크린샷
    try:
        last_msg = page.locator('[data-message-author-role="assistant"]').last
        if last_msg.is_visible():
            last_msg.screenshot(path=output_path)
            log.warning("    어시스턴트 메시지 전체를 스크린샷으로 저장했습니다.")
            return
    except Exception:
        pass

    raise RuntimeError(f"이미지를 저장할 수 없습니다: {output_path}")


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
    prev_count = len(_find_all_images(page))

    _send_image_prompt(page, prompt)

    log.info("    이미지 생성 대기 중...")
    img_src, img_element = _wait_for_new_image(page, prev_count)
    _download_image(page, img_src, img_element, output_path)

    return output_path
