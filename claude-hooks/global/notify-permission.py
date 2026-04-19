#!/usr/bin/env python3
"""グローバル Claude Code PermissionRequest フック — 承認待ちをちょびに報告（60秒クールダウン）"""
import json
import os
import sys
import time
import urllib.request

TWITCH_CAST_DIR = "/home/ubuntu/ai-twitch-cast"
COOLDOWN_FILE = "/tmp/claude_permission_last"
COOLDOWN_SECONDS = 60


def get_port():
    try:
        with open(os.path.join(TWITCH_CAST_DIR, ".env")) as f:
            for line in f:
                if line.strip().startswith("WEB_PORT="):
                    return int(line.split("=", 1)[1].strip())
    except Exception:
        pass
    return 8080


def is_in_cooldown():
    try:
        with open(COOLDOWN_FILE) as f:
            last = float(f.read().strip())
        return (time.time() - last) < COOLDOWN_SECONDS
    except Exception:
        return False


def mark_fired():
    try:
        with open(COOLDOWN_FILE, "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        return

    if is_in_cooldown():
        return

    tool_name = data.get("tool_name", "") or "unknown"

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    project_name = os.path.basename(project_dir) if project_dir else "unknown"

    if project_dir == TWITCH_CAST_DIR:
        event_type = "承認待ち"
    else:
        event_type = f"承認待ち（{project_name}）"

    payload = json.dumps({"event_type": event_type, "detail": tool_name}).encode()
    req = urllib.request.Request(
        f"http://localhost:{get_port()}/api/avatar/speak",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        return  # サーバー未起動時は静かに失敗（クールダウン開始もしない）

    mark_fired()


if __name__ == "__main__":
    main()
