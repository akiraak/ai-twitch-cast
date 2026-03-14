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
STOP_FLAG=""

# 既存プロセスが動いていたら停止する（二重起動防止）
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "既存サーバーを停止します (PID: $OLD_PID)..."
        # whileループの親プロセスも停止
        PARENT_PID=$(ps -o ppid= -p "$OLD_PID" 2>/dev/null | tr -d ' ')
        if [ -n "$PARENT_PID" ] && [ "$PARENT_PID" != "1" ] && [ "$PARENT_PID" != "$$" ]; then
            kill -9 "$PARENT_PID" 2>/dev/null
        fi
        kill -9 "$OLD_PID" 2>/dev/null
        sleep 1
    fi
    rm -f "$PID_FILE"
fi

cleanup() {
    STOP_FLAG=1
    echo "サーバーを停止します..."
    if [ -f "$PID_FILE" ]; then
        kill "$(cat "$PID_FILE")" 2>/dev/null
        wait "$(cat "$PID_FILE")" 2>/dev/null
        rm -f "$PID_FILE"
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

# ポートを使用中のプロセスも停止（PIDファイルがない場合の保険）
PORT_PID=$(lsof -ti :"$WEB_PORT" 2>/dev/null)
if [ -n "$PORT_PID" ]; then
    echo "ポート $WEB_PORT を使用中のプロセスを停止します (PID: $PORT_PID)..."
    kill -9 $PORT_PID 2>/dev/null
    sleep 1
fi

echo "Starting server on port $WEB_PORT..."

while [ -z "$STOP_FLAG" ]; do
    uvicorn scripts.web:app --host 0.0.0.0 --port "$WEB_PORT" 2>&1 | tee -a server.log &
    PID=$!
    echo $PID > "$PID_FILE"
    echo "サーバー起動 (PID: $PID)"
    wait $PID
    EXIT_CODE=$?
    # cleanup によるシグナル停止の場合はループを抜ける
    if [ -n "$STOP_FLAG" ]; then
        break
    fi
    echo "サーバー終了 (code: $EXIT_CODE)、1秒後に再起動..."
    sleep 1
done
