"""Google Sheets 자동화 시트 초기 세팅 스크립트

시트 3개를 생성하고 서식, 유효성 검사, 조건부 서식, 열 너비 등을 설정합니다.
최초 1회만 실행하면 됩니다.

사용법:
    python setup_sheet.py              # 시트 초기 세팅
    python setup_sheet.py --reset      # 기존 시트 삭제 후 재생성
"""

import argparse

import gspread
from gspread_formatting import (
    BooleanCondition,
    BooleanRule,
    CellFormat,
    Color,
    ConditionalFormatRule,
    DataValidationRule,
    GridRange,
    TextFormat,
    batch_updater,
    format_cell_range,
    get_conditional_format_rules,
    set_column_widths,
    set_data_validation_for_cell_range,
    set_frozen,
    set_row_height,
)

import config
from sheet_manager import (
    DEFAULT_SETTINGS,
    SCRIPT_HEADERS,
    TAB_SCRIPT,
    TAB_SETTINGS,
    TAB_TASKS,
    TASK_HEADERS,
)
from utils import log

# ── 색상 정의 ──
WHITE = Color(1, 1, 1)
LIGHT_GRAY = Color(0.95, 0.95, 0.95)
DARK_GRAY = Color(0.3, 0.3, 0.3)
HEADER_BG = Color(0.16, 0.16, 0.2)         # 거의 검정 (헤더 배경)
HEADER_FG = Color(1, 1, 1)                  # 흰색 (헤더 글자)
SETTING_KEY_BG = Color(0.93, 0.93, 0.97)    # 연보라 (설정 항목명)
REQUIRED_BG = Color(1, 0.95, 0.9)           # 연주황 (필수 입력)

# 상태 색상
STATUS_WAIT = Color(0.85, 0.92, 1)          # 연파랑 - 대기
STATUS_PROGRESS = Color(1, 0.96, 0.8)       # 연노랑 - 진행중
STATUS_DONE = Color(0.85, 1, 0.85)          # 연녹색 - 완료
STATUS_ERROR = Color(1, 0.85, 0.85)         # 연빨강 - 오류
STATUS_REVIEW = Color(0.95, 0.9, 1)         # 연보라 - 검토

# ── 설정 항목별 도움말 ──
SETTING_NOTES = {
    "카테고리": "필수. 영상 주제 카테고리 (예: 연애, 직장, 가족, 공포, 먹방)",
    "키워드 개수": "자동 발굴할 토픽 수 (기본: 5)",
    "Claude 프로젝트 URL": "Claude 프로젝트 URL (있으면 프로젝트 컨텍스트 활용)",
    "ChatGPT 프로젝트 URL": "ChatGPT 프로젝트 URL (있으면 프로젝트 컨텍스트 활용)",
    "성우 이름": "음성 생성용 성우 이름 (수동 처리 시 참고용)",
    "이미지 스타일": "DALL-E 프롬프트에 포함할 스타일 키워드",
    "장면 수": "영상 구성 장면 수 (기본: 5)",
    "장면당 컷 수": "장면당 이미지 수 범위 (기본: 3~4)",
    "총 이미지 수": "전체 이미지 수 범위 (기본: 15~20)",
    "목표 길이(초)": "완성 영상 목표 길이 (기본: 30)",
    "편집 모드": "capcut=CapCut 자동편집, skip=에셋만 생성",
    "대본 검토": "Y=대본 생성 후 시트에서 수정 가능, N=바로 진행",
    "편집 검토": "Y=CapCut 배치 후 수동 확인, N=바로 내보내기",
}

# 필수 항목
REQUIRED_SETTINGS = {"카테고리"}

# 드롭다운 선택지
SETTING_DROPDOWNS = {
    "편집 모드": ["capcut", "skip"],
    "대본 검토": ["Y", "N"],
    "편집 검토": ["Y", "N"],
    "장면 수": ["3", "4", "5", "6", "7"],
    "키워드 개수": ["3", "5", "7", "10"],
}


