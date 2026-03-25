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
        text: ChatGPT 응답 텍스트
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
    """ChatGPT의 응답이 완료될 때까지 대기합니다.

    '응답 중지' 버튼이 사라지면 응답 완료로 판단합니다.
    버튼을 찾지 못하면 data-is-streaming 속성으로 대체 감지합니다.
    """
    # ChatGPT 정지 버튼 셀렉터
    stop_selectors = [
        'button[aria-label="Stop Response"]',
        'button[aria-label="Stop response"]',
        'button[aria-label="Stop generating"]',
        'button[aria-label="Stop streaming"]',
        'button[data-testid="stop-button"]',
        'button[class*="stop"]',
        'button[class*="Stop"]',
    ]
    stop_selector = ", ".join(stop_selectors)

    # 스트리밍 상태 감지용
    streaming_selector = '[data-is-streaming="true"]'

    page.wait_for_timeout(3000)  # 응답 시작 대기

    # 정지 버튼 또는 스트리밍 상태 감지
    stop_appeared = False
    for _ in range(15):
        page.wait_for_timeout(500)
        if page.locator(stop_selector).first.is_visible():
            stop_appeared = True
            break
        if page.locator(streaming_selector).count() > 0:
            stop_appeared = True
            break

    if not stop_appeared:
        # DALL-E 이미지 생성 등에서는 stop 버튼 없이 진행될 수 있음
        # 텍스트 응답이 나타나거나 이미지가 로드될 때까지 대기
        log.debug("응답 정지 버튼 미감지. 응답 완료 신호를 추가 대기합니다...")
        for _ in range(min(timeout_sec, 120)):
            page.wait_for_timeout(1000)
            # send 버튼이 다시 나타나면 응답 완료로 판단
            send_ready = page.locator(
                '[data-testid="send-button"], '
                'button[aria-label="Send Message"], '
                'button[aria-label="Send message"]'
            ).first
            try:
                if send_ready.is_visible():
                    break
            except Exception:
                pass
        page.wait_for_timeout(2000)
        return

    # 정지 버튼이 사라지고 스트리밍이 끝날 때까지 대기
    for elapsed in range(timeout_sec):
        page.wait_for_timeout(1000)
        stop_visible = page.locator(stop_selector).first.is_visible()
        still_streaming = page.locator(streaming_selector).count() > 0
        if not stop_visible and not still_streaming:
            break
    else:
        log.warning("응답 대기 타임아웃 (%d초) - 응답이 아직 진행 중일 수 있습니다", timeout_sec)

    page.wait_for_timeout(2000)  # 렌더링 안정화


def get_assistant_response(page: Page) -> str:
    """페이지에서 마지막 어시스턴트(ChatGPT) 응답 텍스트를 추출합니다."""
    # 1차: JavaScript로 응답 텍스트 추출
    try:
        text = page.evaluate("""
            () => {
                // ChatGPT 응답 요소 탐색
                const selectors = [
                    '[data-message-author-role="assistant"]',
                    '[data-testid="chat-message-text"]',
                    '.markdown',
                    '.prose',
                ];
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    if (els.length === 0) continue;
                    const last = els[els.length - 1];
                    const t = last.innerText.trim();
                    if (t && t.length > 20) return t;
                }
                return '';
            }
        """)
        if text and len(text) > 20:
            return _strip_thinking_prefix(text)
    except Exception as e:
        log.debug("JS 응답 추출 실패, 폴백 사용: %s", e)

    # 2차: 기존 셀렉터 방식 폴백
    selectors = [
        "[data-message-author-role='assistant']",
        "[data-testid='chat-message-text']",
        "[data-is-streaming='false']",
        ".markdown",
        ".prose",
    ]
    for sel in selectors:
        try:
            blocks = page.locator(sel).all()
            if not blocks:
                continue
            text = blocks[-1].inner_text().strip()
            if text and len(text) > 20:
                return _strip_thinking_prefix(text)
        except Exception:
            continue

    log.error("응답을 찾을 수 없습니다. 현재 URL: %s", page.url)
    raise RuntimeError(
        "응답을 가져올 수 없습니다. 페이지 구조가 변경되었을 수 있습니다.\n"
        f"현재 URL: {page.url}"
    )


