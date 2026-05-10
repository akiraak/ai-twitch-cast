#!/bin/bash
# 録画AV同期PoC（plans/recording-screen-capture-alternative.md Step 0）
# のビルド＆実行スクリプト。
#
# Usage:
#   ./poc-loopback.sh                          # WinNativeAppウィンドウを60秒録画
#   ./poc-loopback.sh --duration 90            # 録画秒数指定
#   ./poc-loopback.sh --window "Chrome"        # 別ウィンドウを録る
#   ./poc-loopback.sh --output foo.mp4         # 出力先指定（既定: debug-ss/poc_loopback_<ts>.mp4）
#   ./poc-loopback.sh --fps 30                 # フレームレート
#   ./poc-loopback.sh --build-only             # ビルドのみで終了
#
# 動作要件:
#   - 事前に WinNativeApp 本体を起動しておく（TTS/BGMが既定スピーカーへ出ている状態）
#   - WinNativeApp が一度ビルド済みで ffmpeg.exe が同梱されていること
#     （未ビルドなら自動で download-ffmpeg.ps1 を叩いて取得する）

set -e
cd "$(dirname "$0")"

APP_NAME="PocLoopback"

# Windows コマンド出力の文字化け対策（CP932→UTF-8）
win_decode() { iconv -f CP932 -t UTF-8 2>/dev/null; }

# ソース → Windows FS ビルドディレクトリ（stream.sh と同じ親）
SRC_DIR="$(pwd)/win-native-app/PocLoopback"
WIN_NATIVE_SRC_DIR="$(pwd)/win-native-app/WinNativeApp"
BUILD_BASE="/mnt/c/Users/akira/AppData/Local/win-native-app"
BUILD_DIR="$BUILD_BASE/PocLoopback"

# 引数パース
WINDOW="AI Twitch Cast"
DURATION=60
FPS=30
OUTPUT=""
BUILD_ONLY=false
EXTRA_ARGS=""
while [ $# -gt 0 ]; do
    case "$1" in
        --window)     WINDOW="$2"; shift 2 ;;
        --duration)   DURATION="$2"; shift 2 ;;
        --fps)        FPS="$2"; shift 2 ;;
        --output)     OUTPUT="$2"; shift 2 ;;
        --build-only) BUILD_ONLY=true; shift ;;
        -h|--help)
            sed -n '2,18p' "$0"
            exit 0 ;;
        *)
            EXTRA_ARGS="$EXTRA_ARGS $1"; shift ;;
    esac
done

# 既定出力先: Windows 側ローカル（WSL UNC越しは書込が遅く FFmpeg がドロップしやすいので）
# 完走後に WSL 側 debug-ss/ にコピーする
TS=$(date +%Y%m%d_%H%M%S)
WIN_OUTPUT_BASE="$BUILD_BASE/PocLoopback/output"
mkdir -p "$WIN_OUTPUT_BASE"
if [ -z "$OUTPUT" ]; then
    OUTPUT_FILENAME="poc_loopback_${TS}.mp4"
    OUTPUT_ABS="$WIN_OUTPUT_BASE/$OUTPUT_FILENAME"
    COPY_BACK="debug-ss/$OUTPUT_FILENAME"
    mkdir -p debug-ss
else
    # 明示指定時はそのまま使う（ユーザー責任）
    OUTPUT_DIR=$(dirname "$OUTPUT")
    mkdir -p "$OUTPUT_DIR"
    OUTPUT_ABS=$(realpath -m "$OUTPUT")
    COPY_BACK=""
fi

