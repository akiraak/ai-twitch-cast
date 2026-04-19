# Claude Code 承認プロンプト発火時のTTS通知

## ステータス: 完了

## 背景

Claude Code が「Yes/No 承認ダイアログ」を表示したとき、ちょびが気づいて一言しゃべるようにしたい。ユーザーが席を外しても、配信画面やスピーカー経由で「承認待ち」を把握できる。

### 技術的根拠（調査済み）

Claude Code 公式フック一覧（[公式docs](https://code.claude.com/docs/en/hooks)）に **`PermissionRequest`** フックが存在する。Yes/No 承認ダイアログが表示されるタイミングで stdin 経由に以下の JSON が渡る：

```json
{
  "hook_event_name": "PermissionRequest",
  "tool_name": "Bash",
  "tool_input": { "command": "...", "description": "..." },
  "permission_suggestions": [...],
  "session_id": "...",
  "cwd": "...",
  "transcript_path": "..."
}
```

これを既存の `UserPromptSubmit` / `Stop` フックと同じ疎結合パターン（`POST /api/avatar/speak` に投げる）で実装する。

### 要件

- Yes/No 表示時にちょびが発話
- **1分間は再発火しない**（連発防止のクールダウン）
- フック実行がダイアログ表示を遅延させないこと（`async: true`）
- サーバー未起動時は静かに失敗

---

## 方針

### A. 新規フックスクリプト

`claude-hooks/global/notify-permission.py` を新規作成し、既存の `notify-prompt.py` / `notify-stop.py` と同じ規約で書く：

- stdlib only
- 失敗時 silent
- `CLAUDE_PROJECT_DIR` からプロジェクト名を抽出（ai-twitch-cast 以外なら「承認待ち（リポジトリ名）」）
- stdin から `tool_name` / `tool_input` を読み、`detail` に整形

### B. クールダウン実装

ファイルベースの最終発火時刻で判定する（既存の `MARKER_FILE` 方式に倣う）：

- マーカー: `/tmp/claude_permission_last` — 中身は最終発火の UNIX タイムスタンプ
- 判定: `time.time() - last_fired < 60` なら **何もせず終了**
- 発火時: ファイルに現在時刻を書き込む

ファイル方式を選ぶ理由: フックは呼び出しごとに別プロセスなので、メモリ上の変数では状態を持てない。SQLite や Redis は overkill。`/tmp` の 1 ファイルで十分。

### C. 発話内容の設計

シンプルに `event_type="承認待ち"`, `detail=f"{tool_name}"` を `/api/avatar/speak` に POST する。これだけで `reader.speak_event()` が LLM 経由で一言にまとめて発話する（既存の「指示」「作業報告」と同じフロー）。

例：`{"event_type": "承認待ち", "detail": "Bash"}` → ちょびが「Bashの承認待ちだよ」的に発話。

**詳細情報（コマンド内容など）は含めない**。理由：
- 配信で機密コマンドが読み上げられないようにする（secret 誤爆防止）
- tool_name だけで何を許可すべきかはユーザーに伝わる
- 短いほど配信の邪魔にならない

### D. 設定ファイル更新

`claude-hooks/settings-global.json` に追加：

```json
"PermissionRequest": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "python3 $HOME/.claude/hooks/notify-permission.py",
        "async": true
      }
    ]
  }
]
```

### E. セットアップスクリプト更新

`scripts/setup-hooks.sh` の「グローバルフックをコピー」セクションに `cp notify-permission.py` を追加（現状 3 ファイルコピー → 4 ファイル）。

---

## 実装ステップ

1. **`claude-hooks/global/notify-permission.py` 新規作成**
   - `notify-prompt.py` のコピーをベースに作成
   - クールダウン判定ロジック追加（`/tmp/claude_permission_last`）
   - `user_prompt` ではなく `tool_name` / `tool_input` を読むよう変更
   - `event_type = "承認待ち"` に変更
   - タイマー起動ロジックは削除（Stop が面倒を見るので不要）

2. **`claude-hooks/settings-global.json` 更新**
   - `PermissionRequest` エントリ追加

3. **`scripts/setup-hooks.sh` 更新**
   - `notify-permission.py` のコピー行を追加
   - メッセージの「(3ファイル)」→「(4ファイル)」

4. **`CLAUDE.md` 更新**
   - 「作業実況」セクションに「承認待ち通知」を追記
   - 関連ファイル一覧に `notify-permission.py` 追加

5. **セットアップ実行 + 動作確認**
   - `bash scripts/setup-hooks.sh` 実行
   - 実際に承認が必要な操作（例: Bash で `rm` を含むコマンド）を試して発火を確認
   - 1 分以内に再度発火 → 無視されることを確認
   - 1 分経過後 → 再発火することを確認

6. **DONE.md / TODO.md 更新 + コミット**

---

## 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `claude-hooks/global/notify-permission.py` | 新規作成 |
| `claude-hooks/settings-global.json` | `PermissionRequest` 追加 |
| `scripts/setup-hooks.sh` | コピー対象に追加 |
| `CLAUDE.md` | 作業実況セクションに追記 |
| `~/.claude/hooks/notify-permission.py` | `setup-hooks.sh` が展開（コミット対象外） |
| `~/.claude/settings.json` | `setup-hooks.sh` がマージ（コミット対象外） |

---

## リスク / 注意点

- **クールダウン中に「重要な承認」が来たとき音が鳴らない**: 60 秒間は完全に無音になる。緊急度の高い承認（破壊的コマンド）を見落とす可能性。対策案: `tool_name == "Bash"` かつ `rm` / `force` を含む場合だけクールダウン無視、等。ただし初期実装ではシンプルに一律 60 秒で進める。
- **`/tmp` が揮発する環境**: `/tmp` はリブートで消えるが、マーカーが消えるだけなので動作上の問題なし。
- **フックの実行時間**: `async: true` なのでダイアログ表示は遅延しない。ただしフック内で `urllib.request.urlopen(timeout=3)` を使うため、タイムアウトは 3 秒以内に収まる。
- **クールダウンファイルのパーミッション**: `notify-prompt.py` と同じく root が作成する可能性があるが、`/tmp` なので衝突しない。
- **他プロジェクトでも発火する**: グローバルフックなので ai-twitch-cast 以外でも発火する。サーバー未起動時は silent fail で問題なし（既存パターンと同じ）。

---

## 代替案（検討済み・不採用）

### 代替1: ビープ音（`paplay` 等）のみ
シンプルだが、配信中にスピーカーから唐突にビープ音が鳴ると視聴者体験を損なう。キャラ発話のほうが世界観に合う。

### 代替2: `Notification` フック利用
`Notification` フックも存在するが、idle通知など Yes/No 以外のイベントでも発火する可能性がある。`PermissionRequest` のほうが意図に合致する。

### 代替3: クールダウンなし
連発すると TTS キューが詰まり、承認が終わった後もしばらく「承認待ち」発話が続く。必須。

### 代替4: クールダウン 30 秒 / 120 秒
- 30 秒: 連続承認（例: 複数ファイル編集）で連発する可能性
- 120 秒: 間が空きすぎて 2 回目の承認に気づけない
- → **60 秒で開始、様子を見てチューニング**

---

## 完了条件

- `/home/ubuntu/ai-twitch-cast` で実際に承認ダイアログが出る操作を行うと、ちょびが「承認待ち」系の発話をする
- 直後に別の承認ダイアログが出ても 60 秒以内は発話しない
- 60 秒経過後は再発話する
- サーバー停止中は silent fail（エラーログなし）
