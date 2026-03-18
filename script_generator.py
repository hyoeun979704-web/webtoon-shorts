"""Claude 프로젝트를 사용한 웹툰 대본 생성 모듈

지정된 Claude 대본 프로젝트에 주제(키워드)만 전송하면
프로젝트에 설정된 지침에 따라 대본을 생성합니다.

응답 양식 예시:
    [작성 프로세스 로그]
    • Step 0: 키워드 3개 확인 ✅
    • Step 1: 초안 작성
    • Step 2 (Length Gate): 185자 → 범위 내(170~230자) ✅ → 채점 진행
    • Step 2 (Scoring): 13/15 → 기준(12점) 충족 ✅ → 최종 출력

    대본 텍스트...

    [글자 수: 185자 (공백 포함)] [채점: hook 4/5 | clarity 5/5 | flow 4/5 | 합계 13/15]
"""

import re

from playwright.sync_api import Page

import config
from browser_manager import ensure_login
from utils import log, send_and_wait, navigate_to_project


def _extract_script_text(response: str) -> str:
    """Claude 대본 프로젝트 응답에서 대본 텍스트만 추출합니다.

    프로세스 로그, 메타데이터(글자 수, 채점)를 제거하고
    순수 대본 텍스트만 반환합니다.
    """
    # 응답이 두 번 반복되는 경우 첫 번째만 사용
    # (get_assistant_response 셀렉터가 중복 매칭할 수 있음)
    meta_marker = "[글자 수:"
    first_meta = response.find(meta_marker)
    if first_meta != -1:
        second_meta = response.find(meta_marker, first_meta + 1)
        if second_meta != -1:
            response = response[:second_meta].strip()

    # 방법 1: "최종 출력" 이후 ~ "[글자 수:" 이전
    match = re.search(
        r"최종\s*출력.*?\n\s*\n(.+?)\s*\[글자\s*수:",
        response,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    # 방법 2: 프로세스 로그 마지막 Step 이후 ~ "[글자 수:" 이전
    match = re.search(
        r"Step\s*\d.*?\n\s*\n(.+?)\s*\[글자\s*수:",
        response,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    # 방법 3: "[글자 수:" 이전의 마지막 문단 추출
    if meta_marker in response:
        before_meta = response[:response.index(meta_marker)].strip()
        # 빈 줄로 분리된 마지막 문단
        paragraphs = re.split(r"\n\s*\n", before_meta)
        # 프로세스 로그가 아닌 마지막 문단 찾기
        for para in reversed(paragraphs):
            para = para.strip()
            if not para:
                continue
            if "[작성 프로세스 로그]" in para:
                continue
            if re.match(r"^[\s•\-]*Step\s", para):
                continue
            if len(para) > 30:  # 대본은 최소 30자 이상
                return para

    # 방법 4: 프로세스 로그와 메타데이터 라인을 제거하고 남은 텍스트
    lines = response.split("\n")
    script_lines = []
    skip = False
    for line in lines:
        stripped = line.strip()
        # 프로세스 로그 섹션 스킵
        if "[작성 프로세스 로그]" in stripped:
            skip = True
            continue
        if skip and (stripped.startswith("Step") or stripped.startswith("•") or
                     stripped.startswith("- Step") or stripped == ""):
            if stripped == "" and script_lines:
                skip = False
            continue
        skip = False
        # 메타데이터 라인 스킵
        if "[글자 수:" in stripped or "[채점:" in stripped:
            continue
        # 접힌 사고 블록 헤더 스킵
        if stripped.endswith(">") and ("검토" in stripped or "작성" in stripped):
            continue
        if stripped:
            script_lines.append(stripped)

    return "\n".join(script_lines).strip()


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

    response = send_and_wait(page, topic)
    script_text = _extract_script_text(response)

    if not script_text or len(script_text) < 30:
        raise ValueError(
            f"대본 추출 실패. 응답 앞부분:\n{response[:500]}"
        )

    log.info("대본 추출 완료 (%d자)", len(script_text))
    log.info("  대본: %s...", script_text[:80])

    return script_text
