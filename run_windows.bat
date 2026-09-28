@echo off
chcp 65001 > nul
setlocal

echo ==========================================================
echo      🎬 AI Video Subtitle Remover Studio 실행 중...
echo ==========================================================
echo.

:: 가상환경 확인 및 생성
if not exist ".venv" (
    echo 가상환경을 구성하고 있습니다...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo 필수 라이브러리를 설치합니다...
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo 웹 스튜디오 서버를 시작합니다 (http://127.0.0.1:8000)...
python main.py

pause
