"""프로젝트 설정 - 브라우저 자동화 기반"""

import os
from dotenv import load_dotenv

load_dotenv()

# 브라우저 설정
BROWSER_PROFILE_DIR = os.getenv("BROWSER_PROFILE_DIR", "./browser_data")
HEADLESS = False  # 자동화 과정을 눈으로 확인하려면 False
SLOW_MO = 500     # 밀리초 단위 딜레이 (안정성용, 0이면 최대 속도)

# Claude (claude.ai) 설정
CLAUDE_URL = "https://claude.ai"
MAX_SCENES = 6

# ChatGPT (chatgpt.com) 설정 - DALL-E 이미지 생성용
CHATGPT_URL = "https://chatgpt.com"
IMAGE_STYLE = "webtoon style, manhwa art, digital illustration"

# Typecast (typecast.ai) 설정
TYPECAST_URL = "https://typecast.ai"
TYPECAST_ACTOR_NAME = os.getenv("TYPECAST_ACTOR_NAME", "")

# CapCut (capcut.com) 설정
CAPCUT_URL = "https://www.capcut.com"

# 영상 설정
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
TARGET_DURATION_SEC = 30  # 목표 25~40초

# 출력 경로
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
