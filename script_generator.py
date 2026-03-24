"""Claude 프로젝트를 사용한 웹툰 대본 생성 모듈

지정된 Claude 대본 프로젝트에 주제(키워드)만 전송하면
프로젝트에 설정된 지침에 따라 대본을 생성합니다.

대본 생성 후 같은 대화에서 구조화 요청을 추가로 보내
장면/컷/이미지 프롬프트/편집 가이드를 JSON으로 받아옵니다.

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

import json
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

    # 방법 2: "최종 출력/대본" 이후 ~ "[글자 수:" 이전 (양식 v2)
    match = re.search(
        r"최종\s*(?:출력|대본).*?\n\s*\n(.+?)\s*\[글자\s*수:",
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

    # 방법 4: "[글자 수:" 이전의 대본 문단들을 모두 수집
    if meta_marker in response:
        before_meta = response[:response.index(meta_marker)].strip()
        paragraphs = re.split(r"\n\s*\n", before_meta)
        # 메타/로그/헤더가 아닌 실질 대본 문단만 수집
        script_paras = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if "[작성 프로세스 로그]" in para:
                continue
            if "[초안 작성" in para:
                continue
            if re.match(r"^[\s•\-]*Step\s", para):
                continue
            # 섹션 헤더 (예: "최종 대본", "최종 출력") 스킵
            if re.match(r"^(최종|수정|완성)\s*(대본|출력|스크립트)$", para):
                continue
            # 불릿 체크리스트 (• 수치 첫 문장..., • 모호한 수치...) 스킵
            if para.startswith("•") or para.startswith("- "):
                continue
            # CTA/채점/수정안내 메타 블록 스킵
            if any(kw in para for kw in ("[CTA 유형", "채점 근거", "⚠", "clarity")):
                continue
            if len(para) > 30:
                script_paras.append(para)
        if script_paras:
            return "\n".join(script_paras)

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
        # 채점 근거/CTA/수정 안내 등 메타 정보 이후 전부 스킵
        if any(kw in stripped for kw in ("채점 근거", "채점 메모", "⚠ 수정 안내",
                                          "⚠️ 수정 안내", "[CTA 유형", "clarity")):
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


# ── 구조화 프롬프트 ──

_STRUCTURE_PROMPT_TEMPLATE = """\
위 대본을 유튜브 쇼츠 영상 편집용으로 구조화해줘.

조건:
- 총 장면 수: {scene_count}개
- 장면당 컷 수: {cuts_per_scene}개
- 이미지 스타일: {image_style}
- 주인공 캐릭터: 반드시 20대 청순하고 섹시한 한국 여성 (섬세하고 부드러운 이목구비, 큰 눈, 글로시한 입술, 슬림한 몸매, 세련되고 은근히 섹시한 의상). 남성 캐릭터로 절대 대체하지 말 것.
- 각 컷마다 DALL-E 이미지 생성용 영문 프롬프트를 작성해줘
- 이미지 프롬프트에 주인공 외모 설명을 반드시 포함해줘 (beautiful Korean woman in her 20s, innocent yet alluring, delicate features, large expressive eyes, glossy lips, slim figure, stylish subtly revealing outfit)
- 이미지 프롬프트에는 텍스트/글자/말풍선 금지 조건 포함
- 자막은 해당 컷의 나레이션 구간에 맞게 분할
- 효과음과 장면전환 효과도 지정해줘

아래 JSON 형식으로만 응답해줘 (설명 없이 JSON만):
```json
{{
  "scenes": [
    {{
      "scene_number": 1,
      "narration": "이 장면의 전체 나레이션",
      "transition": "fade_in",
      "cuts": [
        {{
          "cut_number": 1,
          "subtitle": "이 컷에 표시할 자막",
          "image_prompt": "vertical 9:16 portrait, cinematic webtoon style, ..., no text no letters no speech bubbles",
          "sfx": "whoosh"
        }}
      ]
    }}
  ]
}}
```"""


def _parse_structure_response(response: str) -> dict | None:
    """구조화 응답에서 JSON을 추출합니다."""
    # ```json ... ``` 블록 추출
    match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # bare JSON 추출
    start = response.find('{"scenes"')
    if start == -1:
        start = response.find('"scenes"')
        if start != -1:
            # { 를 앞에서 찾기
            brace = response.rfind("{", 0, start)
            if brace != -1:
                start = brace
    if start != -1:
        depth = 0
        for i in range(start, len(response)):
            if response[i] == "{":
                depth += 1
            elif response[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(response[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def structure_script(
    page: Page,
    script_text: str,
    settings: dict,
) -> dict:
    """대본 텍스트를 장면/컷/이미지 프롬프트/편집 가이드로 구조화합니다.

    기존 Claude 대화(대본 생성 직후)에서 이어서 구조화를 요청합니다.

    Returns:
        {"scenes": [{"scene_number", "narration", "transition", "cuts": [...]}]}
    """
    scene_count = settings.get("장면 수", "6") or "6"
    cuts_per_scene = settings.get("장면당 컷 수", "3~4") or "3~4"
    image_style = settings.get(
        "이미지 스타일",
        "webtoon style, manhwa art, digital illustration",
    )

    prompt = _STRUCTURE_PROMPT_TEMPLATE.format(
        scene_count=scene_count,
        cuts_per_scene=cuts_per_scene,
        image_style=image_style,
    )

    log.info("대본 구조화 요청 중 (%s장면, 컷 %s개씩)...", scene_count, cuts_per_scene)
    response = send_and_wait(page, prompt, timeout_sec=300)

    # 디버깅용 저장
    debug_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(debug_dir, exist_ok=True)
    debug_path = os.path.join(debug_dir, "last_structure_response.txt")
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(response)

    result = _parse_structure_response(response)

    if not result or "scenes" not in result:
        raise ValueError(
            f"대본 구조화 실패. 전체 응답은 {debug_path} 파일을 확인하세요.\n"
            f"응답 앞부분:\n{response[:500]}"
        )

    total_cuts = sum(len(s.get("cuts", [])) for s in result["scenes"])
    log.info("구조화 완료: %d장면, 총 %d컷", len(result["scenes"]), total_cuts)

    return result
