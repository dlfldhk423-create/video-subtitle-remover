@echo off
chcp 65001 > nul
setlocal

echo ==========================================================
echo    🎬 Subtitle Remover AI - Windows EXE 빌드 스크립트
echo ==========================================================
echo.

:: 1. 파이썬 확인
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Python이 설치되어 있지 않거나 환경변수 PATH에 등록되지 않았습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.10 또는 3.11을 설치해주세요.
    echo (설치 시 "Add Python to PATH" 체크 필수)
    pause
    exit /b 1
)

:: 2. 필수 패키지 설치
echo [1/3] 필수 패키지 및 PyInstaller 설치 중...
pip install -r requirements.txt pyinstaller

:: 3. ffmpeg.exe 확인 및 자동 다운로드
if not exist "ffmpeg.exe" (
    echo [2/3] Windows용 ffmpeg.exe 다운로드 중...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile 'ffmpeg.zip'"
    if exist "ffmpeg.zip" (
        echo ffmpeg.exe 압축 해제 중...
        powershell -Command "Expand-Archive -Path 'ffmpeg.zip' -DestinationPath 'temp_ffmpeg' -Force"
        for /r "temp_ffmpeg" %%f in (ffmpeg.exe) do copy "%%f" "ffmpeg.exe" > nul
        rmdir /s /q "temp_ffmpeg" > nul 2>&1
        del "ffmpeg.zip" > nul 2>&1
    )
)

if not exist "ffmpeg.exe" (
    echo [알림] ffmpeg.exe 자동 다운로드 실패. 시스템 PATH에 ffmpeg이 등록되어 있는지 확인해주세요.
) else (
    echo ffmpeg.exe 준비 완료!
)

:: 4. PyInstaller 빌드 실행
echo [3/3] SubtitleRemover.exe 빌드 시작...
pyinstaller --clean SubtitleRemover.spec

echo.
echo ==========================================================
if exist "dist\SubtitleRemover\SubtitleRemover.exe" (
    echo 🎉 빌드가 성공적으로 완료되었습니다!
    echo.
    echo 실행 파일 경로: dist\SubtitleRemover\SubtitleRemover.exe
    echo dist\SubtitleRemover 폴더 전체를 압축하여 다른 사람에게 전달하시면 됩니다.
) else (
    echo [오류] 빌드에 실패했습니다. 위의 로그를 확인해주세요.
)
echo ==========================================================
echo.
pause
