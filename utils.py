"""공통 유틸리티 모듈

JSON 파싱, Playwright 대기 헬퍼, 로깅 설정 등 여러 모듈에서 공유하는 기능을 제공합니다.
"""

import json
import logging
import re
import sys

from playwright.sync_api import Page


# ── 로깅 설정 ──

def setup_logger(name: str = "webtoon", level: int = logging.INFO) -> logging.Logger:
    """프로젝트 공통 로거를 생성합니다."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(handler)
    return logger


log = setup_logger()


# ── JSON 파싱 ──

def extract_json(text: str, required_key: str = "") -> dict:
    """응답 텍스트에서 JSON 블록을 추출합니다.

    Args:
        text: Claude/ChatGPT 응답 텍스트
        required_key: JSON 내에 반드시 있어야 하는 키 (검증용)

    Raises:
        ValueError: JSON을 찾을 수 없거나 파싱 실패 시
    """
    # 1) ```json ... ``` 코드블록
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
        if required_key and required_key not in data:
            raise ValueError(f"JSON에 '{required_key}' 키가 없습니다")
        return data

    # 2) 코드블록 없이 bare JSON - 중괄호 깊이 기반 추출
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    data = json.loads(candidate)
                    if required_key and required_key not in data:
                        raise ValueError(f"JSON에 '{required_key}' 키가 없습니다")
                    return data

    raise ValueError(f"JSON을 찾을 수 없습니다. 응답 앞부분:\n{text[:500]}")


# ── Playwright 헬퍼 ──

def wait_for_response_complete(page: Page, timeout_sec: int = 120) -> None:
    """Claude/ChatGPT의 응답이 완료될 때까지 대기합니다.

    '응답 중지' 버튼이 사라지면 응답 완료로 판단합니다.
    """
    # Claude/ChatGPT 모두 커버하는 정지 버튼 셀렉터
    stop_selectors = [
        'button[aria-label="Stop Response"]',
        'button[aria-label="Stop generating"]',
        'button[aria-label="Stop streaming"]',
        'button[data-testid="stop-button"]',
        'button[class*="stop"]',
    ]
    stop_selector = ", ".join(stop_selectors)

    page.wait_for_timeout(3000)  # 응답 시작 대기

    # 정지 버튼이 나타날 때까지 잠시 대기 (응답이 실제로 시작됐는지 확인)
    stop_appeared = False
    for _ in range(10):
        page.wait_for_timeout(500)
        if page.locator(stop_selector).first.is_visible():
            stop_appeared = True
            break

    if not stop_appeared:
        # 정지 버튼을 못 찾았으면 충분히 대기 후 리턴
        log.warning("응답 정지 버튼을 감지하지 못했습니다. 추가 대기 후 진행합니다.")
        page.wait_for_timeout(10000)
        return

    # 정지 버튼이 사라질 때까지 대기
    for elapsed in range(timeout_sec):
        page.wait_for_timeout(1000)
        if not page.locator(stop_selector).first.is_visible():
            break
    else:
        log.warning("응답 대기 타임아웃 (%d초) - 응답이 아직 진행 중일 수 있습니다", timeout_sec)

    page.wait_for_timeout(2000)  # 렌더링 안정화


def get_assistant_response(page: Page) -> str:
    """페이지에서 마지막 어시스턴트(Claude/ChatGPT) 응답 텍스트를 추출합니다."""
    selectors = [
        "[data-message-author-role='assistant']",
        ".font-claude-message",
    ]
    for sel in selectors:
        blocks = page.locator(sel).all()
        if blocks:
            # 마지막 응답 블록만 반환 (이전 대화 응답 포함 방지)
            return blocks[-1].inner_text()

    raise RuntimeError("응답을 가져올 수 없습니다. 페이지 구조가 변경되었을 수 있습니다.")


def send_prompt(page: Page, prompt: str) -> None:
    """Claude/ChatGPT 입력창에 프롬프트를 입력하고 전송합니다."""
    # Claude 또는 ChatGPT 입력창 탐색
    editor = page.locator(
        '[contenteditable="true"], #prompt-textarea'
    ).first
    editor.wait_for(timeout=10000)
    editor.click()
    editor.fill(prompt)
    page.wait_for_timeout(500)

    # 전송 버튼 클릭 또는 Enter
    send_btn = page.locator(
        'button[aria-label="Send Message"], [data-testid="send-button"]'
    ).first
    if send_btn.is_visible():
        send_btn.click()
    else:
        editor.press("Enter")


def send_and_wait(page: Page, prompt: str, timeout_sec: int = 120) -> str:
    """프롬프트 전송 → 응답 완료 대기 → 응답 텍스트 반환."""
    send_prompt(page, prompt)
    wait_for_response_complete(page, timeout_sec)
    return get_assistant_response(page)


def navigate_to_project(page: Page, base_url: str, project_url: str = "") -> None:
    """Claude/ChatGPT 프로젝트 또는 새 대화 페이지로 이동합니다."""
    if project_url:
        page.goto(project_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        new_chat_btn = page.locator(
            'button:has-text("New chat"), button:has-text("새 대화"), '
            'button:has-text("Start chat"), a[href*="/new"]'
        ).first
        if new_chat_btn.is_visible():
            new_chat_btn.click()
            page.wait_for_timeout(2000)
    else:
        page.goto(f"{base_url}/new", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
