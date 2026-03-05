#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

cleanup() {
    echo ""
    echo "종료 중..."
    kill $FLASK_PID $CLOUDFLARED_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

# Flask 서버 시작
echo "Flask 서버 시작 중 (port 5001)..."
nohup python3 app.py > app.log 2>&1 &
FLASK_PID=$!

# Flask가 뜰 때까지 잠시 대기
sleep 2

# cloudflared 터널 시작
echo "cloudflared 터널 시작 중..."
cloudflared tunnel --protocol http2 --url http://localhost:5001 &
CLOUDFLARED_PID=$!

echo ""
echo "실행 중 (Ctrl+C로 종료)"
echo "  Flask PID: $FLASK_PID"
echo "  cloudflared PID: $CLOUDFLARED_PID"
echo ""
echo "위 로그에서 'trycloudflare.com' URL을 확인하여 LINE Webhook에 등록하세요."

wait
