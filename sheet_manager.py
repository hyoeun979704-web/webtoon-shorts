"""Google Sheets 연동 모듈

시트 구조:
  [설정] 탭 - 전역 설정 (성우 이름, 이미지 스타일 등)
  [작업목록] 탭 - 영상 제작 작업 큐 (주제, 상태, 결과 등)
  [대본] 탭 - 현재 작업의 대본 (수동 수정 가능)
"""

import os

import gspread
from utils import log

# ── 시트 탭 이름 ──
TAB_SETTINGS = "설정"
TAB_TASKS = "작업목록"
TAB_SCRIPT = "대본"

# ── 설정 탭 기본값 ──
DEFAULT_SETTINGS = {
    "카테고리": "",
    "키워드 개수": "5",
    "Claude 키워드 프로젝트 URL": "",
    "Claude 대본 프로젝트 URL": "",
    "ChatGPT 프로젝트 URL": "",
    "성우 이름": "",
    "Typecast 에디터 URL": "",
    "이미지 스타일": "webtoon style, manhwa art, digital illustration",
    "장면 수": "6",
    "장면당 컷 수": "3~4",
    "총 이미지 수": "15~20",
    "목표 길이(초)": "30",
    "편집 모드": "capcut",
    "대본 검토": "Y",
    "편집 검토": "Y",
    "Claude 계정": "",
    "ChatGPT 계정": "",
    "Typecast 계정": "",
    "CapCut 계정": "",
}

# 기존 시트에서 "Claude 프로젝트 URL"이 중복 사용된 경우 마이그레이션 매핑
_SETTINGS_MIGRATION = {
    # 기존 키 → (키워드 URL 설명 포함 행, 대본 URL 설명 포함 행)
    "Claude 프로젝트 URL": ["Claude 키워드 프로젝트 URL", "Claude 대본 프로젝트 URL"],
}

# ── 작업목록 탭 헤더 ──
TASK_HEADERS = [
    "번호", "주제", "상태", "제목",
    "장면수", "시작시간", "완료시간", "출력경로", "비고",
]

# ── 대본 탭 헤더 ──
SCRIPT_HEADERS = [
    "장면번호", "컷번호", "나레이션", "자막",
    "이미지 프롬프트", "효과음", "장면전환",
    "이미지 상태", "음성 상태",
]

# ── 작업목록 열 인덱스 (1-based) ──
_TASK_COL = {h: i + 1 for i, h in enumerate(TASK_HEADERS)}

# ── 대본 열 인덱스 (1-based) ──
_SCRIPT_COL = {h: i + 1 for i, h in enumerate(SCRIPT_HEADERS)}


def connect(spreadsheet_url: str) -> gspread.Spreadsheet:
    """Google Sheets에 연결합니다.

    인증 방식 우선순위:
      1. 서비스 계정 (SERVICE_ACCOUNT_FILE 환경변수 또는 service_account.json)
      2. OAuth (credentials.json → authorized_user.json)
    """
    sa_file = os.getenv("SERVICE_ACCOUNT_FILE", "")
    _here = os.path.dirname(os.path.abspath(__file__))
    sa_paths = [
        sa_file,
        os.path.join(_here, "service_account.json"),
        "service_account.json",
        os.path.expanduser("~/.config/gspread/service_account.json"),
    ]

    for path in sa_paths:
        if path:
            log.info("  서비스 계정 파일 확인: %s (존재=%s)", path, os.path.isfile(path))
            if os.path.isfile(path):
                log.info("  서비스 계정 인증: %s", path)
                gc = gspread.service_account(filename=path)
                return gc.open_by_url(spreadsheet_url)

    # 서비스 계정 파일이 없으면 폴더 내 파일 목록 출력
    log.warning("  service_account.json을 찾을 수 없습니다.")
    log.warning("  스크립트 폴더: %s", _here)
    try:
        files = [f for f in os.listdir(_here) if f.endswith(".json")]
        log.warning("  폴더 내 JSON 파일: %s", files)
    except Exception:
        pass

    log.info("  OAuth 인증으로 전환합니다...")
    gc = gspread.oauth()
    return gc.open_by_url(spreadsheet_url)


def _get_or_create_worksheet(
    spreadsheet: gspread.Spreadsheet, title: str, rows: int, cols: int
) -> tuple[gspread.Worksheet, bool]:
    """워크시트를 가져오거나 새로 생성합니다. (existed: bool) 반환."""
    existing = [ws.title for ws in spreadsheet.worksheets()]
    if title in existing:
        return spreadsheet.worksheet(title), True
    ws = spreadsheet.add_worksheet(title, rows=rows, cols=cols)
    return ws, False


