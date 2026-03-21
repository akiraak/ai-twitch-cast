# Claude Code 会話へのちょび反応プラン

## 背景

Claude Codeとユーザーの会話（指示・返答）に、ちょびが配信上でリアルタイムに反応する機能。
視聴者が「今何が起きているか」を楽しめるようにする。

## 現状分析

### 既に動いているもの

| フック | タイミング | 内容 | 問題点 |
|--------|----------|------|--------|
| UserPromptSubmit | ユーザーがプロンプト送信時 | prompt を「指示」として発話 | **動作中**。ただし全プロンプトに反応（短い返事にも） |
| Stop | Claude応答完了時 | last_assistant_message を「作業報告」として発話 | **動作中**。80文字未満スキップ |

### まだカバーされていないもの

| イベント | 内容 | 利用可能なフック |
|---------|------|----------------|
| ツール実行 | ファイル編集・Bash実行・検索等 | PostToolUse（tool_name, tool_input, tool_response） |
| サブエージェント | 調査・探索の開始/終了 | SubagentStart / SubagentStop |
| 作業中の経過 | 長い作業の途中経過 | なし（Stopは完了時のみ） |

### 利用可能なClaude Codeフックデータ

```
UserPromptSubmit:
  prompt: "ユーザーの入力テキスト"

Stop:
  last_assistant_message: "Claudeの最後の応答"
  stop_hook_active: true/false
  transcript_path: "/path/to/transcript.jsonl"  ← 会話全履歴

PostToolUse:
  tool_name: "Edit" | "Write" | "Bash" | "Grep" | "Read" | "Agent" 等
  tool_input: { file_path, command, pattern 等 }
  tool_response: { success 等 }

SubagentStart:
  agent_type: "Explore" | "Plan" | "general-purpose" 等

SubagentStop:
  (完了時データ)
```

## 設計方針

### 疎結合（既存と同じ原則）

1. フックはバックグラウンド実行、Claude Codeをブロックしない
2. stdlib only、サーバー側変更ゼロ
3. 既存の `/api/avatar/speak` をそのまま使用
4. 削除が1手順（settings.local.jsonのフック削除のみ）

### 反応の粒度設計（重要）

**やりすぎない**。全ツール実行に反応するとうるさい。

| レベル | 反応するもの | 頻度 |
|--------|-------------|------|
| **現状維持** | ユーザー指示（UserPromptSubmit） | 1タスクに1回 |
| **現状維持** | 作業完了（Stop） | 1タスクに1回 |
| **新規追加** | ファイル編集のサマリ（PostToolUse） | 間引き有り |

### PostToolUse の間引きルール

全ツール実行に反応すると1タスクで数十回発話してしまう。

**方針**: 一定時間（60秒）ごとに最大1回、直近のツール実行をまとめて報告

**実装**:
- PostToolUseフックは毎回ログファイルに追記するだけ（発話しない）
- Stopフックが発火した時点で、ログを読んで「何をしたか」のサマリを含めて発話
  → つまり既存のStopフックを拡張するだけ

これなら**新しいフックスクリプトは不要**。notify-stop.py を改良するだけ。

## 実装方針: Stopフック拡張

### アプローチ

notify-stop.py が `transcript_path` を読み、会話の流れ全体から要約を作成する。

```
Stop フック発火
  → transcript_path から直近のやりとりを読む
  → ユーザー指示 + 実行したツール + 最終応答をまとめる
  → /api/avatar/speak に送信
  → AIが自然な実況に変換して発話
```

### notify-stop.py の改良案

```python
def main():
    data = json.load(sys.stdin)

    # 無限ループ防止・短文スキップ（既存）
    if data.get("stop_hook_active"):
        return
    message = data.get("last_assistant_message", "")
    if not message or len(message) < 80:
        return

    # 【新規】transcript_path から作業サマリを構築
    summary = build_summary(data)

    # /api/avatar/speak に送信
    payload = {"event_type": "作業報告", "detail": summary}
    ...

def build_summary(data):
    """transcript_pathから作業の要約を構築する"""
    transcript = data.get("transcript_path", "")
    message = data.get("last_assistant_message", "")

    if not transcript or not os.path.exists(transcript):
        return message[:300]

    # transcript.jsonl を読んで要約を構築
    edited_files = set()
    bash_commands = []
    user_prompt = ""

    for line in open(transcript):
        entry = json.loads(line)
        # ユーザーの最新プロンプトを取得
        # 編集したファイル一覧を収集
        # 実行したコマンドを収集

    parts = []
    if user_prompt:
        parts.append(f"指示: {user_prompt[:100]}")
    if edited_files:
        parts.append(f"編集: {', '.join(edited_files)}")
    if bash_commands:
        parts.append(f"実行: {bash_commands[-1][:50]}")
    parts.append(f"結果: {message[:150]}")

    return " / ".join(parts)
```

### メリット

- **新しいフックスクリプト不要**（notify-stop.py の改良のみ）
- **PostToolUseフック追加不要**（transcript_pathから全履歴が取れる）
- **発話頻度は変わらない**（Stopフック = 1タスクに1回）
- **情報量が増える**（何をしたかの要約付き）

## 実装ステップ

### Step 1: transcript_path の構造調査
- 実際のtranscript.jsonlを読んで、含まれる情報を確認
- ツール使用履歴（tool_name, file_path等）の取得方法を確定

### Step 2: notify-stop.py にbuild_summary()追加
- transcript_pathからユーザー指示・編集ファイル・コマンドを抽出
- last_assistant_message と組み合わせて要約を構築
- transcript_pathがない場合は現状と同じ動作（フォールバック）

### Step 3: UserPromptSubmitフック改善
- 短い入力（「はい」「次へ」等10文字未満）はスキップ
- /clear 等のコマンドはスキップ

### Step 4: 動作確認
- 適当な作業をして、ちょびの反応内容が改善されたか確認
- サーバー未起動時にエラーが出ないか確認

## 反応のイメージ

### Before（現状）
```
ユーザー: "TODO更新とコミット"
  → ちょび「お仕事来たよ！」

Claude: （ファイル読み→編集→テスト→コミット）

Claude応答完了:
  → ちょび「コミット完了したみたい！」
```

### After（改善後）
```
ユーザー: "TODO更新とコミット"
  → ちょび「TODOの更新とコミットだって！」

Claude: （ファイル読み→編集→テスト→コミット）

Claude応答完了:
  → ちょび「TODO.mdとDONE.md編集して、テスト通って、コミットしたみたい！」
```

**違い**: 何を編集して何をしたかの具体的な情報が入る。

## リスク

| リスク | 対策 |
|-------|------|
| transcript.jsonlの形式が変わる | try/exceptでフォールバック（現状と同じ動作） |
| transcript.jsonlが巨大 | 末尾N行のみ読む（全行読まない） |
| 要約が長すぎる | 300文字に切り詰め（AIが要約） |
| transcript_pathがない | フォールバック（last_assistant_messageのみ） |

## ステータス: 未着手
