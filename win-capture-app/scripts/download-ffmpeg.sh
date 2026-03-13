#!/bin/bash
# Windows用ffmpeg.exeをダウンロードしてwin-capture-app/ffmpeg/に配置する
# ビルドはWSL2上で行うが、実行はWindows上なのでWindows版バイナリが必要

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
FFMPEG_DIR="$APP_DIR/ffmpeg"
FFMPEG_EXE="$FFMPEG_DIR/ffmpeg.exe"

# 既にダウンロード済みならスキップ
if [ -f "$FFMPEG_EXE" ]; then
    SIZE=$(du -h "$FFMPEG_EXE" | cut -f1)
    echo "ffmpeg.exe already exists ($SIZE), skipping download"
    exit 0
fi

mkdir -p "$FFMPEG_DIR"

# BtbN FFmpeg Builds (GPL版: x264/x265含む)
FFMPEG_URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
TEMP_ZIP="/tmp/ffmpeg-win64-$$.zip"

echo "Downloading FFmpeg for Windows..."
echo "URL: $FFMPEG_URL"
curl -L --progress-bar -o "$TEMP_ZIP" "$FFMPEG_URL"

echo "Extracting ffmpeg.exe..."
# zip内の bin/ffmpeg.exe だけ抽出（ディレクトリ構造を無視）
unzip -j -o "$TEMP_ZIP" "*/bin/ffmpeg.exe" -d "$FFMPEG_DIR"

rm -f "$TEMP_ZIP"

if [ -f "$FFMPEG_EXE" ]; then
    SIZE=$(du -h "$FFMPEG_EXE" | cut -f1)
    echo "ffmpeg.exe downloaded successfully ($SIZE)"
else
    echo "ERROR: Failed to extract ffmpeg.exe"
    exit 1
fi
