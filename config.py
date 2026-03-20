"""프로젝트 설정 - 브라우저 자동화 + Google Sheets 기반"""

import os
from dotenv import load_dotenv

load_dotenv()

# Google Sheets
GOOGLE_SHEET_URL = os.getenv(
    "GOOGLE_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1-9j-AwBuDlCC3BjYWW6RTeMCtqG597NoszIFR_VPQnI/edit",
)

# 브라우저 설정
BROWSER_PROFILE_DIR = os.getenv("BROWSER_PROFILE_DIR", "./browser_data")
HEADLESS = False  # 자동화 과정을 눈으로 확인하려면 False
SLOW_MO = 500     # 밀리초 단위 딜레이 (안정성용, 0이면 최대 속도)

# Claude (claude.ai) 설정
CLAUDE_URL = "https://claude.ai"

# ChatGPT (chatgpt.com) 설정 - DALL-E 이미지 생성용
CHATGPT_URL = "https://chatgpt.com"

# CapCut (capcut.com) 설정
CAPCUT_URL = "https://www.capcut.com"

# 영상 설정
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

# 출력 경로
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
