"""Claude 프로젝트를 사용한 카테고리별 토픽 키워드 발굴 모듈

지정된 Claude 프로젝트 내에서 대화를 시작하여
카테고리에 맞는 바이럴 가능성 높은 토픽 키워드를 생성합니다.
"""

from playwright.sync_api import Page
import config
from browser_manager import ensure_login
from utils import log, extract_json, send_and_wait, navigate_to_project


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


def generate_keywords(
    page: Page,
    category: str,
    count: int = 5,
    project_url: str = "",
) -> list[dict]:
    """카테고리에 맞는 토픽 키워드를 생성합니다.

    Returns:
        [{"topic": "...", "hook": "...", "viral_reason": "..."}, ...]
    """
    ensure_login(page, config.CLAUDE_URL, "Claude")
    navigate_to_project(page, config.CLAUDE_URL, project_url)

    prompt = KEYWORD_PROMPT.format(category=category, count=count)
    log.info("Claude 키워드 생성 요청 중 (%s, %d개)...", category, count)

    response = send_and_wait(page, prompt)
    result = extract_json(response, required_key="keywords")

    keywords = result.get("keywords", [])
    if not keywords:
        raise ValueError(f"생성된 키워드가 없습니다. 카테고리: {category}")

    log.info("키워드 %d개 생성 완료", len(keywords))
    for i, kw in enumerate(keywords, 1):
        log.info("  %d. %s - %s", i, kw.get("topic", ""), kw.get("hook", ""))

    return keywords
