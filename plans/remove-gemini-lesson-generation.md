# Gemini授業生成機能の削除（Claude Codeのみに統一）

**ステータス: 作業中（Step 5 完了）**

## 概要

授業生成（プラン生成・スクリプト生成・品質分析）をClaude Codeのみに統一し、Gemini生成機能を削除する。
授業生成に関わらない機能（TTS音声合成、AI応答、画像テキスト抽出、アバター会話デモ等）はそのまま残す。

## 現状

- 授業生成に **Gemini**（自動生成）と **Claude Code**（手動JSONインポート）の2系統がある
- UI上でジェネレータタブ（Gemini / Claude Code）を切り替えて使う
- Gemini系はプラン生成（Step 2a）、スクリプト生成（Step 2b）、品質分析（QA）を自動実行
- Claude Code系はJSONインポートのみ

## 方針

- **削除**: Gemini授業生成のバックエンド・フロントエンド・テスト
- **残す**: テキスト抽出（`extractor.py` — 画像/URL解析はClaude Codeワークフローでも使う）
- **残す**: アルゴリズム品質分析（`analyze_content` — LLM不要の指標計算）→ Claude Codeタブでも表示する
- **削除**: LLM品質分析（`analyze_content_full` — Gemini API呼び出し）
- **残す**: TTS、AI応答、アバター会話デモ（授業生成と無関係）
- **簡素化**: generatorの分岐を削除し、Claude Code固定にする
- **DB**: generatorカラムは残す（既存データの互換性維持）。スキーマのDEFAULTは変更しない（既存データとの整合性維持）。APIパラメータのデフォルトのみ `'claude'` に変更
- **既存データ**: Geminiで生成済みの授業データ（セクション・プラン・TTSキャッシュ）は引き続き表示・再生可能とする

---

## 実装ステップ

### Step 1: 共有関数の移動（dialogue.py → utils.py） ✅ 完了

**背景**: `get_lesson_characters` と `_format_character_for_prompt` は dialogue.py 内にあるが、授業生成以外（lesson_runner.py、avatar.py、teacher.py）で使われている。dialogue.py を削除する前にこれらを安全な場所に移動する。

**実施内容:**
- `get_lesson_characters()` と `_format_character_for_prompt()` を `utils.py` にコピー
- `__init__.py` のre-exportを `utils.py` から取得するよう変更（`dialogue.py` からの2関数のexportを除去）
- `dialogue.py` にはまだ元の関数が残っている（dialogue.py自身の内部利用のため。Step 2で dialogue.py ごと削除予定）
- 利用側（lesson_runner.py, avatar.py, teacher.py）は `__init__.py` 経由のため変更不要
- 全749テスト通過確認済み

### Step 2: バックエンド — lesson_generatorパッケージの整理 ✅ 完了

**削除したファイル（丸ごと）:**
- `src/lesson_generator/planner.py` — プラン生成（Gemini 3回呼び出し）
- `src/lesson_generator/script.py` — スクリプト生成v1
- `src/lesson_generator/v2.py` — スクリプト生成v2（キャラ個別LLM）
- `src/lesson_generator/dialogue.py` — 対話生成関数群（Step 1で共有関数を移動済み）
- `src/lesson_generator/director.py` — 監督レビュー
- `src/lesson_generator/structure.py` — v2セクション構造生成プロンプト

**残したファイル:**
- `src/lesson_generator/extractor.py` — テキスト抽出（画像/URL解析）は授業データ準備で使用
- `src/lesson_generator/utils.py` — `get_client`, `_parse_json_response`, `_guess_mime`, `_build_image_parts`, `_format_main_content_for_prompt`, `_is_english_mode` は extractor.py や avatar.py で使用。Step 1で `get_lesson_characters`, `_format_character_for_prompt` も追加済み

**utils.py から削除した関数:**
- `_get_knowledge_model()` — Gemini専用
- `_get_entertainment_model()` — Gemini専用
- `_get_director_model()` — Gemini専用
- `_get_dialogue_model()` — Gemini専用

**`__init__.py` を更新:**
- 削除したモジュール（planner/script/v2/dialogue/director/structure）のre-exportをすべて除去
- extractor.py と utils.py の残す関数のみ公開（`get_lesson_characters`, `_format_character_for_prompt` 含む）

**追加対応（プラン外）:**
- `scripts/routes/teacher.py` のimport文から削除関数（`generate_lesson_plan`, `generate_lesson_script`, `generate_lesson_script_from_plan`, `generate_lesson_script_v2`）を除去（モジュール削除でインポートエラーになるため前倒し対応。エンドポイント本体はStep 4で削除）

### Step 3: バックエンド — content_analyzer.pyの整理 ✅ 完了

**content_analyzer.py:**
- `analyze_content()` — アルゴリズム指標のみ → **残した**
- `analyze_content_full()` — Gemini LLM評価 → **削除した**
- `_get_director_model()` — content_analyzer.py内の独自コピー → **削除した**
- `_evaluate_with_llm()` — LLM評価本体 → **削除した**
- LLM関連のimport（`google.genai`, `gemini_client`, `os`）→ **削除した**

