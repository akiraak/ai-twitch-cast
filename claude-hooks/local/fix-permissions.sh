#!/bin/bash
# PostToolUse フック — Claude Code（root）が作成・編集したファイルの所有者を修正
# tool_input の file_path を読み取り、ubuntu:ubuntu に chown する

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [ -n "$FILE_PATH" ] && [ -e "$FILE_PATH" ]; then
    chown ubuntu:ubuntu "$FILE_PATH" 2>/dev/null
fi
