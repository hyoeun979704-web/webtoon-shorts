"""웹툰 숏폼 자동 생성 파이프라인 (OpenAI API 전용)

Google Sheets를 컨트롤 패널로 사용합니다:
  [설정] 탭 - 카테고리, 스타일 등
  [작업목록] 탭 - 작업 큐 (상태: 대기/대본완료)
  [대본] 탭 - 생성된 대본 확인/수정

작업 상태별 동작:
  '대기'     → 1단계(대본 생성)부터 전체 파이프라인 실행
  '대본완료' → 시트 [대본] 탭의 대본을 사용, 이미지 생성부터 실행

사용법:
    python main.py           → 실행 (키워드 발굴 → 이미지 에셋 생성)
"""

import argparse
import os
import time

import config
import sheet_manager
from keyword_generator import generate_keywords, select_keyword
from script_generator import generate_script, structure_script
from image_generator import generate_images
from utils import log


def _validate_settings(settings: dict) -> None:
    """필수 설정값이 있는지 검증합니다."""
    if not settings.get("카테고리", "").strip():
        raise ValueError("시트 [설정] 탭에 '카테고리'를 입력해주세요.")
    if not config.OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            ".env 파일에 OPENAI_API_KEY를 입력해주세요."
        )


def _discover_and_select_keyword(settings: dict) -> dict:
    """키워드 발굴 → 응답 파싱 → 1개 선택."""
    category = settings.get("카테고리", "").strip()
    count = int(settings.get("키워드 개수", "5") or "5")

    log.info("카테고리 [%s]에서 키워드 %d개 발굴 중...", category, count)
    items = generate_keywords(category=category, count=count)
    selected = select_keyword(items)
    return selected


def _build_script_prompt(keyword_item: dict) -> str:
    """선택된 키워드 항목으로 대본 프롬프트를 구성합니다."""
    title = keyword_item["title"]
    parts = [title]
    if keyword_item.get("keywords") and "키워드:" not in title:
        parts.append(f"키워드: {', '.join(keyword_item['keywords'])}")
    if keyword_item.get("cta") and "CTA" not in title:
        parts.append(f"CTA 유형: {keyword_item['cta']}")
    return "\n".join(parts)


def _dedup_topic(text: str) -> str:
    """topic 텍스트에서 중복된 줄을 제거합니다."""
    lines = text.strip().split("\n")
    seen = []
    for line in lines:
        line = line.strip()
        if line and line not in seen:
            seen.append(line)
    return "\n".join(seen)