def init_sheet(spreadsheet: gspread.Spreadsheet) -> None:
    """시트에 필요한 탭과 헤더를 초기화합니다. (이미 있으면 건너뜀)

    서식/유효성검사/조건부서식까지 포함한 전체 세팅은
    `python setup_sheet.py`를 사용하세요.
    """
    existing = [ws.title for ws in spreadsheet.worksheets()]
    needs_setup = False

    # 설정 탭
    if TAB_SETTINGS not in existing:
        ws = spreadsheet.add_worksheet(TAB_SETTINGS, rows=20, cols=3)
        rows = [["항목", "값", "설명"]]
        for key, val in DEFAULT_SETTINGS.items():
            rows.append([key, val, ""])
        ws.update(range_name="A1", values=rows)
        ws.format("A1:C1", {"textFormat": {"bold": True}})
        needs_setup = True
        log.info("  [%s] 탭 생성 완료", TAB_SETTINGS)
    else:
        # 기존 설정 탭에 누락된 항목이 있으면 추가
        ws = spreadsheet.worksheet(TAB_SETTINGS)
        all_rows = ws.get_all_values()
        existing_keys = {row[0].strip() for row in all_rows[1:] if row and row[0].strip()}

        # 마이그레이션 소스 키가 있으면 타겟 키를 추가하지 않음
        # + 이전에 잘못 추가된 빈 타겟 행 삭제
        migration_targets = set()
        rows_to_delete = []
        for src, targets in _SETTINGS_MIGRATION.items():
            if src in existing_keys:
                migration_targets.update(targets)
                # 빈 값으로 추가된 타겟 행 찾기 (역순으로 삭제)
                for row_idx, row in enumerate(all_rows[1:], start=2):
                    key = row[0].strip() if row else ""
                    val = row[1].strip() if len(row) >= 2 else ""
                    if key in targets and not val:
                        rows_to_delete.append(row_idx)

        if rows_to_delete:
            for row_idx in sorted(rows_to_delete, reverse=True):
                ws.delete_rows(row_idx)
            log.info("  [%s] 탭에서 빈 마이그레이션 행 %d개 삭제", TAB_SETTINGS, len(rows_to_delete))

        new_rows = []
        for key, val in DEFAULT_SETTINGS.items():
            if key not in existing_keys and key not in migration_targets:
                new_rows.append([key, val, ""])
        if new_rows:
            ws.append_rows(new_rows)
            log.info("  [%s] 탭에 새 항목 %d개 추가: %s",
                      TAB_SETTINGS, len(new_rows),
                      ", ".join(r[0] for r in new_rows))
        else:
            log.info("  [%s] 탭 이미 존재", TAB_SETTINGS)

    # 작업목록 탭
    if TAB_TASKS not in existing:
        ws = spreadsheet.add_worksheet(TAB_TASKS, rows=100, cols=len(TASK_HEADERS))
        ws.update(range_name="A1", values=[TASK_HEADERS])
        ws.format("A1:I1", {"textFormat": {"bold": True}})
        needs_setup = True
        log.info("  [%s] 탭 생성 완료", TAB_TASKS)
    else:
        log.info("  [%s] 탭 이미 존재", TAB_TASKS)

    # 대본 탭
    if TAB_SCRIPT not in existing:
        ws = spreadsheet.add_worksheet(TAB_SCRIPT, rows=30, cols=len(SCRIPT_HEADERS))
        ws.update(range_name="A1", values=[SCRIPT_HEADERS])
        ws.format("A1:I1", {"textFormat": {"bold": True}})
        needs_setup = True
        log.info("  [%s] 탭 생성 완료", TAB_SCRIPT)
    else:
        log.info("  [%s] 탭 이미 존재", TAB_SCRIPT)

    if needs_setup:
        log.info("  팁: `python setup_sheet.py`로 서식/유효성검사/조건부서식을 추가할 수 있습니다.")

    # 기본 Sheet1 삭제
    existing = [ws.title for ws in spreadsheet.worksheets()]
    if "Sheet1" in existing and len(existing) > 1:
        try:
            spreadsheet.del_worksheet(spreadsheet.worksheet("Sheet1"))
        except Exception:
            pass


# ──────────────────────────────────────────────
# 설정 읽기
# ──────────────────────────────────────────────

