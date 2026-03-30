# Claude Code CLIによる授業生成機能の追加

**ステータス: 計画中**

## Context

現在、授業の教材分析・プラン作成・スクリプト生成はすべてGemini APIで行っている（`src/lesson_generator.py`）。Claude Code CLIを代替ジェネレータとして追加し、同じ教材からGemini版とClaude版の授業を比較できるようにする。

**運用方法:**
ユーザーが `claude` を起動し「`prompts/lesson_generate.md` の手順に沿って授業を生成して」と指示 → Claude Codeが画像読み取り+生成+API経由でDB保存。通常のClaude Code開発と同じ対話的なワークフローで、途中の確認・追加指示による品質向上が可能。

**スコープ**: `lesson_generator.py` の教材・スクリプト生成のみ。チャット応答・TTS音声合成は対象外。

---

## Step 1: DBマイグレーション — `generator` カラム追加

**ファイル: `src/db.py`**

### 1-1. マイグレーション追加（`_create_tables()` 内）

```python
# lesson_sections に generator カラム追加
try:
    conn.execute("ALTER TABLE lesson_sections ADD COLUMN generator TEXT NOT NULL DEFAULT 'gemini'")
    conn.commit()
except sqlite3.OperationalError:
    pass

# lesson_plans に generator カラム追加
try:
    conn.execute("ALTER TABLE lesson_plans ADD COLUMN generator TEXT NOT NULL DEFAULT 'gemini'")
    conn.commit()
except sqlite3.OperationalError:
    pass

# lesson_plans に新しいUNIQUEインデックス追加（lesson_id, lang, generator）
try:
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_lesson_plans_lid_lang_gen ON lesson_plans(lesson_id, lang, generator)")
    conn.commit()
except sqlite3.OperationalError:
    pass
```

### 1-2. CRUD関数に `generator` パラメータ追加

全関数で後方互換を維持（`generator=None` → フィルタなし = 既存動作そのまま）

| 関数 | 変更内容 |
|------|---------|
| `add_lesson_section(...)` | `generator="gemini"` パラメータ追加、INSERT文に含める |
| `get_lesson_sections(lesson_id, lang, generator)` | `generator` 指定時はWHERE条件追加 |
| `delete_lesson_sections(lesson_id, lang, generator)` | `generator` 指定時はWHERE条件追加 |
| `upsert_lesson_plan(...)` | `generator="gemini"` パラメータ追加、SELECT/INSERT/UPDATEの条件に含める |
| `get_lesson_plan(lesson_id, lang, generator)` | `generator="gemini"` デフォルト（既存呼び出し互換） |
| `get_lesson_plans(lesson_id)` | 変更不要（SELECT * で generator含む） |

---

## Step 2: `prompts/lesson_generate.md` ワークフロー定義

**新規ファイル: `prompts/lesson_generate.md`**

Claude Code が参照する授業生成の手順書。ユーザーが `claude` セッションで「この手順に沿って授業を生成して」と指示すると、Claude Codeがこのドキュメントを読み取って作業する。

### 内容構成

1. **概要** — 教材画像から授業スクリプトを生成するワークフロー
2. **出力フォーマット（JSON Schema）** — `lesson_sections` テーブルのカラム仕様
   - `section_type`: introduction / explanation / example / question / summary
   - `emotion`: joy / excited / surprise / thinking / sad / embarrassed / neutral
   - `content`: 発話テキスト（タグなし）
   - `tts_text`: TTS入力（`[lang:xx]...[/lang]` タグ付き）
   - `display_text`: 視聴者が見る画面テキスト
   - `dialogues`: JSON配列（speaker, content, tts_text, emotion）
   - `question` / `answer`: 問題セクション用
   - `wait_seconds`: セクション間の待機秒数
3. **生成手順**
   - 画像ファイルを読み取り教材内容を理解する
   - 授業プランを策定（対象、学習目標、セクション構成）
   - 各セクションのスクリプトを生成
   - 対話形式の場合: speaker別にセリフを生成
4. **品質基準** — エンタメ性、教育効果、キャラクター一貫性
5. **キャラクター情報** — `GET /api/characters` で取得する方法
6. **結果の保存方法**
   - `POST /api/lessons/{id}/import-sections?lang=ja&generator=claude` にJSON送信

---

## Step 3: APIエンドポイント追加・修正

**ファイル: `scripts/routes/teacher.py`**

### 3-1. 新規: セクション インポートAPI

```python
class SectionImport(BaseModel):
    sections: list[dict]
    plan_summary: str | None = None

@router.post("/api/lessons/{lesson_id}/import-sections")
async def import_sections(
    lesson_id: int, body: SectionImport,
    lang: str = "ja", generator: str = "claude"
):
    """外部生成されたセクションをインポートする"""
```

