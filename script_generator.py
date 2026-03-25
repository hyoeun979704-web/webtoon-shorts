"""OpenAI API 기반 웹툰 대본 생성 모듈

주제(키워드)를 전송하면 대본을 생성하고,
이어서 장면/컷/이미지 프롬프트를 JSON으로 구조화합니다.
"""

import json
import os
import re

from openai_client import chat, chat_multi, load_system_prompt
from utils import log


def _extract_script_text(response: str) -> str:
    """대본 응답에서 순수 대본 텍스트만 추출합니다.

    프로세스 로그, 메타데이터(글자 수, 채점), 채점 근거 메모를 제거합니다.
    """
    # 응답이 두 번 반복되는 경우 첫 번째만 사용
    meta_marker = "[글자 수:"
    first_meta = response.find(meta_marker)
    if first_meta != -1:
        second_meta = response.find(meta_marker, first_meta + 1)
        if second_meta != -1:
            response = response[:second_meta].strip()

    # 방법 1: "[초안 작성 → ...]" 이후 ~ "[글자 수:" 이전
    match = re.search(
        r"\[초안\s*작성[^\]]*\]\s*\n(.+?)\s*\[글자\s*수:",
        response, re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    # 방법 2: "최종 출력/대본" 이후 ~ "[글자 수:" 이전
    match = re.search(
        r"최종\s*(?:출력|대본).*?\n\s*\n(.+?)\s*\[글자\s*수:",
        response, re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    # 방법 3: 마지막 Step 이후 ~ "[글자 수:" 이전
    match = re.search(
        r"Step\s*\d.*?\n\s*\n(.+?)\s*\[글자\s*수:",
        response, re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    # 방법 4: "[글자 수:" 이전의 대본 문단들
    if meta_marker in response:
        before_meta = response[:response.index(meta_marker)].strip()
        paragraphs = re.split(r"\n\s*\n", before_meta)
        script_paras = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if any(kw in para for kw in ("[작성 프로세스 로그]", "[초안 작성")):
                continue
            if re.match(r"^[\s•\-]*Step\s", para):
                continue
            if re.match(r"^(최종|수정|완성)\s*(대본|출력|스크립트)$", para):
                continue
            if para.startswith("•") or para.startswith("- "):
                continue
            if any(kw in para for kw in ("[CTA 유형", "채점 근거", "⚠", "clarity")):
                continue
            if len(para) > 30:
                script_paras.append(para)
        if script_paras:
            return "\n".join(script_paras)

    # 방법 5: 메타/로그/채점 라인 제거 후 나머지
    lines = response.split("\n")
    script_lines = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if "[작성 프로세스 로그]" in stripped or "[초안 작성" in stripped:
            skip = True
            continue
        if skip and (stripped.startswith("Step") or stripped.startswith("•") or
                     stripped.startswith("- Step") or stripped == ""):
            if stripped == "" and script_lines:
                skip = False
            continue
        skip = False
        if "[글자 수:" in stripped or "[채점:" in stripped:
            continue
        if any(kw in stripped for kw in ("채점 근거", "채점 메모", "⚠ 수정 안내",
                                          "⚠️ 수정 안내", "[CTA 유형", "clarity")):
            break
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


def generate_script(topic: str) -> str:
    """OpenAI API로 대본을 생성합니다.

    Returns:
        추출된 대본 텍스트 (순수 나레이션만)
    """
    system_prompt = load_system_prompt("script")

    log.info("대본 생성 중 (API) - 주제: '%s'", topic)
    response = chat(system_prompt, topic, max_tokens=2048)

    debug_path = _save_response_debug(response, topic)

    script_text = _extract_script_text(response)

    if not script_text or len(script_text) < 30:
        # API 응답은 보통 깔끔하므로 추출 실패 시 응답 전체를 대본으로 사용
        script_text = response.strip()

    if not script_text or len(script_text) < 30:
        raise ValueError(
            f"대본 추출 실패. 전체 응답은 {debug_path} 파일을 확인하세요.\n"
            f"응답 앞부분:\n{response[:500]}"
        )

    log.info("대본 생성 완료 (%d자)", len(script_text))
    return script_text


# ── 구조화 프롬프트 ──

_STRUCTURE_USER_TEMPLATE = """\
아래 대본을 유튜브 쇼츠 영상 편집용으로 구조화해줘.

대본:
{script_text}

조건:
- 총 장면 수: {scene_count}개
- 장면당 컷 수: {cuts_per_scene}개
- 이미지 스타일: {image_style}
"""


def _parse_structure_response(response: str) -> dict | None:
    """구조화 응답에서 JSON을 추출합니다."""
    match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    start = response.find('{"scenes"')
    if start == -1:
        start = response.find('"scenes"')
        if start != -1:
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


def structure_script(script_text: str, settings: dict) -> dict:
    """대본 텍스트를 장면/컷/이미지 프롬프트로 구조화합니다.

    Returns:
        {"scenes": [{"scene_number", "narration", "transition", "cuts": [...]}]}
    """
    scene_count = settings.get("장면 수", "6") or "6"
    cuts_per_scene = settings.get("장면당 컷 수", "3~4") or "3~4"
    image_style = settings.get(
        "이미지 스타일",
        "webtoon style, manhwa art, digital illustration",
    )

    system_prompt = load_system_prompt("structure")
    user_prompt = _STRUCTURE_USER_TEMPLATE.format(
        script_text=script_text,
        scene_count=scene_count,
        cuts_per_scene=cuts_per_scene,
        image_style=image_style,
    )

    log.info("대본 구조화 중 (API) - %s장면, 컷 %s개씩...", scene_count, cuts_per_scene)
    response = chat(system_prompt, user_prompt, max_tokens=4096)

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
