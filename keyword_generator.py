"""Claude 프로젝트를 사용한 카테고리별 토픽 키워드 발굴 모듈

지정된 Claude 키워드 프로젝트에 카테고리만 전송하면
프로젝트에 설정된 지침에 따라 키워드를 생성합니다.
"""

from playwright.sync_api import Page
import config
from browser_manager import ensure_login
from utils import log, extract_json, send_and_wait, navigate_to_project


def generate_keywords(
    page: Page,
    category: str,
    count: int = 5,
    project_url: str = "",
) -> list[dict]:
    """카테고리에 맞는 토픽 키워드를 생성합니다.

    프로젝트 지침이 세팅되어 있으므로 카테고리와 개수만 전송합니다.

    Returns:
        [{"topic": "...", "hook": "...", "viral_reason": "..."}, ...]
    """
    if not project_url:
        raise ValueError(
            "Claude 키워드 프로젝트 URL이 설정되지 않았습니다. "
            "시트 [설정] 탭에서 'Claude 키워드 프로젝트 URL'을 입력하세요."
        )

    ensure_login(page, config.CLAUDE_URL, "Claude")
    navigate_to_project(page, config.CLAUDE_URL, project_url)

    prompt = f"{category} {count}개"
    log.info("Claude 키워드 프로젝트에 요청 중 (%s, %d개)...", category, count)

    response = send_and_wait(page, prompt)
    result = extract_json(response, required_key="keywords")

    keywords = result.get("keywords", [])
    if not keywords:
        raise ValueError(f"생성된 키워드가 없습니다. 카테고리: {category}")

    log.info("키워드 %d개 생성 완료", len(keywords))
    for i, kw in enumerate(keywords, 1):
        log.info("  %d. %s - %s", i, kw.get("topic", ""), kw.get("hook", ""))

    return keywords