処理:
1. lesson存在確認
2. セクションのフォーマット検証（section_type, emotion, content/tts_text/display_text の必須チェック）
3. 該当 (lesson_id, lang, generator) のセクション削除
4. DB保存（`generator` 付き）
5. TTS生成はオプション（別途トリガー可能）

### 3-2. 既存エンドポイント修正

**`GET /api/lessons/{lesson_id}`**: sections を generator 別にグループ化して返す

```python
# 変更前: "sections": all_sections
# 変更後: "sections": all_sections, "sections_by_generator": {"gemini": [...], "claude": [...]}
```

**`POST /api/lessons/{lesson_id}/start`**: `generator` クエリパラメータ追加

```python
async def start_lesson(lesson_id: int, lang: str = "ja", generator: str = "gemini"):
```

**`POST /api/lessons/{lesson_id}/generate-script`**: 内部の `delete_lesson_sections` / `add_lesson_section` 呼び出しに `generator="gemini"` を明示

---

## Step 4: LessonRunner 修正

**ファイル: `src/lesson_runner.py`**

### 4-1. `start()` に `generator` パラメータ追加

```python
async def start(self, lesson_id: int, lang: str = "ja", generator: str = "gemini"):
    sections = db.get_lesson_sections(lesson_id, lang=lang, generator=generator)
    self._generator = generator  # TTS キャッシュパスで使用
```

### 4-2. TTS キャッシュパスに generator を含める

```python
def _cache_path(lesson_id, order_index, part_index, lang="ja", generator="gemini"):
    return LESSON_AUDIO_DIR / str(lesson_id) / lang / generator / f"section_{order_index:02d}_part_{part_index:02d}.wav"

def _dlg_cache_path(lesson_id, order_index, dlg_index, lang="ja", generator="gemini"):
    return LESSON_AUDIO_DIR / str(lesson_id) / lang / generator / f"section_{order_index:02d}_dlg_{dlg_index:02d}.wav"
```

パス構造: `resources/audio/lessons/{lesson_id}/{lang}/{generator}/section_XX_part_YY.wav`

### 4-3. `clear_tts_cache`, `get_tts_cache_info` にも `generator` 対応

---

## Step 5: フロントエンド変更

**ファイル: `static/js/admin/teacher.js`**

### 5-1. ジェネレータ切り替えタブ

言語タブの下にジェネレータ切り替えを追加:

```
[Gemini (3 sections)] [Claude Code (5 sections)]
```

- 各タブにセクション数をバッジ表示
- 切り替えるとセクション一覧が更新
- ジェネレータ状態は `_lessonGeneratorTab[lessonId]` で管理

### 5-2. インポートUI

Claude Code タブに「JSONインポート」ボタン:
- クリック → テキストエリアのモーダル表示
- Claude Codeが出力したJSONを貼り付け
- 「インポート」→ `POST /api/lessons/{id}/import-sections?lang=XX&generator=claude`

### 5-3. 授業再生の generator 指定

「再生」ボタンクリック時に現在選択中のジェネレータを送信:
```javascript
api('POST', `/api/lessons/${id}/start?lang=${lang}&generator=${gen}`)
```

---

## 実装順序

1. **Step 1** (DB) — 既存データに影響なし、後方互換あり
2. **Step 2** (prompts/lesson_generate.md) — プロンプト指示書のみ、コード影響なし
3. **Step 3** (API) — 新規エンドポイント追加 + 既存の最小修正
4. **Step 4** (LessonRunner) — generator パラメータ透過
5. **Step 5** (Frontend) — UI追加

各ステップ完了後にテスト実行で非リグレッション確認。

---

## 修正対象ファイル一覧

| ファイル | 変更種別 |
|---------|---------|
| `src/db.py` | 修正（マイグレーション + CRUD関数） |
| `prompts/lesson_generate.md` | **新規** |
| `scripts/routes/teacher.py` | 修正（新規API + 既存API修正） |
| `src/lesson_runner.py` | 修正（generator パラメータ + キャッシュパス） |
| `static/js/admin/teacher.js` | 修正（ジェネレータUI追加） |
| `tests/test_db.py` | 修正（generatorカラムのテスト追加） |

---

## 検証方法

1. `python3 -m pytest tests/ -q` — 全テスト通過
2. サーバー起動 → 教師モードで既存Gemini生成が正常動作（リグレッションなし）
3. ターミナルで `claude` 起動 → `prompts/lesson_generate.md` に従い生成 → import-sections APIでインポート → 再生確認
4. Gemini/Claude を切り替えて同じ教材の授業を交互に再生して比較
