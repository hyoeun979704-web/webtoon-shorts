# 웹툰 숏폼 자동 생성기

각 서비스의 **Pro 구독**을 브라우저 자동화(Playwright)로 조작하여
25~40초 웹툰 스타일 숏폼 영상을 자동 생성합니다.

## 파이프라인

```
주제 입력 → [Claude 웹] 대본 → [ChatGPT DALL-E] 이미지 → [Typecast 웹] 음성 → [CapCut 웹] 영상
```

| 단계 | 서비스 | 구독 | 역할 |
|------|--------|------|------|
| 대본 | claude.ai | Pro | 장면별 나레이션, 이미지 프롬프트, 자막 생성 |
| 이미지 | chatgpt.com | Plus/Pro | DALL-E로 웹툰 스타일 세로형 이미지 생성 |
| 음성 | typecast.ai | Pro | 한국어 나레이션 음성 합성 |
| 편집 | capcut.com | Pro | 이미지+음성+자막 합성 → 최종 영상 내보내기 |

## 설치

```bash
# 1. 파이썬 패키지 설치
pip install -r requirements.txt

# 2. Playwright 브라우저 설치
playwright install chromium

# 3. 환경변수 설정 (선택)
cp .env.example .env
```

## 사용법

```bash
# 최초 1회: 각 서비스에 로그인 (브라우저가 열리면 직접 로그인)
python main.py "아무주제" --login

# 전체 자동 실행
python main.py "직장인의 월요일 아침"

# 대본만 먼저 확인
python main.py "고양이의 하루" --script-only

# 에셋만 생성 (CapCut 수동 편집)
python main.py "MBTI별 연애 스타일" --skip-edit

# 성우 지정
python main.py "편의점 알바 썰" --actor "차은우"
```

## 작동 방식

1. **세션 유지**: `browser_data/` 폴더에 로그인 세션이 저장됩니다. 최초 1회만 로그인하면 이후 자동 유지
2. **브라우저 자동화**: Playwright가 실제 브라우저를 열어 각 서비스의 웹 UI를 자동 조작
3. **API 불필요**: Pro 구독만 있으면 별도 API 키 없이 동작

## 출력 구조

```
output/project_YYYYMMDD_HHMMSS/
├── script.json              # 생성된 대본
├── images/
│   ├── scene_01.png         # 장면별 이미지
│   └── ...
├── voices/
│   ├── voice_01.wav         # 장면별 음성
│   └── ...
└── {제목}.mp4               # 최종 영상
```

## 주의사항

- `--login`으로 최초 1회 모든 서비스에 로그인 필수
- 브라우저 자동화 특성상 서비스 UI 변경 시 선택자(selector) 업데이트 필요
- `config.py`에서 `HEADLESS = False`로 설정하면 자동화 과정을 눈으로 확인 가능
- `SLOW_MO` 값을 높이면 더 안정적으로 동작 (기본 500ms)
