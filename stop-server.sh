#!/bin/bash
# サーバーの再起動ループを停止してプロセスを終了する

cd "$(dirname "$0")"

PID_FILE=".server.pid"
STOP_FILE=".server.stop"

touch "$STOP_FILE"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "サーバーを停止します (PID: $PID)..."
        kill "$PID" 2>/dev/null
        wait "$PID" 2>/dev/null
    fi
    rm -f "$PID_FILE"
fi

echo "停止完了"
