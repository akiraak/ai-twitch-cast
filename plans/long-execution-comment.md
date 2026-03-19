# Claude Code長時間実行時にちょびがコメント

## 背景

Claude Codeの応答が長い（数分以上）とき、配信画面が静かになってしまう。ちょびが「まだ作業中だよ〜」のようなコメントをすれば、視聴者が離脱しにくくなる。さらに、Claude Codeが今何をしているかを `transcript_path`（リアルタイム更新されるJSONLファイル）から読み取り、具体的な内容付きで報告する。

## 現状

- **UserPromptSubmit**: ユーザーの指示送信時に発火 → 「指示」として報告
- **Stop**: Claude Code応答完了時に発火 → 「作業報告」として報告
- **実行中のフックはない**: Claude Codeにはハートビートや定期発火フックが存在しない
- **transcript_path**: フックのstdinに含まれるJSONLファイルパス。セッション中のツール呼び出し・応答がリアルタイムに追記される

## 方針: タイマー + transcript_path で作業内容付き報告

UserPromptSubmitフックでバックグラウンドタイマーを起動し、一定時間後にちょびにコメントさせる。その際 `transcript_path` のJSONLファイルを読み、直近のツール呼び出しから「今何をしているか」を判定して具体的に報告する。

### フロー

```
UserPromptSubmit → マーカーファイル作成（timestamp + transcript_path）
                 → バックグラウンドタイマー起動
                     ↓
              [3分経過] → マーカー存在確認
                       → transcript_path の更新日時を確認
                         → 2分以上未更新 → アイドル判定 → マーカー削除して終了（発話なし）
                         → 更新あり → 末尾を読んで作業内容を要約
                       → ちょびに「Claude Codeは○○をやってるみたい（○分経過）」と報告
              [以降3分ごと] → 同上（毎回アイドル判定を実施）
                     ↓
Stop → マーカーファイル削除 → タイマーは次回チェック時に自然終了
```

### マーカーファイル

- パス: `/tmp/claude_working`
- 内容（JSON）:
  ```json
  {"start_time": 1710849600.0, "transcript_path": "/path/to/session.jsonl"}
  ```
- UserPromptSubmitで作成、Stopで削除

## 実装ステップ

### Step 1: タイマースクリプト作成

`~/.claude/hooks/long-execution-timer.py`:

```python
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
        "detail": message
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
        try:
            with open(MARKER_FILE) as f:
                marker = json.loads(f.read())
            start_time = marker["start_time"]
            transcript_path = marker.get("transcript_path", "")

            # アイドル検知: transcriptが更新されていなければ終了
            # （Stopフックが発火しなかった場合のセーフガード）
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
```

### Step 2: 既存フックの修正

**`~/.claude/hooks/notify-prompt.py`** に追記:

```python
# main() の末尾に追加
import subprocess
import time

# transcript_path を取得（stdinのJSONに含まれる）
transcript_path = data.get("transcript_path", "")

# マーカーファイル作成
marker = "/tmp/claude_working"
with open(marker, "w") as f:
    json.dump({"start_time": time.time(), "transcript_path": transcript_path}, f)

# 既存タイマーを停止してから新規起動
subprocess.Popen(
    ["pkill", "-f", "long-execution-timer.py"],
    stderr=subprocess.DEVNULL
)
subprocess.Popen(
    ["python3", os.path.expanduser("~/.claude/hooks/long-execution-timer.py")],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,  # 親プロセスから切り離す
)
```

**`~/.claude/hooks/notify-stop.py`** に追記:

```python
# main() の末尾に追加
import subprocess

# マーカーファイル削除 → タイマー自然終了
marker = "/tmp/claude_working"
try:
    os.remove(marker)
except FileNotFoundError:
    pass

# タイマープロセスも明示的に停止
subprocess.Popen(
    ["pkill", "-f", "long-execution-timer.py"],
    stderr=subprocess.DEVNULL
)
```

### Step 3: settings.json の変更は不要

既存のUserPromptSubmit/Stopフックの中でタイマーを管理するため、`~/.claude/settings.json` の変更は不要。

### Step 4: 動作確認

1. Claude Codeに長い作業を依頼 → 3分後にちょびが作業内容付きコメント
2. 3分ごとに繰り返しコメント（内容は直近のtranscriptから更新される）
3. Claude Codeが完了 → マーカー削除 → タイマー自然終了
4. 短い作業（3分未満）→ コメントなし
5. Claude Codeを強制終了（Ctrl+C）→ transcript未更新2分後にタイマー自動終了（発話なし）
6. Stopフック失敗 → 同上、アイドル検知で自動クリーンアップ

## transcript_path の仕様

- フックのstdin JSONに `transcript_path` フィールドとして含まれる
- セッション中のツール呼び出し・応答が**リアルタイムに追記**されるJSONLファイル
- 各行は1つのイベント（ツール呼び出し、応答等）を表すJSON
- 外部プロセスからの読み取りが可能（append-onlyなので安全）

## 考慮事項

- **transcript_pathのフォーマット**: JSONLの具体的なスキーマは公式ドキュメントで詳細に定義されていないため、実装時にサンプルデータを確認して `get_recent_activity()` のパース処理を調整する必要がある
- **同時セッション**: 複数のClaude Codeセッションが同時に動く場合、マーカーファイルが上書きされる。ただし実運用上は1セッションがほとんどなので許容
- **サーバー未起動**: `speak()` が静かに失敗するので問題なし
- **タイマーの残留**: Stopで `pkill` するが、万一残っても次回チェックでマーカーがなければ自然終了。さらに transcript_path の更新日時が2分以上前ならアイドルと判定してマーカー削除+終了（Ctrl+CやStopフック失敗のセーフガード）
- **コメント内容**: `/api/avatar/speak` に渡すのは素材テキスト。ちょびのAIが適切にアレンジして発話する
- **`start_new_session=True`**: タイマープロセスをClaude Codeのフックプロセスから完全に切り離す

## リスク

- **低**: バックグラウンドプロセスが残留する可能性があるが、`pkill` + マーカー削除で二重に対策
- **低**: `time.sleep()` の精度は問題にならない（数秒の誤差は許容）
- **中**: transcript_path のJSONLスキーマが想定と異なる可能性 → `get_recent_activity()` が空配列を返すだけで、フォールバックメッセージが使われる

## ステータス: 完了
