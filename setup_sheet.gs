/**
 * 웹툰 숏폼 자동화 - Google Sheets 초기 세팅
 *
 * 사용법:
 *   1. Google Sheets에서 [확장 프로그램] → [Apps Script] 열기
 *   2. 이 코드를 전체 복사하여 붙여넣기
 *   3. ▶ 실행 버튼 클릭 (함수: setupAll)
 *   4. 권한 승인 후 자동 세팅 완료
 */

function setupAll() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  setupSettingsTab(ss);
  setupTasksTab(ss);
  setupScriptTab(ss);
  removeDefaultSheet(ss);

  SpreadsheetApp.getUi().alert(
    '세팅 완료!\n\n' +
    '다음 단계:\n' +
    '1. [설정] 탭에서 카테고리, 성우 이름 입력\n' +
    '2. python main.py --login (서비스 로그인)\n' +
    '3. python main.py (자동 실행)'
  );
}

// ════════════════════════════════════════
// [설정] 탭
// ════════════════════════════════════════

function setupSettingsTab(ss) {
  var sheet = getOrCreateSheet(ss, '설정', 20, 3);
  sheet.clear();

  // 데이터
  var data = [
    ['항목', '값', '설명'],
    ['카테고리', '', '필수. 영상 주제 카테고리 (예: 연애, 직장, 가족, 공포, 먹방)'],
    ['키워드 개수', '5', '자동 발굴할 토픽 수 (기본: 5)'],
    ['Claude 프로젝트 URL', '', 'Claude 프로젝트 URL (있으면 프로젝트 컨텍스트 활용)'],
    ['ChatGPT 프로젝트 URL', '', 'ChatGPT 프로젝트 URL (있으면 프로젝트 컨텍스트 활용)'],
    ['성우 이름', '', '필수. Typecast 성우 이름 (예: 지수, 민준, 하은)'],
    ['이미지 스타일', 'webtoon style, manhwa art, digital illustration', 'DALL-E 프롬프트에 포함할 스타일 키워드'],
    ['장면 수', '5', '영상 구성 장면 수 (기본: 5)'],
    ['장면당 컷 수', '3~4', '장면당 이미지 수 범위 (기본: 3~4)'],
    ['총 이미지 수', '15~20', '전체 이미지 수 범위 (기본: 15~20)'],
    ['목표 길이(초)', '30', '완성 영상 목표 길이 (기본: 30)'],
    ['편집 모드', 'capcut', 'capcut=CapCut 자동편집, skip=에셋만 생성'],
    ['대본 검토', 'Y', 'Y=대본 생성 후 시트에서 수정 가능, N=바로 진행'],
    ['편집 검토', 'Y', 'Y=CapCut 배치 후 수동 확인, N=바로 내보내기'],
  ];
  sheet.getRange(1, 1, data.length, 3).setValues(data);

  // 헤더 서식
  var headerRange = sheet.getRange('A1:C1');
  headerRange.setBackground('#292833')
             .setFontColor('#ffffff')
             .setFontWeight('bold')
             .setFontSize(10)
             .setHorizontalAlignment('center')
             .setVerticalAlignment('middle');
  sheet.setRowHeight(1, 36);

  // 항목명 열 (A열)
  var lastRow = data.length;
  sheet.getRange(2, 1, lastRow - 1, 1)
       .setBackground('#EDEDF7')
       .setFontWeight('bold')
       .setFontSize(10)
       .setVerticalAlignment('middle');

  // 필수 항목 강조 (카테고리=행2, 성우 이름=행6)
  sheet.getRange('B2').setBackground('#FFF2E6');  // 카테고리
  sheet.getRange('B6').setBackground('#FFF2E6');  // 성우 이름

  // 설명 열 서식
  sheet.getRange(2, 3, lastRow - 1, 1)
       .setFontColor('#808080')
       .setFontSize(9)
       .setFontStyle('italic');

  // 드롭다운 유효성 검사
  var dropdowns = {
    3: ['3', '5', '7', '10'],         // 키워드 개수 (행3)
    8: ['3', '4', '5', '6', '7'],     // 장면 수 (행8)
    12: ['capcut', 'skip'],            // 편집 모드 (행12)
    13: ['Y', 'N'],                    // 대본 검토 (행13)
    14: ['Y', 'N'],                    // 편집 검토 (행14)
  };
  for (var row in dropdowns) {
    var rule = SpreadsheetApp.newDataValidation()
      .requireValueInList(dropdowns[row], true)
      .build();
    sheet.getRange(parseInt(row), 2).setDataValidation(rule);
  }

  // 열 너비
  sheet.setColumnWidth(1, 180);
  sheet.setColumnWidth(2, 350);
  sheet.setColumnWidth(3, 380);

  // 헤더 고정
  sheet.setFrozenRows(1);
}

// ════════════════════════════════════════
// [작업목록] 탭
// ════════════════════════════════════════

