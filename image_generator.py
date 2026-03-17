"""OpenAI DALL-E를 사용한 웹툰 이미지 생성 모듈"""

import os
import requests
from openai import OpenAI
import config


def generate_image(prompt: str, output_path: str) -> str:
    """DALL-E로 이미지를 생성하고 파일로 저장합니다."""
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    response = client.images.generate(
        model=config.DALLE_MODEL,
        prompt=prompt,
        size=config.IMAGE_SIZE,
        quality=config.IMAGE_QUALITY,
        n=1,
    )

    image_url = response.data[0].url
    image_data = requests.get(image_url, timeout=60).content

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(image_data)

    return output_path


def generate_scene_images(script: dict, output_dir: str) -> list[str]:
    """대본의 모든 장면에 대해 이미지를 생성합니다."""
    image_paths = []
    for scene in script["scenes"]:
        scene_num = scene["scene_number"]
        output_path = os.path.join(output_dir, f"scene_{scene_num:02d}.png")

        print(f"  장면 {scene_num} 이미지 생성 중...")
        generate_image(scene["image_prompt"], output_path)
        image_paths.append(output_path)
        print(f"  장면 {scene_num} 이미지 완료: {output_path}")

    return image_paths


if __name__ == "__main__":
    test_prompt = (
        "A tired office worker sitting at desk on Monday morning, "
        "webtoon style, manhwa art, digital illustration, "
        "dramatic lighting, expressive face"
    )
    os.makedirs(config.TEMP_DIR, exist_ok=True)
    path = generate_image(test_prompt, os.path.join(config.TEMP_DIR, "test.png"))
    print(f"테스트 이미지 생성 완료: {path}")
