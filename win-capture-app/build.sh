#!/bin/bash
# Electronアプリをビルドする（WSL2上で実行）
set -e

cd "$(dirname "$0")"

echo "=== Installing dependencies ==="
npm install

echo "=== Building for Windows ==="
npm run build

echo ""
echo "=== Build complete ==="
echo "Output: dist/win-unpacked/win-capture-app.exe"
