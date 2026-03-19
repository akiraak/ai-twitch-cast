# character_memory テーブル導入 — プロンプト層データの統合

**ステータス: 完了**

## Context

5層プロンプト合成の第2層（ペルソナ）と第3層（セルフメモ）が不適切なテーブルに格納されている:

| 層 | 現在の格納先 | 問題 |
|----|-------------|------|
| 第2層 ペルソナ | `settings` テーブル (key="persona") | グローバル。キャラクター切替時に別キャラのペルソナが残る |
| 第3層 セルフメモ | `users` テーブル (name=キャラ名) | アバターを「視聴者」として扱う意味的ミスマッチ |

**注**: 両方とも SQLite に保存済みなので永続化はされている。問題はキャラクターとの紐付けがないこと。

## 変更方針

`character_memory` テーブルを新設し、キャラクターIDに紐づけて persona・self_note を管理する。

### 新テーブル: `character_memory`

```sql
CREATE TABLE IF NOT EXISTS character_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL UNIQUE REFERENCES characters(id),
    persona TEXT NOT NULL DEFAULT '',
    self_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

- `character_id` UNIQUE制約 → 1キャラクター1行
- 既存マイグレーションパターン（`CREATE TABLE IF NOT EXISTS` + try/except ALTER）に従う

### データマイグレーション

既存データを自動移行（`_create_tables()` 内で実行、冪等性を保証）:
1. `character_memory` に既にデータがあればスキップ（再実行安全）
2. `settings` テーブルの `key="persona"` → `character_memory.persona`
3. `users` テーブルのキャラ名行の `note` → `character_memory.self_note`
4. 移行後、users テーブルのキャラ行の note をクリア（行自体は comments FK + `_save_avatar_speech()` のため保持）
5. settings の persona 行は削除せず残す（安全性）

## 変更ファイル一覧

### 1. `src/db.py` — テーブル作成・マイグレーション・CRUD

`_create_tables()` に追加:
- `CREATE TABLE IF NOT EXISTS character_memory ...`
- `_migrate_character_memory(conn)` 呼び出し

新関数:
- `get_character_memory(character_id)` → `{persona, self_note, updated_at}`
- `update_character_persona(character_id, persona)`
- `update_character_self_note(character_id, self_note)`

### 2. `src/comment_reader.py` — 読み書き先の切替（4箇所）

| メソッド | 変更前 | 変更後 |
|---------|--------|--------|
| `_get_self_note()` | `db.get_or_create_user(char_name).note` | `db.get_character_memory(char_id).self_note` |
| `_update_self_note()` | `db.get_or_create_user()` + `db.update_user_note()` | `db.get_character_memory()` で現メモ取得 + `db.update_character_self_note()` |
| `_update_persona()` | `db.set_setting("persona", persona)` | `db.update_character_persona(char_id, persona)` |
| `_generate_ai_response()` | `db.get_setting("persona")` | `db.get_character_memory(char_id).persona` |

import に `get_character_id` を追加。

### 3. `scripts/routes/character.py` — `/api/character/layers` 更新

`get_character_layers()` の persona/self_note 取得を `db.get_character_memory(char_id)` に変更。

### 4. `scripts/routes/db_viewer.py` — `/api/db/update-notes` 更新

アバターメモ更新部分（L84-98）を `db.update_character_self_note()` に変更。

### 5. `tests/test_db.py` — テスト追加

- `TestCharacterMemory` クラス: get/update_persona/update_self_note/upsert
- `TestSchema.test_tables_created` に `character_memory` 追加

### 6. `static/docs/character-prompt.md` — 保存先の記述更新

第2層・第3層の「保存先」を `character_memory` テーブルに修正。

## 変更しないファイル

- `src/ai_responder.py` — `generate_response()` 等は `persona`/`self_note` を文字列引数で受け取るため変更不要
- `src/prompt_builder.py` — 同様に文字列引数のため変更不要
- `static/js/index-app.js` — APIレスポンス形状 `{persona, self_note, viewer_notes}` は変わらない
- `static/index.html` — 変更なし
- `comment_reader._save_avatar_speech()` — アバター発話のDB保存は引き続き `users` テーブルのキャラ行を使用（comments FK のため）
- `comment_reader._note_update_loop()` — `_update_self_note()` と `_update_persona()` を呼ぶだけなので変更不要

## 実装順序

1. `src/db.py` — テーブル・マイグレーション・CRUD（基盤）
2. `tests/test_db.py` — テスト追加・実行
3. `src/comment_reader.py` — 読み書き先切替
4. `scripts/routes/character.py` — API更新
5. `scripts/routes/db_viewer.py` — 手動更新API修正
6. `static/docs/character-prompt.md` — ドキュメント更新
7. 全テスト実行 → サーバー起動確認

## 検証

1. `python3 -m pytest tests/ -q` — 全テスト通過
2. サーバー再起動後 `GET /api/character/layers` で persona・self_note が返る
3. DB に `character_memory` テーブルが存在し、既存データが移行されている
4. WebUI キャラクタータブで第2層・第3層が表示される
