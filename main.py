"""웹툰 숏폼 자동 생성 파이프라인 (Google Sheets + 브라우저 자동화)

Google Sheets를 컨트롤 패널로 사용합니다:
  [설정] 탭 - 카테고리, 프로젝트 URL, 성우, 스타일 등
  [작업목록] 탭 - '대기' 상태 작업을 순서대로 처리
  [대본] 탭 - 생성된 대본 확인/수정

사용법:
    python main.py                 # 시트의 '대기' 작업 처리
    python main.py --init          # 시트 초기 탭/헤더 세팅
    python main.py --login         # 각 서비스 로그인만 수행
    python main.py --keywords      # 카테고리 기반 토픽 키워드 발굴 → 작업목록에 추가
    python main.py --keywords-and-run  # 키워드 발굴 + 바로 영상 생성
"""

import argparse
import json
import os
import time

import config
import sheet_manager
from browser_manager import BrowserManager, ensure_login
from keyword_generator import generate_keywords
from script_generator import generate_script
from image_generator import generate_image
from voice_generator import generate_voice
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


def discover_keywords(browser: BrowserManager, spreadsheet, settings: dict):
    """카테고리에서 토픽 키워드를 발굴하고 작업목록에 추가합니다."""
    category = settings.get("카테고리", "").strip()
    if not category:
        print("\n[설정] 탭에 '카테고리'를 입력해주세요.")
        print("  예: 직장인 공감, 연애, MBTI, 고양이, 학교생활 등")
        return

    count = int(settings.get("키워드 개수", "5"))
    claude_project = settings.get("Claude 프로젝트 URL", "").strip()

    print(f"\n카테고리 [{category}]에서 토픽 {count}개 발굴 중...")
    if claude_project:
        print(f"  Claude 프로젝트: {claude_project}")

    claude_page = browser.new_page()
    keywords = generate_keywords(
        claude_page,
        category=category,
        count=count,
        project_url=claude_project,
    )
    claude_page.close()

    # 작업목록에 추가
    added = sheet_manager.append_tasks(spreadsheet, keywords)
    print(f"\n[작업목록]에 {added}건 추가 완료!")
    print("  → 시트에서 확인 후, 불필요한 항목 삭제 가능")
    print("  → python main.py 로 실행하면 '대기' 작업을 처리합니다")


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

    # 설정 읽기
    actor_name = settings.get("성우 이름", "")
    edit_mode = settings.get("편집 모드", "capcut").strip().lower()
    review_script = settings.get("대본 검토", "Y").strip().upper() == "Y"
    review_edit = settings.get("편집 검토", "Y").strip().upper() == "Y"
    claude_project = settings.get("Claude 프로젝트 URL", "").strip()
    chatgpt_project = settings.get("ChatGPT 프로젝트 URL", "").strip()
    image_style = settings.get("이미지 스타일", "webtoon style, manhwa art, digital illustration")
    scene_count = int(settings.get("장면 수", "5"))
    cuts_per_scene = settings.get("장면당 컷 수", "3~4")
    total_images = settings.get("총 이미지 수", "15~20")

    sheet_manager.update_task_status(
        spreadsheet, row, "진행중",
        시작시간=time.strftime("%Y-%m-%d %H:%M:%S"),
    )

    try:
        # ===== 1단계: 대본 생성 (Claude 프로젝트) =====
        print(f"\n[1/4] 대본 생성 중 (Claude) - '{topic}'")
        if claude_project:
            print(f"  프로젝트: {claude_project}")
        sheet_manager.update_task_status(spreadsheet, row, "1/4 대본 생성중")

        claude_page = browser.new_page()
        script = generate_script(
            claude_page,
            topic=topic,
            project_url=claude_project,
            image_style=image_style,
            scene_count=scene_count,
            cuts_per_scene=cuts_per_scene,
            total_images=total_images,
        )
        claude_page.close()

        total_cuts = sum(len(s.get("cuts", [])) for s in script["scenes"])

        # 대본을 시트에 기록
        sheet_manager.write_script_to_sheet(spreadsheet, script)
        sheet_manager.update_task_status(
            spreadsheet, row, "1/4 대본 생성완료",
            제목=script["title"],
            장면수=f"{len(script['scenes'])}장면/{total_cuts}컷",
        )

        script_path = os.path.join(project_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        print(f"  제목: {script['title']} ({len(script['scenes'])}장면, {total_cuts}컷)")

        # ===== 검토 포인트 1: 대본 검토 =====
        if review_script:
            sheet_manager.update_task_status(spreadsheet, row, "대본 검토 대기")
            print("\n" + "=" * 50)
            print("  [대본 검토] Google Sheets [대본] 탭을 확인하세요.")
            print("")
            print("  수정 가능 항목:")
            print("    - 나레이션 텍스트")
            print("    - 이미지 프롬프트")
            print("    - 자막")
            print("")
            print("  수정 완료 후 Enter를 눌러주세요.")
            print("  (수정 없이 바로 진행하려면 그냥 Enter)")
            print("=" * 50)
            input("  → Enter: ")

            # 수정된 대본 다시 읽기
            edited = sheet_manager.read_script_from_sheet(spreadsheet)
            if edited and edited["scenes"]:
                edited["title"] = script["title"]
                script = edited
                # 수정된 대본 로컬에도 반영
                with open(script_path, "w", encoding="utf-8") as f:
                    json.dump(script, f, ensure_ascii=False, indent=2)
                print("  시트에서 수정된 대본을 반영했습니다.")

        # ===== 2단계: 이미지 생성 (ChatGPT 프로젝트 + DALL-E) =====
        print(f"\n[2/4] 이미지 생성 중 (ChatGPT DALL-E)...")
        if chatgpt_project:
            print(f"  프로젝트: {chatgpt_project}")
        sheet_manager.update_task_status(spreadsheet, row, "2/4 이미지 생성중")

        gpt_page = browser.new_page()
        ensure_login(gpt_page, config.CHATGPT_URL, "ChatGPT")

        image_paths = []  # 컷별 이미지 경로 (전체)
        scene_image_map = {}  # {scene_number: [image_paths]}
        os.makedirs(images_dir, exist_ok=True)

        sheet_row = 2  # 시트 행 번호 (헤더=1)
        for scene in script["scenes"]:
            scene_num = scene["scene_number"]
            cuts = scene.get("cuts", [])
            if not cuts:
                cuts = [{"cut_number": 1, "image_prompt": scene.get("image_prompt", "")}]

            scene_image_map[scene_num] = []
            for cut in cuts:
                cut_num = cut["cut_number"]
                output_path = os.path.join(
                    images_dir, f"scene_{scene_num:02d}_cut_{cut_num:02d}.png"
                )

                print(f"  장면 {scene_num} 컷 {cut_num} 이미지 생성 중...")
                generate_image(gpt_page, cut["image_prompt"], output_path, chatgpt_project)
                image_paths.append(output_path)
                scene_image_map[scene_num].append(output_path)

                sheet_manager.update_script_cut_status(
                    spreadsheet, sheet_row, image_status="완료"
                )
                print(f"  장면 {scene_num} 컷 {cut_num} 이미지 완료")
                sheet_row += 1

        gpt_page.close()
        print(f"  총 {len(image_paths)}장 이미지 생성 완료")

        # ===== 3단계: 음성 생성 (Typecast) =====
        print(f"\n[3/4] 음성 생성 중 (Typecast)...")
        sheet_manager.update_task_status(spreadsheet, row, "3/4 음성 생성중")

        tc_page = browser.new_page()

        voice_paths = []
        os.makedirs(voices_dir, exist_ok=True)

        # 음성은 장면당 1개 (나레이션 기준)
        # 시트에서 각 장면의 첫 번째 컷 행을 찾아 음성 상태 업데이트
        scene_first_row = {}
        current_row = 2
        for scene in script["scenes"]:
            scene_num = scene["scene_number"]
            scene_first_row[scene_num] = current_row
            num_cuts = len(scene.get("cuts", [{"cut_number": 1}]))
            current_row += num_cuts

        for scene in script["scenes"]:
            scene_num = scene["scene_number"]
            output_path = os.path.join(voices_dir, f"voice_{scene_num:02d}.wav")

            print(f"  장면 {scene_num} 음성 생성 중...")
            generate_voice(tc_page, scene["narration"], output_path, actor_name)
            voice_paths.append(output_path)

            sheet_manager.update_script_cut_status(
                spreadsheet, scene_first_row[scene_num], voice_status="완료"
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

            if review_edit:
                sheet_manager.update_task_status(spreadsheet, row, "4/4 편집 배치중")

            assemble_video(
                capcut_page,
                script,
                image_paths,
                voice_paths,
                output_video,
                auto_export=not review_edit,
            )

            if review_edit:
                sheet_manager.update_task_status(spreadsheet, row, "4/4 내보내기중")

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
    parser.add_argument("--keywords", action="store_true", help="카테고리에서 토픽 키워드 발굴")
    parser.add_argument("--keywords-and-run", action="store_true", help="키워드 발굴 후 바로 영상 생성")
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
        print("  1. [설정] 탭에서 카테고리, 프로젝트 URL, 성우 이름 등을 입력")
        print("  2. python main.py --keywords 로 토픽 키워드 자동 발굴")
        print("  3. python main.py 로 영상 자동 생성")
        return

    # 설정 읽기
    settings = sheet_manager.read_settings(spreadsheet)
    print(f"  카테고리: {settings.get('카테고리', '(미지정)')}")
    print(f"  Claude 프로젝트: {settings.get('Claude 프로젝트 URL', '(없음)') or '(없음)'}")
    print(f"  ChatGPT 프로젝트: {settings.get('ChatGPT 프로젝트 URL', '(없음)') or '(없음)'}")
    print(f"  성우: {settings.get('성우 이름', '(미지정)') or '(미지정)'}")

    with BrowserManager() as browser:
        # 로그인 모드
        if args.login:
            login_all(browser)
            return

        # 키워드 발굴 모드
        if args.keywords or args.keywords_and_run:
            discover_keywords(browser, spreadsheet, settings)
            if not args.keywords_and_run:
                return

        # 대기 작업 가져오기
        pending = sheet_manager.get_pending_tasks(spreadsheet)
        if not pending:
            print("\n처리할 '대기' 작업이 없습니다.")
            print("  → [작업목록]에 주제 추가 후 상태를 '대기'로 설정하세요")
            print("  → 또는 python main.py --keywords 로 자동 발굴하세요")
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