def read_settings(spreadsheet: gspread.Spreadsheet) -> dict:
    """[설정] 탭에서 key-value 쌍을 읽어 dict로 반환합니다.

    "Claude 프로젝트 URL" 키가 2개인 레거시 시트도 올바르게 처리합니다.
    첫 번째 → Claude 키워드 프로젝트 URL, 두 번째 → Claude 대본 프로젝트 URL
    """
    ws = spreadsheet.worksheet(TAB_SETTINGS)
    rows = ws.get_all_values()
    settings = {}
    dup_count: dict[str, int] = {}  # 중복 키 카운터

    for row in rows[1:]:
        if len(row) >= 2 and row[0].strip():
            key = row[0].strip()
            val = row[1].strip()

            if key in _SETTINGS_MIGRATION:
                idx = dup_count.get(key, 0)
                mapped_keys = _SETTINGS_MIGRATION[key]
                if idx < len(mapped_keys):
                    mapped = mapped_keys[idx]
                    settings[mapped] = val
                    log.info("  설정 매핑: '%s' (#%d) → '%s' = '%s'",
                             key, idx + 1, mapped, val[:60] if val else "(빈값)")
                dup_count[key] = idx + 1
            elif key in ("Claude 키워드 프로젝트 URL", "Claude 대본 프로젝트 URL"):
                # 새 키 이름: 값이 있을 때만 설정 (빈 행이 마이그레이션 값을 덮어쓰지 않도록)
                if val:
                    settings[key] = val
            else:
                settings[key] = val

    # 디버그: 프로젝트 URL 확인
    kw_url = settings.get("Claude 키워드 프로젝트 URL", "")
    sc_url = settings.get("Claude 대본 프로젝트 URL", "")
    log.info("  Claude 키워드 프로젝트 URL: %s", kw_url[:60] if kw_url else "(없음)")
    log.info("  Claude 대본 프로젝트 URL: %s", sc_url[:60] if sc_url else "(없음)")

    return settings


# ──────────────────────────────────────────────
# 작업목록 읽기/쓰기
# ──────────────────────────────────────────────

def read_tasks(spreadsheet: gspread.Spreadsheet) -> list[dict]:
    """[작업목록] 탭에서 모든 작업을 읽습니다."""
    ws = spreadsheet.worksheet(TAB_TASKS)
    return ws.get_all_records()


def get_pending_tasks(spreadsheet: gspread.Spreadsheet) -> list[dict]:
    """처리 대상 작업을 반환합니다.

    대상 상태:
      - '대기': 1단계(대본 생성)부터 전체 실행
      - '대본완료': 시트 [대본] 탭의 대본을 사용, 3단계(음성)부터 실행
    """
    tasks = read_tasks(spreadsheet)
    return [
        t for t in tasks
        if str(t.get("상태", "")).strip() in ("대기", "대본완료")
    ]


def update_task_status(
    spreadsheet: gspread.Spreadsheet,
    row_number: int,
    status: str,
    **extra_fields,
) -> None:
    """작업목록의 특정 행 상태를 업데이트합니다. row_number는 1-indexed (헤더=1)."""
    ws = spreadsheet.worksheet(TAB_TASKS)
    ws.update_cell(row_number, _TASK_COL["상태"], status)

    for field, value in extra_fields.items():
        col = _TASK_COL.get(field)
        if col:
            ws.update_cell(row_number, col, str(value))


def append_tasks(spreadsheet: gspread.Spreadsheet, keywords: list[dict]) -> int:
    """키워드 목록을 [작업목록] 탭에 '대기' 상태로 추가합니다."""
    ws = spreadsheet.worksheet(TAB_TASKS)
    existing = ws.get_all_values()

    # 기존 최대 번호를 찾아서 이어서 번호 부여 (삭제된 행이 있어도 안전)
    max_num = 0
    for row in existing[1:]:
        try:
            max_num = max(max_num, int(row[0]))
        except (ValueError, IndexError):
            continue

    rows = []
    for i, kw in enumerate(keywords):
        rows.append([
            max_num + i + 1,
            kw["topic"],
            "대기",
            "",  # 제목
            "",  # 장면수
            "",  # 시작시간
            "",  # 완료시간
            "",  # 출력경로
            kw.get("hook", ""),
        ])

    if rows:
        ws.append_rows(rows)
    return len(rows)


def find_task_row(spreadsheet: gspread.Spreadsheet, task_number) -> int:
    """작업 번호로 해당 행 번호를 찾습니다."""
    ws = spreadsheet.worksheet(TAB_TASKS)
    cell = ws.find(str(task_number), in_column=1)
    if cell:
        return cell.row
    raise ValueError(f"작업 번호 {task_number}를 찾을 수 없습니다")


# ──────────────────────────────────────────────
# 대본 읽기/쓰기
# ──────────────────────────────────────────────

