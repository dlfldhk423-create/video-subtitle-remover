@echo off
cd /d "%~dp0"

echo ==========================================================
echo      AI Video Subtitle Remover Studio Launcher
echo ==========================================================
echo.

:: 1. SubtitleRemover.exe가 있으면 직접 실행 (파이썬 설치 불필요!)
if exist "SubtitleRemover.exe" (
    echo Launching SubtitleRemover.exe...
    start "" "SubtitleRemover.exe"
    exit /b 0
)

if exist "dist\SubtitleRemover\SubtitleRemover.exe" (
    echo Launching SubtitleRemover.exe...
    start "" "dist\SubtitleRemover\SubtitleRemover.exe"
    exit /b 0
)

:: 2. 파이썬 환경으로 실행
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed.
    echo Please run SubtitleRemover.exe directly, or install Python from https://www.python.org/
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo Starting Web Studio (http://127.0.0.1:8000)...
python main.py
pause
