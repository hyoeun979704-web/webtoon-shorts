@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ============================================
echo   Webtoon Shorts Auto Generator
echo ============================================
echo.
echo  [1] Start (Run)
echo  [2] Login only
echo.
set /p choice="Select (Enter=1): "

if "%choice%"=="2" (
    python main.py --login
) else (
    python main.py
)

if errorlevel 1 (
    echo.
    echo ============================================
    echo   ERROR - Check the log above
    echo ============================================
)

echo.
pause