**追加対応（プラン外）:**
- `scripts/routes/teacher.py`: `analyze_content_full` のimport削除、2箇所の呼び出しを `analyze_content` に変更、`analyze_lesson` APIから `include_llm` パラメータ削除（モジュール削除でインポートエラーになるため前倒し対応。エンドポイント削除はStep 4で実施）
- `tests/test_content_analyzer.py`: `TestLLMEvaluation` クラス（3テスト）と `test_analyze_with_llm` を削除、`analyze_content_full` import削除、不要import（`pytest`, `unittest.mock`）削除
- `tests/conftest.py`: `src.content_analyzer` の `get_client` パッチ削除

### Step 4: バックエンド — teacher.pyのAPI整理 ✅ 完了

**削除したエンドポイント:**
- `POST /api/lessons/{id}/generate-plan` — プラン生成API（`generate_plan` 関数）
- `POST /api/lessons/{id}/generate-script` — スクリプト生成API（`generate_script` 関数）

**残したエンドポイント:**
- `PUT /api/lessons/{id}/plan` — プラン手動編集（Gemini API不使用、Claude Codeでもplan_summaryインポート可能）
- `POST /api/lessons/{id}/analyze` — 品質分析（Step 3で`analyze_content`のみに変更済み）

**簡素化したエンドポイント（APIデフォルトを`"claude"`に変更）:**
- `POST /api/lessons/{id}/start` — `generator="gemini"` → `generator="claude"` に変更
- `GET /api/lessons/{id}/tts-cache` — `generator="gemini"` → `generator="claude"` に変更
- `POST /api/lessons/{id}/import-sections` — 既に`generator="claude"`デフォルト（変更不要）
- `DELETE /api/lessons/{id}/tts-cache` — `generator=None`（変更不要、全generator対象）
- `DELETE /api/lessons/{id}/tts-cache/{order_index}` — `generator=None`（変更不要）

**import文の整理:**
- ~~`generate_lesson_plan` 等~~ → Step 2で前倒し完了
- ~~`analyze_content_full`~~ → Step 3で前倒し完了
- `StreamingResponse`, `SpeechPipeline`, `synthesize`, `_cache_path`, `_dlg_cache_path` を削除（generate-plan/generate-script削除で不要に）

**テスト修正（プラン外）:**
- `tests/test_api_teacher.py`: `test_start_lesson` と `test_get_tts_cache_empty` で `generator="claude"` を明示（APIデフォルト変更に合わせてセクション追加時のgeneratorを一致させた）

**`GET /api/lessons/{id}` レスポンス:**
- `sections_by_generator` の構造は残した（既存geminiデータ＋claudeデータ両方表示用）
- `plan` 関連のデータ（`plan_json`, `director_json`, `generations`）は表示のみ（新規生成不可）

### Step 5: フロントエンド — teacher.jsの整理 ✅ 完了

**削除したUI:**
- ジェネレータ切り替えタブ（`_buildGeneratorTabs`, `_switchLessonGenerator`）→ Claude Code固定
- `_lessonGeneratorTab` 状態管理・`_getLessonGenerator()` 関数を削除
- Step 2a: プラン生成UI全体（`generator === 'gemini'` ブロック）
- Step 2b: Gemini固有の「スクリプト生成」ボタン・入力データ表示 → Claude Codeの「JSONインポート」のみ残した
- `generatePlan()`, `generateScript()`, `_streamSSE()` 関数を削除

**変更したUI:**
- QA品質分析: `generator === 'gemini'` 条件を外し、全セクションで表示可能に
- `analyzeLesson()` 関数: `include_llm` パラメータを削除（常にアルゴリズム分析のみ）
- `_renderAnalysisResult()`: LLMスコア表示セクションを削除
- Step番号: 2a/2b → 2に統合、`_clearDownstreamSteps`の参照も更新

**デフォルト値変更:**
- `generator` を `'claude'` 固定（`_getLessonGenerator()` 削除）
- セクションフィルタ: `(s.generator || 'gemini')` → `(s.generator || 'claude')`
- バッジ表示・`startLesson`・`clearSectionCache`・`playSectionAudio`: すべて `'claude'` 固定
- 空セクションメッセージ: 「スクリプト生成を押してください」→「JSONインポートでセクションを追加してください」

**残したUI:**
- セクション一覧表示
- JSONインポート機能
- 授業再生コントロール
- TTSキャッシュ管理
- 既存Geminiデータのバッジカウント表示（G:N/C:N）

### Step 6: テストの整理 — 前倒し完了（対象なし）

以下すべて前のStepで対応済み:
- ~~`tests/test_lesson_generator.py`~~ → Step 2時点で既に存在しない（モジュール削除でテストも除去済み）
- ~~`tests/test_content_analyzer.py` のLLMテスト~~ → Step 3で前倒し完了
- ~~`tests/test_api_teacher.py` の `test_generate_plan`/`test_generate_script`~~ → Step 4で前倒し完了（エンドポイント削除に合わせてテストも除去済み）
- ~~`generatorデフォルト値のテスト修正`~~ → Step 4で `test_start_lesson` と `test_get_tts_cache_empty` を修正済み

