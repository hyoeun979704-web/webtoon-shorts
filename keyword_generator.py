"""Claude 키워드 프로젝트 응답 파싱 모듈

Claude 키워드 프로젝트에 카테고리를 전송하면
프로젝트 지침에 따라 키워드 항목을 생성합니다.

응답 양식 예시:
    [모바일-1] 갤럭시 S26 자급제 vs 통신사 비교 세트
    키워드: 갤럭시 S26 자급제, 통신사 공시지원금 비교, ...
    CTA 유형: 링크 클릭 유도
"""

import os
import re

from playwright.sync_api import Page

import config
from browser_manager import ensure_login
from utils import log, send_and_wait, navigate_to_project


def _parse_keyword_items(text: str) -> list[dict]:
    """Claude 키워드 프로젝트 응답에서 항목을 파싱합니다.

    지원하는 형식:
      형식A: [모바일-1] 제목 텍스트
      형식B: ◆ 모바일-1 (또는 🔷, 📌 등 이모지 + 카테고리-번호)
      형식C: **모바일-1** 또는 ### 모바일-1
    """
    items = []
    seen_numbers = set()

    # 카테고리-번호 패턴 (예: 인터넷-1, 모바일-2, 렌탈가전-3)
    _NUM_ID = r"[가-힣A-Za-z]+[\s]*-[\s]*\d+"

    # 항목 헤더를 인식하는 통합 패턴들
    _HEADER_PATTERNS = [
        # [모바일-1] 제목
        re.compile(rf"\[({_NUM_ID})\]\s*(.*)"),
        # ◆ 모바일-1 제목  /  🔷 인터넷-1 제목  (이모지/특수문자 접두사)
        re.compile(rf"[◆◇●○▶►★☆🔷🔶📌📍🏷️💡✅❇️#※]\s*({_NUM_ID})\s*(.*)"),
        # **모바일-1** 제목  (볼드 마크다운)
        re.compile(rf"\*\*({_NUM_ID})\*\*\s*(.*)"),
        # ### 모바일-1 제목  (마크다운 헤딩)
        re.compile(rf"#{1,4}\s*({_NUM_ID})\s*(.*)"),
    ]

    def _match_header(line: str):
        """라인이 항목 헤더인지 확인합니다."""
        for pat in _HEADER_PATTERNS:
            m = pat.search(line)
            if m:
                num = re.sub(r"\s+", "", m.group(1))  # 공백 제거 (인터넷 - 1 → 인터넷-1)
                title = m.group(2).strip() if m.group(2) else ""
                # "글자 수", "채점" 등은 제외
                if "글자" in num or "채점" in num:
                    return None
                return num, title
        return None

    # 라인별로 순회하며 항목 파싱
    lines = text.split("\n")
    current_item = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        header = _match_header(line)
        if header:
            number, title = header
            if number in seen_numbers:
                continue
            seen_numbers.add(number)
            current_item = {
                "number": number,
                "title": title,
                "keywords": [],
                "cta": "",
            }
            items.append(current_item)
            continue

        if current_item:
            kw_match = re.match(r"키워드\s*[:：]\s*(.+)", line)
            if kw_match:
                kw_str = kw_match.group(1).strip()
                current_item["keywords"] = [
                    k.strip() for k in kw_str.split(",") if k.strip()
                ]
                # 제목이 비어있으면 첫 번째 키워드를 제목으로 사용
                if not current_item["title"] and current_item["keywords"]:
                    current_item["title"] = current_item["keywords"][0]
                continue

            cta_match = re.match(r"CTA\s*유형\s*[:：]\s*(.+)", line)
            if cta_match:
                current_item["cta"] = cta_match.group(1).strip()
                continue

    # 제목이 비어있는 항목: 키워드 조합으로 제목 생성
    for item in items:
        if not item["title"] and item["keywords"]:
            item["title"] = ", ".join(item["keywords"][:3])

    return items


def _save_response_debug(response: str, category: str) -> str:
    """디버깅용으로 전체 응답을 파일에 저장합니다."""
    debug_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(debug_dir, exist_ok=True)
    debug_path = os.path.join(debug_dir, "last_keyword_response.txt")
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(f"카테고리: {category}\n")
        f.write(f"응답 길이: {len(response)}자\n")
        f.write("=" * 60 + "\n")
        f.write(response)
    return debug_path


def generate_keywords(
    page: Page,
    category: str,
    count: int = 5,
    project_url: str = "",
) -> list[dict]:
    """Claude 키워드 프로젝트에서 키워드 항목을 생성합니다."""
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

    debug_path = _save_response_debug(response, category)
    log.info("응답 저장됨: %s (%d자)", debug_path, len(response))

    items = _parse_keyword_items(response)

    if not items:
        raise ValueError(
            f"키워드 항목을 파싱할 수 없습니다. 카테고리: {category}\n"
            f"전체 응답은 {debug_path} 파일을 확인하세요.\n"
            f"응답 앞부분 (800자):\n{response[:800]}"
        )

    log.info("키워드 %d개 파싱 완료", len(items))
    return items


def select_keyword(items: list[dict]) -> dict:
    """사용자가 키워드 항목 중 1개를 선택합니다."""
    print()
    print("=" * 60)
    print("  키워드 항목 목록 (1개를 선택하세요)")
    print("-" * 60)
    for i, item in enumerate(items, 1):
        # 카테고리에서 번호 부분 추출 (예: "모바일-1" → "모바일")
        cat = re.sub(r"[-\d]+$", "", item["number"]).strip()
        kw_str = ", ".join(item["keywords"][:3])  # 최대 3개만 표시
        if len(item["keywords"]) > 3:
            kw_str += " ..."
        print(f"  {i}. [{cat}] {item['title']}")
        print(f"     키워드: {kw_str}")
        print(f"     CTA: {item['cta']}")
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
