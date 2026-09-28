#!/bin/bash
# AI Video Subtitle Remover - 온라인 공유 실행기

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "    🌐 AI Video Subtitle Remover - 온라인 라이브 호스팅   "
echo "=========================================================="

# 백엔드 서버 확인 및 실행
if ! curl -s http://127.0.0.1:8000/ > /dev/null; then
    echo "로컬 서버를 시작합니다..."
    .venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000 &
    sleep 2
fi

echo "공개 온라인 접속 URL(Cloudflare Tunnel)을 생성합니다..."
cloudflared tunnel --url http://127.0.0.1:8000
