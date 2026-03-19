# Claude Code 作業実況プラン

## 背景

Claude Codeが作業中に、ちょびがリアルタイムで視聴者に「今何してるか」を実況する機能。
配信を見ている人がClaude Codeの作業を楽しめるようにする。

## 設計原則: 疎結合

**この機能は「壊れても何も影響しない」ことを最優先とする。**

### 疎結合ルール

1. **Claude Code を絶対にブロックしない**
   - フックは必ずバックグラウンド実行（`&`）
   - タイムアウトは短く（最大3秒）
   - 失敗時は即座にexit 0（フック失敗でClaude Codeが止まるのを防ぐ）

2. **報告スクリプトは完全独立**
   - プロジェクトの `src/` や `scripts/` のモジュールを一切importしない
   - Python標準ライブラリのみ使用（`json`, `urllib`, `sys`, `os`）
   - `.env` の読み込みも自前で行う（dotenv等のライブラリ不要）

3. **サーバー側に新しいエンドポイントを作らない**
   - 既存の `POST /api/avatar/speak` をそのまま使う
   - サーバーが落ちていても、スクリプトが壊れていても、何も起きないだけ

4. **削除が1手順で完了する設計**
   - 機能を無効化したい場合:
     - `settings.local.json` のStopフックを削除 → 自動報告が止まる
     - CLAUDE.md の報告ルールを削除 → 手動報告が止まる
   - サーバー側のコード変更は一切不要

5. **既存機能に手を入れない**
   - `speak_event()` の変更なし
   - `CommentReader` の変更なし
   - `SpeechPipeline` の変更なし
   - 新しいキュー機構・ロック機構は追加しない

### 依存関係図

```
Claude Code
  ├── UserPromptSubmit フック（既存） → notify-prompt.sh → notify-prompt.py → HTTP POST
  └── Stop フック（新規）             → notify-stop.sh  → notify-stop.py  → HTTP POST
                                                                               ↓
                                                              POST /api/avatar/speak（既存API）
                                                                               ↓
                                                              speak_event()（既存メソッド）
```

**新規コードはフック側のみ。サーバー側は変更ゼロ。**

## 現状の仕組み

### 既存のインフラ
- **`POST /api/avatar/speak`** — イベント発話API（event_type + detail → AI応答 → TTS → 字幕）
- **`notify-prompt.py`** — UserPromptSubmitフックで、ユーザーの指示をちょびに発話させる（既存・動作中）
- **`speak_event()`** — CommentReaderのイベント発話メソッド（コミット通知等で使用中）

### 既存の報告系
| イベント | タイミング | 仕組み |
|---------|----------|--------|
| ユーザーの指示 | プロンプト送信時 | `UserPromptSubmit` フック → `notify-prompt.py` → `/api/avatar/speak` |
| Gitコミット | コミット検知時 | `GitWatcher` → `speak_event("コミット", ...)` |
| 外部リポジトリ | fetchで新コミット検知 | `DevStreamManager` → `speak_event("開発実況", ...)` |

## 実装方針

### アプローチ: Stopフック + 疎結合スクリプト

Claude Codeの **Stopフック** を使い、応答完了時に自動で報告する。
CLAUDE.mdによる手動呼び出しルールは設けない（忘れる・ブレるリスクを排除）。

### 報告スクリプト (`.claude/hooks/notify-stop.py`)

**配置場所: `.claude/hooks/`**（サーバーコードとは完全分離）

