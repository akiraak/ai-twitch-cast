# 汎用Git開発配信機能

## 背景

現在のシステムには2つの関連機能がある：
1. **GitWatcher**: 自プロジェクト（ai-twitch-cast）のコミットを監視 → アバターが短くコメント
2. **TODO表示**: 自プロジェクトの `TODO.md` を2秒ポーリングで監視 → 配信画面のTODOパネルにリアルタイム表示

これらを拡張し、**外部の任意のGitリポジトリをcloneして、その開発の進行を実況する**機能を追加する。外部リポジトリのTODO.mdも同様に配信画面に表示する。

## ゴール

- 外部リポジトリのURLを指定してclone・監視を開始できる
- 新しいコミットを検知したら、diff内容を分析してAIが開発の進行を実況する
- **外部リポジトリのTODO.mdを配信画面のTODOパネルに表示する**（既存の自プロジェクトTODOと切り替え or 統合）
- 配信画面（overlay）にリポジトリ情報・最新コミットを表示する
- WebUIからリポジトリの追加・削除・監視ON/OFFを管理できる

## 方針

- 既存の `GitWatcher` はそのまま残す（自プロジェクト監視用）
- 新しく `DevStreamManager` クラスを作り、外部リポジトリの管理・監視を担当
- リポジトリ情報はSQLite DBに保存（再起動後も復元可能）
- AIコメンタリーは既存の `speak_event` フローに乗せる（TTS・字幕・チャット投稿すべて連動）
- **TODO表示は「TODOソース」の概念を導入** — 自プロジェクト or 外部リポジトリのTODO.mdを切り替え可能にする

## ディレクトリ構成（追加分）

```
ai-twitch-cast/
├── repos/                        # cloneした外部リポジトリ格納先
│   └── {repo_name}/             # git clone先
├── src/
│   └── dev_stream.py            # DevStreamManager（リポジトリ管理+監視+diff分析）
└── scripts/routes/
    └── dev_stream.py            # APIルート（リポジトリCRUD・監視制御）
```

## 実装ステップ

### Phase 1: リポジトリ管理基盤

**DBテーブル追加** (`src/db.py`):
```sql
CREATE TABLE IF NOT EXISTS dev_repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- 表示名（owner/repo形式）
    url TEXT NOT NULL UNIQUE,        -- clone URL
    local_path TEXT NOT NULL,        -- repos/ 以下のパス
    branch TEXT DEFAULT 'main',      -- 監視ブランチ
    last_commit_hash TEXT,           -- 最後に処理したコミットハッシュ
    active INTEGER DEFAULT 1,        -- 監視ON/OFF
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

**DB関数**:
- `add_dev_repo(name, url, local_path, branch)` → INSERT
- `get_dev_repos()` → 全リポジトリ一覧
- `get_active_dev_repos()` → active=1のリポジトリ
- `update_dev_repo_commit(id, hash)` → last_commit_hash更新
- `toggle_dev_repo(id, active)` → ON/OFF切り替え
- `delete_dev_repo(id)` → 削除

### Phase 2: DevStreamManager

**`src/dev_stream.py`**:

```python
class DevStreamManager:
    """外部Gitリポジトリの管理・監視・実況"""

    def __init__(self, on_event):
        """on_event: async def(repo_name, commits_info)"""
        self._on_event = on_event
        self._running = False
        self._task = None
        self._poll_interval = 60  # 秒

    async def add_repo(self, url, branch="main") -> dict:
        """リポジトリをcloneしてDBに登録"""
        # 1. URLからowner/repo名を抽出
        # 2. repos/{name} にgit clone
        # 3. DBに登録
        # 4. last_commit_hashを記録
        pass

    async def remove_repo(self, repo_id):
        """リポジトリを削除（ローカルファイルも削除）"""
        pass

    async def start(self):
        """全activeリポジトリの監視を開始"""
        pass

    async def stop(self):
        """監視を停止"""
        pass

    async def _watch_loop(self):
        """定期的にgit pullして新コミットを検出"""
        # 1. get_active_dev_repos()
        # 2. 各リポジトリで git fetch origin + git log
        # 3. last_commit_hash以降の新コミットを検出
        # 4. 新コミットがあればdiff分析 → on_event呼び出し
        pass

    def _analyze_commits(self, repo_path, old_hash, new_hash) -> list[dict]:
        """old_hash..new_hashの間のコミットを分析"""
        # git log old_hash..new_hash --format="%H\t%s\t%an"
        # 各コミットの git diff --stat を取得
        # 変更ファイル数・行数・主な変更内容をまとめる
        pass

    def _get_diff_summary(self, repo_path, commit_hash) -> str:
        """コミットの変更内容を要約用テキストにする"""
        # git show --stat {hash} → 変更ファイル一覧
        # git diff {hash}~1..{hash} → 差分（大きすぎる場合は先頭N行）
        pass
