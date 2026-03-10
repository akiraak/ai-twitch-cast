#!/bin/bash
# .envからWEB_PORTを読み込んでuvicornを起動する
# コミット時に .git/hooks/post-commit が SIGTERM → 自動再起動

cd "$(dirname "$0")"

# .envからWEB_PORT読み込み（デフォルト: 8080）
if [ -f .env ]; then
    WEB_PORT=$(grep -E '^WEB_PORT=' .env | cut -d= -f2)
fi
WEB_PORT="${WEB_PORT:-8080}"

PID_FILE=".server.pid"

cleanup() {
    echo "サーバーを停止します..."
    if [ -f "$PID_FILE" ]; then
        kill "$(cat "$PID_FILE")" 2>/dev/null
        rm -f "$PID_FILE"
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "Starting server on port $WEB_PORT..."

while true; do
    uvicorn scripts.web:app --host 0.0.0.0 --port "$WEB_PORT" &
    PID=$!
    echo $PID > "$PID_FILE"
    echo "サーバー起動 (PID: $PID)"
    wait $PID
    EXIT_CODE=$?
    echo "サーバー終了 (code: $EXIT_CODE)、1秒後に再起動..."
    sleep 1
done
