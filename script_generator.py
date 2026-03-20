"""Claude 프로젝트를 사용한 웹툰 대본 생성 모듈

지정된 Claude 대본 프로젝트에 주제(키워드)만 전송하면
프로젝트에 설정된 지침에 따라 대본을 생성합니다.

응답 양식 예시 (v1):
    [초안 작성 → 글자 수 확인 → 채점 통과]
    대본 텍스트...
    [글자 수: 207자 (공백 포함)] [채점: hook 5/5 | clarity 5/5 | flow 4/5 | 합계 14/15]
    채점 근거 메모
    • hook 5/5 — ...

응답 양식 예시 (v2):
    [작성 프로세스 로그]
    • Step 0: 키워드 3개 확인 ✅
    • Step 2 (Scoring): 13/15 → 기준(12점) 충족 ✅ → 최종 출력
    대본 텍스트...
    [글자 수: 185자 (공백 포함)] [채점: hook 4/5 | ...]
"""

import os
import re

from playwright.sync_api import Page

import config
from browser_manager import ensure_login
from utils import log, send_and_wait, navigate_to_project


def _extract_script_text(response: str) -> str:
    """Claude 대본 프로젝트 응답에서 대본 텍스트만 추출합니다.

    프로세스 로그, 메타데이터(글자 수, 채점), 채점 근거 메모를 제거하고
    순수 대본 텍스트만 반환합니다.
    """
    # 응답이 두 번 반복되는 경우 첫 번째만 사용
    meta_marker = "[글자 수:"
    first_meta = response.find(meta_marker)
    if first_meta != -1:
        second_meta = response.find(meta_marker, first_meta + 1)
        if second_meta != -1:
            response = response[:second_meta].strip()

    # 방법 1: "[초안 작성 → ...]" 이후 ~ "[글자 수:" 이전 (새 양식 v1)
    match = re.search(
        r"\[초안\s*작성[^\]]*\]\s*\n(.+?)\s*\[글자\s*수:",
        response,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    # 방법 2: "최종 출력" 이후 ~ "[글자 수:" 이전 (양식 v2)
    match = re.search(
        r"최종\s*출력.*?\n\s*\n(.+?)\s*\[글자\s*수:",
        response,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    # 방법 3: 마지막 Step 이후 ~ "[글자 수:" 이전
    match = re.search(
        r"Step\s*\d.*?\n\s*\n(.+?)\s*\[글자\s*수:",
        response,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    # 방법 4: "[글자 수:" 이전의 마지막 문단 추출
    if meta_marker in response:
        before_meta = response[:response.index(meta_marker)].strip()
        paragraphs = re.split(r"\n\s*\n", before_meta)
        for para in reversed(paragraphs):
            para = para.strip()
            if not para:
                continue
            if "[작성 프로세스 로그]" in para:
                continue
            if "[초안 작성" in para:
                continue
            if re.match(r"^[\s•\-]*Step\s", para):
                continue
            if len(para) > 30:
                return para

    # 방법 5: 모든 메타/로그/채점 라인 제거
    lines = response.split("\n")
    script_lines = []
    skip = False
    for line in lines:
        stripped = line.strip()
        # 프로세스 로그 / 프로세스 요약 스킵
        if "[작성 프로세스 로그]" in stripped or "[초안 작성" in stripped:
            skip = True
            continue
        if skip and (stripped.startswith("Step") or stripped.startswith("•") or
                     stripped.startswith("- Step") or stripped == ""):
            if stripped == "" and script_lines:
                skip = False
            continue
        skip = False
        # 메타데이터 스킵
        if "[글자 수:" in stripped or "[채점:" in stripped:
            continue
        # 채점 근거 메모 이후 전부 스킵
        if "채점 근거" in stripped or "채점 메모" in stripped:
            break
        # thinking 헤더 스킵
        if stripped.endswith(">") and ("검토" in stripped or "작성" in stripped
                                       or "평가" in stripped or "완료" in stripped):
            continue
        if stripped:
            script_lines.append(stripped)

    return "\n".join(script_lines).strip()


def _save_response_debug(response: str, topic: str) -> str:
    """디버깅용으로 전체 응답을 파일에 저장합니다."""
    debug_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(debug_dir, exist_ok=True)
    debug_path = os.path.join(debug_dir, "last_script_response.txt")
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(f"주제: {topic}\n")
        f.write(f"응답 길이: {len(response)}자\n")
        f.write("=" * 60 + "\n")
        f.write(response)
    return debug_path


def generate_script(
    page: Page,
    topic: str,
    project_url: str = "",
) -> str:
    """Claude 대본 프로젝트에서 대본을 생성합니다.

    Returns:
        추출된 대본 텍스트 (순수 나레이션만)
    """
    if not project_url:
        raise ValueError(
            "Claude 대본 프로젝트 URL이 설정되지 않았습니다. "
            "시트 [설정] 탭에서 'Claude 대본 프로젝트 URL'을 입력하세요."
        )

    ensure_login(page, config.CLAUDE_URL, "Claude")
    navigate_to_project(page, config.CLAUDE_URL, project_url)

    log.info("Claude 대본 프로젝트에 요청 중 - 주제: '%s'", topic)

    response = send_and_wait(page, topic, timeout_sec=300)

    # 디버깅용 응답 저장
    debug_path = _save_response_debug(response, topic)

    script_text = _extract_script_text(response)

    if not script_text or len(script_text) < 30:
        raise ValueError(
            f"대본 추출 실패. 전체 응답은 {debug_path} 파일을 확인하세요.\n"
            f"응답 앞부분:\n{response[:500]}"
        )

    log.info("대본 추출 완료 (%d자)", len(script_text))
    log.info("  대본: %s...", script_text[:80])

    return script_text
