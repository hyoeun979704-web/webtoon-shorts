# 웹툰 숏폼 자동 생성기

**Google Sheets**를 컨트롤 패널로, 각 서비스의 **Pro 구독 + 프로젝트** 기능을 브라우저 자동화로 조작하여
25~40초 웹툰 스타일 숏폼 영상을 자동 생성합니다.

## 파이프라인

```
[시트] 카테고리 설정
     ↓
[Claude 프로젝트] 토픽 키워드 발굴 → [시트] 작업목록에 자동 추가
     ↓
[Claude 프로젝트] 대본 생성 → [시트] 대본 탭에서 확인/수정
     ↓
[ChatGPT 프로젝트] DALL-E 이미지 생성 (장면별 실시간 상태)
     ↓
[Typecast 웹] 음성 합성 (장면별 실시간 상태)
     ↓
[CapCut 웹] 영상 편집 → 최종 출력
```

## Google Sheets 구조

### [설정] 탭
| 항목 | 값 | 설명 |
|------|------|------|
| **카테고리** | 직장인 공감 | 토픽 키워드 발굴 대상 카테고리 |
| **키워드 개수** | 5 | 한 번에 발굴할 토픽 수 |
| **Claude 프로젝트 URL** | https://claude.ai/project/xxx | 대본 생성용 프로젝트 (시스템 프롬프트 적용) |
| **ChatGPT 프로젝트 URL** | https://chatgpt.com/g/g-xxx | 이미지 생성용 GPT/프로젝트 (스타일 지침 적용) |
| 성우 이름 | | Typecast 성우 |
| 이미지 스타일 | webtoon style, manhwa art... | DALL-E 프롬프트에 추가 |
| 장면 수 | 5 | 장면 개수 |
| 편집 모드 | capcut | capcut / skip |
| 자동 대본 승인 | N | Y면 대본 수정 없이 바로 진행 |

### [작업목록] 탭
| 번호 | 주제 | 상태 | 제목 | 장면수 | 시작시간 | 완료시간 | 출력경로 | 비고 |
|------|------|------|------|--------|----------|----------|----------|------|
| 1 | 월요일 아침 지각 위기 | 대기 | | | | | | 출근길 공감 필수 |

→ `--keywords`로 자동 생성되거나 직접 입력

### [대본] 탭
→ 대본 생성 후 자동 기록. 나레이션/이미지 프롬프트를 수정 후 Enter로 진행

## 설치

```bash
pip install -r requirements.txt
playwright install chromium

# Google OAuth 설정
# 1. Google Cloud Console → OAuth 2.0 클라이언트 ID 생성 (데스크톱 앱)
# 2. credentials.json 다운로드 → 프로젝트 루트에 배치
```

## 사용법

```bash
# 1) 시트 초기 세팅
python main.py --init

# 2) 시트 [설정] 탭에 입력:
#    - 카테고리: "직장인 공감"
#    - Claude 프로젝트 URL: (Claude에서 만든 프로젝트 URL)
#    - ChatGPT 프로젝트 URL: (ChatGPT에서 만든 GPT/프로젝트 URL)
#    - 성우 이름, 이미지 스타일 등

# 3) 서비스 로그인 (최초 1회)
python main.py --login

# 4) 카테고리 기반 토픽 키워드 자동 발굴
python main.py --keywords
# → 시트 [작업목록]에 자동 추가됨. 확인 후 불필요한 항목 삭제

# 5) 영상 자동 생성 (대기 작업 처리)
python main.py

# 6) 키워드 발굴 + 바로 영상 생성 (한 번에)
python main.py --keywords-and-run
```

## Claude/ChatGPT 프로젝트 활용

### Claude 프로젝트 설정 예시
Claude 프로젝트에 시스템 프롬프트를 설정하면 대본 품질이 향상됩니다:
- 웹툰 장르 가이드 (로맨스, 공감, 개그 등)
- 캐릭터 페르소나 설정
- 참고 대본 예시를 knowledge에 업로드

### ChatGPT GPT 설정 예시
커스텀 GPT에 이미지 스타일을 지정하면 일관된 이미지가 생성됩니다:
- 특정 웹툰 화풍 지침
- 색감, 선 굵기, 음영 스타일
- 캐릭터 디자인 레퍼런스를 knowledge에 업로드
