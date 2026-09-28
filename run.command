#!/bin/bash
# Mac 전용 원클릭 더블클릭 실행기
# 이 파일을 마우스로 더블클릭하면 자동으로 터미널이 열리며 실행됩니다.

cd "$(dirname "$0")"

echo "=========================================================="
echo "    🎬 AI Video Subtitle Remover Studio 실행 중...        "
echo "=========================================================="

# 가상환경 확인
if [ ! -d ".venv" ]; then
    echo "가상환경을 구성하고 있습니다 (최초 1회 약 10초 소요)..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo "웹 스튜디오를 실행합니다. 잠시 후 브라우저가 열립니다..."
(sleep 1.5 && open "http://127.0.0.1:8000") &

python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
