"""OpenAI API 클라이언트 모듈

키워드 발굴, 대본 생성, 이미지 생성을 API로 처리합니다.
"""

import os

from openai import OpenAI

import config
from utils import log


def get_client() -> OpenAI:
    """OpenAI 클라이언트를 반환합니다."""
    if not config.OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY가 설정되지 않았습니다.\n"
            ".env 파일에 OPENAI_API_KEY=sk-... 를 추가하세요."
        )
    return OpenAI(api_key=config.OPENAI_API_KEY)


def load_system_prompt(name: str) -> str:
    """prompts/ 폴더에서 시스템 프롬프트를 로드합니다.

    Args:
        name: 프롬프트 파일 이름 (확장자 제외). 예: "keyword", "script"
    """
    import datetime
    path = os.path.join(config.PROMPTS_DIR, f"{name}.txt")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"시스템 프롬프트 파일이 없습니다: {path}\n"
            f"prompts/{name}.txt 파일을 생성하세요."
        )
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    # 동적으로 현재 연도 주입
    current_date = datetime.datetime.now()
    content += f"\n\n[매우 중요 정보: 현재 시점은 {current_date.year}년 {current_date.month}월입니다. 과거(예: 2023년, 2024년 등)를 현재로 착각하지 말고, 반드시 {current_date.year}년 기준의 최신 트렌드와 정보를 반영하여 응답하세요.]"
    return content


def chat(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """OpenAI Chat API를 호출하고 응답 텍스트를 반환합니다."""
    client = get_client()
    model = model or config.OPENAI_MODEL

    log.debug("  API 호출: model=%s, prompt=%d자", model, len(user_prompt))

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    text = response.choices[0].message.content.strip()
    log.debug("  API 응답: %d자", len(text))
    return text


def chat_multi(
    system_prompt: str,
    messages: list[dict],
    model: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """여러 턴의 대화를 포함한 Chat API 호출."""
    client = get_client()
    model = model or config.OPENAI_MODEL

    all_messages = [{"role": "system", "content": system_prompt}] + messages

    response = client.chat.completions.create(
        model=model,
        messages=all_messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return response.choices[0].message.content.strip()


def generate_image(
    prompt: str,
    output_path: str,
    size: str = "1024x1792",
    quality: str = "standard",
    max_retries: int = 3,
) -> str | None:
    """DALL-E API로 이미지를 생성하고 파일로 저장합니다. (Rate Limit 재시도 포함)

    Returns:
        저장된 파일 경로 또는 실패 시 None
    """
    import time
    import httpx
    import openai

    client = get_client()
    model = config.DALLE_MODEL

    for attempt in range(max_retries):
        try:
            response = client.images.generate(
                model=model,
                prompt=prompt,
                n=1,
                size=size,
                quality=quality,
                style="natural",
            )

            image_url = response.data[0].url
            if not image_url:
                log.warning("  이미지 URL이 비어있습니다")
                return None

            # 이미지 다운로드
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            img_response = httpx.get(image_url, timeout=60)
            img_response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(img_response.content)

            if os.path.getsize(output_path) > 1000:
                return output_path

            log.warning("  이미지 파일이 너무 작습니다: %d bytes", os.path.getsize(output_path))
            return None

        except openai.RateLimitError as e:
            wait_time = (attempt + 1) * 20  # 20s, 40s, 60s
            log.warning("  RateLimit 발생! %d초 대기 후 재시도 (%d/%d) - %s", wait_time, attempt + 1, max_retries, e)
            time.sleep(wait_time)
        except Exception as e:
            log.error("  DALL-E 이미지 생성 실패: %s", e)
            return None

    log.error("  최대 재시도 횟수 초과로 이미지 생성 실패.")
    return None