def _strip_thinking_prefix(text: str) -> str:
    """응답 앞부분에 포함된 사고 요약 텍스트를 제거합니다.

    LLM이 thinking 블록 요약을 응답 앞에 붙이는 경우가 있어
    첫 줄이 중복되면 제거합니다.
    """
    lines = text.split("\n")
    if len(lines) < 3:
        return text

    # 첫 줄이 두 번 반복되면 첫 번째를 제거
    first = lines[0].strip()
    if first and len(lines) > 1 and lines[1].strip() == first:
        lines = lines[1:]

    return "\n".join(lines)


def _wait_for_cloudflare(page: Page, timeout_sec: int = 120) -> None:
    """Cloudflare 보안 확인 페이지가 감지되면 통과할 때까지 대기합니다.

    browser_manager의 _wait_for_captcha를 재사용합니다.
    """
    from browser_manager import _wait_for_captcha
    _wait_for_captcha(page, "ChatGPT")


def send_prompt(page: Page, prompt: str) -> None:
    """ChatGPT 입력창에 프롬프트를 입력하고 전송합니다."""
    # Cloudflare 보안 확인이 있으면 통과될 때까지 대기
    _wait_for_cloudflare(page)

    # ChatGPT 입력창 탐색
    editor_selectors = [
        '[contenteditable="true"]',
        '#prompt-textarea',
        'textarea[placeholder]',
        'div[role="textbox"]',
    ]
    editor = page.locator(", ".join(editor_selectors)).first
    editor.wait_for(timeout=15000)
    editor.click()
    editor.fill(prompt)
    page.wait_for_timeout(500)

    # 전송 버튼 클릭 또는 Enter
    send_selectors = [
        'button[aria-label="Send Message"]',
        'button[aria-label="Send message"]',
        'button[aria-label="Send prompt"]',
        '[data-testid="send-button"]',
        'button[type="submit"]',
    ]
    send_btn = page.locator(", ".join(send_selectors)).first
    if send_btn.is_visible():
        send_btn.click()
    else:
        editor.press("Enter")


def send_and_wait(page: Page, prompt: str, timeout_sec: int = 120) -> str:
    """프롬프트 전송 → 응답 완료 대기 → 응답 텍스트 반환.

    첫 대기 후 응답을 찾지 못하면 30초 간격으로 최대 10분까지 재확인합니다.
    """
    send_prompt(page, prompt)
    wait_for_response_complete(page, timeout_sec)

    # 응답 추출 시도 → 실패 시 30초 간격으로 재확인 (최대 10분)
    max_retry_sec = 600
    retry_interval = 30
    elapsed = 0

    while True:
        try:
            return get_assistant_response(page)
        except RuntimeError:
            elapsed += retry_interval
            if elapsed > max_retry_sec:
                raise
            log.info(
                "응답이 아직 준비되지 않았습니다. %d초 후 재확인합니다... (경과: %d초/%d초)",
                retry_interval, elapsed, max_retry_sec,
            )
            page.wait_for_timeout(retry_interval * 1000)


def _safe_goto(page: Page, url: str, **kwargs):
    """page.goto 래퍼 - OAuth 리다이렉트 등으로 네비게이션이 중단되어도 안전하게 처리합니다."""
    try:
        page.goto(url, **kwargs)
    except Exception as e:
        if "interrupted by another navigation" in str(e):
            log.info("  리다이렉트 감지, 페이지 로딩 대기 중...")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
        else:
            raise


def navigate_to_project(page: Page, base_url: str, project_url: str = "") -> None:
    """ChatGPT 프로젝트 또는 새 대화 페이지로 이동합니다.

    프로젝트 페이지에는 이미 입력창이 있으므로
    별도 버튼 클릭 없이 바로 프롬프트를 입력할 수 있습니다.
    """
    if project_url:
        _safe_goto(page, project_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Cloudflare 보안 확인이 있으면 통과 대기
        _wait_for_cloudflare(page)

        # 프로젝트 페이지에 있는지 확인
        current = page.url
        if "/project/" in current or "/g/" in current:
            log.info("  프로젝트 페이지 접속 완료: %s", current[:80])
        else:
            log.warning("  프로젝트 페이지가 아닙니다. 현재 URL: %s", current[:80])
    else:
        _safe_goto(page, f"{base_url}/new", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
