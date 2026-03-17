"""웹툰 숏폼 자동 생성 파이프라인 (Google Sheets + 브라우저 자동화)

Google Sheets에서 설정과 작업목록을 읽어 자동으로 영상을 생성합니다.

시트 구조:
  [설정] 탭   - 성우 이름, 이미지 스타일, 편집 모드 등
  [작업목록] 탭 - 주제를 '대기' 상태로 적어두면 순서대로 처리
  [대본] 탭   - 생성된 대본 확인/수정 가능

사용법:
    python main.py              # 시트의 '대기' 작업을 순서대로 처리
    python main.py --init       # 시트 초기 탭/헤더 세팅
    python main.py --login      # 각 서비스 로그인만 수행
"""

import argparse
import json
import os
import time

import config
import sheet_manager
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


def process_task(browser: BrowserManager, spreadsheet, task: dict, settings: dict):
    """하나의 작업(주제)을 처리합니다."""
    topic = task["주제"]
    task_num = task["번호"]
    row = sheet_manager.find_task_row(spreadsheet, task_num)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = os.path.join(config.OUTPUT_DIR, f"project_{timestamp}")
    images_dir = os.path.join(project_dir, "images")
    voices_dir = os.path.join(project_dir, "voices")
    os.makedirs(project_dir, exist_ok=True)

    actor_name = settings.get("성우 이름", "")
    edit_mode = settings.get("편집 모드", "capcut").strip().lower()
    auto_approve = settings.get("자동 대본 승인", "N").strip().upper() == "Y"

    # 상태 업데이트: 진행중
    sheet_manager.update_task_status(
        spreadsheet, row, "진행중",
        시작시간=time.strftime("%Y-%m-%d %H:%M:%S"),
    )

    try:
        # ===== 1단계: 대본 생성 (Claude) =====
        print(f"\n[1/4] 대본 생성 중 (Claude) - '{topic}'")
        sheet_manager.update_task_status(spreadsheet, row, "1/4 대본 생성중")

        claude_page = browser.new_page()
        script = generate_script(claude_page, topic)
        claude_page.close()

        # 대본을 시트에 기록
        sheet_manager.write_script_to_sheet(spreadsheet, script)
        sheet_manager.update_task_status(
            spreadsheet, row, "1/4 대본 생성완료",
            제목=script["title"],
            장면수=len(script["scenes"]),
        )

        # 대본을 로컬에도 저장
        script_path = os.path.join(project_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        print(f"  제목: {script['title']} ({len(script['scenes'])}장면)")

        # 자동 승인이 아니면 사용자가 시트에서 대본 수정할 시간 제공
        if not auto_approve:
            print("\n" + "=" * 50)
            print("  [대본] 탭에서 나레이션/프롬프트를 확인·수정하세요.")
            print("  수정 완료 후 Enter를 눌러주세요.")
            print("=" * 50)
            input("  → Enter: ")
            # 수정된 대본 다시 읽기
            edited = sheet_manager.read_script_from_sheet(spreadsheet)
            if edited and edited["scenes"]:
                edited["title"] = script["title"]
                script = edited
                print("  시트에서 수정된 대본을 반영했습니다.")

        # ===== 2단계: 이미지 생성 (ChatGPT + DALL-E) =====
        print(f"\n[2/4] 이미지 생성 중 (ChatGPT DALL-E)...")
        sheet_manager.update_task_status(spreadsheet, row, "2/4 이미지 생성중")

        gpt_page = browser.new_page()
        ensure_login(gpt_page, config.CHATGPT_URL, "ChatGPT")

        image_paths = []
        for scene in script["scenes"]:
            scene_num = scene["scene_number"]
            output_path = os.path.join(images_dir, f"scene_{scene_num:02d}.png")
            os.makedirs(images_dir, exist_ok=True)

            print(f"  장면 {scene_num} 이미지 생성 중...")
            from image_generator import generate_image
            generate_image(gpt_page, scene["image_prompt"], output_path)
            image_paths.append(output_path)

            sheet_manager.update_script_scene_status(
                spreadsheet, scene_num, image_status="완료"
            )
            print(f"  장면 {scene_num} 이미지 완료")

        gpt_page.close()

        # ===== 3단계: 음성 생성 (Typecast) =====
        print(f"\n[3/4] 음성 생성 중 (Typecast)...")
        sheet_manager.update_task_status(spreadsheet, row, "3/4 음성 생성중")

        tc_page = browser.new_page()

        voice_paths = []
        for scene in script["scenes"]:
            scene_num = scene["scene_number"]
            output_path = os.path.join(voices_dir, f"voice_{scene_num:02d}.wav")
            os.makedirs(voices_dir, exist_ok=True)

            print(f"  장면 {scene_num} 음성 생성 중...")
            from voice_generator import generate_voice
            generate_voice(tc_page, scene["narration"], output_path, actor_name)
            voice_paths.append(output_path)

            sheet_manager.update_script_scene_status(
                spreadsheet, scene_num, voice_status="완료"
            )
            print(f"  장면 {scene_num} 음성 완료")

        tc_page.close()

        # ===== 4단계: 영상 편집 (CapCut) =====
        if edit_mode == "skip":
            sheet_manager.update_task_status(
                spreadsheet, row, "완료 (에셋만)",
                완료시간=time.strftime("%Y-%m-%d %H:%M:%S"),
                출력경로=project_dir,
            )
            print(f"\n에셋 생성 완료! 폴더: {project_dir}")
        else:
            print(f"\n[4/4] 영상 편집 중 (CapCut)...")
            sheet_manager.update_task_status(spreadsheet, row, "4/4 편집중")

            capcut_page = browser.new_page()
            output_video = os.path.join(project_dir, f"{script['title']}.mp4")
            assemble_video(
                capcut_page, script, image_paths, voice_paths, output_video
            )
            capcut_page.close()

            sheet_manager.update_task_status(
                spreadsheet, row, "완료",
                완료시간=time.strftime("%Y-%m-%d %H:%M:%S"),
                출력경로=output_video,
            )
            print(f"\n완료! 최종 영상: {output_video}")

    except Exception as e:
        sheet_manager.update_task_status(
            spreadsheet, row, "오류",
            비고=str(e)[:200],
        )
        print(f"\n오류 발생: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="웹툰 숏폼 자동 생성기 (Google Sheets 기반)"
    )
    parser.add_argument("--init", action="store_true", help="시트 초기 세팅")
    parser.add_argument("--login", action="store_true", help="서비스 로그인만 수행")
    parser.add_argument("--headless", action="store_true", help="브라우저 숨김")
    args = parser.parse_args()

    if args.headless:
        config.HEADLESS = True

    # Google Sheets 연결
    print("Google Sheets 연결 중...")
    spreadsheet = sheet_manager.connect(config.GOOGLE_SHEET_URL)
    print(f"  시트 연결 완료: {spreadsheet.title}")

    # 초기 세팅 모드
    if args.init:
        print("\n시트 초기화 중...")
        sheet_manager.init_sheet(spreadsheet)
        print("\n시트 초기화 완료!")
        print("  1. [설정] 탭에서 성우 이름 등을 입력하세요")
        print("  2. [작업목록] 탭에서 주제를 추가하고 상태를 '대기'로 설정하세요")
        print("  3. python main.py 로 실행하면 '대기' 작업을 순서대로 처리합니다")
        return

    # 설정 읽기
    settings = sheet_manager.read_settings(spreadsheet)
    print(f"  성우: {settings.get('성우 이름', '(미지정)')}")
    print(f"  편집 모드: {settings.get('편집 모드', 'capcut')}")
    print(f"  자동 대본 승인: {settings.get('자동 대본 승인', 'N')}")

    with BrowserManager() as browser:
        # 로그인 모드
        if args.login:
            login_all(browser)
            return

        # 대기 작업 가져오기
        pending = sheet_manager.get_pending_tasks(spreadsheet)
        if not pending:
            print("\n처리할 '대기' 작업이 없습니다.")
            print("  → [작업목록] 탭에서 주제를 추가하고 상태를 '대기'로 설정하세요")
            return

        print(f"\n처리할 작업: {len(pending)}건")
        for t in pending:
            print(f"  #{t['번호']} {t['주제']}")

        # 작업 순서대로 처리
        for task in pending:
            print(f"\n{'='*50}")
            print(f"  작업 #{task['번호']}: {task['주제']}")
            print(f"{'='*50}")
            process_task(browser, spreadsheet, task, settings)

    print(f"\n모든 작업 완료!")


if __name__ == "__main__":
    main()
