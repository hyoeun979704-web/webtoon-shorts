# 웹툰 숏폼 자동 생성기

**OpenAI API**와 **Google Sheets**를 사용해 웹툰 숏폼 영상 에셋(대본 + 이미지)을
자동 생성합니다. 브라우저 자동화 없이 API만 사용합니다.

## 파이프라인

```
[시트] 카테고리 설정
     ↓
[OpenAI API] 토픽 키워드 발굴 → [시트] 작업목록에 자동 추가
     ↓
[OpenAI API] 대본 생성 → [시트] 대본 탭에서 확인/수정 ← 검토 포인트
     ↓
[OpenAI API] 대본 구조화 (장면/컷/이미지 프롬프트)
     ↓
[DALL-E API] 이미지 생성 (컷별)
     ↓
output/project_YYYYMMDD_HHMMSS/
  ├── script.txt       # 대본
  └── images/          # 컷별 이미지 (PNG)
```

생성된 이미지/대본을 CapCut 등 원하는 편집 도구에서 수동으로 영상을 만드세요.

## 설치

```bash
pip install -r requirements.txt
```

### API 키 설정
1. `.env.example`을 복사해서 `.env`로 이름 변경
2. `.env`에 OpenAI API 키 입력:
   ```
   OPENAI_API_KEY=sk-...
   ```

### Google Sheets 인증
서비스 계정 방식(권장):
1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성
2. **Google Sheets API**, **Google Drive API** 활성화
3. 서비스 계정 생성 → JSON 키 다운로드
4. 파일을 `service_account.json`으로 이름 변경 후 프로젝트 루트에 배치
5. 사용할 Google Sheet를 서비스 계정 이메일(`xxx@xxx.iam.gserviceaccount.com`)에 **편집자**로 공유

## 사용법

```bash
# 0) 시트 초기 세팅 (최초 1회)
python setup_sheet.py
# 또는 Apps Script: setup_sheet.gs 내용을 시트 Apps Script에 붙여넣고 실행

# 1) 시트 [설정] 탭에 필수 항목 입력:
#    - 카테고리: "직장인 공감" (필수)

# 2) 실행
python main.py
# Windows: run.bat 더블클릭
```

`python main.py`로 다음이 자동 실행됩니다:
1. 시트 탭/헤더 자동 초기화 (없으면 생성)
2. 대기 작업 없으면 → 키워드 자동 발굴 → 작업목록 추가
3. 대본 생성 → **대본 검토 (시트에서 수정 후 Enter)**
4. 대본 구조화 (장면/컷/이미지 프롬프트 생성)
5. 이미지 생성 (DALL-E, 컷별 PNG 저장)

## Google Sheets 구조

### [설정] 탭
| 항목 | 값 | 설명 |
|------|------|------|
| **카테고리** | 직장인 공감 | 필수. 토픽 발굴 대상 카테고리 |
| 키워드 개수 | 5 | 한 번에 발굴할 토픽 수 |
| 이미지 스타일 | webtoon style, manhwa art, digital illustration | DALL-E 프롬프트에 추가 |
| 장면 수 | 6 | 장면 개수 |
| 장면당 컷 수 | 3~4 | 장면당 이미지 수 |
| 총 이미지 수 | 15~20 | 전체 이미지 수 |
| 목표 길이(초) | 30 | 완성 영상 목표 길이 |
| 대본 검토 | Y | Y면 대본 생성 후 시트에서 수정 가능 |

### [작업목록] 탭
| 번호 | 주제 | 상태 | 제목 | 장면수 | 시작시간 | 완료시간 | 출력경로 | 비고 |
|------|------|------|------|--------|----------|----------|----------|------|

- 상태 `대기`: 1단계(대본 생성)부터 실행
- 상태 `대본완료`: [대본] 탭의 내용을 사용해 이미지 생성부터 실행

### [대본] 탭
| 장면번호 | 컷번호 | 나레이션 | 자막 | 이미지 프롬프트 | 효과음 | 장면전환 | 이미지 상태 | 음성 상태 |
|----------|--------|----------|------|----------------|--------|----------|------------|----------|

## 프로젝트 구조

```
├── main.py              # 메인 파이프라인 오케스트레이터
├── setup_sheet.py       # Google Sheets 초기 세팅 (Python)
├── setup_sheet.gs       # Google Sheets 초기 세팅 (Apps Script)
├── config.py            # 설정 (API 키, 경로 등)
├── utils.py             # 로깅 유틸
├── openai_client.py     # OpenAI API 래퍼 (chat, DALL-E)
├── sheet_manager.py     # Google Sheets CRUD
├── keyword_generator.py # 키워드 발굴
├── script_generator.py  # 대본 생성 + 구조화
├── image_generator.py   # DALL-E 이미지 생성
├── prompts/             # 시스템 프롬프트 (keyword, script, structure)
├── requirements.txt     # Python 의존성
└── .env.example         # 환경변수 예시
```

## 시스템 프롬프트 커스터마이징

`prompts/` 폴더의 텍스트 파일을 수정해 생성 스타일을 조정할 수 있습니다:
- `prompts/keyword.txt` - 키워드 발굴 지침
- `prompts/script.txt` - 대본 작성 지침
- `prompts/structure.txt` - 장면/컷 구조화 지침
