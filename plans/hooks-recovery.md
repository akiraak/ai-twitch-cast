# Claude Code フック復旧可能化プラン

## 背景

Claude Codeのフック（`~/.claude/hooks/`）は、キャラクターが配信中にClaude Codeの作業状況を実況する重要な機能を担う。しかし、これらのスクリプトとsettings.jsonの設定はGitリポジトリの外（`~/.claude/`）にあるため、PC環境が変わると失われる。

**現在の状況**: `~/.claude/hooks/` ディレクトリが存在しない。`~/.claude/settings.json` にもフック設定がない。すべて失われている。

## 現在のフック構成（復旧対象）

### グローバルフック（`~/.claude/hooks/`）
| ファイル | イベント | 役割 |
|---------|--------|------|
| `notify-stop.py` | Stop | 作業完了報告 → `/api/avatar/speak` + マーカー削除 + タイマー停止 |
| `notify-prompt.py` | UserPromptSubmit | 指示受信報告 → `/api/avatar/speak` + マーカー作成 + タイマー起動 |
| `long-execution-timer.py` | (バックグラウンド) | 3分以上の長時間実行時に定期報告（transcript解析） |

### プロジェクトローカルフック（`.claude/hooks/`）
| ファイル | イベント | 役割 |
|---------|--------|------|
| `fix-permissions.sh` | PostToolUse | Claude Code（root）が編集したファイルの所有者を `ubuntu:ubuntu` に修正 |

### 設定ファイル
| ファイル | 内容 |
|---------|------|
| `~/.claude/settings.json` | グローバルフック登録（Stop, UserPromptSubmit）+ `async: true` |
| `.claude/settings.local.json` | プロジェクトローカルフック登録（PostToolUse）+ permissions |

## 設計方針

### 原則: リポジトリに正本を持ち、セットアップスクリプトで展開

1. **フックスクリプトの正本をリポジトリ内に保存** — `claude-hooks/global/` と `claude-hooks/local/`
2. **settings.jsonのフック設定テンプレートも保存** — `claude-hooks/settings-global.json`, `claude-hooks/settings-local.json`
3. **ワンコマンドで復旧できるセットアップスクリプト** — `scripts/setup-hooks.sh`
4. **シンボリックリンクではなくコピー** — `~/.claude/hooks/` はグローバル領域なのでコピーの方が安全（他リポジトリのフックと混在しない）

### 疎結合の維持

既存の疎結合設計（plans/archive/claude-code-narration.md）を維持する:
- フックスクリプトは **stdlib only**（プロジェクトモジュールのimportなし）
- `async: true` で非ブロッキング実行
- サーバー未起動時は静かに失敗

## ディレクトリ構成

```
ai-twitch-cast/
├── claude-hooks/
│   ├── global/                          # ~/.claude/hooks/ にコピーされる
│   │   ├── notify-stop.py              # Stopフック
│   │   ├── notify-prompt.py            # UserPromptSubmitフック
│   │   └── long-execution-timer.py     # 長時間実行タイマー
│   ├── local/                           # .claude/hooks/ にコピーされる
│   │   └── fix-permissions.sh          # PostToolUseフック
│   ├── settings-global.json             # ~/.claude/settings.json のフック部分テンプレート
│   └── settings-local.json              # .claude/settings.local.json のフック部分テンプレート
└── scripts/
    └── setup-hooks.sh                   # セットアップスクリプト
```

## 実装ステップ

### Step 1: フックスクリプトの再作成とリポジトリ保存

アーカイブされたプラン（`plans/archive/`）を基に、以下の4ファイルを `claude-hooks/` に作成:

#### `claude-hooks/global/notify-stop.py`
- Stop時に `last_assistant_message` を `/api/avatar/speak` に送信（event_type: "作業報告"）
- `CLAUDE_PROJECT_DIR` からプロジェクト名を抽出（ai-twitch-cast以外は「作業報告（リポジトリ名）」）
- `/tmp/claude_working` マーカー削除
- `long-execution-timer.py` を `pkill` で停止
- 10文字未満の短い応答はスキップ

#### `claude-hooks/global/notify-prompt.py`
- UserPromptSubmit時にユーザーの指示テキストを `/api/avatar/speak` に送信（event_type: "指示"）
- `/tmp/claude_working` マーカーファイル作成（`start_time` + `transcript_path`）
- 既存タイマーを停止してから `long-execution-timer.py` をバックグラウンド起動
- `CLAUDE_PROJECT_DIR` からプロジェクト名を抽出

#### `claude-hooks/global/long-execution-timer.py`
- 3分待機後、`/tmp/claude_working` マーカーの存在を確認
- transcript_pathの末尾20行からツール使用を解析して直近の作業内容を取得
- `/api/avatar/speak` に「Claude Codeが○分作業中。直近の作業: ○○」と報告
- 3分間隔で繰り返し
- transcript未更新2分でアイドル判定 → マーカー削除して終了
- `/tmp/claude_watcher_active` が存在する場合（ClaudeWatcherが稼働中）はスキップ

#### `claude-hooks/local/fix-permissions.sh`
- Claude Code（root）が作成・編集したファイルの所有者を `ubuntu:ubuntu` に変更
- `chown ubuntu:ubuntu` を対象ファイルに適用

### Step 2: 設定テンプレートの作成

#### `claude-hooks/settings-global.json`
```json
{
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

#### `claude-hooks/settings-local.json`
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/fix-permissions.sh"
          }
        ]
      }
    ]
  }
}
```

### Step 3: セットアップスクリプト作成

`scripts/setup-hooks.sh`:
- グローバルフック: `claude-hooks/global/*` → `~/.claude/hooks/` にコピー
- ローカルフック: `claude-hooks/local/*` → `.claude/hooks/` にコピー
- `~/.claude/settings.json` にフック設定をマージ（既存の `effortLevel` 等を保持しつつ `hooks` を追加/上書き）
- `.claude/settings.local.json` にフック設定をマージ（既存の `permissions` を保持しつつ `hooks` を追加）
- 実行権限の付与
- 冪等（何度実行しても同じ結果）

### Step 4: CLAUDE.md・TODO.md 更新

- CLAUDE.md の「作業実況」セクションに `claude-hooks/` ディレクトリの説明を追加
- セットアップ手順を記載: `bash scripts/setup-hooks.sh`
- TODO.md から該当タスクを削除、DONE.md に追加

## リスク

| リスク | 対策 |
|-------|------|
| settings.json のマージで既存設定が壊れる | `jq` でマージ。バックアップも作成 |
| フックスクリプトの内容が古い | アーカイブプラン + CLAUDE.md を正とし、ClaudeWatcherとの共存も考慮 |
| セットアップスクリプトの冪等性 | 上書きコピー + マージで対応 |

## ステータス: 完了
