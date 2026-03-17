"""Typecast API를 사용한 음성 생성 모듈"""

import os
import time
import requests
import config


def generate_voice(text: str, output_path: str, actor_id: str = "") -> str:
    """Typecast API로 음성을 생성하고 파일로 저장합니다."""
    actor_id = actor_id or config.TYPECAST_ACTOR_ID
    headers = {
        "Authorization": f"Bearer {config.TYPECAST_API_TOKEN}",
        "Content-Type": "application/json",
    }

    # 1) 음성 합성 요청
    payload = {
        "actor_id": actor_id,
        "text": text,
        "lang": "auto",
        "tempo": 1.0,
        "volume": 100,
        "pitch": 0,
        "xapi_hd": True,
        "model_version": "latest",
    }

    response = requests.post(
        "https://typecast.ai/api/speak", json=payload, headers=headers, timeout=30
    )
    response.raise_for_status()
    result = response.json()
    speak_v2_url = result["result"]["speak_v2_url"]

    # 2) 폴링: 음성 생성 완료 대기
    for _ in range(60):
        poll = requests.get(speak_v2_url, headers=headers, timeout=30)
        poll.raise_for_status()
        poll_data = poll.json()
        status = poll_data["result"]["status"]

        if status == "done":
            audio_url = poll_data["result"]["audio_download_url"]
            break
        elif status == "failed":
            raise RuntimeError(f"Typecast 음성 생성 실패: {poll_data}")
        time.sleep(1)
    else:
        raise TimeoutError("Typecast 음성 생성 타임아웃 (60초)")

    # 3) 오디오 파일 다운로드
    audio_data = requests.get(audio_url, timeout=60).content
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(audio_data)

    return output_path


def generate_scene_voices(
    script: dict, output_dir: str, actor_id: str = ""
) -> list[str]:
    """대본의 모든 장면에 대해 음성을 생성합니다."""
    voice_paths = []
    for scene in script["scenes"]:
        scene_num = scene["scene_number"]
        output_path = os.path.join(output_dir, f"voice_{scene_num:02d}.wav")

        print(f"  장면 {scene_num} 음성 생성 중...")
        generate_voice(scene["narration"], output_path, actor_id)
        voice_paths.append(output_path)
        print(f"  장면 {scene_num} 음성 완료: {output_path}")

    return voice_paths


if __name__ == "__main__":
    os.makedirs(config.TEMP_DIR, exist_ok=True)
    path = generate_voice(
        "안녕하세요, 웹툰 숏폼 테스트입니다.",
        os.path.join(config.TEMP_DIR, "test_voice.wav"),
    )
    print(f"테스트 음성 생성 완료: {path}")
