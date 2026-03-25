"""OpenAI API 기반 키워드 발굴 모듈

카테고리를 입력받아 키워드 항목을 생성합니다.

응답 양식 예시:
    [모바일-1] 갤럭시 S26 자급제 vs 통신사 비교 세트
    키워드: 갤럭시 S26 자급제, 통신사 공시지원금 비교, ...
    CTA 유형: 링크 클릭 유도
"""

import os
import re

from openai_client import chat, load_system_prompt
from utils import log


def _parse_keyword_items(text: str) -> list[dict]:
    """키워드 응답에서 항목을 파싱합니다.

    지원하는 형식:
      형식A: [모바일-1] 제목 텍스트
      형식B: ◆ 모바일-1 (또는 이모지 + 카테고리-번호)
      형식C: **모바일-1** 또는 ### 모바일-1
    """
    items = []
    seen_numbers = set()

    _NUM_ID = r"[가-힣A-Za-z]+[\s]*-[\s]*\d+"

    _HEADER_PATTERNS = [
        re.compile(rf"\[({_NUM_ID})\]\s*(.*)"),
        re.compile(rf"[◆◇●○▶►★☆🔷🔶📌📍🏷️💡✅❇️#※]\s*({_NUM_ID})\s*(.*)"),
        re.compile(rf"\*\*({_NUM_ID})\*\*\s*(.*)"),
        re.compile(rf"#{1,4}\s*({_NUM_ID})\s*(.*)"),
    ]

    def _match_header(line: str):
        for pat in _HEADER_PATTERNS:
            m = pat.search(line)
            if m:
                num = re.sub(r"\s+", "", m.group(1))
                title = m.group(2).strip() if m.group(2) else ""
                if "글자" in num or "채점" in num:
                    return None
                return num, title
        return None

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
                if not current_item["title"] and current_item["keywords"]:
                    current_item["title"] = current_item["keywords"][0]
                continue

            cta_match = re.match(r"CTA\s*유형\s*[:：]\s*(.+)", line)
            if cta_match:
                current_item["cta"] = cta_match.group(1).strip()
                continue

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
    category: str,
    count: int = 5,
) -> list[dict]:
    """OpenAI API로 키워드 항목을 생성합니다."""
    system_prompt = load_system_prompt("keyword")
    user_prompt = f"{category} {count}개"

    log.info("키워드 발굴 중 (API) - %s, %d개...", category, count)
    response = chat(system_prompt, user_prompt)

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
        cat = re.sub(r"[-\d]+$", "", item["number"]).strip()
        kw_str = ", ".join(item["keywords"][:3])
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
