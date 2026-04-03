#!/bin/bash
# Claude Code フック セットアップスクリプト
# リポジトリ内の正本（claude-hooks/）から ~/.claude/ と .claude/ にフックを展開する
# 冪等: 何度実行しても同じ結果

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_SRC="$PROJECT_DIR/claude-hooks"

GLOBAL_HOOKS_DIR="$HOME/.claude/hooks"
LOCAL_HOOKS_DIR="$PROJECT_DIR/.claude/hooks"
GLOBAL_SETTINGS="$HOME/.claude/settings.json"
LOCAL_SETTINGS="$PROJECT_DIR/.claude/settings.local.json"

echo "=== Claude Code フック セットアップ ==="
echo "プロジェクト: $PROJECT_DIR"
echo ""

# --- グローバルフック ---
echo "[1/4] グローバルフックをコピー..."
mkdir -p "$GLOBAL_HOOKS_DIR"
cp "$HOOKS_SRC/global/notify-stop.py" "$GLOBAL_HOOKS_DIR/"
cp "$HOOKS_SRC/global/notify-prompt.py" "$GLOBAL_HOOKS_DIR/"
cp "$HOOKS_SRC/global/long-execution-timer.py" "$GLOBAL_HOOKS_DIR/"
chmod +x "$GLOBAL_HOOKS_DIR"/*.py
echo "  -> $GLOBAL_HOOKS_DIR/ (3ファイル)"

# --- ローカルフック ---
echo "[2/4] ローカルフックをコピー..."
mkdir -p "$LOCAL_HOOKS_DIR"
cp "$HOOKS_SRC/local/fix-permissions.sh" "$LOCAL_HOOKS_DIR/"
chmod +x "$LOCAL_HOOKS_DIR/fix-permissions.sh"
echo "  -> $LOCAL_HOOKS_DIR/ (1ファイル)"

# --- グローバル settings.json にフック設定をマージ ---
echo "[3/4] グローバル settings.json を更新..."
if command -v jq &>/dev/null; then
    # jq がある場合: 既存設定を保持しつつ hooks をマージ
    if [ -f "$GLOBAL_SETTINGS" ]; then
        cp "$GLOBAL_SETTINGS" "$GLOBAL_SETTINGS.bak"
        jq -s '.[0] * .[1]' "$GLOBAL_SETTINGS.bak" "$HOOKS_SRC/settings-global.json" > "$GLOBAL_SETTINGS"
        echo "  -> マージ完了（バックアップ: settings.json.bak）"
    else
        mkdir -p "$(dirname "$GLOBAL_SETTINGS")"
        cp "$HOOKS_SRC/settings-global.json" "$GLOBAL_SETTINGS"
        echo "  -> 新規作成"
    fi
else
    # jq がない場合: Python で マージ
    python3 -c "
import json, sys
existing = {}
try:
    with open('$GLOBAL_SETTINGS') as f:
        existing = json.load(f)
except FileNotFoundError:
    pass
with open('$HOOKS_SRC/settings-global.json') as f:
    hooks = json.load(f)
existing.update(hooks)
with open('$GLOBAL_SETTINGS', 'w') as f:
    json.dump(existing, f, indent=2)
    f.write('\n')
"
    echo "  -> マージ完了（Python使用）"
fi

# --- ローカル settings.local.json にフック設定をマージ ---
echo "[4/4] ローカル settings.local.json を更新..."
if command -v jq &>/dev/null; then
    if [ -f "$LOCAL_SETTINGS" ]; then
        cp "$LOCAL_SETTINGS" "$LOCAL_SETTINGS.bak"
        jq -s '.[0] * .[1]' "$LOCAL_SETTINGS.bak" "$HOOKS_SRC/settings-local.json" > "$LOCAL_SETTINGS"
        echo "  -> マージ完了（バックアップ: settings.local.json.bak）"
    else
        cp "$HOOKS_SRC/settings-local.json" "$LOCAL_SETTINGS"
        echo "  -> 新規作成"
    fi
else
    python3 -c "
import json
existing = {}
try:
    with open('$LOCAL_SETTINGS') as f:
        existing = json.load(f)
except FileNotFoundError:
    pass
with open('$HOOKS_SRC/settings-local.json') as f:
    hooks = json.load(f)
# hooks キーだけマージ（permissions等は保持）
existing.setdefault('hooks', {}).update(hooks.get('hooks', {}))
with open('$LOCAL_SETTINGS', 'w') as f:
    json.dump(existing, f, indent=2)
    f.write('\n')
"
    echo "  -> マージ完了（Python使用）"
fi

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "設置されたフック:"
echo "  [グローバル] Stop        -> notify-stop.py     (作業完了報告 + タイマー停止)"
echo "  [グローバル] Prompt      -> notify-prompt.py    (指示受信報告 + タイマー起動)"
echo "  [グローバル] Timer       -> long-execution-timer.py (3分以上で定期報告)"
echo "  [ローカル]   PostToolUse -> fix-permissions.sh  (ファイル所有者修正)"