def _split_text_to_scenes(text: str) -> list[dict]:
    """대본 텍스트를 문장 단위로 나누어 장면을 구성합니다.

    한국어 문장 종결 패턴(다, 요, 니다, !, ?)으로 분리하여
    2~3문장씩 묶어 장면을 만듭니다.
    """
    import re

    # 문장 분리: 마침표/느낌표/물음표 뒤 공백 기준
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return [{
            "scene_number": 1,
            "narration": text,
            "cuts": [{"cut_number": 1, "image_prompt": "", "subtitle": text, "sfx": ""}],
            "transition": "",
        }]

    # 대본 길이에 따라 장면 수 결정
    total_len = len(text)
    if total_len <= 100:
        target_scenes = 2
    elif total_len <= 200:
        target_scenes = 3
    elif total_len <= 300:
        target_scenes = 4
    else:
        target_scenes = 5

    # 문장 수가 장면 수보다 적으면 조정
    target_scenes = min(target_scenes, len(sentences))

    # 문장을 장면에 균등 분배
    per_scene = max(1, len(sentences) // target_scenes)
    scenes = []

    for i in range(0, len(sentences), per_scene):
        chunk = sentences[i:i + per_scene]
        narration = " ".join(chunk)
        scenes.append({
            "scene_number": len(scenes) + 1,
            "narration": narration,
            "cuts": [{
                "cut_number": 1,
                "image_prompt": "",
                "subtitle": narration,
                "sfx": "",
            }],
            "transition": "",
        })

    return scenes


def write_plain_script_to_sheet(
    spreadsheet: gspread.Spreadsheet,
    title: str,
    script_text: str,
) -> None:
    """plain text 대본을 장면으로 분할하여 [대본] 탭에 씁니다.

    대본 길이에 따라 자동으로 2~5개 장면으로 구성합니다.
    """
    scenes = _split_text_to_scenes(script_text)
    script = {"title": title, "scenes": scenes}
    write_script_to_sheet(spreadsheet, script)
    log.info("  대본 시트 반영: %d장면", len(scenes))


def write_script_to_sheet(
    spreadsheet: gspread.Spreadsheet, script: dict
) -> None:
    """생성된 대본을 [대본] 탭에 씁니다."""
    ws = spreadsheet.worksheet(TAB_SCRIPT)
    ws.clear()
    ws.update(range_name="A1", values=[SCRIPT_HEADERS])
    ws.format("A1:I1", {"textFormat": {"bold": True}})

    rows = []
    for scene in script["scenes"]:
        cuts = scene.get("cuts", [])
        if not cuts:
            cuts = [{"cut_number": 1, "image_prompt": scene.get("image_prompt", ""), "sfx": "", "subtitle": ""}]

        transition = scene.get("transition", "")
        narration = scene.get("narration", "")

        for i, cut in enumerate(cuts):
            subtitle = cut.get("subtitle", "")
            if not subtitle and i == 0:
                subtitle = narration

            rows.append([
                scene["scene_number"],
                cut["cut_number"],
                narration if i == 0 else "",
                subtitle,
                cut["image_prompt"],
                cut.get("sfx", ""),
                transition if i == 0 else "",
                "",  # 이미지 상태
                "",  # 음성 상태
            ])

    if rows:
        ws.update(range_name="A2", values=rows)


def read_script_from_sheet(spreadsheet: gspread.Spreadsheet) -> dict | None:
    """[대본] 탭에서 대본을 읽어 dict로 반환합니다."""
    ws = spreadsheet.worksheet(TAB_SCRIPT)
    records = ws.get_all_records()
    if not records:
        return None

    scenes_map: dict[int, dict] = {}
    for rec in records:
        scene_num = rec.get("장면번호", "")
        if not str(scene_num).strip():
            continue
        try:
            scene_num = int(scene_num)
        except (ValueError, TypeError):
            continue

        cut_num = int(rec.get("컷번호", 1) or 1)

        if scene_num not in scenes_map:
            scenes_map[scene_num] = {
                "scene_number": scene_num,
                "narration": rec.get("나레이션", ""),
                "transition": rec.get("장면전환", ""),
                "cuts": [],
            }

        scenes_map[scene_num]["cuts"].append({
            "cut_number": cut_num,
            "image_prompt": rec.get("이미지 프롬프트", ""),
            "subtitle": rec.get("자막", ""),
            "sfx": rec.get("효과음", ""),
        })

        if rec.get("나레이션", "").strip():
            scenes_map[scene_num]["narration"] = rec["나레이션"]
        if rec.get("장면전환", "").strip():
            scenes_map[scene_num]["transition"] = rec["장면전환"]

    if not scenes_map:
        return None

    scenes = [scenes_map[k] for k in sorted(scenes_map)]
    return {"title": "", "scenes": scenes}


def update_script_cut_status(
    spreadsheet: gspread.Spreadsheet,
    sheet_row: int,
    image_status: str = "",
    voice_status: str = "",
) -> None:
    """[대본] 탭에서 특정 행의 이미지/음성 상태를 업데이트합니다."""
    ws = spreadsheet.worksheet(TAB_SCRIPT)
    if image_status:
        ws.update_cell(sheet_row, _SCRIPT_COL["이미지 상태"], image_status)
    if voice_status:
        ws.update_cell(sheet_row, _SCRIPT_COL["음성 상태"], voice_status)
