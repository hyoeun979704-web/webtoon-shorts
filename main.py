"""웹툰 숏폼 자동 생성 파이프라인

사용법:
    python main.py "주제"
    python main.py "주제" --capcut       # CapCut 에셋도 함께 내보내기
    python main.py "주제" --capcut-only  # CapCut 에셋만 내보내기 (FFmpeg 없이)
"""

import argparse
import json
import os
import sys
import time

import config
from script_generator import generate_script
from image_generator import generate_scene_images
from voice_generator import generate_scene_voices
from video_editor import assemble_video, export_capcut_project


def main():
    parser = argparse.ArgumentParser(description="웹툰 숏폼 자동 생성기")
    parser.add_argument("topic", help="영상 주제 (예: '직장인의 월요일 아침')")
    parser.add_argument(
        "--actor-id", default="", help="Typecast 성우 ID (미지정시 config 기본값)"
    )
    parser.add_argument(
        "--capcut", action="store_true", help="CapCut 에셋도 함께 내보내기"
    )
    parser.add_argument(
        "--capcut-only",
        action="store_true",
        help="CapCut 에셋만 내보내기 (FFmpeg 영상 생성 건너뜀)",
    )
    parser.add_argument(
        "--script-only", action="store_true", help="대본만 생성하고 종료"
    )
    args = parser.parse_args()

    # 작업 디렉토리 준비
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = os.path.join(config.OUTPUT_DIR, f"project_{timestamp}")
    images_dir = os.path.join(project_dir, "images")
    voices_dir = os.path.join(project_dir, "voices")
    os.makedirs(project_dir, exist_ok=True)
    os.makedirs(config.TEMP_DIR, exist_ok=True)

    # ===== 1단계: 대본 생성 (Claude) =====
    print("\n[1/4] 대본 생성 중 (Claude)...")
    script = generate_script(args.topic)

    script_path = os.path.join(project_dir, "script.json")
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    print(f"  대본 저장 완료: {script_path}")
    print(f"  제목: {script['title']}")
    print(f"  장면 수: {len(script['scenes'])}")

    total_duration = sum(s.get("duration_sec", 5) for s in script["scenes"])
    print(f"  예상 길이: {total_duration}초")

    if args.script_only:
        print("\n대본 생성 완료!")
        print(json.dumps(script, ensure_ascii=False, indent=2))
        return

    # ===== 2단계: 이미지 생성 (DALL-E) =====
    print("\n[2/4] 이미지 생성 중 (DALL-E)...")
    image_paths = generate_scene_images(script, images_dir)
    print(f"  이미지 {len(image_paths)}장 생성 완료")

    # ===== 3단계: 음성 생성 (Typecast) =====
    print("\n[3/4] 음성 생성 중 (Typecast)...")
    voice_paths = generate_scene_voices(script, voices_dir, args.actor_id)
    print(f"  음성 {len(voice_paths)}개 생성 완료")

    # ===== 4단계: 영상 편집 =====
    if args.capcut_only:
        print("\n[4/4] CapCut 에셋 내보내기...")
        export_capcut_project(script, image_paths, voice_paths, project_dir)
        print(f"\n완료! CapCut 에셋 위치: {project_dir}/capcut_assets/")
        print("  → CapCut에서 editing_guide.json을 참고하여 편집하세요")
    else:
        print("\n[4/4] 영상 합성 중 (FFmpeg)...")
        output_video = os.path.join(project_dir, f"{script['title']}.mp4")
        assemble_video(script, image_paths, voice_paths, output_video)
        print(f"\n완료! 최종 영상: {output_video}")

        if args.capcut:
            print("\n[추가] CapCut 에셋 내보내기...")
            export_capcut_project(script, image_paths, voice_paths, project_dir)
            print(f"  CapCut 에셋: {project_dir}/capcut_assets/")

    print(f"\n프로젝트 폴더: {project_dir}")


if __name__ == "__main__":
    main()
