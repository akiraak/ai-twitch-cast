# 開発実況リポジトリ監視機能の完全削除

## 背景
開発実況のリポジトリ監視機能（clone→fetch→コミット検知→AI実況）を全削除する。
パスベースへの変更ではなく、機能自体が不要になったため。

## 方針
- dev_stream関連のコード・テスト・UI・CSSをすべて削除
- overlay内のdev_activity パネルも削除
- TODO切替（_todo_source）のdev:ルーティングも削除
- DBテーブル `dev_repos` は DROP TABLE で削除
- `repos/` ディレクトリと `.gitignore` のエントリも削除

## 削除対象ファイル（丸ごと削除）

| ファイル | 内容 |
|---------|------|
| `src/dev_stream.py` | DevStreamManager 本体 |
| `scripts/routes/dev_stream.py` | APIルート（6エンドポイント） |
| `tests/test_dev_stream.py` | ユニットテスト |
| `tests/test_api_dev_stream.py` | APIテスト |
| `repos/` ディレクトリ | cloneされたリポジトリ（akiraak-cooking-basket） |
| `plans/dev-stream.md` | 元のプランファイル |

## 編集対象ファイル（部分削除）

### 1. `src/db.py`
- `dev_repos` テーブルのCREATE TABLE文を削除
- `_ensure_tables()` にDROP TABLE IF EXISTS dev_repos を追加（既存DB対応）
- 全 dev_repo 関連関数を削除（6関数）:
  - `add_dev_repo`, `get_dev_repos`, `get_active_dev_repos`
  - `get_dev_repo`, `update_dev_repo_commit`, `toggle_dev_repo`, `delete_dev_repo`

### 2. `scripts/state.py`
- `from src.dev_stream import DevStreamManager` を削除
- `_on_dev_stream_event()` コールバックを削除
- `dev_stream_manager = DevStreamManager(...)` を削除

### 3. `scripts/web.py`
- `from scripts.routes.dev_stream import router as dev_stream_router` を削除
- `app.include_router(dev_stream_router)` を削除
- `dev_stream_manager.start()` の呼び出しを削除（startup/go_live/shutdown）

### 4. `scripts/routes/overlay.py`
- `_todo_source` 変数と `dev:` ルーティングを削除
  - `_get_todo_path()`: dev:分岐を削除、常にTODO_PATHを返す簡素化
  - `_get_todo_source_label()`: 関数ごと削除
  - `broadcast_todo()` 内のsource_label参照を削除
- `GET/POST /api/todo/source` エンドポイントを削除
- `_OVERLAY_DEFAULTS` から `dev_activity` エントリを削除
- `fixed_items` セットから `dev_activity` を削除

### 5. `scripts/routes/items.py`
- `dev_activity` の特別扱い（prefix判定）を削除

### 6. `static/index.html`
- 「開発実況」タブ全体を削除（tab-devstream セクション）
- タブナビゲーションから開発実況タブボタンを削除

### 7. `static/js/index-app.js`
- `loadDevstream()` 関数を削除
- `dsAddRepo()`, `dsSelectRepo()`, `dsToggleRepo()`, `dsCheckRepo()`, `dsDeleteRepo()` を削除
- `/api/todo/source` の呼び出しを削除
- 初期化処理のloadDevstream()呼び出しを削除

### 8. `static/broadcast.html`
- `dev-activity-panel` のHTML要素を削除

### 9. `static/js/broadcast-main.js`
- パネルレジストリから `dev-activity-panel` エントリを削除
- `dev_activity` のoverlay適用処理を削除
- `dev_commit` WebSocketイベントハンドラを削除

### 10. `static/css/broadcast.css`
- `#dev-activity-panel`, `.dev-activity-title`, `#dev-activity-content` のCSSルールを削除
- `.custom-text-color` 内の dev-activity 関連セレクタを削除

### 11. `tests/conftest.py`
- `dev_stream_manager` のモック設定を削除

### 12. `tests/test_broadcast_patterns.py`
- `dev_activity` 関連のテストケースをすべて削除:
  - `EXPECTED_ITEMS` から除外
  - `test_dev_activity_skips_visible`
  - `test_dev_activity_panel_in_css`
  - `test_dev_activity_panel_no_inline_styles`
  - パネルID→HTML IDマッピングから除外

### 13. `tests/test_overlay.py`
- `dev_activity` 関連テストを削除:
  - `visual_items` リストから除外
  - `test_dev_activity_in_overlay_defaults`
  - `test_post_saves_dev_activity`
  - overlay defaults のdev_activity検証
- `_todo_source` テスト群を削除:
  - `test_get_todo_source_label_*`
  - `test_get_todo_source_api`
  - `test_set_todo_source_*`

### 14. `tests/test_db.py`
- dev_repos関連テストがあれば削除（※grepでは未検出だが念のため確認）

### 15. `.gitignore`
- `repos/` 行を削除

## 実装順序

1. **ファイル丸ごと削除**（6ファイル + repos/）
2. **バックエンド編集**（db.py → state.py → web.py → overlay.py → items.py）
3. **フロントエンド編集**（index.html → index-app.js → broadcast.html → broadcast-main.js → broadcast.css）
4. **テスト編集**（conftest.py → test_broadcast_patterns.py → test_overlay.py → test_db.py）
5. **.gitignore 編集**
6. **テスト実行** `python3 -m pytest tests/ -q` で全パス確認
7. **サーバー起動確認**

## リスク
- DBに既存の `dev_repos` レコードがある → DROP TABLE で自動消去
- broadcast.htmlからパネルを消すとレイアウトが変わる → 他パネルに影響なし（絶対配置）
- plans/dev-stream.md を消すとDONE.mdのリンクが切れる → DONE.mdのリンクも削除

## ステータス: 完了
