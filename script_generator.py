"""Claude 웹(claude.ai)을 사용한 웹툰 대본 생성 모듈

Claude Pro 구독의 웹 인터페이스를 Playwright로 자동화합니다.
"""

import json
import re
from playwright.sync_api import Page
import config
from browser_manager import ensure_login


PROMPT_TEMPLATE = """웹툰 숏폼 영상 대본을 작성해줘.

주제: {topic}

반드시 아래 JSON 형식으로만 응답해:
```json
{{
  "title": "영상 제목",
  "scenes": [
    {{
      "scene_number": 1,
      "narration": "나레이션 텍스트 (한국어, 1~2문장)",
      "image_prompt": "DALL-E용 영어 이미지 프롬프트 (webtoon style, manhwa art 포함)",
      "subtitle": "자막 (짧고 임팩트 있게)"
    }}
  ]
}}
```

규칙:
- 장면 4~6개
- 각 나레이션은 읽는데 4~7초
- 전체 25~40초 분량
- image_prompt는 영어, "webtoon style, manhwa art, digital illustration" 필수 포함
- image_prompt에 텍스트/말풍선 묘사 금지
- JSON만 출력"""


def generate_script(page: Page, topic: str) -> dict:
    """Claude 웹에서 대본을 생성합니다."""
    ensure_login(page, config.CLAUDE_URL, "Claude")

    # 새 대화 시작
    page.goto(f"{config.CLAUDE_URL}/new", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 프롬프트 입력
    prompt = PROMPT_TEMPLATE.format(topic=topic)
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

    # 응답 대기 (Claude가 응답을 완료할 때까지)
    print("  Claude 응답 대기 중...")
    page.wait_for_timeout(5000)

    # 응답 완료 감지: 전송 버튼이 다시 활성화될 때까지 대기
    for _ in range(120):  # 최대 2분
        page.wait_for_timeout(1000)
        # 스트리밍이 끝나면 "Stop" 버튼이 사라지고 입력 가능 상태가 됨
        stop_btn = page.locator('button[aria-label="Stop Response"]')
        if not stop_btn.is_visible():
            break
    page.wait_for_timeout(2000)

    # 응답 텍스트 추출
    response_blocks = page.locator("[data-message-author-role='assistant']").all()
    if not response_blocks:
        # 대체 선택자
        response_blocks = page.locator(".font-claude-message").all()

    full_response = ""
    for block in response_blocks:
        full_response += block.inner_text() + "\n"

    if not full_response.strip():
        raise RuntimeError("Claude 응답을 가져올 수 없습니다")

    # JSON 파싱
    json_match = re.search(r"```json\s*(.*?)\s*```", full_response, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r"\{[\s\S]*\"scenes\"[\s\S]*\}", full_response)
        if json_match:
            json_str = json_match.group(0)
        else:
            raise ValueError(f"JSON을 찾을 수 없습니다. 응답:\n{full_response[:500]}")

    script = json.loads(json_str)
    print(f"  대본 생성 완료: {script['title']} ({len(script['scenes'])}장면)")
    return script