def _connect() -> gspread.Spreadsheet:
    """Google Sheets에 연결합니다. (sheet_manager.connect와 동일한 인증 로직)"""
    from sheet_manager import connect
    return connect(config.GOOGLE_SHEET_URL)


def _remove_default_sheet(spreadsheet: gspread.Spreadsheet) -> None:
    """기본 Sheet1을 삭제합니다."""
    names = [ws.title for ws in spreadsheet.worksheets()]
    if "Sheet1" in names and len(names) > 1:
        try:
            spreadsheet.del_worksheet(spreadsheet.worksheet("Sheet1"))
        except Exception:
            pass


def _header_fmt() -> CellFormat:
    """공통 헤더 포맷을 반환합니다."""
    return CellFormat(
        backgroundColor=HEADER_BG,
        textFormat=TextFormat(
            bold=True,
            foregroundColor=HEADER_FG,
            fontSize=10,
        ),
        horizontalAlignment="CENTER",
        verticalAlignment="MIDDLE",
    )


# ══════════════════════════════════════════════
# [설정] 탭
# ══════════════════════════════════════════════

def setup_settings_tab(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    """[설정] 탭을 생성하고 서식을 적용합니다."""
    log.info("[설정] 탭 세팅 중...")

    names = [ws.title for ws in spreadsheet.worksheets()]
    if TAB_SETTINGS in names:
        ws = spreadsheet.worksheet(TAB_SETTINGS)
        ws.clear()
    else:
        ws = spreadsheet.add_worksheet(TAB_SETTINGS, rows=20, cols=3)

    # 데이터 입력
    rows = [["항목", "값", "설명"]]
    settings_keys = list(DEFAULT_SETTINGS.keys())
    for key in settings_keys:
        val = DEFAULT_SETTINGS[key]
        note = SETTING_NOTES.get(key, "")
        rows.append([key, val, note])
    ws.update(range_name="A1", values=rows)

    # 헤더 서식
    format_cell_range(ws, "A1:C1", _header_fmt())
    set_row_height(ws, "1", 36)

    # 항목명 열 서식 (A열)
    num_settings = len(settings_keys)
    last_row = num_settings + 1
    format_cell_range(ws, f"A2:A{last_row}", CellFormat(
        backgroundColor=SETTING_KEY_BG,
        textFormat=TextFormat(bold=True, fontSize=10),
        verticalAlignment="MIDDLE",
    ))

    # 필수 항목 강조 (값 셀 배경)
    for i, key in enumerate(settings_keys, start=2):
        if key in REQUIRED_SETTINGS:
            format_cell_range(ws, f"B{i}", CellFormat(
                backgroundColor=REQUIRED_BG,
            ))

    # 설명 열 서식 (C열)
    format_cell_range(ws, f"C2:C{last_row}", CellFormat(
        textFormat=TextFormat(
            foregroundColor=Color(0.5, 0.5, 0.5),
            fontSize=9,
            italic=True,
        ),
    ))

    # 드롭다운 유효성 검사
    for key, options in SETTING_DROPDOWNS.items():
        row_idx = settings_keys.index(key) + 2
        rule = DataValidationRule(
            BooleanCondition("ONE_OF_LIST", options),
            showCustomUi=True,
        )
        set_data_validation_for_cell_range(ws, f"B{row_idx}", rule)

    # 열 너비
    set_column_widths(ws, [
        ("A", 180),
        ("B", 350),
        ("C", 380),
    ])

    # 헤더 고정
    set_frozen(ws, rows=1)

    log.info("  [설정] 탭 완료 (%d개 항목)", num_settings)
    return ws


# ══════════════════════════════════════════════
# [작업목록] 탭
# ══════════════════════════════════════════════

def _task_status_rules(ws: gspread.Worksheet) -> list:
    """작업목록 상태 컬럼에 조건부 서식 규칙을 생성합니다."""
    sheet_id = ws.id
    # 상태 컬럼 = C (index 2), 행 2~100
    range_ref = GridRange(sheetId=sheet_id, startRowIndex=1, endRowIndex=100,
                          startColumnIndex=0, endColumnIndex=len(TASK_HEADERS))

    rules = []
    status_colors = [
        ("대기", STATUS_WAIT),
        ("진행중", STATUS_PROGRESS),
        ("완료", STATUS_DONE),
        ("오류", STATUS_ERROR),
    ]
    # 부분 일치: "1/4 대본 생성중" 등도 노랑 처리
    partial_colors = [
        ("1/4", STATUS_PROGRESS),
        ("2/4", STATUS_PROGRESS),
        ("3/4", STATUS_PROGRESS),
        ("4/4", STATUS_PROGRESS),
        ("검토", STATUS_REVIEW),
    ]

    for text, color in status_colors + partial_colors:
        rules.append(ConditionalFormatRule(
            ranges=[range_ref],
            booleanRule=BooleanRule(
                condition=BooleanCondition("CUSTOM_FORMULA", [
                    f'=SEARCH("{text}",$C2)'
                ]),
                format=CellFormat(backgroundColor=color),
            ),
        ))
    return rules


def setup_tasks_tab(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    """[작업목록] 탭을 생성하고 서식을 적용합니다."""
    log.info("[작업목록] 탭 세팅 중...")

    names = [ws.title for ws in spreadsheet.worksheets()]
    if TAB_TASKS in names:
        ws = spreadsheet.worksheet(TAB_TASKS)
        ws.clear()
    else:
        ws = spreadsheet.add_worksheet(TAB_TASKS, rows=100, cols=len(TASK_HEADERS))

    # 헤더 입력
    ws.update(range_name="A1", values=[TASK_HEADERS])

    # 헤더 서식
    format_cell_range(ws, "A1:I1", _header_fmt())
    set_row_height(ws, "1", 36)

    # 데이터 영역 기본 서식
    format_cell_range(ws, "A2:I100", CellFormat(
        verticalAlignment="MIDDLE",
        wrapStrategy="WRAP",
    ))

    # 상태 열 가운데 정렬
    format_cell_range(ws, "C2:C100", CellFormat(
        horizontalAlignment="CENTER",
    ))

    # 번호 열 가운데 정렬
    format_cell_range(ws, "A2:A100", CellFormat(
        horizontalAlignment="CENTER",
    ))

    # 열 너비
    set_column_widths(ws, [
        ("A", 50),   # 번호
        ("B", 280),  # 주제
        ("C", 120),  # 상태
        ("D", 200),  # 제목
        ("E", 100),  # 장면수
        ("F", 150),  # 시작시간
        ("G", 150),  # 완료시간
        ("H", 250),  # 출력경로
        ("I", 200),  # 비고
    ])

    # 조건부 서식 (상태별 색상)
    rules = get_conditional_format_rules(ws)
    rules.clear()
    rules.extend(_task_status_rules(ws))
    rules.save()

    # 헤더 고정
    set_frozen(ws, rows=1)

    # 상태 열 드롭다운 (수동 입력용)
    rule = DataValidationRule(
        BooleanCondition("ONE_OF_LIST", ["대기", "진행중", "완료", "오류"]),
        showCustomUi=True,
    )
    set_data_validation_for_cell_range(ws, "C2:C100", rule)

    log.info("  [작업목록] 탭 완료")
    return ws


# ══════════════════════════════════════════════
# [대본] 탭
# ══════════════════════════════════════════════

def setup_script_tab(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    """[대본] 탭을 생성하고 서식을 적용합니다."""
    log.info("[대본] 탭 세팅 중...")

    names = [ws.title for ws in spreadsheet.worksheets()]
    if TAB_SCRIPT in names:
        ws = spreadsheet.worksheet(TAB_SCRIPT)
        ws.clear()
    else:
        ws = spreadsheet.add_worksheet(TAB_SCRIPT, rows=30, cols=len(SCRIPT_HEADERS))

    # 헤더 입력
    ws.update(range_name="A1", values=[SCRIPT_HEADERS])

    # 헤더 서식
    format_cell_range(ws, "A1:I1", _header_fmt())
    set_row_height(ws, "1", 36)

    # 데이터 영역 기본 서식
    format_cell_range(ws, "A2:I30", CellFormat(
        verticalAlignment="TOP",
        wrapStrategy="WRAP",
    ))

    # 번호 열 가운데 정렬
    format_cell_range(ws, "A2:B30", CellFormat(
        horizontalAlignment="CENTER",
    ))

    # 상태 열 가운데 정렬
    format_cell_range(ws, "H2:I30", CellFormat(
        horizontalAlignment="CENTER",
    ))

    # 열 너비
    set_column_widths(ws, [
        ("A", 70),   # 장면번호
        ("B", 60),   # 컷번호
        ("C", 250),  # 나레이션
        ("D", 250),  # 자막
        ("E", 350),  # 이미지 프롬프트
        ("F", 100),  # 효과음
        ("G", 100),  # 장면전환
        ("H", 80),   # 이미지 상태
        ("I", 80),   # 음성 상태
    ])

    # 상태 조건부 서식 (완료=녹색)
    sheet_id = ws.id
    for col_start, col_end in [(7, 8), (8, 9)]:  # H열, I열
        range_ref = GridRange(
            sheetId=sheet_id, startRowIndex=1, endRowIndex=30,
            startColumnIndex=col_start, endColumnIndex=col_end,
        )
        rules = get_conditional_format_rules(ws)
        rules.append(ConditionalFormatRule(
            ranges=[range_ref],
            booleanRule=BooleanRule(
                condition=BooleanCondition("TEXT_EQ", ["완료"]),
                format=CellFormat(backgroundColor=STATUS_DONE),
            ),
        ))
        rules.save()

    # 수정 가능 열 배경 강조 (나레이션, 자막, 이미지 프롬프트, 효과음, 장면전환)
    format_cell_range(ws, "C2:G30", CellFormat(
        backgroundColor=Color(1, 1, 0.95),  # 아주 연한 노랑 (편집 가능 영역)
    ))

    # 헤더 고정
    set_frozen(ws, rows=1)

    log.info("  [대본] 탭 완료")
    return ws


# ══════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════

def setup_all(reset: bool = False) -> None:
    """모든 시트를 세팅합니다."""
    log.info("Google Sheets 연결 중...")
    spreadsheet = _connect()
    log.info("  시트: %s", spreadsheet.title)

    if reset:
        log.info("기존 탭 초기화 (--reset)...")
        for tab in [TAB_SETTINGS, TAB_TASKS, TAB_SCRIPT]:
            names = [ws.title for ws in spreadsheet.worksheets()]
            if tab in names and len(names) > 1:
                spreadsheet.del_worksheet(spreadsheet.worksheet(tab))
                log.info("  [%s] 삭제", tab)

    setup_settings_tab(spreadsheet)
    setup_tasks_tab(spreadsheet)
    setup_script_tab(spreadsheet)
    _remove_default_sheet(spreadsheet)

    log.info("")
    log.info("=" * 50)
    log.info("  시트 세팅 완료!")
    log.info("")
    log.info("  다음 단계:")
    log.info("    1. [설정] 탭에서 '카테고리' 입력")
    log.info("    2. python main.py --login  (최초 로그인)")
    log.info("    3. python main.py          (자동 실행)")
    log.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Sheets 자동화 시트 초기 세팅")
    parser.add_argument("--reset", action="store_true", help="기존 탭 삭제 후 재생성")
    args = parser.parse_args()
    setup_all(reset=args.reset)
