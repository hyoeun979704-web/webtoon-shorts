/**
 * 웹툰 숏폼 자동화 - Google Sheets 초기 세팅
 *
 * 타임아웃 방지를 위해 단계별 실행:
 *   1. step1_설정탭 실행
 *   2. step2_작업목록탭 실행
 *   3. step3_대본탭 실행
 */

function step1_설정탭() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('설정');
  if (!sheet) sheet = ss.insertSheet('설정');
  sheet.clear();

  var data = [
    ['항목', '값', '설명'],
    ['카테고리', '', '필수. 영상 주제 카테고리 (예: 연애, 직장, 가족, 공포, 먹방)'],
    ['키워드 개수', '5', '자동 발굴할 토픽 수 (기본: 5)'],
    ['이미지 스타일', 'webtoon style, manhwa art, digital illustration', 'DALL-E 프롬프트에 포함할 스타일 키워드'],
    ['장면 수', '6', '영상 구성 장면 수 (기본: 5)'],
    ['장면당 컷 수', '3~4', '장면당 이미지 수 범위 (기본: 3~4)'],
    ['총 이미지 수', '15~20', '전체 이미지 수 범위 (기본: 15~20)'],
    ['목표 길이(초)', '30', '완성 영상 목표 길이 (기본: 30)'],
    ['대본 검토', 'Y', 'Y=대본 생성 후 시트에서 수정 가능, N=바로 진행'],
  ];
  sheet.getRange(1, 1, data.length, 3).setValues(data);
  sheet.getRange('A1:C1').setBackground('#292833').setFontColor('#ffffff').setFontWeight('bold');
  sheet.setColumnWidth(1, 180);
  sheet.setColumnWidth(2, 350);
  sheet.setColumnWidth(3, 380);
  sheet.setFrozenRows(1);

  SpreadsheetApp.getUi().alert('1단계 완료! 다음: step2_작업목록탭 실행');
}

function step2_작업목록탭() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('작업목록');
  if (!sheet) sheet = ss.insertSheet('작업목록');
  sheet.clear();

  var headers = ['번호', '주제', '상태', '제목', '장면수', '시작시간', '완료시간', '출력경로', '비고'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setBackground('#292833').setFontColor('#ffffff').setFontWeight('bold');
  var widths = [50, 280, 120, 200, 100, 150, 150, 250, 200];
  for (var i = 0; i < widths.length; i++) {
    sheet.setColumnWidth(i + 1, widths[i]);
  }
  sheet.setFrozenRows(1);

  SpreadsheetApp.getUi().alert('2단계 완료! 다음: step3_대본탭 실행');
}

function step3_대본탭() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('대본');
  if (!sheet) sheet = ss.insertSheet('대본');
  sheet.clear();

  var headers = ['장면번호', '컷번호', '나레이션', '자막', '이미지 프롬프트', '효과음', '장면전환', '이미지 상태', '음성 상태'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setBackground('#292833').setFontColor('#ffffff').setFontWeight('bold');
  var widths = [70, 60, 250, 250, 350, 100, 100, 80, 80];
  for (var i = 0; i < widths.length; i++) {
    sheet.setColumnWidth(i + 1, widths[i]);
  }
  sheet.setFrozenRows(1);

  // 기본 시트 삭제
  var sheet1 = ss.getSheetByName('Sheet1') || ss.getSheetByName('시트1');
  if (sheet1 && ss.getSheets().length > 1) {
    try { ss.deleteSheet(sheet1); } catch(e) {}
  }

  SpreadsheetApp.getUi().alert(
    '세팅 완료!\n\n' +
    '다음 단계:\n' +
    '1. [설정] 탭에서 카테고리 입력\n' +
    '2. .env 파일에 OPENAI_API_KEY 설정\n' +
    '3. python main.py (자동 실행)'
  );
}