def process_task(spreadsheet, task: dict, settings: dict):
    """하나의 작업(주제)을 처리합니다.

    작업 상태에 따라 시작 단계가 달라집니다:
      '대기'     → 1단계(대본 생성)부터 시작
      '대본완료' → 시트 [대본] 탭의 대본을 사용, 이미지 생성부터 시작
    """
    topic = _dedup_topic(str(task.get("비고", "")).strip() or task["주제"])
    task_num = task["번호"]
    task_status = str(task.get("상태", "")).strip()
    row = sheet_manager.find_task_row(spreadsheet, task_num)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = os.path.join(config.OUTPUT_DIR, f"project_{timestamp}")
    images_dir = os.path.join(project_dir, "images")
    os.makedirs(project_dir, exist_ok=True)

    review_script = settings.get("대본 검토", "Y").strip().upper() == "Y"
    image_style = settings.get(
        "이미지 스타일",
        "webtoon style, manhwa art, digital illustration",
    )

    sheet_manager.update_task_status(
        spreadsheet, row, "진행중",
        시작시간=time.strftime("%Y-%m-%d %H:%M:%S"),
    )

    skip_script_gen = task_status == "대본완료"

    try:
        if skip_script_gen:
            # ===== 시트 대본 읽기 (1~2단계 건너뜀) =====
            log.info("[대본완료] 시트 [대본] 탭에서 대본을 읽습니다...")
            script_data = sheet_manager.read_script_from_sheet(spreadsheet)
            if not script_data or not script_data.get("scenes"):
                raise ValueError(
                    "시트 [대본] 탭에 대본이 없습니다. "
                    "장면번호/컷번호/나레이션/이미지 프롬프트를 입력해주세요."
                )

            script_data["title"] = task["주제"]
            structured = script_data

            total_cuts = sum(len(s.get("cuts", [])) for s in structured["scenes"])
            log.info("  시트 대본 로드: %d장면, %d컷", len(structured["scenes"]), total_cuts)

            sheet_manager.update_task_status(
                spreadsheet, row, "2/3 구조화완료",
                제목=task["주제"],
                장면수=len(structured["scenes"]),
            )

        else:
            # ===== 1단계: 대본 생성 (OpenAI API) =====
            log.info("[1/3] 대본 생성 중 (OpenAI API) - '%s'", topic)
            sheet_manager.update_task_status(spreadsheet, row, "1/3 대본 생성중")

            script_text = generate_script(topic=topic)

            script_path = os.path.join(project_dir, "script.txt")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script_text)

            log.info("  대본 (%d자): %s...", len(script_text), script_text[:100])

            # ===== 검토 포인트: 대본 검토 =====
            if review_script:
                sheet_manager.update_task_status(spreadsheet, row, "대본 검토 대기")
                log.info("")
                log.info("=" * 50)
                log.info("  [대본 검토] 추출된 대본:")
                log.info("")
                log.info("  %s", script_text)
                log.info("")
                log.info("  수정하려면 새 대본을 입력, 그대로 진행하려면 Enter")
                log.info("=" * 50)
                user_input = input("  → 대본 수정 (Enter=유지): ").strip()
                if user_input:
                    script_text = user_input
                    with open(script_path, "w", encoding="utf-8") as f:
                        f.write(script_text)
                    log.info("  대본이 수정되었습니다.")

            # ===== 2단계: 구조화 (OpenAI API) =====
            log.info("[2/3] 대본 구조화 중 (장면/컷/이미지 프롬프트)...")
            sheet_manager.update_task_status(spreadsheet, row, "2/3 구조화중")

            structured = structure_script(script_text, settings)

            script_data = {"title": task["주제"], "scenes": structured["scenes"]}
            sheet_manager.write_script_to_sheet(spreadsheet, script_data)

            total_cuts = sum(len(s.get("cuts", [])) for s in structured["scenes"])
            log.info("  시트 반영 완료: %d장면, %d컷", len(structured["scenes"]), total_cuts)

            sheet_manager.update_task_status(
                spreadsheet, row, "2/3 구조화완료",
                제목=task["주제"],
                장면수=len(structured["scenes"]),
            )

        # ===== 3단계: 이미지 생성 (DALL-E API) =====
        total_cuts = sum(len(s.get("cuts", [])) for s in structured["scenes"])
        log.info("[3/3] 이미지 생성 중 (DALL-E API) - %d컷...", total_cuts)
        sheet_manager.update_task_status(spreadsheet, row, "3/3 이미지 생성중")

        image_paths, failed_cuts = generate_images(
            structured=structured,
            images_dir=images_dir,
            image_style=image_style,
        )

        # 이미지 상태를 시트에 반영
        img_idx = 0
        for scene in structured["scenes"]:
            for cut in scene.get("cuts", []):
                img_idx += 1
                output_path = os.path.join(
                    images_dir,
                    f"s{scene['scene_number']:02d}_c{cut['cut_number']:02d}.png",
                )
                if output_path in image_paths:
                    sheet_row = 1 + img_idx
                    sheet_manager.update_script_cut_status(
                        spreadsheet, sheet_row, image_status="완료"
                    )

        if failed_cuts:
            log.warning("  이미지 생성 완료: 성공 %d컷, 실패 %d컷 (%s)",
                        len(image_paths), len(failed_cuts), ", ".join(failed_cuts))
        else:
            log.info("  이미지 생성 완료 (%d컷)", len(image_paths))

        # ===== 완료 =====
        sheet_manager.update_task_status(
            spreadsheet, row, "완료",
            완료시간=time.strftime("%Y-%m-%d %H:%M:%S"),
            출력경로=project_dir,
        )
        log.info("완료! 출력 폴더: %s", project_dir)
        log.info("  - 대본: %s/script.txt", project_dir)
        log.info("  - 이미지: %s/", images_dir)

    except Exception as e:
        sheet_manager.update_task_status(
            spreadsheet, row, "오류",
            비고=str(e)[:200],
        )
        log.error("오류 발생: %s", e)
        raise


def main():
    parser = argparse.ArgumentParser(description="웹툰 숏폼 자동 생성기")
    parser.parse_args()

    # ===== Google Sheets 연결 =====
    log.info("Google Sheets 연결 중...")
    spreadsheet = sheet_manager.connect(config.GOOGLE_SHEET_URL)
    log.info("  시트 연결 완료: %s", spreadsheet.title)

    sheet_manager.init_sheet(spreadsheet)

    settings = sheet_manager.read_settings(spreadsheet)

    _validate_settings(settings)

    # 대기 작업 확인
    pending = sheet_manager.get_pending_tasks(spreadsheet)

    if not pending:
        # 키워드 발굴 → 파싱 → 1개 선택 → 작업 추가
        log.info("대기 작업이 없어 키워드를 발굴합니다...")
        selected = _discover_and_select_keyword(settings)

        topic_text = _build_script_prompt(selected)
        added = sheet_manager.append_tasks(spreadsheet, [
            {"topic": selected["title"], "hook": topic_text}
        ])
        log.info("[작업목록]에 %d건 추가 완료", added)

        pending = sheet_manager.get_pending_tasks(spreadsheet)

    if not pending:
        log.error("대기 작업이 없습니다. 시트를 확인해주세요.")
        return

    log.info("처리할 작업: %d건", len(pending))
    for t in pending:
        log.info("  #%s %s", t["번호"], t["주제"])

    # 작업 순서대로 처리
    failed = 0
    for task in pending:
        log.info("")
        log.info("=" * 50)
        log.info("  작업 #%s: %s", task["번호"], task["주제"])
        log.info("=" * 50)
        try:
            process_task(spreadsheet, task, settings)
        except Exception as e:
            log.error("작업 #%s 실패: %s", task["번호"], e)
            failed += 1
            continue

    if failed:
        log.warning("완료! (성공 %d건 / 실패 %d건)", len(pending) - failed, failed)
    else:
        log.info("모든 작업 완료! (%d건)", len(pending))


if __name__ == "__main__":
    main()
