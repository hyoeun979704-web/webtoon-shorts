"""Claude 프로젝트를 사용한 카테고리별 토픽 키워드 발굴 모듈

지정된 Claude 프로젝트 내에서 대화를 시작하여
카테고리에 맞는 바이럴 가능성 높은 토픽 키워드를 생성합니다.
"""

import json
import re
from playwright.sync_api import Page
import config
from browser_manager import ensure_login


KEYWORD_PROMPT = """다음 카테고리에 대해 숏폼 웹툰 영상으로 만들기 좋은 토픽 키워드를 {count}개 추천해줘.

카테고리: {category}

조건:
- 유튜브/틱톡에서 바이럴될 수 있는 공감형 주제
- 구체적이고 시각화하기 좋은 주제
- 25~40초 숏폼에 맞게 하나의 에피소드로 완결되는 주제
- 한국 MZ세대 타겟

반드시 아래 JSON 형식으로만 응답해:
```json
{{
  "category": "{category}",
  "keywords": [
    {{
      "topic": "구체적인 토픽 제목",
      "hook": "시청자를 끌어당기는 한 줄 훅",
      "viral_reason": "왜 바이럴 가능성이 높은지 한 줄 설명"
    }}
  ]
}}
```

JSON만 출력해."""


def _send_and_wait(page: Page, prompt: str) -> str:
    """Claude 웹에서 프롬프트를 전송하고 응답을 기다립니다."""
    editor = page.locator('[contenteditable="true"]').first
    editor.wait_for(timeout=10000)
    editor.click()
    editor.fill(prompt)
    page.wait_for_timeout(500)

    # 전송
    send_button = page.locator('button[aria-label="Send Message"]').first
    if send_button.is_visible():
        send_button.click()
    else:
        editor.press("Enter")

    # 응답 완료 대기
    page.wait_for_timeout(5000)
    for _ in range(120):
        page.wait_for_timeout(1000)
        stop_btn = page.locator('button[aria-label="Stop Response"]')
        if not stop_btn.is_visible():
            break
    page.wait_for_timeout(2000)

    # 응답 추출
    response_blocks = page.locator("[data-message-author-role='assistant']").all()
    if not response_blocks:
        response_blocks = page.locator(".font-claude-message").all()

    full_response = ""
    for block in response_blocks:
        full_response += block.inner_text() + "\n"

    return full_response


def _parse_json(text: str) -> dict:
    """응답에서 JSON을 추출합니다."""
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))

    json_match = re.search(r"\{[\s\S]*\"keywords\"[\s\S]*\}", text)
    if json_match:
        return json.loads(json_match.group(0))

    raise ValueError(f"JSON을 찾을 수 없습니다. 응답:\n{text[:500]}")


def generate_keywords(
    page: Page,
    category: str,
    count: int = 5,
    project_url: str = "",
) -> list[dict]:
    """카테고리에 맞는 토픽 키워드를 생성합니다.

    Args:
        page: Playwright 페이지
        category: 카테고리 (예: "직장인 공감", "연애", "MBTI")
        count: 생성할 키워드 수
        project_url: Claude 프로젝트 URL (비어있으면 기본 대화)

    Returns:
        [{"topic": "...", "hook": "...", "viral_reason": "..."}, ...]
    """
    ensure_login(page, config.CLAUDE_URL, "Claude")

    # 프로젝트 URL이 있으면 해당 프로젝트에서 새 대화 시작
    if project_url:
        page.goto(project_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        # 프로젝트 내 새 대화 버튼 클릭
        new_chat_btn = page.locator(
            'button:has-text("New chat"), button:has-text("새 대화"), '
            'a[href*="/new"]'
        ).first
        if new_chat_btn.is_visible():
            new_chat_btn.click()
            page.wait_for_timeout(2000)
    else:
        page.goto(f"{config.CLAUDE_URL}/new", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

    prompt = KEYWORD_PROMPT.format(category=category, count=count)
    print(f"  Claude 키워드 생성 요청 중 ({category}, {count}개)...")

    response = _send_and_wait(page, prompt)
    result = _parse_json(response)

    keywords = result.get("keywords", [])
    print(f"  키워드 {len(keywords)}개 생성 완료")
    for i, kw in enumerate(keywords, 1):
        print(f"    {i}. {kw['topic']} - {kw.get('hook', '')}")

    return keywords
