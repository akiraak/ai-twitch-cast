# Gemini授業生成機能の削除（Claude Codeのみに統一）

**ステータス: 作業中（Step 2 完了）**

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

### Step 3: バックエンド — content_analyzer.pyの整理

**content_analyzer.py:**
- `analyze_content()` — アルゴリズム指標のみ → **残す**
- `analyze_content_full()` — Gemini LLM評価 → **削除**
- `_get_director_model()` — content_analyzer.py内の独自コピー → `analyze_content_full` と共に **削除**
- LLM関連のimport（`google.genai`, `gemini_client`）は`analyze_content_full`削除後に不要なら除去

### Step 4: バックエンド — teacher.pyのAPI整理

**削除するエンドポイント:**
- `POST /api/lessons/{id}/generate-plan` — プラン生成API（`generate_plan` 関数, 413行〜）
- `POST /api/lessons/{id}/generate-script` — スクリプト生成API（`generate_script` 関数, 534行〜）

**残すエンドポイント:**
- `PUT /api/lessons/{id}/plan` — プラン手動編集（Gemini API不使用、Claude Codeでもplan_summaryインポート可能）
- `POST /api/lessons/{id}/analyze` — 品質分析（`include_llm`パラメータを削除し、`analyze_content`のみ使用に変更）

**簡素化するエンドポイント（APIデフォルトを`"claude"`に変更）:**
- `POST /api/lessons/{id}/import-sections` — 既に`generator="claude"`デフォルト（変更不要）
- `POST /api/lessons/{id}/start` — `generator="gemini"` → `generator="claude"` に変更
- `GET /api/lessons/{id}/tts-cache` — `generator="gemini"` → `generator="claude"` に変更
- `DELETE /api/lessons/{id}/tts-cache` — `generator=None`（変更不要、全generator対象）
- `DELETE /api/lessons/{id}/tts-cache/{order_index}` — `generator=None`（変更不要）

**import文の整理:**
- ~~`generate_lesson_plan`, `generate_lesson_script`, `generate_lesson_script_from_plan`, `generate_lesson_script_v2` のimport削除~~ → Step 2で前倒し完了
- `analyze_content_full` のimport削除

**`GET /api/lessons/{id}` レスポンス:**
- `sections_by_generator` の構造は残す（既存geminiデータ＋claudeデータ両方表示用）
- `plan` 関連のデータ（`plan_json`, `director_json`, `generations`）は表示のみ（新規生成不可）

### Step 5: フロントエンド — teacher.jsの整理

**削除するUI:**
- ジェネレータ切り替えタブ（`_buildGeneratorTabs`, `_switchLessonGenerator`）→ Claude Code固定
- `_lessonGeneratorTab` 状態管理を削除
- Step 2a: プラン生成UI（`generator === 'gemini'` ブロック全体、lines 310-469）
- Step 2b: Gemini固有の「スクリプト生成」ボタン・入力データ表示（`generator === 'gemini'` ブロック）→ Claude Codeの「JSONインポート」のみ残す
- `generatePlan()`, `generateScript()` 関数

**変更するUI:**
- QA品質分析: `generator === 'gemini'` 条件を外し、Claude Codeインポート後のセクションにも表示
- `analyzeLesson()` 関数: `include_llm` パラメータを削除（常にアルゴリズム分析のみ）

**デフォルト値変更:**
- `_getLessonGenerator()` のデフォルト: `'gemini'` → `'claude'`（line 26）
- セクションフィルタ: `(s.generator || 'gemini')` → `(s.generator || 'claude')`（line 131）
- バッジ表示: generator別バッジのデフォルトも同様に変更

**残すUI:**
- セクション一覧表示（Step 3相当）
- JSONインポート機能
- 授業再生コントロール（Step 4）
- TTSキャッシュ管理
- 既存Geminiデータの閲覧（sections_by_generatorで表示される）

### Step 6: テストの整理

**削除:**
- `tests/test_lesson_generator.py` — Gemini LLM呼び出しのモックテスト全体
  - `generate_lesson_plan` テスト
  - `generate_lesson_script` テスト
  - `generate_lesson_script_v2` テスト
  - dialogue/director テスト
- `tests/test_content_analyzer.py` の `analyze_content_full` テスト（`test_llm_evaluation`, `test_llm_error_handling`, `test_llm_score_clamping`, `test_analyze_with_llm`）
- `tests/test_api_teacher.py` の以下テスト:
  - `test_generate_plan`, `test_generate_plan_no_text`, `test_generate_plan_not_found`
  - `test_generate_script`, `test_generate_script_with_rejection`, `test_generate_script_no_text`, `test_generate_script_uses_plan`

**残す:**
- `tests/test_api_teacher.py` の `import-sections`, `start`, `tts-cache` テスト
- `tests/test_lesson_runner.py` — 授業再生テスト
- `tests/test_content_analyzer.py` の `analyze_content`（アルゴリズム分析）テスト
- `tests/conftest.py` の `mock_gemini`（ai_responder/tts等で引き続き使用）

**修正:**
- generatorデフォルト値変更に合わせてテストのパラメータ修正
- `get_lesson_characters` のテストがtest_lesson_generator.pyにある場合、移動先に合わせて新テスト作成

### Step 7: クリーンアップ

- `prompts/lesson_generate.md` — 変更不要（Claude Code用マニュアル）
- 環境変数の整理（`.env.example`）:
  - 削除: `GEMINI_KNOWLEDGE_MODEL`, `GEMINI_ENTERTAINMENT_MODEL`, `GEMINI_DIRECTOR_MODEL`, `GEMINI_DIALOGUE_MODEL`
  - 残す: `GEMINI_API_KEY`（TTS/AI応答で使用）, `GEMINI_CHAT_MODEL`, `GEMINI_TOPIC_MODEL`, `GEMINI_TTS_MODEL`
- `conftest.py` の Gemini モック:
  - `src.lesson_generator` と `src.lesson_generator.utils` のパッチは残す（extractor.pyがget_clientを使用）
  - `src.content_analyzer` のパッチは `analyze_content_full` 削除後に不要なら除去
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
