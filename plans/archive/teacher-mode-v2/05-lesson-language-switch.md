# 授業の言語切替対応プラン

ステータス: 完了

## コンテキスト

英語のみモード対応（`plans/english-only-mode.md` ✅完了）により、LLMプロンプト・TTS・チャット応答が言語切替に対応した。しかし現在のデータモデルでは **1つの授業に1つのプラン・スクリプト・音声** しか保存できず、言語を切り替えると既存データが上書きされる。

**ゴール**: 1つの授業コンテンツに対して **日本語版（バイリンガル）と英語版を並行保存** し、授業開始時にどちらで再生するか選べるようにする。

## 方針

- **言語は "ja"（バイリンガル）と "en"（英語のみ）の2種類** を対象
- 教材テキスト（`extracted_text`）とソース画像は言語共通（翻訳はLLMが行う）
- プラン・スクリプト・TTS音声を言語別に保存
- UIで言語タブ切替 → 各言語でプラン生成・スクリプト生成 → 授業開始時に言語選択
- **既存DBデータの移行**: 既存データは `lang="ja"` として扱う

## 修正対象

### 1. DB スキーマ変更（`src/db.py`）

**1a. `lesson_plans` テーブル新設**

現在 `lessons` テーブルに直置きの `plan_knowledge`, `plan_entertainment`, `plan_json` を、言語別テーブルに移動。

```sql
CREATE TABLE IF NOT EXISTS lesson_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    lang TEXT NOT NULL DEFAULT 'ja',
    knowledge TEXT NOT NULL DEFAULT '',
    entertainment TEXT NOT NULL DEFAULT '',
    plan_json TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(lesson_id, lang)
);
```

**1b. `lesson_sections` テーブルに `lang` カラム追加**

```sql
ALTER TABLE lesson_sections ADD COLUMN lang TEXT NOT NULL DEFAULT 'ja';
```

**1c. DB関数の追加・修正**

| 関数 | 変更内容 |
|------|----------|
| `get_lesson_plan(lesson_id, lang)` | 新規。指定言語のプランを返す |
| `upsert_lesson_plan(lesson_id, lang, knowledge, entertainment, plan_json)` | 新規。INSERT OR REPLACE |
| `get_lesson_sections(lesson_id, lang=None)` | langパラメータ追加。Noneなら全言語 |
| `add_lesson_section(lesson_id, ..., lang="ja")` | langパラメータ追加 |
| `delete_lesson_sections(lesson_id, lang=None)` | langパラメータ追加。Noneなら全言語 |
| `get_lesson(lesson_id)` | プラン情報を lesson_plans テーブルから取得するよう変更 |

**1d. マイグレーション**

- `lessons` テーブルの既存 `plan_*` データを `lesson_plans` (lang="ja") に移行
- `lesson_sections` の既存データに `lang="ja"` を設定
- `lessons` テーブルの `plan_*` カラムはそのまま残す（段階削除。参照は新テーブル優先）

### 2. TTS音声の言語別保存（`src/lesson_runner.py`）

**現在**: `resources/audio/lessons/{lesson_id}/section_{order:02d}_part_{part:02d}.wav`

**変更後**: `resources/audio/lessons/{lesson_id}/{lang}/section_{order:02d}_part_{part:02d}.wav`

修正箇所:
- `lesson_runner.py` の `_get_cache_path()` / 音声パス生成
- `scripts/routes/teacher.py` のTTSキャッシュ削除・一覧
- プラン/スクリプト生成時のTTSプリジェネレート

### 3. API変更（`scripts/routes/teacher.py`）

| エンドポイント | 変更内容 |
|---------------|----------|
| `GET /api/lessons/{id}` | レスポンスに `plans: {ja: {...}, en: {...}}` と `sections` に `lang` フィールド追加 |
| `POST /api/lessons/{id}/generate-plan` | `lang` パラメータ追加。指定言語で生成 → `lesson_plans` に保存 |
| `PUT /api/lessons/{id}/plan` | `lang` パラメータ追加 |
| `POST /api/lessons/{id}/generate-script` | `lang` パラメータ追加。指定言語のセクション+TTSを生成 |
| `POST /api/lessons/{id}/start` | `lang` パラメータ追加。その言語のセクションで授業開始 |
| `GET /api/lessons/{id}/tts-cache` | `lang` パラメータ追加 |
| `DELETE /api/lessons/{id}/tts-cache` | `lang` パラメータ追加 |

生成時の動作:
1. API受信 → `lang` パラメータ取得（デフォルト "ja"）
2. `set_stream_language()` を一時的に切替
3. `lesson_generator` でプラン/スクリプト生成
4. DB保存時に `lang` を付与
5. 元の言語設定に復元

### 4. LessonRunner変更（`src/lesson_runner.py`）

- `start(lesson_id, lang="ja")`: 指定言語のセクションのみロード
- 音声キャッシュパスに `lang` を含める
- ステータスに `lang` フィールド追加

### 5. lesson_generator変更（`src/lesson_generator.py`）

- `generate_lesson_plan()`, `generate_lesson_script()`, `generate_lesson_script_from_plan()` に `lang` パラメータ追加
- 関数内で `set_stream_language()` を呼ぶ代わりに、**呼び出し元（teacher route）が設定** → 既存の `_is_english_mode()` がそのまま使える
- 変更不要（呼び出し元のteacher routeで制御）

### 6. WebUI変更（`static/js/admin/teacher.js`）

**6a. 言語タブ追加**

各レッスンのプラン・スクリプト領域に言語タブを追加:

```
[🇯🇵 日本語] [🇺🇸 English]
```

- タブ切替でプラン表示・セクション表示が切り替わる
- 各タブに「プラン生成」「スクリプト生成」ボタン
- 生成済みかどうかをバッジ表示（✅ / 未生成）

**6b. 授業開始ダイアログ**

「授業開始」ボタン押下時、生成済みの言語が複数あればダイアログで選択:

```
どの言語で授業を始めますか？
[🇯🇵 日本語で開始]  [🇺🇸 Englishで開始]
```

生成済みが1言語のみならダイアログなしで即開始。

**6c. ステータス表示**

レッスン一覧のサマリに言語バッジ表示:
- `[JA ✅] [EN ✅]` — 両方生成済み
- `[JA ✅] [EN -]` — 日本語のみ

## 実装順序

1. DB スキーマ変更 + マイグレーション（`src/db.py`）
2. TTS 音声パスの言語対応（`src/lesson_runner.py`）
3. API 変更（`scripts/routes/teacher.py`）
4. WebUI 言語タブ + 授業開始ダイアログ（`static/js/admin/teacher.js`）
5. テスト追加（`tests/test_db.py`, `tests/test_api_teacher.py`）

## 対象外（意図的にスキップ）

| 項目 | 理由 |
|------|------|
| 教材テキストの言語別翻訳 | 教材はソースが1つ。LLMが言語に合わせて授業を生成する |
| 2言語以上の対応 | 現時点では ja/en の2言語で十分 |
| チャット応答の言語切替 | 既に `POST /api/language` で対応済み。授業とは独立 |

## 検証方法

1. `python3 -m pytest tests/ -q` — 全テスト通過
2. 既存レッスンがマイグレーション後も正常に表示・再生できること（lang="ja"）
3. 英語でプラン生成 → 英語スクリプト → 英語TTS音声が別保存されること
4. 日本語版と英語版を切り替えて授業開始できること
5. 片方のTTSキャッシュを消してももう片方に影響しないこと
6. 日本語モードのプラン→英語モードでスクリプト再生成が正しく動作すること