# ソースを Windows FS にコピー（ビルド高速化）
echo "ソース同期中..."
mkdir -p "$BUILD_DIR"
cp "$SRC_DIR"/*.cs "$SRC_DIR"/*.csproj "$BUILD_DIR/" 2>/dev/null
# ffmpeg ダウンロードスクリプトも転送（ffmpeg未取得時に叩くため）
cp "$WIN_NATIVE_SRC_DIR/download-ffmpeg.ps1" "$BUILD_DIR/" 2>/dev/null || true

WIN_PROJECT=$(wslpath -w "$BUILD_DIR")

# ビルド
echo "ビルド中..."
BUILD_OUTPUT=$(dotnet.exe build "$WIN_PROJECT" -c Release --nologo -v q 2>&1)
BUILD_EXIT=$?
if [ $BUILD_EXIT -ne 0 ]; then
    echo "ビルドエラー:"
    echo "$BUILD_OUTPUT" | win_decode
    exit 1
fi
echo "ビルド完了"

EXE_PATH="$BUILD_DIR/bin/Release/net8.0-windows10.0.22621.0/${APP_NAME}.exe"
if [ ! -f "$EXE_PATH" ]; then
    echo "エラー: ビルド成果物が見つかりません: $EXE_PATH"
    exit 1
fi

# ffmpeg.exe を確保する
# 探索順:
#   1. 兄弟 WinNativeApp の build 出力（stream.sh で一度ビルド済みの想定）
#   2. PocLoopback 自身の bin 配下に download-ffmpeg.ps1 で取得
FFMPEG_CANDIDATES=(
    "$BUILD_BASE/WinNativeApp/bin/Release/net8.0-windows10.0.22621.0/resources/ffmpeg/ffmpeg.exe"
    "$BUILD_BASE/WinNativeApp/bin/Debug/net8.0-windows10.0.22621.0/resources/ffmpeg/ffmpeg.exe"
    "$(dirname "$EXE_PATH")/resources/ffmpeg/ffmpeg.exe"
)
FFMPEG_EXE=""
for c in "${FFMPEG_CANDIDATES[@]}"; do
    if [ -f "$c" ]; then FFMPEG_EXE="$c"; break; fi
done

if [ -z "$FFMPEG_EXE" ]; then
    echo "ffmpeg.exe が見つかりません。download-ffmpeg.ps1 で取得します..."
    FFMPEG_TARGET="$(dirname "$EXE_PATH")/resources/ffmpeg"
    mkdir -p "$FFMPEG_TARGET"
    WIN_TARGET=$(wslpath -w "$FFMPEG_TARGET")
    WIN_PS1=$(wslpath -w "$BUILD_DIR/download-ffmpeg.ps1")
    if ! powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$WIN_PS1" -OutDir "$WIN_TARGET" 2>&1 | win_decode; then
        echo "ffmpeg のダウンロードに失敗しました。先に ./stream.sh を一度実行してください。"
        exit 1
    fi
    FFMPEG_EXE="$FFMPEG_TARGET/ffmpeg.exe"
fi
echo "ffmpeg: $FFMPEG_EXE"

if [ "$BUILD_ONLY" = true ]; then
    echo "ビルドのみで終了"
    exit 0
fi

# Windows パスに変換（PoC バイナリは Windows プロセスなので Windows パスを渡す）
WIN_OUTPUT=$(wslpath -w "$OUTPUT_ABS")
WIN_FFMPEG=$(wslpath -w "$FFMPEG_EXE")

echo "録画開始:"
echo "  window:   $WINDOW"
echo "  duration: ${DURATION}s"
echo "  fps:      $FPS"
echo "  output:   $OUTPUT_ABS"
echo

# フォアグラウンド実行（Ctrl+C で停止可能、ffmpeg ログがそのまま出る）
"$EXE_PATH" \
    --window "$WINDOW" \
    --duration "$DURATION" \
    --fps "$FPS" \
    --output "$WIN_OUTPUT" \
    --ffmpeg "$WIN_FFMPEG" \
    $EXTRA_ARGS
EXIT_CODE=$?

if [ -f "$OUTPUT_ABS" ]; then
    echo
    echo "=== 録画完了 ==="
    echo "ファイル: $OUTPUT_ABS"
    echo "サイズ:   $(du -h "$OUTPUT_ABS" | cut -f1)"
    if [ -n "$COPY_BACK" ]; then
        cp "$OUTPUT_ABS" "$COPY_BACK"
        echo "WSL側コピー: $(realpath "$COPY_BACK")"
    fi
    echo
    echo "次のチェック:"
    echo "  1. VLC で再生して口パク／音声ズレを目視（≦33ms 目標）"
    echo "  2. PTS 差を確認:"
    echo "     ffprobe -hide_banner -show_packets -select_streams v -of csv \"$OUTPUT_ABS\" | head -5"
    echo "     ffprobe -hide_banner -show_packets -select_streams a -of csv \"$OUTPUT_ABS\" | head -5"
fi

exit $EXIT_CODE
