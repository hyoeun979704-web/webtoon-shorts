"""ChatGPT 웹(chatgpt.com)의 DALL-E를 사용한 이미지 생성 모듈

ChatGPT Plus/Pro 구독의 웹 인터페이스를 Playwright로 자동화합니다.
"""

import os
import re
import requests
from playwright.sync_api import Page
import config
from browser_manager import ensure_login


def generate_image(page: Page, prompt: str, output_path: str) -> str:
    """ChatGPT에서 DALL-E로 이미지를 생성하고 다운로드합니다."""
    # 새 대화 시작
    page.goto(f"{config.CHATGPT_URL}/?model=gpt-4", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 이미지 생성 프롬프트 입력
    full_prompt = f"Generate an image: {prompt}. Do not include any text, letters, or speech bubbles in the image."
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

        # DALL-E 생성 이미지 찾기 (여러 선택자 시도)
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
                img_element = imgs[-1]  # 마지막(최신) 이미지
                break

        if img_element and img_element.is_visible():
            # 이미지 로딩 완료 대기
            page.wait_for_timeout(3000)
            break
    else:
        raise TimeoutError("ChatGPT 이미지 생성 타임아웃 (3분)")

    # 이미지 다운로드
    img_src = img_element.get_attribute("src")
    if not img_src:
        raise RuntimeError("이미지 URL을 찾을 수 없습니다")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ChatGPT의 이미지는 페이지 컨텍스트에서 다운로드 필요할 수 있음
    if img_src.startswith("http"):
        img_data = requests.get(img_src, timeout=60).content
        with open(output_path, "wb") as f:
            f.write(img_data)
    else:
        # base64 등의 경우 스크린샷으로 대체
        img_element.screenshot(path=output_path)

    return output_path


def generate_scene_images(page: Page, script: dict, output_dir: str) -> list[str]:
    """대본의 모든 장면에 대해 ChatGPT로 이미지를 생성합니다."""
    image_paths = []
    os.makedirs(output_dir, exist_ok=True)

    for scene in script["scenes"]:
        scene_num = scene["scene_number"]
        output_path = os.path.join(output_dir, f"scene_{scene_num:02d}.png")

        print(f"  장면 {scene_num} 이미지 생성 중...")
        generate_image(page, scene["image_prompt"], output_path)
        image_paths.append(output_path)
        print(f"  장면 {scene_num} 이미지 완료: {output_path}")

    return image_paths
