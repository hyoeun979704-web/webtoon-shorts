"""프로젝트 설정 - OpenAI API + Google Sheets + 브라우저(CapCut) 기반"""

import os
from dotenv import load_dotenv

load_dotenv()

# Google Sheets
GOOGLE_SHEET_URL = os.getenv(
    "GOOGLE_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1-9j-AwBuDlCC3BjYWW6RTeMCtqG597NoszIFR_VPQnI/edit",
)

# OpenAI API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
DALLE_MODEL = os.getenv("DALLE_MODEL", "dall-e-3")

# 시스템 프롬프트 경로
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

# 브라우저 설정 (CapCut 편집용)
BROWSER_PROFILE_DIR = os.getenv("BROWSER_PROFILE_DIR", "./browser_data")
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "msedge")
HEADLESS = False
SLOW_MO = 500

# CapCut (capcut.com) 설정
CAPCUT_URL = "https://www.capcut.com"

# 영상 설정
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

# 출력 경로
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
