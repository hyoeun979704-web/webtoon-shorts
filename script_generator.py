"""Claude 프로젝트를 사용한 웹툰 대본 생성 모듈

지정된 Claude 대본 프로젝트에 주제(키워드)만 전송하면
프로젝트에 설정된 지침에 따라 대본을 생성합니다.
"""

from playwright.sync_api import Page
import config
from browser_manager import ensure_login
from utils import log, extract_json, send_and_wait, navigate_to_project


def _validate_script(script: dict) -> None:
    """생성된 대본의 구조를 검증합니다."""
    if "title" not in script:
        raise ValueError("대본에 'title' 필드가 없습니다")
    if "scenes" not in script or not script["scenes"]:
        raise ValueError("대본에 장면(scenes)이 없습니다")

    for i, scene in enumerate(script["scenes"]):
        if "scene_number" not in scene:
            scene["scene_number"] = i + 1
        if "narration" not in scene or not scene["narration"].strip():
            raise ValueError(f"장면 {scene.get('scene_number', i+1)}에 나레이션이 없습니다")
        if "cuts" not in scene or not scene["cuts"]:
            raise ValueError(f"장면 {scene.get('scene_number', i+1)}에 컷이 없습니다")
        for j, cut in enumerate(scene["cuts"]):
            if "cut_number" not in cut:
                cut["cut_number"] = j + 1
            if "image_prompt" not in cut or not cut["image_prompt"].strip():
                raise ValueError(
                    f"장면 {scene['scene_number']} 컷 {cut.get('cut_number', j+1)}에 이미지 프롬프트가 없습니다"
                )
            cut.setdefault("sfx", "")
        scene.setdefault("transition", "")


def generate_script(
    page: Page,
    topic: str,
    project_url: str = "",
) -> dict:
    """Claude 대본 프로젝트에서 대본을 생성합니다.

    프로젝트 지침이 세팅되어 있으므로 주제(키워드)만 전송합니다.
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
    script = extract_json(response, required_key="scenes")
    _validate_script(script)

    total_cuts = sum(len(s["cuts"]) for s in script["scenes"])
    sfx_count = sum(
        1 for s in script["scenes"]
        for c in s["cuts"]
        if c.get("sfx", "")
    )
    log.info(
        "대본 생성 완료: %s (%d장면, %d컷, 효과음 %d개)",
        script["title"], len(script["scenes"]), total_cuts, sfx_count,
    )
    return script
