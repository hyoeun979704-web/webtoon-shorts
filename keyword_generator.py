"""Claude 키워드 프로젝트 응답 파싱 모듈

Claude 키워드 프로젝트에 카테고리를 전송하면
프로젝트 지침에 따라 키워드 항목을 생성합니다.

응답 양식 예시:
    [모바일-1] 갤럭시 S26 자급제 vs 통신사 비교 세트
    키워드: 갤럭시 S26 자급제, 통신사 공시지원금 비교, ...
    CTA 유형: 링크 클릭 유도
"""

import re

from playwright.sync_api import Page

import config
from browser_manager import ensure_login
from utils import log, send_and_wait, navigate_to_project


def _parse_keyword_items(text: str) -> list[dict]:
    """Claude 키워드 프로젝트 응답에서 항목을 파싱합니다.

    양식:
        [카테고리-N] 제목
        키워드: k1, k2, k3
        CTA 유형: 유형명

    Returns:
        [{"number": "모바일-1", "title": "...", "keywords": [...], "cta": "..."}, ...]
    """
    items = []

    # [카테고리-N] 제목 패턴으로 항목 분리
    pattern = r"\[([^\]]+)\]\s*(.+)"
    blocks = re.split(r"(?=\[[^\]]+\]\s+)", text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        header_match = re.match(pattern, block)
        if not header_match:
            continue

        number = header_match.group(1).strip()
        title = header_match.group(2).strip()

        # 키워드 추출
        kw_match = re.search(r"키워드\s*[:：]\s*(.+)", block)
        keywords_str = kw_match.group(1).strip() if kw_match else ""
        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

        # CTA 유형 추출
        cta_match = re.search(r"CTA\s*유형\s*[:：]\s*(.+)", block)
        cta = cta_match.group(1).strip() if cta_match else ""

        items.append({
            "number": number,
            "title": title,
            "keywords": keywords,
            "cta": cta,
        })

    return items


def generate_keywords(
    page: Page,
    category: str,
    count: int = 5,
    project_url: str = "",
) -> list[dict]:
    """Claude 키워드 프로젝트에서 키워드 항목을 생성합니다.

    Returns:
        파싱된 키워드 항목 리스트
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
    items = _parse_keyword_items(response)

    if not items:
        raise ValueError(
            f"키워드 항목을 파싱할 수 없습니다. 카테고리: {category}\n"
            f"응답 앞부분: {response[:300]}"
        )

    log.info("키워드 %d개 파싱 완료", len(items))
    for i, item in enumerate(items, 1):
        log.info("  %d. [%s] %s", i, item["number"], item["title"])
        log.info("     키워드: %s", ", ".join(item["keywords"]))
        log.info("     CTA: %s", item["cta"])

    return items


def select_keyword(items: list[dict]) -> dict:
    """사용자가 키워드 항목 중 1개를 선택합니다.

    Returns:
        선택된 키워드 항목
    """
    print()
    print("=" * 60)
    print("  키워드 항목 목록 (1개를 선택하세요)")
    print("=" * 60)
    for i, item in enumerate(items, 1):
        print(f"  {i}. [{item['number']}] {item['title']}")
        print(f"     키워드: {', '.join(item['keywords'])}")
        print(f"     CTA: {item['cta']}")
        print()
    print("=" * 60)

    while True:
        try:
            choice = input(f"  번호 선택 (1-{len(items)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                selected = items[idx]
                log.info("선택됨: [%s] %s", selected["number"], selected["title"])
                return selected
            print(f"  1~{len(items)} 사이 숫자를 입력해주세요.")
        except ValueError:
            print("  숫자를 입력해주세요.")
