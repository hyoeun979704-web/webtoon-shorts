# 웹툰 숏폼 자동 생성기

웹툰 스타일의 25~40초 숏폼 영상을 자동으로 생성하는 파이프라인입니다.

## 파이프라인

```
주제 입력 → [Claude] 대본 생성 → [DALL-E] 이미지 생성 → [Typecast] 음성 생성 → [FFmpeg/CapCut] 영상 편집
```

| 단계 | 도구 | 설명 |
|------|------|------|
| 대본 | Claude API | 장면별 나레이션, 이미지 프롬프트, 자막 생성 |
| 이미지 | OpenAI DALL-E 3 | 웹툰 스타일 세로형(9:16) 이미지 생성 |
| 음성 | Typecast API | 한국어 나레이션 음성 합성 |
| 편집 | FFmpeg / CapCut | 이미지+음성+자막 합성 → 최종 영상 |

## 설치

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. FFmpeg 설치 (자동 편집 사용시)
# Ubuntu/Debian
sudo apt install ffmpeg
# macOS
brew install ffmpeg

# 3. 환경변수 설정
cp .env.example .env
# .env 파일에 API 키를 입력하세요
```

## 사용법

```bash
# 기본: FFmpeg로 자동 영상 생성
python main.py "직장인의 월요일 아침"

# CapCut 에셋만 내보내기 (수동 편집용)
python main.py "고양이의 하루" --capcut-only

# FFmpeg 영상 + CapCut 에셋 모두 생성
python main.py "MBTI별 연애 스타일" --capcut

# 대본만 먼저 확인
python main.py "편의점 알바 썰" --script-only

# Typecast 성우 지정
python main.py "직장인의 월요일 아침" --actor-id "your_actor_id"
```

## 출력 구조

```
output/project_YYYYMMDD_HHMMSS/
├── script.json              # 생성된 대본
├── images/
│   ├── scene_01.png         # 장면별 이미지
│   ├── scene_02.png
│   └── ...
├── voices/
│   ├── voice_01.wav         # 장면별 음성
│   ├── voice_02.wav
│   └── ...
├── {제목}.mp4               # 최종 영상 (FFmpeg 모드)
└── capcut_assets/           # CapCut 에셋 (--capcut 옵션)
    └── editing_guide.json   # 편집 가이드
```

## API 키 발급

- **Claude API**: https://console.anthropic.com/
- **OpenAI API**: https://platform.openai.com/
- **Typecast API**: https://typecast.ai/ (대시보드에서 API 토큰 발급)

## 설정 커스터마이징

`config.py`에서 조정 가능한 설정:

- `CLAUDE_MODEL`: 사용할 Claude 모델
- `MAX_SCENES`: 최대 장면 수
- `DALLE_MODEL`: DALL-E 모델 버전
- `IMAGE_SIZE`: 이미지 크기
- `VIDEO_WIDTH/HEIGHT`: 영상 해상도
- `VIDEO_FPS`: 프레임 레이트
