#!/usr/bin/env python3
"""グローバル Claude Code UserPromptSubmit フック — 指示受信をちょびに報告 + タイマー起動"""
import json
import os
import subprocess
import sys
import time
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

    message = data.get("user_prompt", "")
    if not message or len(message) < 2:
        return

    # プロジェクト名を抽出
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    project_name = os.path.basename(project_dir) if project_dir else "unknown"

    if project_dir == TWITCH_CAST_DIR:
        event_type = "指示"
    else:
        event_type = f"指示（{project_name}）"

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

    # transcript_path を取得
    transcript_path = data.get("transcript_path", "")

    # マーカーファイル作成
    try:
        with open(MARKER_FILE, "w") as f:
            json.dump({"start_time": time.time(), "transcript_path": transcript_path}, f)
    except Exception:
        pass

    # 既存タイマーを停止してから新規起動
    subprocess.Popen(
        ["pkill", "-f", "long-execution-timer.py"],
        stderr=subprocess.DEVNULL,
    )
    timer_path = os.path.expanduser("~/.claude/hooks/long-execution-timer.py")
    subprocess.Popen(
        ["python3", timer_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # 親プロセスから切り離す
    )


if __name__ == "__main__":
    main()
