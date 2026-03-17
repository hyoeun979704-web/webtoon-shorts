"""Google Sheets 연동 모듈

시트 구조:
  [설정] 탭 - 전역 설정 (성우 이름, 이미지 스타일 등)
  [작업목록] 탭 - 영상 제작 작업 큐 (주제, 상태, 결과 등)
  [대본] 탭 - 현재 작업의 대본 (수동 수정 가능)
"""

import gspread

# ── 시트 탭 이름 ──
TAB_SETTINGS = "설정"
TAB_TASKS = "작업목록"
TAB_SCRIPT = "대본"

# ── 설정 탭 기본값 ──
DEFAULT_SETTINGS = {
    "카테고리": "",
    "키워드 개수": "5",
    "Claude 프로젝트 URL": "",
    "ChatGPT 프로젝트 URL": "",
    "성우 이름": "",
    "이미지 스타일": "webtoon style, manhwa art, digital illustration",
    "장면 수": "5",
    "장면당 컷 수": "3~4",
    "총 이미지 수": "15~20",
    "목표 길이(초)": "30",
    "편집 모드": "capcut",
    "대본 검토": "Y",
    "편집 검토": "Y",
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


def connect(spreadsheet_url: str) -> gspread.Spreadsheet:
    """Google Sheets에 OAuth로 연결합니다.

    최초 1회 브라우저 로그인 필요, 이후 토큰이 자동 저장됩니다.
    사전에 Google Cloud Console에서 OAuth 클라이언트 ID를 발급받고
    credentials.json 파일을 프로젝트 루트에 두세요.
    """
    gc = gspread.oauth()
    return gc.open_by_url(spreadsheet_url)


def init_sheet(spreadsheet: gspread.Spreadsheet) -> None:
    """시트에 필요한 탭과 헤더를 초기화합니다. (이미 있으면 건너뜀)"""
    existing = [ws.title for ws in spreadsheet.worksheets()]

    # 설정 탭
    if TAB_SETTINGS not in existing:
        ws = spreadsheet.add_worksheet(TAB_SETTINGS, rows=20, cols=2)
        rows = [["항목", "값"]]
        for key, val in DEFAULT_SETTINGS.items():
            rows.append([key, val])
        ws.update(range_name="A1", values=rows)
        print(f"  [{TAB_SETTINGS}] 탭 생성 완료")
    else:
        print(f"  [{TAB_SETTINGS}] 탭 이미 존재")

    # 작업목록 탭
    if TAB_TASKS not in existing:
        ws = spreadsheet.add_worksheet(TAB_TASKS, rows=100, cols=len(TASK_HEADERS))
        ws.update(range_name="A1", values=[TASK_HEADERS])
        ws.format("A1:I1", {"textFormat": {"bold": True}})
        print(f"  [{TAB_TASKS}] 탭 생성 완료")
    else:
        print(f"  [{TAB_TASKS}] 탭 이미 존재")

    # 대본 탭
    if TAB_SCRIPT not in existing:
        ws = spreadsheet.add_worksheet(TAB_SCRIPT, rows=30, cols=len(SCRIPT_HEADERS))
        ws.update(range_name="A1", values=[SCRIPT_HEADERS])
        ws.format("A1:I1", {"textFormat": {"bold": True}})
        print(f"  [{TAB_SCRIPT}] 탭 생성 완료")
    else:
        print(f"  [{TAB_SCRIPT}] 탭 이미 존재")

    # 기본 Sheet1 삭제 (초기 빈 시트)
    if "Sheet1" in existing and len(existing) > 1:
        try:
            spreadsheet.del_worksheet(spreadsheet.worksheet("Sheet1"))
        except Exception:
            pass


# ──────────────────────────────────────────────
# 설정 읽기/쓰기
# ──────────────────────────────────────────────

def read_settings(spreadsheet: gspread.Spreadsheet) -> dict:
    """[설정] 탭에서 key-value 쌍을 읽어 dict로 반환합니다."""
    ws = spreadsheet.worksheet(TAB_SETTINGS)
    rows = ws.get_all_values()
    settings = {}
    for row in rows[1:]:  # 헤더 스킵
        if len(row) >= 2 and row[0].strip():
            settings[row[0].strip()] = row[1].strip()
    return settings


# ──────────────────────────────────────────────
# 작업목록 읽기/쓰기
# ──────────────────────────────────────────────

def read_tasks(spreadsheet: gspread.Spreadsheet) -> list[dict]:
    """[작업목록] 탭에서 모든 작업을 읽습니다."""
    ws = spreadsheet.worksheet(TAB_TASKS)
    records = ws.get_all_records()
    return records


def get_pending_tasks(spreadsheet: gspread.Spreadsheet) -> list[dict]:
    """상태가 '대기'인 작업만 반환합니다."""
    tasks = read_tasks(spreadsheet)
    return [t for t in tasks if t.get("상태", "").strip() == "대기"]


def update_task_status(
    spreadsheet: gspread.Spreadsheet,
    row_number: int,
    status: str,
    **extra_fields,
) -> None:
    """작업목록의 특정 행 상태를 업데이트합니다. row_number는 1-indexed (헤더=1)."""
    ws = spreadsheet.worksheet(TAB_TASKS)
    # 상태 열 = C (3번째)
    ws.update_cell(row_number, 3, status)

    field_col_map = {
        "제목": 4,
        "장면수": 5,
        "시작시간": 6,
        "완료시간": 7,
        "출력경로": 8,
        "비고": 9,
    }
    for field, value in extra_fields.items():
        col = field_col_map.get(field)
        if col:
            ws.update_cell(row_number, col, str(value))


def append_tasks(spreadsheet: gspread.Spreadsheet, keywords: list[dict]) -> int:
    """키워드 목록을 [작업목록] 탭에 '대기' 상태로 추가합니다.

    Returns:
        추가된 작업 수
    """
    ws = spreadsheet.worksheet(TAB_TASKS)
    existing = ws.get_all_values()
    next_num = len(existing)  # 헤더 포함이므로 다음 번호 = 행 수

    rows = []
    for i, kw in enumerate(keywords):
        rows.append([
            next_num + i,                                  # 번호
            kw["topic"],                                   # 주제
            "대기",                                        # 상태
            "",                                            # 제목
            "",                                            # 장면수
            "",                                            # 시작시간
            "",                                            # 완료시간
            "",                                            # 출력경로
            kw.get("hook", ""),                            # 비고 (훅 문구)
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

def write_script_to_sheet(
    spreadsheet: gspread.Spreadsheet, script: dict
) -> None:
    """생성된 대본을 [대본] 탭에 씁니다.

    구조: 장면당 여러 컷(이미지)이 있고, 나레이션/자막은 장면 첫 컷에만 표시.
    """
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
            # 자막: 컷에 개별 자막이 있으면 사용, 없으면 첫 컷에 나레이션 그대로
            subtitle = cut.get("subtitle", "")
            if not subtitle and i == 0:
                subtitle = narration

            rows.append([
                scene["scene_number"],
                cut["cut_number"],
                narration if i == 0 else "",               # 나레이션(음성용)은 첫 컷에만
                subtitle,                                  # 자막: 컷별 자유 작성
                cut["image_prompt"],
                cut.get("sfx", ""),                        # 효과음: CapCut 이름 그대로
                transition if i == 0 else "",              # 장면전환: CapCut 이름 그대로
                "",  # 이미지 상태
                "",  # 음성 상태
            ])
    if rows:
        ws.update(range_name="A2", values=rows)


def read_script_from_sheet(spreadsheet: gspread.Spreadsheet) -> dict | None:
    """[대본] 탭에서 대본을 읽어 dict로 반환합니다.

    컷 기반 행을 장면 단위로 묶어 반환합니다.
    """
    ws = spreadsheet.worksheet(TAB_SCRIPT)
    records = ws.get_all_records()
    if not records:
        return None

    scenes_map: dict[int, dict] = {}
    for rec in records:
        scene_num = rec.get("장면번호", "")
        if not scene_num:
            continue
        scene_num = int(scene_num)
        cut_num = int(rec.get("컷번호", 1))

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

    scenes = [scenes_map[k] for k in sorted(scenes_map)]
    return {"title": "", "scenes": scenes}


def update_script_cut_status(
    spreadsheet: gspread.Spreadsheet,
    sheet_row: int,
    image_status: str = "",
    voice_status: str = "",
) -> None:
    """[대본] 탭에서 특정 행의 이미지/음성 상태를 업데이트합니다.

    Args:
        sheet_row: 시트 행 번호 (1-indexed, 헤더=1)
    """
    ws = spreadsheet.worksheet(TAB_SCRIPT)
    if image_status:
        ws.update_cell(sheet_row, 8, image_status)  # H열
    if voice_status:
        ws.update_cell(sheet_row, 9, voice_status)  # I열
