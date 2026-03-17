"""Claude API를 사용한 웹툰 대본 생성 모듈"""

import json
import anthropic
import config


SYSTEM_PROMPT = """당신은 웹툰 숏폼 영상 대본 작가입니다.
주어진 주제로 25~40초 분량의 웹툰 스타일 숏폼 대본을 작성합니다.

반드시 아래 JSON 형식으로만 응답하세요:
{
  "title": "영상 제목",
  "scenes": [
    {
      "scene_number": 1,
      "narration": "이 장면의 나레이션 텍스트 (한국어, 1~2문장)",
      "image_prompt": "이 장면을 묘사하는 영어 이미지 생성 프롬프트 (webtoon style, manhwa art style 포함)",
      "subtitle": "자막 텍스트 (짧고 임팩트 있게)",
      "duration_sec": 5
    }
  ]
}

규칙:
- 장면은 4~6개로 구성
- 각 장면의 나레이션은 읽는데 4~7초 소요되도록 작성
- 전체 나레이션 합산이 25~40초가 되도록 조절
- image_prompt는 영어로 작성하며, 반드시 "webtoon style, manhwa art, digital illustration" 키워드를 포함
- image_prompt에 텍스트/글자/말풍선 묘사를 넣지 마세요
- 각 장면이 시각적으로 구분되고 이야기 흐름이 자연스럽게 이어지도록 작성
- 자막은 시청자의 시선을 끄는 핵심 문구로 작성
- JSON 외에 다른 텍스트를 출력하지 마세요"""


def generate_script(topic: str) -> dict:
    """주제를 받아 웹툰 숏폼 대본을 생성합니다."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": f"다음 주제로 웹툰 숏폼 대본을 작성해주세요: {topic}",
            }
        ],
        system=SYSTEM_PROMPT,
    )

    response_text = message.content[0].text
    # JSON 파싱 (코드 블록으로 감싸진 경우 처리)
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    script = json.loads(response_text.strip())
    return script


if __name__ == "__main__":
    import sys

    topic = sys.argv[1] if len(sys.argv) > 1 else "직장인의 월요일 아침"
    result = generate_script(topic)
    print(json.dumps(result, ensure_ascii=False, indent=2))
