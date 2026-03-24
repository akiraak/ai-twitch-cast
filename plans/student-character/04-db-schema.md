# Step 4: DBスキーマ + 設定

## ステータス: 未着手

## ゴール

`lesson_sections` テーブルに `dialogues` カラムを追加し、生徒キャラの設定を `settings` テーブルに保存する。

## 変更対象

| ファイル | 変更内容 |
|---------|---------|
| `src/db.py` | dialoguesカラム追加・マイグレーション・設定seed |

## 実装

### 4-1. lesson_sections に dialogues カラム追加

```sql
ALTER TABLE lesson_sections ADD COLUMN dialogues TEXT DEFAULT '';
```

`create_tables()` の CREATE TABLE と `_migrate()` の両方に追加。

### 4-2. get_lesson_sections() / save_lesson_sections() 対応

- `get_lesson_sections()`: 返り値 dict に `"dialogues"` を含める
- `save_lesson_sections()`: `section.get("dialogues")` をJSON文字列として保存

### 4-3. 生徒キャラ設定の初期値

`create_tables()` 内で `INSERT OR IGNORE`:

| キー | デフォルト値 |
|------|-------------|
| `student.enabled` | `true` |
| `student.name` | `まなび` |
| `student.voice` | `Kore` |
| `student.style` | `元気で明るい生徒のトーンで読み上げてください` |
| `student.vrm` | `""` |

## 完了条件

- [ ] `dialogues` カラムが存在し、既存DBのマイグレーションが動作する
- [ ] `get_lesson_sections()` に `dialogues` が含まれる
- [ ] `save_lesson_sections()` で `dialogues` が保存される
- [ ] 生徒設定が `settings` テーブルに存在する
- [ ] `test_db.py` にテスト追加
