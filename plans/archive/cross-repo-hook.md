# 他リポジトリのClaude Code動作検知

## 背景

現在、ai-twitch-castリポジトリのClaude Code操作はプロジェクトレベルのフック（`.claude/settings.local.json`）でちょびに実況されている。他のリポジトリで開発実況する場合にも、同様にちょびがコメントできるようにしたい。

## 現状の仕組み

- **Stop フック**: Claude Code応答完了 → `notify-stop.sh` → `notify-stop.py` → `POST /api/avatar/speak`
- **UserPromptSubmit フック**: ユーザー指示送信 → `notify-prompt.sh` → `notify-prompt.py` → `POST /api/avatar/speak`
- **設定場所**: `.claude/settings.local.json`（プロジェクトローカル）
- **スクリプト場所**: `.claude/hooks/`（プロジェクトローカル）
- **環境変数**: `CLAUDE_PROJECT_DIR` がフック実行時に自動設定される

## 方針: ユーザーレベルのグローバルフック

Claude Codeのフックは `~/.claude/settings.json`（ユーザーレベル）にも設定可能で、**全プロジェクトに適用**される。

### 設計

1. **グローバルフックスクリプト** を `~/.claude/hooks/` に配置
2. `~/.claude/settings.json` にStop/UserPromptSubmitフックを追加（`"async": true` で非ブロッキング）
3. スクリプトは `CLAUDE_PROJECT_DIR` からプロジェクト名を取得して報告に含める
4. ai-twitch-castのWebサーバー（`localhost:$WEB_PORT`）に送信
5. ai-twitch-castプロジェクト内のローカルフックは削除（グローバルと重複するため）

### フックの優先順位

1. Managed settings（組織レベル）
2. コマンドライン引数
3. `.claude/settings.local.json`（プロジェクトローカル）
4. `.claude/settings.json`（プロジェクト共有）
5. `~/.claude/settings.json`（ユーザーレベル） ← ここに追加

**注意**: プロジェクトローカルとユーザーレベルの両方にフックがある場合、**両方が実行される**（配列がマージされる）。ai-twitch-castのローカルフックを残すと二重発火するので、移行後は削除する。

## 実装ステップ

### Step 1: グローバルフックスクリプト作成

`~/.claude/hooks/notify-stop.py` を作成。現在のプロジェクトローカル版との差分:

- `CLAUDE_PROJECT_DIR` からプロジェクト名を抽出して `event_type` に含める
- `.env` の読み取り先を ai-twitch-cast 固定（他リポジトリには `.env` がない）
- ポートも ai-twitch-cast の `.env` から取得、なければデフォルト8080

```python
"""グローバル Claude Code Stop フック"""
import json, os, sys, urllib.request

# ai-twitch-cast の .env からポートを取得
TWITCH_CAST_DIR = "/home/ubuntu/ai-twitch-cast"

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
        pass

if __name__ == "__main__":
    main()
```

同様に `~/.claude/hooks/notify-prompt.py` も作成（`event_type` を `"指示"` / `"指示（{project_name}）"` にする）。

### Step 2: `~/.claude/settings.json` にフック追加

`"async": true` を指定することで、フックはバックグラウンド実行される。シェルラッパー（`.sh`）は不要。

```json
{
  "effortLevel": "high",
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 $HOME/.claude/hooks/notify-prompt.py",
            "async": true
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 $HOME/.claude/hooks/notify-stop.py",
            "async": true
          }
        ]
      }
    ]
  }
}
```

**パスについて**: `~` の展開はClaude Codeで保証されていないため、`$HOME` 環境変数を使用する。

### Step 3: ai-twitch-cast ローカルフックの整理

`.claude/settings.local.json` から Stop / UserPromptSubmit フックを削除（PostToolUse の fix-permissions.sh はプロジェクト固有なので残す）。

プロジェクトローカルの `.claude/hooks/notify-stop.sh`, `notify-stop.py`, `notify-prompt.sh`, `notify-prompt.py` は削除する（グローバルに移行済みのため）。

### Step 4: 動作確認

1. ai-twitch-castリポジトリでClaude Codeを使用 → ちょびが「作業報告」と発話
2. 別リポジトリでClaude Codeを使用 → ちょびが「作業報告（リポジトリ名）」と発話
3. サーバー未起動時 → エラーなく静かに失敗

## 考慮事項

- **fix-permissions.sh はグローバル化しない**: ai-twitch-cast固有の処理（`ubuntu:ubuntu` へのchown）なので、プロジェクトローカルに残す
- **サーバー未起動**: 他リポジトリ作業時にai-twitch-castサーバーが動いていなければ、静かに失敗する（既存と同じ挙動）
- **パス依存**: `TWITCH_CAST_DIR` をハードコードする（この環境専用なのでシンプルさ優先）
- **同時実行**: 複数リポジトリで同時にClaude Codeを使った場合、フックが同時に `/api/avatar/speak` を叩く可能性があるが、サーバー側はTTSキュー処理なので問題なし

## リスク

- **低**: `"async": true` で非ブロッキング。失敗しても他のClaude Code操作に影響なし
- **低**: サーバーが落ちていても `timeout=3` + `except: pass` で無影響

## ステータス: 完了