```python
#!/usr/bin/env python3
"""Claude Code Stop フック — 作業完了をちょびに報告させる"""
import json
import os
import sys
import urllib.request

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    # 無限ループ防止
    if data.get("stop_hook_active"):
        return

    message = data.get("last_assistant_message", "")
    if not message:
        return

    # 短すぎる応答（質問回答・確認等）はスキップ
    if len(message) < 80:
        return

    # ポートを .env から読む（標準ライブラリのみ）
    port = 8080
    env_path = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", ""), ".env")
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("WEB_PORT="):
                    port = int(line.split("=", 1)[1].strip())
                    break
    except Exception:
        pass

    # 先頭300文字を送信（AIが要約して発話する）
    detail = message[:300]
    payload = json.dumps({"event_type": "作業報告", "detail": detail}).encode()
    req = urllib.request.Request(
        f"http://localhost:{port}/api/avatar/speak",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass  # サーバー未起動・エラー時は何もしない

if __name__ == "__main__":
    main()
```

### シェルラッパー (`.claude/hooks/notify-stop.sh`)

```bash
#!/bin/bash
# Claude Code Stop フック — バックグラウンドで報告（Claudeをブロックしない）
python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/notify-stop.py" &
exit 0
```

### フック設定 (`settings.local.json` への追加)

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/notify-stop.sh"
          }
        ]
      }
    ]
  }
}
```

## 実装ステップ

### Step 1: Stopフック作成
- `.claude/hooks/notify-stop.py` を作成（上記コード）
- `.claude/hooks/notify-stop.sh` を作成（上記コード）
- `chmod +x` でシェルスクリプトに実行権限付与

### Step 2: 既存フック改善
- `notify-prompt.py` のポートを `.env` 対応に修正（8000 → WEB_PORT）
- 他の変更なし

### Step 3: settings.local.json にStopフック追加
- 既存の `UserPromptSubmit` / `PostToolUse` フックはそのまま
- `Stop` セクションを追加

### Step 4: CLAUDE.md 更新
- 報告ルールセクション追加（ただしClaude自身に手動呼び出しさせるルールではなく、フックの存在と動作の説明のみ）

### Step 5: 動作確認
- Claude Codeで適当な作業をして、完了時にちょびが発話するか確認
- 短い質問応答では発話しないか確認
- サーバー未起動時にClaude Codeの動作に影響がないか確認

## 技術的検討

### フィルタリング（何を報告するか）
- `len(last_assistant_message) < 80` → スキップ（短い応答は質問回答等）
- `stop_hook_active: true` → スキップ（無限ループ防止）
- それ以外 → 報告（AIが内容を見て自然な発話に変換する）

### 発話の競合
- `speak_event()` は既存のGitコミット通知と同じ経路
- 音声重複の可能性はあるが、既存と同じ挙動なので許容
- 新しいキュー機構やロック機構は追加しない（疎結合原則）

### レート制限
- Stopフックは「応答完了時」のみ発火 → 1タスクにつき基本1回
- サブエージェント使用時は複数回発火する可能性あり → 短い応答フィルタで自然に制限される
- 追加のレート制限は不要

### ポート番号
- `.env` の `WEB_PORT`（デフォルト8080）を使用
- `notify-prompt.py` は現在ハードコードで8000 → 修正が必要

## リスク

| リスク | 対策 | 疎結合による保証 |
|-------|------|----------------|
| 報告が多すぎてうるさい | 短文フィルタ（80文字未満スキップ） | フック削除で即停止可能 |
| サーバー未起動時のエラー | `try/except` で静かに失敗 | Claude Codeに一切影響なし |
| スクリプト自体のバグ | バックグラウンド実行 + `exit 0` | Claude Codeに一切影響なし |
| TTS生成中に報告が来る | 既存の `speak_event` と同じ挙動 | サーバー側コード変更なし |
| フィルタが甘い/厳しい | 閾値（80文字）を調整するだけ | スクリプト1箇所の変更で完結 |

## 将来の改善（今回はやらない）

- CLAUDE.mdに手動報告ルールを追加（作業開始時の報告等）→ まずStopフックの自動報告で様子を見る
- `SpeechPipeline` にロック機構追加 → 音声重複が問題になってから検討
- サブエージェント完了時のフック → Claude Codeが対応したら検討
- フィルタリングの高度化（AIで判定等）→ 現状の文字数フィルタで十分か見てから

## ステータス: 完了
