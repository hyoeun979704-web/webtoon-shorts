"""프로젝트 설정"""

import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TYPECAST_API_TOKEN = os.getenv("TYPECAST_API_TOKEN")

# Claude 대본 설정
CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_SCENES = 6  # 25~40초 분량에 적합한 장면 수
TARGET_DURATION_SEC = 30  # 목표 영상 길이(초)

# DALL-E 이미지 설정
DALLE_MODEL = "dall-e-3"
IMAGE_SIZE = "1024x1792"  # 세로형 (9:16 비율에 가까운 옵션)
IMAGE_QUALITY = "standard"

# Typecast 음성 설정
TYPECAST_API_URL = "https://typecast.ai/api/speak"
TYPECAST_ACTOR_ID = ""  # Typecast에서 원하는 성우 ID 설정

# 영상 설정
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
SCENE_DURATION_SEC = 5  # 장면당 기본 표시 시간(초), 음성 길이에 맞춰 조정됨

# 출력 경로
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