**残っているテスト（変更不要）:**
- `tests/test_api_teacher.py` の `import-sections`, `start`, `tts-cache` テスト
- `tests/test_lesson_runner.py` — 授業再生テスト
- `tests/test_content_analyzer.py` の `analyze_content`（アルゴリズム分析）テスト
- `tests/conftest.py` の `mock_gemini`（ai_responder/tts等で引き続き使用）・`src.lesson_generator` パッチ（extractor.pyで使用）

### Step 7: クリーンアップ

- `prompts/lesson_generate.md` — 変更不要（Claude Code用マニュアル）
- 環境変数の整理（`.env.example`）:
  - 削除: `GEMINI_KNOWLEDGE_MODEL`, `GEMINI_ENTERTAINMENT_MODEL`, `GEMINI_DIRECTOR_MODEL`, `GEMINI_DIALOGUE_MODEL`
  - 残す: `GEMINI_API_KEY`（TTS/AI応答で使用）, `GEMINI_CHAT_MODEL`, `GEMINI_TOPIC_MODEL`, `GEMINI_TTS_MODEL`
- `conftest.py` の Gemini モック:
  - `src.lesson_generator` と `src.lesson_generator.utils` のパッチは残す（extractor.pyがget_clientを使用）
  - ~~`src.content_analyzer` のパッチは `analyze_content_full` 削除後に不要なら除去~~ → Step 3で完了済み
- CLAUDE.md のディレクトリ構成・テスト表を更新

---

## 影響を受けるファイル一覧

| ファイル | 操作 | 備考 |
|---------|------|------|
| `src/lesson_generator/dialogue.py` | 削除 | 共有関数はStep 1でutils.pyに移動済み |
| `src/lesson_generator/planner.py` | 削除 | プラン生成 |
| `src/lesson_generator/script.py` | 削除 | スクリプト生成v1 |
| `src/lesson_generator/v2.py` | 削除 | スクリプト生成v2 |
| `src/lesson_generator/director.py` | 削除 | 監督レビュー |
| `src/lesson_generator/structure.py` | 削除 | セクション構造プロンプト |
| `src/lesson_generator/__init__.py` | 修正 | re-export整理（削除モジュール除去、utils.pyの新関数追加） |
| `src/lesson_generator/utils.py` | 修正 | 不要モデル選択関数削除 + `get_lesson_characters`/`_format_character_for_prompt`追加 |
| `src/lesson_generator/extractor.py` | 残す | テキスト抽出は継続使用 |
| `src/content_analyzer.py` | 修正 | `analyze_content_full` + `_get_director_model()` + LLM import削除 |
| `scripts/routes/teacher.py` | 修正 | generate-plan/generate-script削除、analyzeからLLM除去、generatorデフォルト変更 |
| `static/js/admin/teacher.js` | 修正 | Gemini UI削除、Claude Code固定、QAをgenerator非依存に、デフォルト値変更 |
| `scripts/routes/avatar.py` | 確認 | インポートパスは__init__.py経由で変更不要 |
| `src/lesson_runner.py` | 確認 | インポートパスは__init__.py経由で変更不要 |
| `tests/test_lesson_generator.py` | 削除 | Gemini生成テスト全体 |
| `tests/test_content_analyzer.py` | 修正 | LLM評価テスト削除 |
| `tests/test_api_teacher.py` | 修正 | plan/script APIテスト削除、analyzeテスト修正 |
| `tests/conftest.py` | 修正 | 不要モック削除 |
| `.env.example` | 修正 | 不要環境変数削除 |
| `TODO.md` / `DONE.md` | 更新 | タスク記録 |
| `CLAUDE.md` | 更新 | ディレクトリ構成・テスト表 |

## リスク

- **既存データの表示**: generator='gemini'の既存セクション/プランはDBに残る。sections_by_generatorで見えるが、新規生成はできなくなる。デフォルト値が'claude'に変わるため、UIで既存Geminiデータを見るにはsections_by_generatorの全generator表示が必要
- **関数移動の漏れ**: Step 1の`get_lesson_characters`移動が不完全だとlesson_runner（授業再生）とavatar（会話デモ）が壊れる。__init__.pyのre-export更新を忘れないこと
- **品質分析の精度**: `analyze_content`（アルゴリズムのみ）はTODO.mdで「数値が体感と違って高すぎる」と指摘済み。LLM評価を削除するとさらに精度が下がる可能性がある

## 確認事項

- [ ] 全テスト通過
- [ ] サーバー起動確認
- [ ] 管理画面で授業一覧表示
- [ ] Claude CodeでJSONインポート → 授業再生が動作
- [ ] 既存Gemini生成データの授業が表示・再生できる
- [ ] アバター会話デモ（`/api/debug/conversation-demo/generate`）が動作する
- [ ] 品質分析がClaude Codeインポート後のセクションで動作する