```

**監視フロー**:
1. 60秒ごとに各activeリポジトリを `git fetch origin` でチェック
2. `git log {last_hash}..origin/{branch} --format=...` で新コミットを検出
3. 新コミットがあれば `git merge --ff-only origin/{branch}` でローカルを更新
4. 各コミットの diff 情報を収集
5. AIに渡して実況コメントを生成 → speak_event で読み上げ

### Phase 3: AI開発実況

**`src/ai_responder.py` に追加**:

```python
def generate_dev_commentary(repo_name, commits_info):
    """開発の進行状況に対するAI実況コメントを生成する

    Args:
        repo_name: リポジトリ名
        commits_info: [{hash, message, author, diff_summary, files_changed}, ...]

    Returns:
        dict: {"response": str, "emotion": str, "english": str}
    """
```

**プロンプト設計**:
- リポジトリ名とコミット情報（メッセージ・著者・変更ファイル・diff要約）を提供
- アバターが開発者の仕事を見守りながら実況するスタイル
- 技術的な内容をわかりやすく・楽しく解説
- diff が大きい場合は要約（最大500文字程度）に制限

**既存フローとの統合**:
- `state.py` に `dev_stream_manager` を追加
- コールバックで `reader.speak_event("開発実況", detail)` を呼ぶ
- 既存のTTS・字幕・チャット投稿・感情連動がすべて動く

### Phase 4: APIルート

**`scripts/routes/dev_stream.py`**:

| Method | Path | 説明 |
|--------|------|------|
| GET | `/api/dev-stream/repos` | リポジトリ一覧 |
| POST | `/api/dev-stream/repos` | リポジトリ追加（clone） |
| DELETE | `/api/dev-stream/repos/{id}` | リポジトリ削除 |
| POST | `/api/dev-stream/repos/{id}/toggle` | 監視ON/OFF切り替え |
| POST | `/api/dev-stream/repos/{id}/check` | 手動でpull＆チェック |
| GET | `/api/dev-stream/status` | 監視状態（実行中/停止） |
| POST | `/api/dev-stream/start` | 監視開始 |
| POST | `/api/dev-stream/stop` | 監視停止 |

### Phase 5: WebUI

**`static/index.html` に「開発実況」タブ追加**:

1. **リポジトリ追加フォーム**
   - URL入力（GitHub/GitLab等）
   - ブランチ指定（デフォルト: main）
   - 「追加」ボタン → clone進行中のローディング表示

2. **リポジトリ一覧**
   - 名前・URL・ブランチ・最終コミット・状態（active/inactive）
   - ON/OFFトグルスイッチ
   - 「今すぐチェック」ボタン
   - 削除ボタン

3. **監視制御**
   - 全体の開始/停止ボタン
   - ポーリング間隔設定

### Phase 6: 外部リポジトリTODO表示

**現在の仕組み**（`scripts/routes/overlay.py`）:
- `TODO_PATH = PROJECT_DIR / "TODO.md"` を2秒ポーリングで監視
- 変更検知 → `todo_update` WebSocketイベントをbroadcast.htmlに送信
- `GET /api/todo` で `[ ]`（未着手）`[>]`（作業中）をパース

**拡張方針**: TODOソースを切り替え可能にする

1. **TODOソース管理**
   - `_todo_source` 変数を追加: `"self"` (自プロジェクト) or `"dev:{repo_id}"` (外部リポジトリ)
   - デフォルトは `"self"`（従来どおり）
   - 外部リポジトリを選択すると、そのリポジトリの TODO.md を監視対象に切り替え

2. **TODO監視の汎用化**（`overlay.py` 変更）
   - `_watch_todo_file()` を拡張: 監視対象パスを動的に切り替え
   - 外部リポジトリの場合: `repos/{name}/TODO.md` を監視
   - git fetch/pull 後にTODO更新チェックも行う（DevStreamManagerと連携）

3. **APIエンドポイント追加**
   | Method | Path | 説明 |
   |--------|------|------|
   | GET | `/api/todo/source` | 現在のTODOソースを返す |
   | POST | `/api/todo/source` | TODOソースを切り替え（`{"source": "self"}` or `{"source": "dev", "repo_id": 1}`） |

4. **WebUI統合**
   - 「開発実況」タブにTODOソース切り替えセレクトボックスを追加
   - 選択肢: 「自プロジェクト」+ 登録済み外部リポジトリ一覧
   - 切り替え時に即座にTODOパネルの内容が更新される

5. **broadcast.htmlへの影響**
   - `todo_update` イベントの形式は変わらない（items配列）
   - TODOパネルのタイトルにリポジトリ名を表示（外部リポジトリ選択時）
   - WebSocketイベントに `source` フィールド追加: `{"type": "todo_update", "items": [...], "source": "owner/repo"}`

6. **`/api/todo/start` の対応**
   - 外部リポジトリのTODO.mdも `[ ]` → `[>]` マーク変更可能
   - 変更後に `git add + git commit` は**しない**（ローカルのみ変更）
   - fetch/pull時にローカル変更がある場合は `git stash` → pull → `git stash pop` で対応

### Phase 7: Overlay表示（オプション）

**broadcast.htmlに「開発アクティビティ」パネル追加**:
- 最新のコミット情報をリアルタイム表示
- リポジトリ名・コミットメッセージ・著者を表示
- WebSocketイベント `dev_commit` で更新

## サーバーライフサイクル統合

- **startup**: `.server_state` がある場合、activeなリポジトリの監視を自動再開
- **shutdown**: `dev_stream_manager.stop()` を呼ぶ
- **Go Live**: `dev_stream_manager.start()` も呼ぶ
- **Stop**: `dev_stream_manager.stop()` も呼ぶ

## リスクと注意点

1. **ディスク容量**: 大きなリポジトリをcloneすると容量を圧迫する → `--depth 100` のshallow cloneを使用
2. **ネットワーク負荷**: 多数のリポジトリをpollすると負荷が高い → 最大10リポジトリに制限、間隔は最低30秒
3. **差分の大きさ**: 大規模なコミットのdiffは巨大になる → diff要約は最大500文字に制限
4. **プライベートリポジトリ**: SSH鍵やトークンが必要 → Phase 1ではpublicリポジトリのみ対応
5. **クールダウン**: 連続コミットの実況が配信を妨げないよう、既存の60秒クールダウン＋バッチ通知を踏襲

## 実装優先順位

1. **Phase 1-3** を最初に実装（コア機能：clone・監視・AI実況）
2. **Phase 4-5** でWebUIから操作可能に
3. **Phase 6** で外部リポジトリTODO表示を実装
4. **Phase 7** はオプション（開発アクティビティパネル）

## ステータス: 完了
