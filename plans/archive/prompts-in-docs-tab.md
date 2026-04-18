# 管理画面にpromptsを表示する

## ステータス: 完了

## 背景

管理画面の「Docs」タブでは `plans/` と `docs/` の切り替えボタンがあり、Markdownファイルを閲覧できる。同じUIで `prompts/` ディレクトリも閲覧できるようにする。

既に `prompts.py` ルートが存在し、`/api/prompts` で一覧取得・内容取得・編集・AI編集が可能だが、Docsタブには統合されていない。

## 方針

`docs_viewer.py` の `ALLOWED_DIRS` に `prompts` を追加し、フロントエンドにボタンを1つ追加する。既存の docs viewer インフラをそのまま活用する最小変更アプローチ。

prompts には既に独自の編集API（PUT, AI編集）があるが、docs タブでの表示は **閲覧のみ** とする（plans/docs と同じ扱い）。編集機能の統合は将来課題とする。

## 実装ステップ

### Step 1: バックエンド — `ALLOWED_DIRS` に `prompts` を追加
- **ファイル**: `scripts/routes/docs_viewer.py`
- `ALLOWED_DIRS = {"plans", "docs"}` → `{"plans", "docs", "prompts"}` に変更
- これだけで `/api/docs/files?dir=prompts` と `/api/docs/file?dir=prompts&name=xxx.md` が動作する

### Step 2: フロントエンド HTML — ボタン追加
- **ファイル**: `static/index.html`
- `plans` / `docs` ボタンの横に `prompts` ボタンを追加
- ID: `docs-dir-prompts`

### Step 3: フロントエンド JS — トグル処理
- **ファイル**: `static/js/admin/docs.js`
- `switchDocsDir()` で `prompts` ボタンの active 切り替えを追加
- 3つのボタン全てのトグルを汎用化

### Step 4: フロントエンド JS — タブ初期化
- **ファイル**: `static/js/admin/init.js` / `static/js/admin/utils.js`
- URLハッシュ `#docs:prompts:filename.md` が正しく動作するか確認（既存ロジックがdir名を動的に扱っていれば変更不要の可能性あり）

### Step 5: テスト
- `python3 -m pytest tests/ -q` で既存テスト通過確認
- サーバー起動して管理画面で動作確認

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `scripts/routes/docs_viewer.py` | `ALLOWED_DIRS` に `"prompts"` 追加 |
| `static/index.html` | `prompts` ボタン追加 |
| `static/js/admin/docs.js` | `switchDocsDir()` を3ボタン対応に |

## リスク

- 低リスク: 既存の仕組みに1ディレクトリを追加するだけ
- prompts API（`/api/prompts`）との機能重複があるが、用途が異なる（閲覧 vs 編集）ため問題なし
