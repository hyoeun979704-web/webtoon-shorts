"""Claude 프로젝트를 사용한 웹툰 대본 생성 모듈

지정된 Claude 프로젝트 내에서 대화를 시작하여
프로젝트에 설정된 시스템 프롬프트 + 지식 기반으로 고퀄리티 대본을 생성합니다.
"""

from playwright.sync_api import Page
import config
from browser_manager import ensure_login
from utils import log, extract_json, send_and_wait, navigate_to_project


PROMPT_TEMPLATE = """웹툰 숏폼 영상 대본을 작성해줘.

주제: {topic}
{style_instruction}

반드시 아래 JSON 형식으로만 응답해:
```json
{{
  "title": "영상 제목 (호기심 유발, 15자 이내)",
  "scenes": [
    {{
      "scene_number": 1,
      "narration": "나레이션 텍스트 (한국어, 1~2문장, 감정과 리듬감 있게)",
      "transition": "장면 전환 효과 (fade/slide_left/slide_up/zoom_in/glitch/flash/none)",
      "cuts": [
        {{
          "cut_number": 1,
          "image_prompt": "DALL-E용 영어 이미지 프롬프트",
          "sfx": "효과음 (whoosh/impact/ding/pop/dramatic/heartbeat/silence/none)"
        }}
      ]
    }}
  ]
}}
```

규칙:
- 장면 {scene_count}개 구성
- 각 장면당 컷(이미지) {cuts_per_scene}개씩, 총 이미지 {total_images}장
- 웹툰처럼 한 장면 안에서 컷이 빠르게 전환되는 구성

자막 규칙:
- 자막은 기본적으로 나레이션 텍스트를 그대로 표시
- 별도 자막 필드 불필요 (나레이션 = 자막)

효과음(sfx) 규칙:
- 모든 컷에 효과음을 넣지 말 것. 임팩트 있는 순간에만 배치
- 효과음은 분위기를 한국어로 간단히 설명 (예: "타격", "긴장", "등장", "깨달음", "웃음", "정적" 등)
- 사용자가 시트에서 CapCut에 있는 실제 효과음 이름으로 수정할 수 있음
- 효과음이 없는 컷은 sfx를 빈 문자열("")로 설정
- 전체 컷의 30~50%만 효과음 배치 (나머지는 "")

장면 전환(transition) 규칙:
- 장면 사이 전환 효과. 분위기를 한국어로 간단히 설명 (예: "페이드", "슬라이드", "줌인", "글리치", "플래시" 등)
- 사용자가 시트에서 CapCut에 있는 실제 전환 효과 이름으로 수정할 수 있음
- 첫 장면은 전환 없음 (빈 문자열)

컷 구성 예시:
  - 컷1: 상황 설정 (와이드샷) + sfx: ""
  - 컷2: 인물 반응 (미디엄샷) + sfx: "등장"
  - 컷3: 감정 강조 (클로즈업) + sfx: "타격"
  - 컷4: 결과/반전 (새로운 앵글) + sfx: ""

기타 규칙:
- 첫 장면은 반드시 강렬한 훅 (시청자 이탈 방지)
- 마지막 장면은 반전 또는 여운이 있는 마무리
- 나레이션은 구어체로, 읽는데 4~7초
- 전체 25~40초 분량
- image_prompt 규칙:
  - 영어로 작성
  - "{image_style}" 키워드 필수 포함
  - 캐릭터 외형을 일관되게 묘사 (같은 인물은 같은 특징 반복)
  - 구도(extreme close-up, medium shot, wide shot 등), 조명, 표정을 구체적으로
  - 텍스트/글자/말풍선 묘사 절대 금지
- JSON만 출력"""


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
            # sfx 기본값 보장
            cut.setdefault("sfx", "")
        # transition 기본값 보장
        scene.setdefault("transition", "")


def generate_script(
    page: Page,
    topic: str,
    project_url: str = "",
    image_style: str = "webtoon style, manhwa art, digital illustration",
    scene_count: int = 5,
    cuts_per_scene: str = "3~4",
    total_images: str = "15~20",
) -> dict:
    """Claude 프로젝트에서 대본을 생성합니다."""
    ensure_login(page, config.CLAUDE_URL, "Claude")
    navigate_to_project(page, config.CLAUDE_URL, project_url)

    style_instruction = ""
    if image_style:
        style_instruction = f"이미지 스타일 참고: {image_style}"

    prompt = PROMPT_TEMPLATE.format(
        topic=topic,
        style_instruction=style_instruction,
        scene_count=scene_count,
        cuts_per_scene=cuts_per_scene,
        total_images=total_images,
        image_style=image_style,
    )

    response = send_and_wait(page, prompt)
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
