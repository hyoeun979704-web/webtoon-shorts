"""웹툰 숏폼 자동 생성 파이프라인 (브라우저 자동화 버전)

각 서비스의 Pro 구독을 Playwright로 자동화합니다:
- Claude (claude.ai) → 대본 생성
- ChatGPT (chatgpt.com) → DALL-E 이미지 생성
- Typecast (typecast.ai) → 음성 생성
- CapCut (capcut.com) → 영상 편집

사용법:
    python main.py "주제"
    python main.py "주제" --login        # 각 서비스 로그인만 먼저 수행
    python main.py "주제" --script-only  # 대본만 생성
    python main.py "주제" --skip-edit    # 편집 전까지만 (에셋 생성)
"""

import argparse
import json
import os
import time

import config
from browser_manager import BrowserManager, ensure_login
from script_generator import generate_script
from image_generator import generate_scene_images
from voice_generator import generate_scene_voices
from video_editor import assemble_video


def login_all(browser: BrowserManager):
    """모든 서비스에 미리 로그인합니다."""
    services = [
        (config.CLAUDE_URL, "Claude"),
        (config.CHATGPT_URL, "ChatGPT"),
        (config.TYPECAST_URL, "Typecast"),
        (config.CAPCUT_URL, "CapCut"),
    ]
    page = browser.new_page()
    for url, name in services:
        print(f"\n{name} 로그인 확인 중...")
        ensure_login(page, url, name)
        print(f"  {name} 로그인 완료!")
    page.close()
    print("\n모든 서비스 로그인 완료!")


def main():
    parser = argparse.ArgumentParser(description="웹툰 숏폼 자동 생성기 (브라우저 자동화)")
    parser.add_argument("topic", help="영상 주제 (예: '직장인의 월요일 아침')")
    parser.add_argument(
        "--actor", default="", help="Typecast 성우 이름"
    )
    parser.add_argument(
        "--login", action="store_true", help="서비스 로그인만 수행"
    )
    parser.add_argument(
        "--script-only", action="store_true", help="대본만 생성"
    )
    parser.add_argument(
        "--skip-edit", action="store_true", help="CapCut 편집을 건너뜀 (에셋만 생성)"
    )
    parser.add_argument(
        "--headless", action="store_true", help="브라우저를 화면에 표시하지 않음"
    )
    args = parser.parse_args()

    if args.headless:
        config.HEADLESS = True

    # 작업 디렉토리 준비
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = os.path.join(config.OUTPUT_DIR, f"project_{timestamp}")
    images_dir = os.path.join(project_dir, "images")
    voices_dir = os.path.join(project_dir, "voices")
    os.makedirs(project_dir, exist_ok=True)

    with BrowserManager() as browser:
        # 로그인 모드
        if args.login:
            login_all(browser)
            return

        # ===== 1단계: 대본 생성 (Claude) =====
        print("\n[1/4] 대본 생성 중 (Claude)...")
        claude_page = browser.new_page()
        script = generate_script(claude_page, args.topic)
        claude_page.close()

        script_path = os.path.join(project_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)
        print(f"  제목: {script['title']}")
        print(f"  장면 수: {len(script['scenes'])}")

        if args.script_only:
            print("\n대본 생성 완료!")
            print(json.dumps(script, ensure_ascii=False, indent=2))
            return

        # ===== 2단계: 이미지 생성 (ChatGPT + DALL-E) =====
        print("\n[2/4] 이미지 생성 중 (ChatGPT DALL-E)...")
        gpt_page = browser.new_page()
        ensure_login(gpt_page, config.CHATGPT_URL, "ChatGPT")
        image_paths = generate_scene_images(gpt_page, script, images_dir)
        gpt_page.close()
        print(f"  이미지 {len(image_paths)}장 생성 완료")

        # ===== 3단계: 음성 생성 (Typecast) =====
        print("\n[3/4] 음성 생성 중 (Typecast)...")
        tc_page = browser.new_page()
        voice_paths = generate_scene_voices(tc_page, script, voices_dir, args.actor)
        tc_page.close()
        print(f"  음성 {len(voice_paths)}개 생성 완료")

        if args.skip_edit:
            print(f"\n에셋 생성 완료! 프로젝트 폴더: {project_dir}")
            print("  → CapCut에서 수동으로 편집하세요")
            return

        # ===== 4단계: 영상 편집 (CapCut) =====
        print("\n[4/4] 영상 편집 중 (CapCut)...")
        capcut_page = browser.new_page()
        output_video = os.path.join(project_dir, f"{script['title']}.mp4")
        assemble_video(capcut_page, script, image_paths, voice_paths, output_video)
        capcut_page.close()

        print(f"\n{'='*50}")
        print(f"  완료! 최종 영상: {output_video}")
        print(f"  프로젝트 폴더: {project_dir}")
        print(f"{'='*50}")


if __name__ == "__main__":
    main()
