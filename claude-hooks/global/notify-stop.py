#!/usr/bin/env python3
"""グローバル Claude Code Stop フック — 作業完了をちょびに報告 + タイマー停止"""
import json
import os
import subprocess
import sys
import urllib.request

TWITCH_CAST_DIR = "/home/ubuntu/ai-twitch-cast"
MARKER_FILE = "/tmp/claude_working"


def get_port():
    try:
        with open(os.path.join(TWITCH_CAST_DIR, ".env")) as f:
            for line in f:
                if line.strip().startswith("WEB_PORT="):
                    return int(line.split("=", 1)[1].strip())
    except Exception:
        pass
    return 8080


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        return

    if data.get("stop_hook_active"):
        return

    # マーカーファイル削除 → タイマー自然終了
    try:
        os.remove(MARKER_FILE)
    except FileNotFoundError:
        pass

    # タイマープロセスも明示的に停止
    subprocess.Popen(
        ["pkill", "-f", "long-execution-timer.py"],
        stderr=subprocess.DEVNULL,
    )

    message = data.get("last_assistant_message", "")
    if not message or len(message) < 10:
        return

    # プロジェクト名を抽出
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    project_name = os.path.basename(project_dir) if project_dir else "unknown"

    # ai-twitch-cast 自身の場合はプロジェクト名を省略
    if project_dir == TWITCH_CAST_DIR:
        event_type = "作業報告"
    else:
        event_type = f"作業報告（{project_name}）"

    detail = message[:300]
    payload = json.dumps({"event_type": event_type, "detail": detail}).encode()
    req = urllib.request.Request(
        f"http://localhost:{get_port()}/api/avatar/speak",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass  # サーバー未起動時は静かに失敗


if __name__ == "__main__":
    main()
