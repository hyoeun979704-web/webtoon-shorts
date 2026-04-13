@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ============================================
echo   Webtoon Shorts Auto Generator
echo ============================================
echo.

REM Install dependencies
pip install -q -r requirements.txt 2>nul

echo.
python main.py

if errorlevel 1 (
    echo.
    echo ============================================
    echo   ERROR - Check the log above
    echo ============================================
)

echo.
pause
