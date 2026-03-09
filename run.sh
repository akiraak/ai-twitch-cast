#!/bin/bash
# .envからWEB_PORTを読み込んでuvicornを起動する

set -e
cd "$(dirname "$0")"

# .envからWEB_PORT読み込み（デフォルト: 8080）
if [ -f .env ]; then
    WEB_PORT=$(grep -E '^WEB_PORT=' .env | cut -d= -f2)
fi
WEB_PORT="${WEB_PORT:-8080}"

echo "Starting server on port $WEB_PORT..."
uvicorn scripts.web:app --reload --host 0.0.0.0 --port "$WEB_PORT"
