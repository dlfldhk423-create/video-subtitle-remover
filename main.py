"""
Subtitle Remover AI - Windows EXE Main Launcher
더블클릭 시 Uvicorn 웹 서버를 가동하고 웹 브라우저를 자동으로 엽니다.
"""

import sys
import os
import time
import webbrowser
import threading
import uvicorn

# 멀티프로세싱 freeze 지원
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()

    print("=" * 60)
    print("      🎬 AI Video Subtitle Remover Studio 실행 중...      ")
    print("=" * 60)
    print("서버가 시작되었습니다. 잠시 후 웹 브라우저가 자동으로 열립니다.")
    print("접속 주소: http://127.0.0.1:8000")
    print("프로그램을 종료하려면 이 창을 닫거나 Ctrl+C를 누르세요.")
    print("=" * 60)

    # 1.5초 후 브라우저 자동 오픈
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:8000")

    threading.Thread(target=open_browser, daemon=True).start()

    # FastAPI 서버 구동
    from app import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