function setupTasksTab(ss) {
  var headers = ['번호', '주제', '상태', '제목', '장면수', '시작시간', '완료시간', '출력경로', '비고'];
  var sheet = getOrCreateSheet(ss, '작업목록', 100, headers.length);
  sheet.clear();

  // 헤더
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  var headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setBackground('#292833')
             .setFontColor('#ffffff')
             .setFontWeight('bold')
             .setFontSize(10)
             .setHorizontalAlignment('center')
             .setVerticalAlignment('middle');
  sheet.setRowHeight(1, 36);

  // 데이터 영역 서식
  sheet.getRange('A2:I100')
       .setVerticalAlignment('middle')
       .setWrapStrategy(SpreadsheetApp.WrapStrategy.WRAP);
  sheet.getRange('A2:A100').setHorizontalAlignment('center');
  sheet.getRange('C2:C100').setHorizontalAlignment('center');

  // 열 너비
  var widths = [50, 280, 120, 200, 100, 150, 150, 250, 200];
  for (var i = 0; i < widths.length; i++) {
    sheet.setColumnWidth(i + 1, widths[i]);
  }

  // 상태 열 드롭다운
  var statusRule = SpreadsheetApp.newDataValidation()
    .requireValueInList(['대기', '진행중', '완료', '오류'], true)
    .build();
  sheet.getRange('C2:C100').setDataValidation(statusRule);

  // 조건부 서식 (상태별 행 배경색)
  var statusColors = [
    { text: '대기',   color: '#D9EBFF' },
    { text: '진행중', color: '#FFF5CC' },
    { text: '완료',   color: '#D9FFD9' },
    { text: '오류',   color: '#FFD9D9' },
    { text: '1/4',    color: '#FFF5CC' },
    { text: '2/4',    color: '#FFF5CC' },
    { text: '3/4',    color: '#FFF5CC' },
    { text: '4/4',    color: '#FFF5CC' },
    { text: '검토',   color: '#F2E6FF' },
  ];

  var range = sheet.getRange('A2:I100');
  var rules = sheet.getConditionalFormatRules();
  statusColors.forEach(function(s) {
    var rule = SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied('=SEARCH("' + s.text + '",$C2)')
      .setBackground(s.color)
      .setRanges([range])
      .build();
    rules.push(rule);
  });
  sheet.setConditionalFormatRules(rules);

  // 헤더 고정
  sheet.setFrozenRows(1);
}

// ════════════════════════════════════════
// [대본] 탭
// ════════════════════════════════════════

function setupScriptTab(ss) {
  var headers = ['장면번호', '컷번호', '나레이션', '자막', '이미지 프롬프트', '효과음', '장면전환', '이미지 상태', '음성 상태'];
  var sheet = getOrCreateSheet(ss, '대본', 30, headers.length);
  sheet.clear();

  // 헤더
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  var headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setBackground('#292833')
             .setFontColor('#ffffff')
             .setFontWeight('bold')
             .setFontSize(10)
             .setHorizontalAlignment('center')
             .setVerticalAlignment('middle');
  sheet.setRowHeight(1, 36);

  // 데이터 영역 서식
  sheet.getRange('A2:I30')
       .setVerticalAlignment('top')
       .setWrapStrategy(SpreadsheetApp.WrapStrategy.WRAP);
  sheet.getRange('A2:B30').setHorizontalAlignment('center');
  sheet.getRange('H2:I30').setHorizontalAlignment('center');

  // 수정 가능 영역 배경 (나레이션 ~ 장면전환: C~G열)
  sheet.getRange('C2:G30').setBackground('#FFFFF2');

  // 열 너비
  var widths = [70, 60, 250, 250, 350, 100, 100, 80, 80];
  for (var i = 0; i < widths.length; i++) {
    sheet.setColumnWidth(i + 1, widths[i]);
  }

  // 조건부 서식: 상태 "완료" → 녹색
  var scriptRules = sheet.getConditionalFormatRules();
  ['H2:H30', 'I2:I30'].forEach(function(rangeStr) {
    var r = sheet.getRange(rangeStr);
    var rule = SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo('완료')
      .setBackground('#D9FFD9')
      .setRanges([r])
      .build();
    scriptRules.push(rule);
  });
  sheet.setConditionalFormatRules(scriptRules);

  // 헤더 고정
  sheet.setFrozenRows(1);
}

// ════════════════════════════════════════
// 유틸리티
// ════════════════════════════════════════

function getOrCreateSheet(ss, name, rows, cols) {
  var sheet = ss.getSheetByName(name);
  if (sheet) return sheet;
  return ss.insertSheet(name, ss.getSheets().length, { template: null });
}

function removeDefaultSheet(ss) {
  var sheet1 = ss.getSheetByName('Sheet1') || ss.getSheetByName('시트1');
  if (sheet1 && ss.getSheets().length > 1) {
    try { ss.deleteSheet(sheet1); } catch(e) {}
  }
}
