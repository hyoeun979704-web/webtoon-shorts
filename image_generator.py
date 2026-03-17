"""ChatGPT 프로젝트/GPT를 사용한 이미지 생성 모듈

지정된 ChatGPT 프로젝트 또는 커스텀 GPT 내에서
DALL-E로 고퀄리티 웹툰 이미지를 생성합니다.
프로젝트에 설정된 지침이 이미지 스타일에 적용됩니다.
"""

import os
import requests
from playwright.sync_api import Page
import config
from browser_manager import ensure_login


def _navigate_to_project_or_new(page: Page, project_url: str = ""):
    """ChatGPT 프로젝트/GPT 또는 새 대화로 이동합니다."""
    if project_url:
        # 프로젝트 URL: https://chatgpt.com/g/g-xxx (GPT)
        # 또는 https://chatgpt.com/project/xxx (프로젝트)
        page.goto(project_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # 프로젝트/GPT 내 새 대화가 필요하면 시작
        new_chat_btn = page.locator(
            'button:has-text("New chat"), button:has-text("Start chat"), '
            'a[href*="/new"]'
        ).first
        if new_chat_btn.is_visible():
            new_chat_btn.click()
            page.wait_for_timeout(2000)
    else:
        page.goto(f"{config.CHATGPT_URL}/?model=gpt-4", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)


def generate_image(
    page: Page,
    prompt: str,
    output_path: str,
    project_url: str = "",
) -> str:
    """ChatGPT 프로젝트에서 DALL-E로 이미지를 생성합니다.

    Args:
        page: Playwright 페이지
        prompt: 이미지 프롬프트
        output_path: 저장 경로
        project_url: ChatGPT 프로젝트/GPT URL (스타일 지침 적용됨)
    """
    _navigate_to_project_or_new(page, project_url)

    # 고퀄리티 이미지 생성 프롬프트
    full_prompt = (
        f"Generate a single image with the following description. "
        f"Make it cinematic, high detail, professional quality:\n\n"
        f"{prompt}\n\n"
        f"IMPORTANT: No text, letters, words, or speech bubbles in the image. "
        f"Vertical portrait orientation (9:16 aspect ratio)."
    )

    editor = page.locator("#prompt-textarea").first
    editor.wait_for(timeout=10000)
    editor.click()
    editor.fill(full_prompt)
    page.wait_for_timeout(500)

    # 전송
    send_btn = page.locator('[data-testid="send-button"]').first
    if send_btn.is_visible():
        send_btn.click()
    else:
        editor.press("Enter")

    # 이미지 생성 대기 (최대 3분)
    print("    이미지 생성 대기 중...")
    img_element = None
    for _ in range(180):
        page.wait_for_timeout(1000)

        selectors = [
            'img[alt*="Generated"]',
            'img[src*="oaidalleapi"]',
            'img[src*="dall-e"]',
            '.dalle-image img',
            '[data-message-author-role="assistant"] img[src*="https"]',
        ]
        for sel in selectors:
            imgs = page.locator(sel).all()
            if imgs:
                img_element = imgs[-1]
                break

        if img_element and img_element.is_visible():
            page.wait_for_timeout(3000)
            break
    else:
        raise TimeoutError("ChatGPT 이미지 생성 타임아웃 (3분)")

    # 이미지 다운로드
    img_src = img_element.get_attribute("src")
    if not img_src:
        raise RuntimeError("이미지 URL을 찾을 수 없습니다")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if img_src.startswith("http"):
        img_data = requests.get(img_src, timeout=60).content
        with open(output_path, "wb") as f:
            f.write(img_data)
    else:
        img_element.screenshot(path=output_path)

    return output_path


def generate_scene_images(
    page: Page,
    script: dict,
    output_dir: str,
    project_url: str = "",
) -> list[str]:
    """대본의 모든 장면에 대해 이미지를 생성합니다."""
    image_paths = []
    os.makedirs(output_dir, exist_ok=True)

    for scene in script["scenes"]:
        scene_num = scene["scene_number"]
        output_path = os.path.join(output_dir, f"scene_{scene_num:02d}.png")

        print(f"  장면 {scene_num} 이미지 생성 중...")
        generate_image(page, scene["image_prompt"], output_path, project_url)
        image_paths.append(output_path)
        print(f"  장면 {scene_num} 이미지 완료: {output_path}")

    return image_paths
