"""Claude 프로젝트를 사용한 웹툰 대본 생성 모듈

지정된 Claude 프로젝트 내에서 대화를 시작하여
프로젝트에 설정된 시스템 프롬프트 + 지식 기반으로 고퀄리티 대본을 생성합니다.
"""

import json
import re
from playwright.sync_api import Page
import config
from browser_manager import ensure_login


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
      "subtitle": "자막 (핵심 한마디, 8자 이내)",
      "cuts": [
        {{
          "cut_number": 1,
          "image_prompt": "DALL-E용 영어 이미지 프롬프트 (상세한 구도, 표정, 분위기)"
        }},
        {{
          "cut_number": 2,
          "image_prompt": "같은 장면의 다른 앵글/순간 묘사"
        }},
        {{
          "cut_number": 3,
          "image_prompt": "감정이 고조되는 클로즈업 등"
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
- 컷 구성 예시:
  - 컷1: 상황 설정 (와이드샷)
  - 컷2: 인물 반응 (미디엄샷/클로즈업)
  - 컷3: 감정 강조 (익스트림 클로즈업/리액션)
  - 컷4: 결과/반전 (새로운 앵글)
- 첫 장면은 반드시 강렬한 훅 (시청자 이탈 방지)
- 마지막 장면은 반전 또는 여운이 있는 마무리
- 나레이션은 구어체로, 읽는데 4~7초
- 전체 25~40초 분량
- image_prompt 규칙:
  - 영어로 작성
  - "{image_style}" 키워드 필수 포함
  - 캐릭터 외형을 일관되게 묘사 (같은 인물은 같은 특징 반복)
  - 구도(extreme close-up, medium shot, wide shot, bird's eye 등), 조명, 표정을 구체적으로
  - 텍스트/글자/말풍선 묘사 절대 금지
- 자막은 임팩트 있는 핵심 문구, 초성체 가능
- JSON만 출력"""


def _navigate_to_project_or_new(page: Page, project_url: str = ""):
    """Claude 프로젝트 또는 새 대화로 이동합니다."""
    if project_url:
        page.goto(project_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        # 프로젝트 내 새 대화 시작
        new_chat_btn = page.locator(
            'button:has-text("New chat"), button:has-text("새 대화"), '
            'a[href*="/new"]'
        ).first
        if new_chat_btn.is_visible():
            new_chat_btn.click()
            page.wait_for_timeout(2000)
    else:
        page.goto(f"{config.CLAUDE_URL}/new", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)


def _send_and_wait(page: Page, prompt: str) -> str:
    """프롬프트를 전송하고 응답 완료까지 대기합니다."""
    editor = page.locator('[contenteditable="true"]').first
    editor.wait_for(timeout=10000)
    editor.click()
    editor.fill(prompt)
    page.wait_for_timeout(500)

    send_button = page.locator('button[aria-label="Send Message"]').first
    if send_button.is_visible():
        send_button.click()
    else:
        editor.press("Enter")

    print("  Claude 응답 대기 중...")
    page.wait_for_timeout(5000)

    for _ in range(120):
        page.wait_for_timeout(1000)
        stop_btn = page.locator('button[aria-label="Stop Response"]')
        if not stop_btn.is_visible():
            break
    page.wait_for_timeout(2000)

    # 응답 추출
    response_blocks = page.locator("[data-message-author-role='assistant']").all()
    if not response_blocks:
        response_blocks = page.locator(".font-claude-message").all()

    full_response = ""
    for block in response_blocks:
        full_response += block.inner_text() + "\n"

    if not full_response.strip():
        raise RuntimeError("Claude 응답을 가져올 수 없습니다")

    return full_response


def generate_script(
    page: Page,
    topic: str,
    project_url: str = "",
    image_style: str = "webtoon style, manhwa art, digital illustration",
    scene_count: int = 5,
    cuts_per_scene: str = "3~4",
    total_images: str = "15~20",
) -> dict:
    """Claude 프로젝트에서 대본을 생성합니다.

    Args:
        page: Playwright 페이지
        topic: 영상 주제
        project_url: Claude 프로젝트 URL (프로젝트의 시스템 프롬프트가 적용됨)
        image_style: 이미지 스타일 키워드
        scene_count: 장면 수
        cuts_per_scene: 장면당 컷 수 (예: "3~4")
        total_images: 총 이미지 수 (예: "15~20")
    """
    ensure_login(page, config.CLAUDE_URL, "Claude")
    _navigate_to_project_or_new(page, project_url)

    style_instruction = ""
    if image_style and image_style != "webtoon style, manhwa art, digital illustration":
        style_instruction = f"이미지 스타일 참고: {image_style}"

    prompt = PROMPT_TEMPLATE.format(
        topic=topic,
        style_instruction=style_instruction,
        scene_count=scene_count,
        cuts_per_scene=cuts_per_scene,
        total_images=total_images,
        image_style=image_style,
    )

    response = _send_and_wait(page, prompt)

    # JSON 파싱
    json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r"\{[\s\S]*\"scenes\"[\s\S]*\}", response)
        if json_match:
            json_str = json_match.group(0)
        else:
            raise ValueError(f"JSON을 찾을 수 없습니다. 응답:\n{response[:500]}")

    script = json.loads(json_str)
    total_cuts = sum(len(s.get("cuts", [])) for s in script["scenes"])
    print(f"  대본 생성 완료: {script['title']} ({len(script['scenes'])}장면, {total_cuts}컷)")
    return script
