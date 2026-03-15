#!/bin/bash
# C#ネイティブ配信アプリ起動スクリプト
#
# Usage:
#   ./stream.sh                  # 基本起動（WebView2 + WGCキャプチャ確認）
#   ./stream.sh --stream         # Twitch配信（.envのTWITCH_STREAM_KEYを使用）
#   ./stream.sh --stop           # アプリ停止
#   ./stream.sh --status         # 動作状況確認
#   ./stream.sh --save-frames    # デバッグ: フレームをPNG保存
#
# オプション:
#   --stream          配信開始（TWITCH_STREAM_KEY必須）
#   --stop            アプリ停止
#   --status          動作状況確認
#   --save-frames     キャプチャフレームをPNG保存（デバッグ用）
#   --resolution WxH  解像度（デフォルト: 1920x1080）
#   --fps N           フレームレート（デフォルト: 30）
#   --bitrate Nk      映像ビットレート（デフォルト: 2500k）

cd "$(dirname "$0")"

APP_NAME="WinNativeApp"

# ソース（リポジトリ内）→ Windows FSビルドディレクトリ
SRC_DIR="$(pwd)/win-native-app/WinNativeApp"
BUILD_BASE="/mnt/c/Users/akira/AppData/Local/win-native-app"
BUILD_DIR="$BUILD_BASE/WinNativeApp"

# --stop: アプリ停止
if [[ "$1" == "--stop" ]]; then
    echo "停止中..."
    taskkill.exe /IM "${APP_NAME}.exe" /F 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "停止しました"
    else
        echo "実行中のアプリはありません"
    fi
    exit 0
fi

# --status: 動作状況
if [[ "$1" == "--status" ]]; then
    if tasklist.exe /FI "IMAGENAME eq ${APP_NAME}.exe" /NH 2>/dev/null | grep -q "$APP_NAME"; then
        echo "実行中"
        LOG_DIR="$BUILD_DIR/bin/Release/net8.0-windows10.0.22621.0/logs"
        LOG_FILE=$(ls -t "$LOG_DIR"/app*.log 2>/dev/null | head -1)
        if [ -n "$LOG_FILE" ]; then
            echo "--- 最新ログ ---"
            tail -5 "$LOG_FILE"
        fi
    else
        echo "停止中"
    fi
    exit 0
fi

# 既に起動中なら停止してから起動
if tasklist.exe /FI "IMAGENAME eq ${APP_NAME}.exe" /NH 2>/dev/null | grep -q "$APP_NAME"; then
    echo "既存のアプリを停止中..."
    taskkill.exe /IM "${APP_NAME}.exe" /F 2>/dev/null
    sleep 1
fi

# .envから設定読み込み
if [ -f .env ]; then
    WEB_PORT=$(grep -E '^WEB_PORT=' .env | cut -d= -f2)
    TWITCH_STREAM_KEY=$(grep -E '^TWITCH_STREAM_KEY=' .env | cut -d= -f2)
fi
WEB_PORT="${WEB_PORT:-8080}"
SERVER_URL="http://localhost:${WEB_PORT}"

# サーバー起動確認
echo "サーバー接続確認中..."
if ! curl -sf "${SERVER_URL}/api/status" > /dev/null 2>&1; then
    echo "エラー: Webサーバーが起動していません"
    echo "  先に ./server.sh を実行してください"
    exit 1
fi

# broadcast.htmlのトークンを取得
TOKEN=$(curl -sf "${SERVER_URL}/api/broadcast/token" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])" 2>/dev/null)
if [ -z "$TOKEN" ]; then
    echo "エラー: broadcastトークンを取得できません"
    exit 1
fi

# ソースをWindows FSにコピー（ビルド高速化）
echo "ソースを同期中..."
mkdir -p "$BUILD_DIR/Capture" "$BUILD_DIR/Streaming" "$BUILD_DIR/Server"
cp "$SRC_DIR"/*.cs "$SRC_DIR"/*.csproj "$BUILD_DIR/" 2>/dev/null
cp "$SRC_DIR"/Capture/*.cs "$BUILD_DIR/Capture/"
cp "$SRC_DIR"/Streaming/*.cs "$BUILD_DIR/Streaming/"
cp "$SRC_DIR"/Server/*.cs "$BUILD_DIR/Server/"
# Phase 7: パネルHTMLをビルド出力にコピー
cp "$SRC_DIR"/control-panel.html "$BUILD_DIR/" 2>/dev/null

WIN_PROJECT=$(wslpath -w "$BUILD_DIR")

# ビルド
echo "ビルド中..."
BUILD_OUTPUT=$(dotnet.exe build "$WIN_PROJECT" -c Release --nologo -v q 2>&1)
BUILD_EXIT=$?
if [ $BUILD_EXIT -ne 0 ]; then
    echo "ビルドエラー:"
    echo "$BUILD_OUTPUT"
    exit 1
fi
echo "ビルド完了"

# EXEパス
EXE_PATH="$BUILD_DIR/bin/Release/net8.0-windows10.0.22621.0/${APP_NAME}.exe"

# FFmpegパス（Electronアプリがダウンロード済みのものを優先）
if [ -z "$FFMPEG_PATH" ]; then
    ELECTRON_FFMPEG="/mnt/c/Users/akira/AppData/Local/ai-twitch-cast-capture/ffmpeg/ffmpeg.exe"
    if [ -f "$ELECTRON_FFMPEG" ]; then
        FFMPEG_PATH=$(wslpath -w "$ELECTRON_FFMPEG")
    fi
fi

# broadcast.html URL（トークン付き）
URL="${SERVER_URL}/broadcast?token=${TOKEN}"

# コマンドライン引数を構築
NATIVE_ARGS="$URL"
STREAM_MODE=false

# FFmpegパスは常に渡す（Go Live APIから後で配信開始される場合にも必要）
if [ -n "$FFMPEG_PATH" ]; then
    NATIVE_ARGS="$NATIVE_ARGS --ffmpeg-path $FFMPEG_PATH"
fi

# ストリームキーは常に渡す（パネルのGo Liveボタンから配信開始する場合にも必要）
if [ -n "$TWITCH_STREAM_KEY" ]; then
    NATIVE_ARGS="$NATIVE_ARGS --stream-key $TWITCH_STREAM_KEY"
fi

for arg in "$@"; do
    case "$arg" in
        --stream)
            STREAM_MODE=true
            ;;
        *)
            NATIVE_ARGS="$NATIVE_ARGS $arg"
            ;;
    esac
done

# 配信モード
if [ "$STREAM_MODE" = true ]; then
    if [ -z "$TWITCH_STREAM_KEY" ]; then
        echo "エラー: TWITCH_STREAM_KEY が .env に設定されていません"
        exit 1
    fi
    NATIVE_ARGS="$NATIVE_ARGS --stream --stream-key $TWITCH_STREAM_KEY"
    echo "配信モード: ON"
else
    echo "表示モード（配信なし）"
fi

echo "URL: ${SERVER_URL}/broadcast?token=***"

# EXEを直接起動（バックグラウンド）
"$EXE_PATH" $NATIVE_ARGS > /dev/null 2>&1 &
disown

echo "起動しました"
echo "  停止: ./stream.sh --stop"
echo "  状況: ./stream.sh --status"
