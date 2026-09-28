#!/bin/bash
# AI 자막 삭제 프로그램 원클릭 실행 스크립트

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "      AI Video Subtitle Remover Studio 실행 중...         "
echo "=========================================================="

# 가상환경 확인
if [ ! -d ".venv" ]; then
    echo "가상환경을 구성하고 있습니다..."
    /Users/luhuji/.local/bin/uv venv --python 3.11 .venv
    /Users/luhuji/.local/bin/uv pip install --python .venv/bin/python fastapi "uvicorn[standard]" python-multipart opencv-python numpy pillow aiofiles tqdm jinja2
fi

echo "웹 스튜디오 서버를 시작합니다 (http://localhost:8000)"
echo "브라우저에서 접속하여 영상을 업로드하세요."
echo "종료하려면 Ctrl+C 를 누르세요."

# 브라우저 자동 열기 (Mac)
(sleep 1.5 && open "http://localhost:8000") &

# FastAPI 서버 실행
.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000
