#!/usr/bin/env python3
"""Claude Code長時間実行タイマー

UserPromptSubmitフックからバックグラウンド起動される。
一定時間ごとにマーカーファイルを確認し、transcript_pathから作業内容を読み取り、
ちょびにコメントさせる。
"""
import json
import os
import time
import urllib.request

TWITCH_CAST_DIR = "/home/ubuntu/ai-twitch-cast"
MARKER_FILE = "/tmp/claude_working"
WATCHER_ACTIVE_FILE = "/tmp/claude_watcher_active"

# 初回コメントまでの待機（秒）と以降の間隔（秒）
FIRST_WAIT = 180   # 3分
INTERVAL = 180     # 3分ごと
IDLE_TIMEOUT = 120 # transcript が2分間更新されなければアイドルと判定


def get_port():
    try:
        with open(os.path.join(TWITCH_CAST_DIR, ".env")) as f:
            for line in f:
                if line.strip().startswith("WEB_PORT="):
                    return int(line.split("=", 1)[1].strip())
    except Exception:
        pass
    return 8080


def get_recent_activity(transcript_path):
    """transcript_pathの末尾からClaude Codeの直近の作業内容を取得"""
    try:
        with open(transcript_path) as f:
            lines = f.readlines()

        # 末尾20行を解析（十分な直近コンテキスト）
        recent = lines[-20:] if len(lines) > 20 else lines
        activities = []
        for line in reversed(recent):
            try:
                entry = json.loads(line)
            except Exception:
                continue

            # ツール呼び出しを探す
            if entry.get("type") == "tool_use" or "tool_name" in entry:
                tool = entry.get("tool_name", entry.get("name", ""))
                tool_input = entry.get("tool_input", entry.get("input", {}))

                if tool == "Bash":
                    cmd = tool_input.get("command", "")
                    activities.append(f"コマンド実行: {cmd[:80]}")
                elif tool == "Edit":
                    path = tool_input.get("file_path", "")
                    activities.append(f"ファイル編集: {os.path.basename(path)}")
                elif tool == "Write":
                    path = tool_input.get("file_path", "")
                    activities.append(f"ファイル作成: {os.path.basename(path)}")
                elif tool == "Read":
                    path = tool_input.get("file_path", "")
                    activities.append(f"ファイル読み取り: {os.path.basename(path)}")
                elif tool in ("Grep", "Glob"):
                    pattern = tool_input.get("pattern", "")
                    activities.append(f"コード検索: {pattern[:50]}")
                elif tool == "Agent":
                    desc = tool_input.get("description", "")
                    activities.append(f"サブエージェント: {desc[:50]}")
                else:
                    activities.append(f"{tool}を使用中")

                if len(activities) >= 3:
                    break

        return activities
    except Exception:
        return []


def is_idle(transcript_path):
    """transcriptファイルが一定時間更新されていなければアイドルと判定"""
    if not transcript_path:
        return False  # transcript_pathが不明なら安全側（アイドルとしない）
    try:
        mtime = os.path.getmtime(transcript_path)
        return (time.time() - mtime) > IDLE_TIMEOUT
    except Exception:
        return True  # ファイルが消えていたらアイドル扱い


def speak(message):
    payload = json.dumps({
        "event_type": "待機コメント",
        "detail": message,
    }).encode()
    req = urllib.request.Request(
        f"http://localhost:{get_port()}/api/avatar/speak",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


def main():
    # 初回待機
    time.sleep(FIRST_WAIT)

    while os.path.exists(MARKER_FILE):
        # ClaudeWatcherが稼働中ならスキップ
        if os.path.exists(WATCHER_ACTIVE_FILE):
            time.sleep(INTERVAL)
            continue

        try:
            with open(MARKER_FILE) as f:
                marker = json.loads(f.read())
            start_time = marker["start_time"]
            transcript_path = marker.get("transcript_path", "")

            # アイドル検知: transcriptが更新されていなければ終了
            if is_idle(transcript_path):
                try:
                    os.remove(MARKER_FILE)
                except FileNotFoundError:
                    pass
                break

            elapsed_min = int((time.time() - start_time) / 60)

            # 作業内容を取得
            activities = get_recent_activity(transcript_path) if transcript_path else []

            if activities:
                activity_text = "、".join(activities[:2])
                message = f"Claude Codeが{elapsed_min}分作業中。直近の作業: {activity_text}"
            else:
                message = f"Claude Codeが{elapsed_min}分以上作業中です。もう少しかかりそうです。"

            speak(message)
        except Exception:
            pass

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
