@echo off
cd /d "%~dp0"
echo ============================================
echo   웹툰 쇼츠 자동 생성기
echo ============================================
echo.
echo  [1] 로그인 + 작업 시작 (기본)
echo  [2] 로그인만 (계정 설정용)
echo.
set /p choice="선택 (Enter=1): "

if "%choice%"=="2" (
    python main.py --login
) else (
    python main.py
)

if errorlevel 1 (
    echo.
    echo ============================================
    echo   오류가 발생했습니다! 위 메시지를 확인하세요.
    echo ============================================
)

echo.
pause
