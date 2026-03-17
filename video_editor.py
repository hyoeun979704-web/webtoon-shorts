"""FFmpeg 기반 영상 편집 모듈 + CapCut 프로젝트 내보내기"""

import json
import os
import subprocess
import config


def get_audio_duration(audio_path: str) -> float:
    """오디오 파일의 길이(초)를 반환합니다."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            audio_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def create_scene_video(
    image_path: str,
    audio_path: str,
    subtitle_text: str,
    output_path: str,
) -> str:
    """이미지 + 음성 + 자막을 합쳐 하나의 장면 영상을 만듭니다."""
    duration = get_audio_duration(audio_path) + 0.5  # 여유 0.5초

    # 자막 필터 (하단 중앙, 흰색, 검정 테두리)
    escaped_sub = subtitle_text.replace("'", "'\\''").replace(":", "\\:")
    subtitle_filter = (
        f"drawtext=text='{escaped_sub}'"
        f":fontsize=48:fontcolor=white:borderw=3:bordercolor=black"
        f":x=(w-text_w)/2:y=h-h/6"
        f":fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    )

    # 이미지를 영상 해상도에 맞춰 스케일 + 패딩
    scale_filter = (
        f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}"
        f":force_original_aspect_ratio=decrease,"
        f"pad={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black"
    )

    # Ken Burns 효과 (살짝 줌인)
    zoompan_filter = (
        f"zoompan=z='min(zoom+0.0015,1.08)'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={int(duration * config.VIDEO_FPS)}:s={config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}"
        f":fps={config.VIDEO_FPS}"
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-vf", f"{scale_filter},{zoompan_filter},{subtitle_filter}",
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration),
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def concatenate_scenes(scene_videos: list[str], output_path: str) -> str:
    """여러 장면 영상을 하나로 이어붙입니다."""
    concat_list_path = os.path.join(config.TEMP_DIR, "concat_list.txt")
    os.makedirs(os.path.dirname(concat_list_path), exist_ok=True)
    with open(concat_list_path, "w") as f:
        for video in scene_videos:
            f.write(f"file '{os.path.abspath(video)}'\n")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def assemble_video(
    script: dict,
    image_paths: list[str],
    voice_paths: list[str],
    output_path: str,
) -> str:
    """전체 파이프라인: 각 장면 영상 생성 → 하나로 합치기"""
    scene_videos = []

    for i, scene in enumerate(script["scenes"]):
        scene_num = scene["scene_number"]
        scene_output = os.path.join(config.TEMP_DIR, f"scene_video_{scene_num:02d}.mp4")

        print(f"  장면 {scene_num} 영상 조합 중...")
        create_scene_video(
            image_path=image_paths[i],
            audio_path=voice_paths[i],
            subtitle_text=scene.get("subtitle", scene["narration"][:20]),
            output_path=scene_output,
        )
        scene_videos.append(scene_output)
        print(f"  장면 {scene_num} 영상 완료")

    print("  최종 영상 합치는 중...")
    concatenate_scenes(scene_videos, output_path)
    return output_path


def export_capcut_project(
    script: dict,
    image_paths: list[str],
    voice_paths: list[str],
    output_dir: str,
) -> str:
    """CapCut에서 수동 편집할 수 있도록 에셋과 가이드를 내보냅니다.

    CapCut은 공개 API가 없으므로, 에셋 파일들과 편집 가이드를 생성합니다.
    사용자가 CapCut으로 직접 불러와서 미세 조정할 수 있습니다.
    """
    project_dir = os.path.join(output_dir, "capcut_assets")
    os.makedirs(project_dir, exist_ok=True)

    guide = {
        "project_name": script["title"],
        "resolution": f"{config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}",
        "orientation": "portrait (9:16)",
        "scenes": [],
    }

    for i, scene in enumerate(script["scenes"]):
        scene_info = {
            "scene_number": scene["scene_number"],
            "image_file": os.path.basename(image_paths[i]),
            "voice_file": os.path.basename(voice_paths[i]),
            "subtitle": scene.get("subtitle", ""),
            "narration": scene["narration"],
            "suggested_duration_sec": scene.get("duration_sec", 5),
            "tip": "음성 길이에 맞춰 이미지 표시 시간을 조절하세요",
        }
        guide["scenes"].append(scene_info)

    guide["editing_tips"] = [
        "1. CapCut에서 새 프로젝트를 9:16 비율로 생성",
        "2. 이미지 파일을 순서대로 타임라인에 배치",
        "3. 각 이미지 위에 해당 음성 파일을 배치",
        "4. 자막 추가 (subtitle 필드 참고)",
        "5. 전환 효과 추가 (페이드 또는 슬라이드 권장)",
        "6. Ken Burns 효과 (살짝 줌인) 적용 권장",
        "7. 배경음악 추가 (볼륨 20~30% 권장)",
    ]

    guide_path = os.path.join(project_dir, "editing_guide.json")
    with open(guide_path, "w", encoding="utf-8") as f:
        json.dump(guide, f, ensure_ascii=False, indent=2)

    print(f"  CapCut 에셋 및 가이드 내보내기 완료: {project_dir}")
    return project_dir
