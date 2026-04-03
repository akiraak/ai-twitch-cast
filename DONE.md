# DONE

## 授業パネルサイズのセクション別制御

- [x] セクションごとに `display_properties`（maxHeight/width/fontSize）を指定可能に → [plans/lesson-panel-size-control.md](plans/lesson-panel-size-control.md)
  - DB: `lesson_sections` に `display_properties` カラム追加
  - API: セクション更新・インポート・改善で対応
  - 授業再生: WebSocketイベントに `display_properties` を含めてフロント側で一時適用
  - 管理画面: セクション別パネルサイズ設定UI、注釈UIリデザイン（モーダル入力）
  - AIプロンプト: コンテンツ量別サイズガイドライン追加
  - テスト: DB・API・LessonRunner 計125行追加
- [x] 全800テスト通過

## Claude Watcher 完了（全7ステップ）

- [x] Claude Code作業実況の二人会話機能 → [plans/claude-watcher-conversation.md](plans/claude-watcher-conversation.md)
  - Step 1: TranscriptParser（JSONL差分解析・サマリ生成）
  - Step 2: ClaudeWatcherサービス（監視ループ・再生・割り込み対応）
  - Step 3: 会話生成プロンプト（作業実況→二人会話スクリプト生成）
  - Step 4: CommentReader統合（コメント割り込み対応）
  - Step 5: long-execution-timerとの共存（フラグチェック追加）
  - Step 6: 管理画面UI（ステータス表示・間隔設定）
  - Step 7: テスト（会話生成12テスト追加、合計57テスト）
- [x] 全793テスト通過

## Claude Watcher Step 4: CommentReader統合

- [x] `src/comment_reader.py` にClaudeWatcher統合
  - `__init__` でClaudeWatcherインスタンス作成（SpeechPipeline共有、comment_reader=selfで割り込み判定）
  - `claude_watcher` プロパティ追加
  - `start()` で `asyncio.create_task(self._claude_watcher.start())` 起動
  - `stop()` で `await self._claude_watcher.stop()` + タスクキャンセル
- [x] `tests/test_claude_watcher.py` に統合テスト6件追加（合計45テスト）
  - ClaudeWatcher保持・参照渡し・SpeechPipeline共有・start/stop連動・queue_size参照
- [x] 全781テスト通過

## Claude Watcher Step 3: 会話生成プロンプト

- [x] `src/ai_responder.py` に `generate_claude_work_conversation()` 追加
  - 作業実況専用プロンプトを独自構築（キャラ設定・感情・言語ルール）
  - 作業コンテキスト（ユーザー指示・直近10アクション・Claudeメモ3件・経過時間）をユーザープロンプトとして送信
  - `_validate_multi_response()` でspeaker/emotion検証（既存再利用）
  - 日本語/英語の両言語モード対応
  - 前回会話の直近4発話で繰り返し防止
- [x] `src/claude_watcher.py` の `_generate_conversation()` を実装接続
  - `get_chat_characters()` でキャラ設定取得
  - `asyncio.to_thread()` で同期LLM呼び出しを非ブロッキング実行
  - エラー時は `None` 返却（発話スキップ）
- [x] `plans/claude-watcher-conversation.md` ステータス更新（Step 3 完了）
- [x] 全775テスト通過

## Claude Watcher Step 2: ClaudeWatcherサービス

- [x] `src/claude_watcher.py` に `ClaudeWatcher` クラス追加
  - `/tmp/claude_working` マーカーファイルのポーリング監視（10秒間隔）
  - `/tmp/claude_watcher_active` フラグ管理（long-execution-timer抑制）
  - セッション変更検出・パーサー自動リセット
  - `_check_and_converse()`: transcript差分解析 → アクション数判定 → 会話生成（Step 3待ち）
  - `_play_conversation()`: 順次再生 + コメント割り込み対応（queue_sizeチェック）
  - DB保存（trigger_type="claude_work"）、statusプロパティ
- [x] `tests/test_claude_watcher.py` に20テスト追加（合計39テスト）
  - ライフサイクル: start/stop/フラグ作成・削除/二重start/状態リセット
  - マーカー検出: ファイル検出・消失リセット・セッション変更
  - check_and_converse: 変化なし/アクション不足/十分なアクション/会話再生
  - play_conversation: 全発話再生/コメント割り込み/DB保存/エラー中断
  - status: アイドル/アクティブ/is_active
- [x] 全775テスト通過

## Claude Watcher Step 1: TranscriptParser

- [x] `src/claude_watcher.py` 新規作成 — TranscriptParser + TranscriptSummary
  - JSONL差分解析（前回位置記憶、新しい行のみ処理）
  - ユーザー指示抽出（isMeta/command/tool_resultスキップ）
  - ツール使用を人間可読な説明に変換（Bash/Edit/Write/Read/Grep/Glob/Agent等）
  - アシスタントテキスト応答抽出
  - 不正JSON行の個別スキップ、パース成功率50%未満で警告+None
  - 未知typeスキップ（フォーマット変更耐性）
- [x] `tests/test_claude_watcher.py` 新規作成（19テスト）
- [x] 全755テスト通過
- [x] プランステータスを「Step 1 完了」に更新

## TTS事前生成 Step 6: テスト（プラン完了）

- [x] `tests/test_tts_pregenerate.py` 新規作成（18テスト）
  - _generate_one: 正常生成・失敗・voice/style渡し
  - _parse_dialogues: v4形式・リスト形式・空・student_cfgなし・不正JSON
  - pregenerate_section_tts: 単話者・キャッシュヒット・対話モード・キャンセル・空content・リトライ・tts_textオーバーライド
  - pregenerate_lesson_tts: 全セクション一括・進捗コールバック・キャンセル・セクション0件
- [x] `tests/test_api_teacher.py` にTTS事前生成APIテスト追加（10テスト）
  - tts-pregen-status: idle・not found・running状態
  - tts-pregen: 手動トリガー・not found
  - tts-pregen-cancel: タスクなし・not found・version未指定・実行中キャンセル
- [x] 全736テスト通過
- [x] プランステータスを「完了」に更新

## TTS事前生成 Step 5: フロントエンド進捗表示・手動トリガー/キャンセルUI

- [x] TTS一括生成ボタンをバージョンセレクターに追加
- [x] 進捗バーUI（生成中スピナー・プログレスバー・完了/エラー表示・中止ボタン）
- [x] 3秒間隔ポーリングで進捗自動更新（完了時5秒後フェードアウト+一覧リロード）
- [x] import_sections / improve_content 完了後に自動ポーリング開始
- [x] レッスン展開時に実行中タスクがあればポーリング自動再開
- [x] triggerTtsPregen / cancelTtsPregen API呼び出し関数

## TTS事前生成 Step 3: import_sections / improve_content に統合

- [x] `import_sections` のreturn前に `_start_tts_pregeneration()` 呼び出し追加
- [x] `improve_content` のreturn前に `_start_tts_pregeneration()` 呼び出し追加
- [x] 両APIレスポンスに `"tts_pregeneration_started": True` を追加
- [x] 全112教師モードテスト通過

## TTS事前生成 Step 1: `src/tts_pregenerate.py` 新規作成

- [x] TTS事前生成コアモジュール作成（`src/tts_pregenerate.py`）
- [x] `pregenerate_lesson_tts()` — 全セクション一括生成（キャンセル・進捗コールバック対応）
- [x] `pregenerate_section_tts()` — 単話者/対話モード分岐、キャッシュ判定、1回リトライ
- [x] LessonRunnerと同じキャッシュパス・voice/style処理で互換性保証
- [x] 全708テスト通過

## 教師モード カテゴリUI再設計 — Step 4: テスト・動作確認 + UX改善（プラン完了）

- [x] 全708テスト通過（教師モード112テスト含む）
- [x] カテゴリを独立カードとして教師モードの上に配置
- [x] カテゴリ0件時は「カテゴリがありません」+ 目立つ追加ボタン表示
- [x] カテゴリ作成を1画面フォーム化（旧3ステップモーダルを廃止、名前のみ入力でslug自動生成）
- [x] カテゴリなしでは授業コンテンツを作成できないようガード追加
- [x] 授業作成時にカテゴリ選択を必須化（ドロップダウン + コンテンツ名の1画面フォーム）
- [x] プランステータスを「完了」に更新

## 教師モード カテゴリUI再設計 — Step 3: CSSスタイリング + インラインスタイル→CSSクラス移行

- [x] カテゴリタブバーのCSSクラス追加（`.cat-tabs`, `.cat-tab`, `.cat-tab.active`, `.cat-tab--action`, `.cat-tab--manage`）
- [x] 学習セクション・ダッシュボードカードのCSSクラス追加（`#learning-section`, `.learning-header`, `.learning-card`, `.learning-btn--*`, `.learning-detail`）
- [x] 横スクロール対応（薄いスクロールバー）、hover/active状態追加
- [x] JS側インラインスタイルをCSSクラス参照に全面置換
- [x] 全708テスト通過

## 教師モード カテゴリUI再設計 — Step 2: 学習ダッシュボードの教師モード内統合

- [x] サブタブ「学習」を削除し、学習ダッシュボードを教師モード内コンテンツ一覧の下に統合
- [x] `_renderLearningSection()` 新設 — コンテンツ一覧末尾に学習セクション描画
- [x] `loadLearningsDashboard()` を選択カテゴリでフィルタ連動するよう修正
- [x] `switchConvSubtab()` から `learnings` 分岐を削除

## 教師モード カテゴリUI再設計 — Step 1: カテゴリタブバー新設 + カテゴリ管理モーダル化

- [x] カテゴリタブバー（「全て」+ 各カテゴリ + 「+ 新規」+ 「⚙ 管理」）を教師モード上部に新設
- [x] カテゴリ選択でレッスン一覧をフィルタ表示
- [x] カテゴリ管理をモーダルダイアログ化（旧 `<details>` 折りたたみを置換）
- [x] カテゴリ追加時のエラーハンドリング改善
- [x] 学習パターン（prompts/learnings/_common.md）のリセット

## 授業コンテンツ バージョニング — Step 7: テスト&動作確認（機能完了）

- [x] 全708テスト通過
- [x] 手動テスト全項目OK: カテゴリCRUD、バージョンコピー/切替、注釈、整合性チェック（verify）、部分改善（improve）、差分確認、学習分析→ファイル書き出し、プロンプト改善提案
- [x] プランステータスを「完了」に更新

## 授業コンテンツ バージョニング — Step 6: UI実装

- [x] カテゴリ管理UI（折りたたみ一覧 + 追加/削除）+ レッスンヘッダーにカテゴリselect
- [x] バージョンセレクタ（Step 3先頭: バージョンボタン列、メモ編集、コピー/削除、改善メタ表示）
- [x] セクション注釈UI（◎良い/△要改善/✕作り直し ボタン + コメントinput）
- [x] 整合性チェック: verifyボタン → coverage/contradictions表示 + プロンプト・raw_output折りたたみ
- [x] 部分改善: 改善元version選択 + 対象セクションcheckbox + 追加指示 → 新version自動切替
- [x] バージョン差分比較: 2version間のsection-by-section grid差分表示
- [x] 学習ダッシュボード（新サブタブ「学習」: 注釈統計、分析実行、学習結果表示、プロンプト改善提案→適用/却下）
- [x] LLM呼び出し全文表示ヘルパー `_buildLlmCallDisplay()` （CLAUDE.md準拠）
- [x] 全708テスト通過（UI変更のためバックエンドテストへの影響なし）

## 授業コンテンツ バージョニング — Step 5: 授業再生エンジン対応

- [x] TTSキャッシュパスをバージョン別サブディレクトリ `v{N}/` に変更（3段階フォールバック: v{N}/ → generator直下 → lang直下）
- [x] `clear_tts_cache()` に `version_number` パラメータ追加（特定バージョンのみ削除可能）
- [x] `get_tts_cache_info()` に `version_number` パラメータ追加
- [x] `LessonRunner` に `_version_number` 保持、`get_status()` に含む
- [x] TTSキャッシュAPI・セクション編集/削除で `version` パラメータ対応
- [x] テスト +12件追加（全708通過）

## 授業コンテンツ バージョニング — Step 4: 学習ループAPI

- [x] カテゴリ別パターン分析API（POST /api/lessons/analyze-learnings）— 注釈付きセクション収集→AIパターン抽出→学習ファイル＆DB保存
- [x] プロンプト改善diff生成API（POST /api/lessons/improve-prompt）— 学習結果からプロンプト改善差分を生成
- [x] プロンプト改善適用API（POST /api/lessons/apply-prompt-diff）— diff指示に従いプロンプトファイルを更新
- [x] カテゴリ専用プロンプト作成API（POST /api/lessons/categories/{slug}/create-prompt）— 共通プロンプトをベースにカテゴリ特化版を生成
- [x] 学習結果ファイル出力（prompts/learnings/配下にカテゴリ別・共通のMDファイル）
- [x] 分析用・改善用プロンプトテンプレート追加（prompts/lesson_analyze.md, lesson_improve_prompt.md）
- [x] テスト +45件追加（全696通過）

## 授業コンテンツ バージョニング — Step 3: 検証&部分改善API

- [x] verify/improveエンドポイント + improverモジュール + テスト20件追加

## 授業コンテンツ バージョニング — Step 2: API実装

- [x] カテゴリCRUD API（GET/POST/DELETE /api/lesson-categories）
- [x] バージョンCRUD API（GET/POST/PUT/DELETE /api/lessons/{id}/versions/...、copy_from対応）
- [x] セクション注釈API（PUT /api/lessons/{id}/sections/{sid}/annotation）
- [x] GET /api/lessons/{id} に versions 一覧追加 + ?version=N フィルタ
- [x] import-sections: version未指定→新バージョン自動作成、指定→置換
- [x] start: version省略時は最新バージョン自動選択（後方互換維持）
- [x] lesson/lesson_update に category フィールド対応
- [x] lesson_runner.start() に version_number パラメータ追加
- [x] テスト +27件追加（全651通過）

## 授業コンテンツ バージョニング — Step 1: DBスキーマ & マイグレーション

- [x] `lesson_categories` テーブル作成（slug, name, description, prompt_file）
- [x] `lessons` に `category` カラム追加
- [x] `lesson_versions` テーブル作成（verify_json, improve_source_version 等含む）
- [x] `lesson_sections` に `version_number`, `annotation_rating`, `annotation_comment` 追加
- [x] `lesson_plans` に `version_number` 追加 + UNIQUE制約変更（テーブル再作成方式）
- [x] `lesson_learnings` テーブル作成
- [x] 既存データから `lesson_versions` v1 自動生成マイグレーション
- [x] CRUD関数追加（カテゴリ・バージョン・注釈・学習）+ 既存関数に version_number 対応
- [x] テスト追加（+30テスト、全624通過）

## 品質チェック機能削除
- [x] content_analyzer.py・テスト・プランファイル削除
- [x] teacher.py: analyzeエンドポイント・import削除
- [x] db: analysis_jsonカラムのマイグレーション・allowed削除
- [x] teacher.js: Step 4（品質チェック）UI・関数・ランクバッジ削除、旧Step 5→新Step 4に繰り上げ

## 教師モードUI一新 — 4ステップ化 + インライン生成フロー

- [x] CSS追加（インポートエリア・CLIコマンド・成功バナー・ステップ左ボーダー）
- [x] teacher.js: buildLessonItem()を4ステップに分割（生成/セクション確認/再生）
- [x] インラインJSONインポート（モーダル→textarea直貼り）
- [x] CLIコマンドコピー機能
- [x] モードA/B切替（未作成時=インポートUI、作成済み=成功バナー）
- [x] index.html キャッシュバスト更新

## Claude Code授業生成ドキュメント化 + プロンプト管理UI

- [x] `scripts/routes/prompts.py` 新規作成（GET一覧/GET取得/PUT更新/POST AI編集の4エンドポイント）
- [x] `scripts/web.py` にルーター登録
- [x] teacher.js Step 2 にガイド折りたたみ + プロンプト表示・AI編集UI
- [x] diff表示用CSS（`static/css/index.css`）
- [x] `docs/speech-generation-flow.md` から削除済みGeminiフロー除去 + Claude Codeフロー記述
- [x] `prompts/lesson_generate.md` のGemini共存記述削除

## アバターパラメータ保存抜け根本修正

- [x] `GET /api/overlay/settings`がDBの全プロパティをマージするよう修正（`_OVERLAY_DEFAULTS`に無いキーも返す）
- [x] avatar1/avatar2のデフォルトに全パラメータ（headTilt, scale, idle系）を追加
- [x] フロントエンド3箇所のハードコードidleKeysリストを除去（settings.js, avatar-renderer.js, settings-panel.js）
- [x] 今後はスキーマにパラメータ追加するだけで保存→復元が自動的に動く

## English 1-1 授業コンテンツ生成

- [x] 教材画像読み取り（Kenjiの自己紹介・Section B穴埋め・Culture Note）
- [x] 授業スクリプト生成（8セクション: 導入→読解2回→文法整理→実践→文化理解→クイズ2回→まとめ）
- [x] APIでDBにインポート（lesson_id=168, lang=ja, generator=claude）
- [x] teacher.jsバグ修正: プラン表示で`langPlan`→`plans[lang]`に修正（プラン情報が正しく渡されていなかった）

## Gemini授業生成削除 Step 7: クリーンアップ

- [x] `.env.example` から授業モード役割別モデル環境変数4つを削除（GEMINI_KNOWLEDGE/ENTERTAINMENT/DIRECTOR/DIALOGUE_MODEL）
- [x] CLAUDE.md: lesson_generatorのディレクトリ構成を更新（パッケージ化 → extractor.py + utils.py）
- [x] CLAUDE.md: テスト表からtest_lesson_generator.py（削除済み）を除去
- [x] プランファイルのステータスを「完了」に更新

## Gemini授業生成削除 Step 5: teacher.jsフロントエンド整理

- [x] ジェネレータタブ削除（`_buildGeneratorTabs`, `_switchLessonGenerator`, `_lessonGeneratorTab`, `_getLessonGenerator`）
- [x] Step 2a プラン生成UI全体を削除（約160行）
- [x] Step 2bのGemini分岐削除（入力データ表示・スクリプト生成ボタン）→ Claude Code JSONインポートのみ
- [x] `generatePlan()`, `generateScript()`, `_streamSSE()` 関数を削除
- [x] QA品質分析: `generator === 'gemini'`条件を除去、「＋LLM評価」ボタン削除、`_renderAnalysisResult`のLLMスコア表示削除
- [x] デフォルト値 `'gemini'` → `'claude'` に統一（セクションフィルタ・バッジ・startLesson・clearSectionCache・playSectionAudio）
- [x] Step番号 2a/2b → 2 に統合、`_clearDownstreamSteps`参照も更新
- [x] Step 6（テスト整理）は前倒し完了済みのため対象なし

## Gemini授業生成削除 Step 4: teacher.py API整理

- [x] `generate_plan` エンドポイント（POST /api/lessons/{id}/generate-plan）を削除
- [x] `generate_script` エンドポイント（POST /api/lessons/{id}/generate-script）を削除
- [x] 不要import削除（StreamingResponse, SpeechPipeline, synthesize, _cache_path, _dlg_cache_path）
- [x] `start_lesson` / `get_tts_cache` のgeneratorデフォルトを "gemini" → "claude" に変更
- [x] テスト修正: test_start_lesson / test_get_tts_cache_empty で generator="claude" を明示

## Gemini授業生成削除 Step 3: content_analyzer.py整理

- [x] `analyze_content_full`, `_get_director_model`, `_evaluate_with_llm` を削除
- [x] LLM関連import（`google.genai`, `gemini_client`, `os`）を削除
- [x] teacher.py: `analyze_content_full` → `analyze_content` に変更、`include_llm`パラメータ削除（Step 4から前倒し）
- [x] test_content_analyzer.py: LLMテスト4件削除（Step 6から前倒し）
- [x] conftest.py: `src.content_analyzer` の `get_client` パッチ削除（Step 7から前倒し）

## Gemini授業生成削除 Step 2: lesson_generatorパッケージ整理

- [x] planner.py / script.py / v2.py / dialogue.py / director.py / structure.py を削除（-2,396行）
- [x] utils.py からGemini専用モデル関数4個を削除
- [x] `__init__.py` から削除モジュールのre-exportを除去
- [x] teacher.py のimport文から削除関数を前倒し除去
- [x] test_lesson_generator.py を削除（削除モジュールのテスト、Step 6から前倒し）
- [x] test_api_teacher.py からgenerate_plan/generate_scriptテスト7件を削除（Step 6から前倒し）

## Claude Code授業生成: 動作確認・バグ修正

- [x] `teacher.js` インポート成功トーストの `res.imported` → `res.count` バグ修正
- [x] Step 2a（プラン生成）をGeminiタブのみ表示に変更
- [x] QA（品質分析）をGeminiタブのみ表示に変更
- [x] Step 2bラベルのtypo修正（「スクリプ生成」→「スクリプト生成」）
- [x] プランステータスを「完了」に更新

## Claude Code授業生成 Step 5: フロントエンド変更（全Step完了）

- [x] ジェネレータ切り替えタブ追加（言語タブの下に `[Gemini (N)] [Claude Code (N)]`）
- [x] セクション表示をlang+generatorでフィルタ、ヘッダーバッジにgenerator情報追加
- [x] Claude Codeタブに「JSONインポート」ボタン+テキストエリアモーダル追加
- [x] `showModal` に `textarea`/`placeholder` オプション追加（`utils.js`）
- [x] 授業再生 `startLesson()` にgeneratorパラメータ追加
- [x] TTSキャッシュ取得・削除・セクション再生にgeneratorパラメータ追加
- [x] プランステータスを「完了」に更新

## Claude Code授業生成 Step 4: LessonRunner修正

- [x] `_cache_path` / `_dlg_cache_path` に `generator` パラメータ追加（新パス `{lang}/{generator}/` + gemini旧パスフォールバック）
- [x] `clear_tts_cache` に `generator` パラメータ追加（`None`=全ジェネレータ、指定時はそのgeneratorのみ）
- [x] `get_tts_cache_info` に `generator` パラメータ追加（新パス+レガシーパスの重複排除スキャン）
- [x] `LessonRunner` に `self._generator` 保持（start/stop/完了時にセット・リセット）
- [x] `get_status()` に `generator` フィールド追加
- [x] `teacher.py`: TTSキャッシュAPI 3エンドポイントに `generator` クエリパラメータ追加
- [x] テスト追加（レガシーフォールバック・新パス優先・generator別キャッシュ削除など10件）

## Claude Code授業生成 Step 3: APIエンドポイント追加・修正

- [x] `POST /api/lessons/{id}/import-sections` 新規追加（フォーマット検証・generator指定・dialogues JSON変換）
- [x] `GET /api/lessons/{id}` に `sections_by_generator` レスポンス追加
- [x] `POST /api/lessons/{id}/start` に `generator` クエリパラメータ追加
- [x] `POST /api/lessons/{id}/generate-script` — `generator="gemini"` 明示（delete/add）
- [x] `POST /api/lessons/{id}/generate-plan` — `generator="gemini"` 明示（upsert）
- [x] `LessonRunner.start()` に `generator` パラメータ追加（Step 4-1 先取り）
- [x] テスト追加（7件: インポートCRUD・バリデーション・generator共存・sections_by_generator）

## Claude Code授業生成 Step 2: ワークフロー定義

- [x] `prompts/lesson_generate.md` 新規作成（Claude Codeが授業スクリプトを生成する手順書）

## Claude Code授業生成 Step 1: DBマイグレーション

- [x] `lesson_sections` に `generator` カラム追加（デフォルト: `'gemini'`）
- [x] `lesson_plans` テーブル再作成で `generator` カラム追加 + UNIQUE制約を `(lesson_id, lang, generator)` に変更
- [x] CRUD関数に `generator` パラメータ追加（後方互換維持）
- [x] テスト追加（generator別セクション・プランのCRUD）

## リファクタリング Phase 1: lesson_generator.py パッケージ化

- [x] `src/lesson_generator.py`（2,666行）を `src/lesson_generator/` パッケージに分割
  - `utils.py` — モデル選択、JSONパース、画像/コンテンツ整形
  - `extractor.py` — テキスト抽出・前処理・画像/URL解析
  - `dialogue.py` — キャラクター取得、プロンプト構築、セリフ個別生成
  - `structure.py` — セクション構造設計プロンプト構築
  - `director.py` — ディレクター評価（セリフレビュー）
  - `planner.py` — 三者視点プラン生成
  - `script.py` — スクリプト生成（v1 + from_plan）
  - `v2.py` — v2パイプライン（構造→セリフ→レビュー→再生成）
  - `__init__.py` — 全公開関数 + 内部関数の re-export（import互換維持）
- [x] 未使用 import `base64` を削除

## リファクタリング Phase 2: db.py パッケージ化

- [x] `src/db.py`（2,138行）を `src/db/` パッケージに分割
  - `core.py` — 接続管理・マイグレーション・channels/characters/shows/episodes/users/comments/settings/character_memory
  - `audio.py` — BGM・SE トラック CRUD
  - `lessons.py` — レッスン（教師モード）CRUD
  - `items.py` — ブロードキャストアイテム・カスタムテキスト・キャプチャウィンドウ CRUD + アイテム移行関数
  - `__init__.py` — 全公開関数 + 移行関数の re-export（import互換維持）
- [x] `conftest.py` の `test_db` フィクスチャを `src.db.core` パッチに更新
- [x] `conftest.py` の `mock_gemini` を submodule 対応に更新
- [x] 全725テスト通過確認

## リファクタリング Phase 3: ai_responder.py キャラクター管理分離

- [x] `src/character_manager.py` 新規作成 — キャラクターライフサイクル管理（12関数+定数+キャッシュ）
  - `get_channel_id()` — `_get_channel_id()` を公開化
  - `seed_character()`, `seed_all_characters()` — DB初期化
  - `build_character_context()`, `build_all_character_contexts()` — コンテキスト構築
  - `load_character()`, `get_character()`, `get_character_id()` — キャッシュ付きキャラ取得
  - `get_all_characters()`, `get_chat_characters()`, `get_tts_config()` — 各種取得
  - `invalidate_character_cache()` — キャッシュ無効化
  - `DEFAULT_CHARACTER`, `DEFAULT_STUDENT_CHARACTER` — デフォルト定数
- [x] `ai_responder.py` を応答生成に集中（re-export で import 互換維持）
- [x] `_build_comment_context()` + `_build_timeline_contents()` でmulti/singleコンテキスト構築の重複解消
- [x] 外部呼び出し元（comment_reader, lesson_generator/dialogue, db/core）を `character_manager` に直接import
- [x] 未使用 `from pathlib import Path` 削除
- [x] 全725テスト通過確認

## リファクタリング Phase 4: overlay.py TODO操作ロジック抽出

- [x] `scripts/services/todo_service.py` 新規作成 — TODO操作ロジック
  - `get_active_source()`, `get_files()` — TODOソース管理
  - `get_in_progress()`, `set_in_progress()` — 作業中状態の読み書き
  - `parse_todo_text()` — TODOテキストパース
  - `get_items()` — プロジェクトファイル or DB からアイテム取得
  - `start_task()`, `stop_task()` — タスクの開始/停止（ファイル書き戻し含む）
  - `upload_file()`, `switch_source()`, `delete_file()` — ファイル管理
- [x] `overlay.py` のルートハンドラを薄くした（todo_service への委譲のみ）
- [x] 不要な import（`re`, `secrets`）を削除
- [x] テストのパッチ先を `scripts.services.todo_service` に更新
- [x] 全725テスト通過確認

## リファクタリング Phase 5: 未使用 import の削除

- [x] `scripts/routes/teacher.py` の `LESSON_AUDIO_DIR` import 削除
- [x] 全725テスト通過確認

## ドキュメントページのリロード時ファイル選択状態復元

- [x] URL hashにdir+file情報を保存（`#docs:plans:filename.md` 形式）
- [x] ページロード時にhashからdir/fileを復元しファイル内容を再表示
- [x] ディレクトリ切替・タブ切替時もhashを適切に更新

## Docsファイルリスト表示改善

- [x] APIにファイルタイトル抽出追加（1行目の`# Title`）
- [x] ファイルリストを2行表示（タイトル＋ファイル名）
- [x] サブディレクトリ（archive等）を折りたたみ表示
- [x] ソート順を修正日時の新しい順に変更
- [x] サイドバー幅拡大＋スクロール対応

## アバター体の向き設定＋見回しモーション

- [x] Step 1: `_get_item_type` バグ修正（avatar1/avatar2 → "avatar" マッピング）
- [x] Step 2: avatarスキーマに `bodyAngle` スライダー追加
- [x] Step 3: `_OVERLAY_DEFAULTS` に `bodyAngle` デフォルト値追加
- [x] Step 4: `AvatarInstance` にsetBodyAngle() + 見回しgaze system追加
- [x] Step 5: `applySettings()` でbodyAngle適用（settings.js）
- [x] Step 6: 設定パネルのスライダー即時反映（settings-panel.js）
- [x] プラン完了（全6 Step）
- [x] bodyAngle回転バグ修正: Math.PIベースに加算（VRMの正面方向を考慮）
- [x] 管理画面に固有スキーマ注入（layout.js: _injectCommonProps async化）
- [x] VRMロード後のbodyAngle再適用（module実行順序問題の修正）
- [x] _savedOverlaySettingsをwindowに公開
- [x] 待機モーションパラメータ調整UIプラン作成
- [x] Step 1: avatarスキーマに待機モーションスライダー追加（8パラメータ）
- [x] Step 2: AvatarInstanceにパラメータ変数（7種）＋setIdleParams() setter追加
- [x] Step 3: animate()でハードコード値をインスタンス変数に置換（breathScale/swayScale/gazeRange/headScale/armAngle/armScale/earFreq）
- [x] Step 4: applySettings()でavatar1/avatar2の待機パラメータをsetIdleParams()で適用
- [x] Step 5: 設定パネルのスライダー操作で待機モーションパラメータ即時反映（settings-panel.js）
- [x] Step 6: VRMロード後に保存済み待機モーションパラメータを再適用（avatar-renderer.js initAvatar）
- [x] 顔の上下（headTilt）設定追加 — 固有設定にスライダー（-30°〜+30°）、即時反映・DB保存・VRMロード後再適用

## speech-generation-flow.md 同期

- [x] Step 1: 授業フロー図にテキスト抽出→クリーニング→メインコンテンツ識別ステップを追記
- [x] Step 2: Phase B-1 に `_format_main_content_for_prompt()` の上限ルール（2000文字/200文字）・🔊マーカー条件を追記
- [x] Step 3: Phase B-2 に `GEMINI_DIALOGUE_MODEL` 環境変数（フォールバックチェーン含む）を追記
- [x] Step 4: Phase B-3 レビュー観点を6→8に更新（🔊読み上げ網羅性 + 🔊導入チェック追加）
- [x] Step 5: イベント応答の `generate_multi_event_response()` 戻り値から `se` を削除
- [x] Step 6: キャラクター設定テーブルのなるこ `tts_voice` を Aoede → Kore に修正
- [x] Step 7: `apply_emotion()` に gesture パラメータと EMOTION_GESTURES マッピングの説明を追記
- [x] Step 8: 環境変数一覧セクション追加（全6モデル環境変数のフォールバックチェーン・用途・使用箇所）
- [x] プラン完了（全8 Step）

## メインコンテンツ読み上げ機能

- [x] Step 1: `_EXTRACT_MAIN_CONTENT_PROMPT` に `read_aloud` フィールド追加 + `_normalize_roles()` でデフォルト補完
- [x] Step 2: `_format_main_content_for_prompt()` の切り詰め緩和（read_aloud=true+main→全文2000文字、🔊マーカー付与）
- [x] Step 3: `_build_structure_prompt()` に🔊読み上げ指示追加（EN/JP両方、原文忠実使用・role分担・direction引用指示）
- [x] Step 4: `_director_review()` に🔊読み上げ対象レビュー観点追加（EN/JP両方、省略・意訳は不合格）
- [x] Step 5: テスト追加（read_aloud: normalize_roles/extract/format/structure_prompt/director_review 全20件）
- [x] Step 6: `_build_structure_prompt()` の🔊読み上げ指示に自然な導入パターン追加（EN/JP両方、文脈説明→役割分担→読み上げの3段階指示+dialogue_plan構成例）
- [x] Step 7: `_director_review()` のレビュー観点に🔊読み上げ導入チェック追加（EN/JP両方、導入なし→不合格）
- [x] Step 8: Phase 2テスト追加（導入パターン指示5件 + 導入チェック観点4件、計9件）

## UI/UXバグ修正

- [x] teacher.js: プラン未生成でもスクリプト音声生成ボタンが押せる問題を修正
- [x] teacher.js: 「キャ���設定」の文字化け修正（UTF-8バイト破損）
- [x] stream.sh: Windows コマンド（taskkill/tasklist）のCP932出力をUTF-8変換

## メインコンテンツ階層化（主要/補助の役割分け）

- [x] Step 1: `_normalize_roles()` ヘルパー追加 + `extract_main_content()` 更新
- [x] Step 2: `_EXTRACT_MAIN_CONTENT_PROMPT` に role 指示追加
- [x] Step 3: `_format_main_content_for_prompt()` に ★主要/補助タグ付与
- [x] Step 4: `_build_structure_prompt()` に優先度ガイダンス追加
- [x] Step 5: `_director_review()` にロール対応レビュー基準追加
- [x] Step 6: Teacher UI に主要/補助の視覚区別追加（★マーク・太枠・黄色背景）
- [x] Step 7: テスト更新・追加（`TestNormalizeRoles` 新規、全テストにrole対応）
- [x] ドキュメント更新（speech-generation-flow.md）

## セクション間つながり改善（全Step完了）

- [x] Step 1: ヘルパー関数 `_build_adjacent_sections()` 追加
- [x] Step 2: `_generate_single_dialogue()` に前後セクション情報注入（EN/JA）
- [x] Step 3: `_generate_section_dialogues()` にパラメータ追加
- [x] Step 4: `section_worker()` / `regen_worker()` で隣接情報構築・渡し
- [x] Step 5: 監督 Phase A プロンプトにつなぎ指示追加（EN/JA）
- [x] Step 6: テスト追加（10件: ヘルパー4件 + プロンプト注入6件）

## 授業スコアをタイトルに表示

- [x] 管理画面の授業一覧タイトルにランクバッジ+スコアを表示（teacher.js）
- [x] ランク色背景＋白文字で視認性確保（S=金, A=緑, B=青, C=橙, D=赤）

## 管理画面Docs閲覧機能（完了）

- [x] Step 1: バックエンドAPI（docs_viewer.py 新規: ファイル一覧 + 内容取得、パストラバーサル対策）
- [x] Step 2: ルート登録（web.py に docs_viewer_router 追加）
- [x] Step 3: フロントエンドUI（Docsタブ + docs.js + utils.js TAB_NAMES追加）
- [x] Step 3.5: UIレイアウト改善（サイドバー化 + スクロール委譲）
- [x] Step 4: テスト（test_api_docs_viewer.py 新規: 9テスト）、全680テスト通過

## Phase B-5でLLM評価を自動実行（Phase 2 完了）

- [x] Step 5: `analyze_content` → `asyncio.run(analyze_content_full(...))` に切り替え（lesson_generator.py）
- [x] Step 6: teacher.py フォールバックも `analyze_content_full` に統一
- [x] Step 7: テスト更新（analyze_content_fullモック化、引数検証、llm_scores確認）、全671テスト通過

## 品質分析をパイプライン内に完全統合（2c完了）

- [x] Step 1: Phase B-5追加（lesson_generator.py に analyze_content() 組み込み）
- [x] Step 2: 戻り値変更（`return result` → `return {"sections": result, "analysis": analysis.to_dict()}`）
- [x] Step 3: teacher.py 呼び出し側更新（v2/非v2分岐 + 埋め込みanalysis利用 + フォールバック）
- [x] Step 4: テスト追加（v2戻り値形式テスト + APIテストのanalysis検証）、全669テスト通過

## 品質分析の自動実行（サーバー側）

- [x] `lessons`テーブルに`analysis_json`カラム追加（DB永続化）
- [x] スクリプト生成完了時にアルゴリズム分析を自動実行→DB保存（`teacher.py` `event_stream()`内）
- [x] 手動分析（アルゴリズム/LLM評価）の結果もDB保存
- [x] 管理画面ページ表示時にDB保存済み分析結果を自動描画（`_renderAnalysisResult()`切り出し）
- [x] 全668テスト通過

## コンテンツ品質分析モード（数値化）

- [x] アルゴリズム指標エンジン（`src/content_analyzer.py` 新規: カバー率・対話バランス・構成多様性・クイズ充実度・ペーシング、50点満点）
- [x] LLM評価エンジン（エンタメ性・教育効果・キャラ活用・構成力を1コールで評価、50点満点）
- [x] APIエンドポイント（`POST /api/lessons/{id}/analyze` を `scripts/routes/teacher.py` に追加）
- [x] 管理画面UI（`static/js/admin/teacher.js` に品質分析QAステップ・プログレスバー・ランク表示追加）
- [x] テスト38件（`tests/test_content_analyzer.py` 新規）、全668テスト通過
- [x] プラン → [plans/content-quality-analyzer.md](plans/content-quality-analyzer.md)（完了）

## speech-generation-flow.md 全面改訂

- [x] 現状コードとの乖離20箇所を調査・特定 → [plans/speech-generation-flow-audit.md](plans/speech-generation-flow-audit.md)
- [x] docs/speech-generation-flow.md を全面改訂（520行→約450行、行番号参照を全削除し関数名のみで参照）
- [x] 主な修正: Phase B-3/B-4（監督レビュー・再生成）追加、content_type対応追加、感情BlendShapeの適用タイミング修正、LLMモデル名更新、直接発話APIの仕様修正、戻り値にtts_text/se追加、generate_response()関数名修正

## メインコンテ��ツ読み上げ方式改善 Step 6（自動テスト完了）

- [x] 全自動テスト630件通過確認
- [x] 本機能で追加したテスト計32件（クリーニング18 + コンテンツ識別5 + API 3 + 構造プロンプト3 + 監督レビュー3）

## メインコンテンツ読み上げ方式改善 Step 5

- [x] 管理画面（teacher.js）のレッスン詳細STEP 1にメインコンテンツ折りたたみ表示を追加
- [x] 種別ごとにアイコン・色分け（💬会話/📄文章/📝単語/📊表）

## メインコンテンツ読み上げ方式改善 Step 4

- [x] `_director_review()` に `main_content` パラメータ追加、種別レビュー観点（EN/JA）をシステムプロンプトに追加
- [x] ユーザープロンプトにも事前分析済みメインコンテンツ情報を追加
- [x] テスト3件追加（`TestDirectorReviewMainContent`）

## メインコンテンツ読み上げ方式改善 Step 3

- [x] `_build_structure_prompt()` に `main_content` パラメータ追加、種別ルール（EN/JA）をシステムプロンプトに統合
- [x] `generate_lesson_script_v2()` → teacher.py の呼び出しチェーンで `main_content` を DB から渡す
- [x] テスト3件追加（main_content あり/なし、英語/日本語）

## メインコンテンツ読み上げ方式改善 Step 2

- [x] `extract_main_content()` を `src/lesson_generator.py` に追加（LLMでcontent_type判定）
- [x] `lessons` テーブルに `main_content` TEXT カラム追加（マイグレーション）
- [x] `extract-text` / `add-url` APIでテキスト抽出後に自動識別・DB保存
- [x] テスト8件追加（`TestExtractMainContent` 5件 + API 3件）

## メインコンテンツ読み上げ方式改善 Step 1

- [x] `clean_extracted_text()` を `src/lesson_generator.py` に追加（正規表現ベース、LLM不要）
- [x] `extract_text_from_image()` / `extract_text_from_url()` の return でクリーニング適用
- [x] テスト18件追加（`TestCleanExtractedText`）

## 再生成過程の管理画面表示

- [x] 再生成前の元セリフを `original_dialogues` として dialogues JSON に保存
- [x] `revised_directions`（監督の修正指示）を review データに保存
- [x] 管理画面に再生成過程を折りたたみ表示（修正指示・元セリフ・生成プロンプト）
- [x] 不合格→再生成ケースのテスト追加（`test_generate_script_with_rejection`）

## 監督レビュー + display_text 読み上げ強化 Step 2〜7

- [x] Step 2: display_text[:200] 切り詰め撤廃（全文をキャラクターAIに渡す）
- [x] Step 3: `_director_review()` 新設（Phase B-3: 監督レビュー）
- [x] Step 4: Phase B-4 再生成ロジック（不合格セクションのみ再生成、1回のみ）
- [x] Step 5: `generate_lesson_script_v2()` に Phase B-3/B-4 統合
- [x] Step 6: レビュー結果の保存（dialogues JSON内review埋め込み）・管理画面表示（teacher.js）
- [x] Step 7: SSE 進捗表示更新（レビュー中・再生成中のメッセージ追加）
- [x] lesson_runner/teacher.pyのdialoguesパース互換対応（新旧JSON形式の両方をサポート）
- [x] テスト更新（レビューレスポンスのモック追加、dialogues新形式の検証）

## 監督レビュー + display_text 読み上げ強化 Step 1

- [x] 監督プロンプト（英語・日本語）に display_text 読み上げルール追加（key_content 分配ルール）
- [x] `_build_structure_prompt()`（英語・日本語）にも同ルール追加（dialogue_plan direction 分配ルール）

## /broadcast トークン認証廃止

- [x] `overlay.py`: `BROADCAST_TOKEN`・トークンチェック・`/api/broadcast/token`エンドポイント削除
- [x] `stream.sh`: トークン取得ロジック削除、URLを`/broadcast`に単純化
- [x] `MainForm.cs`: 403ハンドリング・`RefreshBroadcastTokenAsync()`削除
- [x] 不要プランファイル `plans/broadcast-token-auto-recovery.md` 削除

## 英語モードのセリフを英語にする Step 6

- [x] `docs/speech-generation-flow.md` を更新: キャラ設定に言語版フィールド追記、Phase B-2のプロンプト構築説明を `build_lesson_dialogue_prompt()` に更新、self_note/persona対応、TTS言語対応、個性度★★★★★に更新
- [x] プランステータスを「完了」に更新

## 英語モードのセリフを英語にする Step 5

- [x] `get_tts_config()` で `get_localized_field(config, "tts_style")` を使い言語モード対応
- [x] テスト3件追加（`TestGetTtsConfig`）

## 英語モードのセリフを英語にする Step 4

- [x] `build_lesson_dialogue_prompt()` を `prompt_builder.py` に新設（8セクション構成、言語モード対応）
- [x] `get_lesson_characters()` に self_note/persona 取得を追加
- [x] `_generate_single_dialogue()` の手動プロンプトを `build_lesson_dialogue_prompt()` に差し替え
- [x] テスト9件追加（`TestBuildLessonDialoguePrompt`）

## 英語モードのセリフを英語にする Step 3

- [x] 管理画面に言語タブ（日本語/English/バイリンガル）追加
- [x] 各タブにシステムプロンプト・ルール・TTSスタイルの入力欄を配置
- [x] renderRules/addRule/collectRulesを言語サフィックス対応に拡張
- [x] saveCharacter/loadCharacterで全言語フィールドの読み書き対応

## 英語モードのセリフを英語にする Step 2

- [x] `CharacterUpdate` スキーマに英語/バイリンガル版6フィールド追加（`system_prompt_en`, `rules_en`, `tts_style_en`, `*_bilingual`）
- [x] `model_dump(exclude_none=True)` でNone値が既存フィールドを上書きしないよう修正
- [x] テスト4件追加（英語版保存/取得、バイリンガル版、後方互換、None非上書き）

## 英語モードのセリフを英語にする Step 1

- [x] キャラ設定に3言語パターン追加（`system_prompt_en/bilingual`, `rules_en/bilingual`, `tts_style_en/bilingual`）
- [x] `get_localized_field()` ヘルパーを `prompt_builder.py` に追加
- [x] DEFAULT_CHARACTER（ちょビ）・DEFAULT_STUDENT_CHARACTER（なるこ）に英語/バイリンガル版追加
- [x] テスト12件追加

## 機能ごとのREADME検討 → 不要と結論

- [x] 現行の3層構造（CLAUDE.md + メモリ + 個別docs）で十分と判断
- [x] 分析結果を [docs/feature-documentation-analysis.md](docs/feature-documentation-analysis.md) に記録

## キャラのライト設定が反映されないバグ修正

- [x] 原因: `applySettings` で旧 `lighting` セクションが `lighting_teacher`/`lighting_student` を上書きしていた
- [x] 修正: `lighting_teacher`/`lighting_student` が存在する場合は旧 `lighting` をスキップ

## 授業パネルのデザイン編集機能

- [x] 授業タイトル・テキスト・進捗パネルのデザインを管理画面から変更可能に（背景・文字・枠線等）
- [x] C#プレビューからドラッグ・右クリックで位置・デザイン編集可能に
- [x] C#コントロールパネルにDesignタブ追加（スキーマ駆動UI）
- [x] 進捗パネルのタイトル文字・カウント文字に個別デザイン調整（サイズ・色・縁取り）
- 関連プラン: [plans/lesson-panel-design-editor.md](plans/lesson-panel-design-editor.md), [plans/lesson-panel-csharp-preview.md](plans/lesson-panel-csharp-preview.md), [plans/lesson-progress-title-count-design.md](plans/lesson-progress-title-count-design.md)

## 進捗パネルの位置変更（キャラクター被り解消）

- [x] `broadcast.css`: 進捗パネルを左中央（top:50%）から左上（top:2%）に移動
- [x] `broadcast.css`: max-heightを80%→26%に縮小し生徒アバターと被らないよう制限
- [x] `broadcast.css`: スクロールバーを非表示に（scrollbar-width: none）

## Playwrightブラウザテストを削除

- [x] `tests/browser/` ディレクトリ削除（conftest.py, test_smoke.py, test_pages.py, __init__.py）
- [x] `requirements.txt` から pytest-playwright, playwright を削除
- [x] `pytest.ini` から browser マーカー定義を削除
- [x] `plans/playwright-browser-testing.md` のステータスを「中止」に更新
- 理由: pytest-playwrightのpageフィクスチャが動作せず13件全ERR。同期SQLiteによるテストサーバー不安定も未解決

## 授業の流れパネルに進捗表示を追加

- [x] `panels.js`: `_updateProgressTitle()` でタイトル行に「1/10」形式の進捗を右寄せ表示
- [x] `panels.js`: `showLessonProgress()` / `updateLessonProgress()` でセクション切替時に進捗更新
- [x] `panels.js`: `hideLessonProgress()` でパネル非表示時にタイトルリセット
- [x] `broadcast.css`: タイトル行をflex配置、進捗数値を小さめ・薄紫で右寄せ

## 授業タイトルを配信画面に表示

- [x] `lesson_runner.py`: `_notify_status()` の `lesson_status` イベントに `lesson_name` フィールドを追加
- [x] `broadcast.html`: 授業タイトル専用パネル（`lesson-title-panel`）を新規追加
- [x] `broadcast.css`: 画面上部中央に表示、紫枠・半透明背景のスタイル
- [x] `panels.js`: `showLessonTitle()` / `hideLessonTitle()` 追加、授業終了時に自動非表示
- [x] `websocket.js`: `lesson_status` イベントでタイトルパネルに表示

## 授業モード: セリフ生成にキャラのrulesを適用

- [x] `_generate_single_dialogue()` のシステムプロンプトに `char.rules`（文字数制限等）を追加
- [x] コメント応答と同じキャラ固有の応答ルールが授業セリフにも適用されるように修正
- [x] 日本語・英語両方のプロンプトに対応

## ブラウザテスト（Playwright）Step 3a: 授業モード CRUDテスト

- [x] test_teacher_workflow.py 作成（TestLessonCRUD 6テスト + TestPlanDisplay 2テスト等、計28テスト）
- [x] UI操作テスト: 新規作成・一覧表示・削除・名前変更・4ステップ構造・言語タブ
- [x] API事前データ投入（方式C）でプラン表示テスト（Phase Aヘッダー・step-done状態）
- [x] session-scopedフィクスチャ + requestsライブラリでAPI操作安定化
- [x] update-dialog強制除去・テスト残骸自動掃除（conftest.py）
- [x] 12テスト安定通過。残り16テストはテストサーバー過負荷で不安定→Step 3bで対応

## ブラウザテスト（Playwright）Step 2: 基本ページ表示テスト

- [x] 管理画面テスト: 全8タブ表示・教師モードサブタブ遷移・初期タブ確認・JSエラー検出
- [x] 配信ページテスト: TODOパネル・字幕・アバターエリア・授業パネル存在確認
- [x] WebSocket接続確立テスト（window._ws.readyState === OPEN）
- [x] JSエラー自動検出（VRM関連は除外）
- [x] 全10テスト通過（13秒）

## ブラウザテスト（Playwright）Step 1: 環境構築 + Smoke Test

- [x] pytest-playwright / playwright を requirements.txt に追加
- [x] pytest.ini に browser マーカー追加
- [x] tests/browser/ ディレクトリ作成（conftest.py + test_smoke.py）
- [x] テストサーバー自動起動フィクスチャ（session スコープ、ポート18080）
- [x] Smoke Test 3件（管理画面読み込み・配信ページ読み込み・APIステータス）

## 授業モード v3 Step 7: 管理画面 — 全LLM入出力の可視化

- [x] Phase A: JSハードコードプロンプト全廃止 → plan_generations（API）からsystem_prompt/user_prompt/raw_output/model/tempを表示
- [x] 旧データ（plan_generationsなし）は出力のみ表示 + 「旧形式」注記でフォールバック
- [x] データフロー矢印: ステップ間に「▼ 知識先生の出力が入力に含まれる」等を表示
- [x] 監督セクション v3対応: display_text, dialogue_directions, key_contentを展開可能カードで表示
- [x] Phase C: renderSectionsIntoで監督のdialogue_directionsを各セリフカードに「🎬 監督: (指示)」として表示
- [x] Phase Cヘッダー「🎭 Phase C: セリフ個別生成」追加
- [x] Step 2bメタデータ修正:「1回のLLM呼び出し」→「個別LLM呼び出し」、ハードコードtemp/model削除

## 授業モード v3 Step 5+6: teacher.pyルート対応 + DBスキーマ調整

- [x] lesson_plansテーブルに `director_json`, `plan_generations` カラム追加（マイグレーション）
- [x] lesson_sectionsテーブルに `dialogue_directions` カラム追加（マイグレーション）
- [x] `upsert_lesson_plan()` が `director_json`, `plan_generations` を保存
- [x] `add_lesson_section()` / `update_lesson_section()` が `dialogue_directions` に対応
- [x] プラン生成API: `director_sections` → `director_json`、`generations` → `plan_generations` をDB保存、SSE返却
- [x] スクリプト生成API: DBから `director_json` を取得し `generate_lesson_script_v2(director_sections=...)` に渡す
- [x] スクリプト生成API: セクション保存時に `director_sections` から `dialogue_directions` を抽出して保存
- [x] レッスン取得API: プランレスポンスに `director_json`, `plan_generations` を含める

## 授業モード v3 Step 4: セリフ個別生成のkey_content対応

- [x] `_generate_single_dialogue()` で `dialogue_plan_entry` から `key_content` を取得
- [x] 日本語プロンプトに「このターンで触れるべき内容」として追加
- [x] 英語プロンプトに「Key content to mention in this turn」として追加
- [x] 空文字の場合はプロンプトに含めない
- [x] テスト3件追加（日本語・空文字スキップ・英語モード）

## 授業モード v3 Step 3: Phase B-1除去（監督の設計を直接使用）

- [x] `generate_lesson_script_v2()` に `director_sections` パラメータを追加
- [x] `director_sections` がある場合、Phase B-1（構造デザイナーLLM呼び出し）をスキップし監督の設計をそのまま使用
- [x] `director_sections` がない場合は従来のPhase B-1にフォールバック（後方互換性維持）
- [x] `_generate_section_dialogues()` が `dialogue_directions`（v3）を `dialogue_plan`（v2）より優先して使用
- [x] Phase 2のターン数集計・section_workerも `dialogue_directions` に対応
- [x] テスト追加: `dialogue_directions` での動作確認・優先度テスト

## 授業モード v3 Step 2: 全LLM呼び出しにgenerationメタデータ付与

- [x] 知識先生・エンタメ先生・監督の3つのLLM呼び出しに generation メタデータ（system_prompt, user_prompt, raw_output, model, temperature）を記録
- [x] `generate_lesson_plan()` の戻り値に `generations` dict を追加
- [x] 監督の `raw_output` はJSONパース前の生テキストを保持（デバッグ・管理画面表示用）
- [x] セリフ個別生成（`_generate_single_dialogue()`）は既に同パターンで実装済みのため変更不要

## 授業モード v3 Step 1: 監督プロンプト拡張

- [x] 監督の出力形式を `{summary, has_question}` → `{display_text, dialogue_directions, question, answer}` に拡張
- [x] `_build_structure_prompt()` の display_text ガイドライン（視聴者環境・具体的内容ルール）を監督プロンプトに統合
- [x] `dialogue_directions` 設計指針を追加（speaker + direction + key_content）
- [x] 英語版・日本語版の両プロンプトに具体的な出力例を含めて品質確保
- [x] フィールド検証・デフォルト補完を新形式に対応
- [x] 戻り値に `director_sections`（完全出力）を追加、`plan_sections`（互換用メタデータ）も維持

## 授業モード v3 Step 0: 役割別モデルヘルパー関数

- [x] `_get_knowledge_model()`, `_get_entertainment_model()`, `_get_director_model()`, `_get_dialogue_model()` 追加
- [x] 知識先生・エンタメ先生・監督・セリフ生成・Phase B-1の各LLM呼び出しを役割別関数に切り替え
- [x] temperature を Gemini 3系推奨の 1.0 に統一
- [x] 監督の `max_output_tokens` を 4096 → 8192 に増加
- [x] `.env.example` に `GEMINI_KNOWLEDGE_MODEL` / `GEMINI_ENTERTAINMENT_MODEL` / `GEMINI_DIRECTOR_MODEL` / `GEMINI_DIALOGUE_MODEL` 追記

## セリフ個別LLM生成 + 管理画面プロンプト表示 + JSON修復

- [x] セリフ生成を「全キャラ一括LLM呼び出し」から「キャラごとに個別LLM呼び出し（ターン制）」に変更
- [x] 各セリフの生成に使われたプロンプト（System/User）と結果（Raw Output）を管理画面に全文表示
- [x] Phase 1（セクション構造+dialogue_plan生成）→ Phase 2（キャラ個別セリフ生成）の2段階フロー
- [x] セクション間並列化（ThreadPoolExecutor max_workers=3）
- [x] `json-repair` 導入: LLM応答の壊れたJSON（途中切れ・末尾カンマ等）を自動修復
- [x] 全13箇所のLLMレスポンスJSONパースを `parse_llm_json()` に統一

## 生徒キャラにも先生と同等のテキスト生成フローを追加

- [x] CharacterContextパターンで先生・生徒共通のメモ更新フローを実装
- [x] db.py: get_recent_avatar_commentsにspeakerフィルタ追加
- [x] ai_responder.py: generate_self_note/generate_persona/generate_persona_from_promptをchar_configパラメータ化
- [x] ai_responder.py: build_character_context()/build_all_character_contexts()新規追加
- [x] ai_responder.py: generate_multi_responseに生徒のself_note/persona引数追加
- [x] prompt_builder.py: build_multi_system_promptに生徒のself_note/persona注入
- [x] comment_reader.py: 共通メソッド_update_character_self_note/_update_character_personaで全キャラ更新
- [x] comment_reader.py: _generate_multi_ai_responseで両キャラのメモ・ペルソナを取得して渡す
- [x] 管理画面: teacher-only制限を削除し生徒でもペルソナ・セルフメモ・視聴者メモを表示
- [x] API: /api/character/{id}/layers, persona, self-note/generate等キャラID対応エンドポイント追加
- [x] JS: キャラ切替時にレイヤーリロード、全API呼び出しをキャラID対応

## キャラの位置を左に先生・右に生徒に変更

- [x] アバター配置を変更（先生=左、生徒=右）

## 管理画面の項目名をメイン/サブに変更 & キャラ名の一元管理化

- [x] アバター（ちょび/まなび）→ アバター（メイン/サブ）、字幕（先生/生徒）→ 字幕（メイン/サブ）に変更
- [x] index.html / broadcast.html / items.py / character.js / db.py のラベル更新
- [x] キャラ名の定義を `characters.name` カラムに一元化（config JSON の "name" を廃止）
- [x] DB読み出し時に name を config dict へ注入、書き込み時に自動除去
- [x] マイグレーション追加（既存DBの config.name を自動除去）
- [x] テスト更新

## C#プレビュー黒画面修正（サーバー再起動時の403トークン失効）

- [x] OnNavigationCompletedで403チェックをIsSuccessチェックの前に移動（到達不能だったトークンリフレッシュを修正）

## 生徒名を「まなび」→「なるこ」に変更

- [x] DEFAULT_STUDENT_CHARACTERのname・system_promptを更新
- [x] フォールバック値を全箇所更新（ai_responder/prompt_builder/lesson_runner）
- [x] seed_all_characters()にDBマイグレーション追加（既存レコードの自動更新）
- [x] デモデータ（conv_demo/meta.json）の名前・会話テキスト更新
- [x] テスト更新（test_lesson_generator/test_prompt_builder）

## 字幕の重なり防止（先生・生徒の会話時）

- [x] 新しい字幕を上（z-index高）に表示、前の字幕は0.5秒で速くフェードアウト
- [x] CSS: `.fading-fast`クラス追加（0.5秒フェード、通常は1.5秒）

## 字幕のデザインをキャラごとで分ける

- [x] broadcast.html: 先生用`#subtitle` + 生徒用`#subtitle-2`の2要素に分離
- [x] CSS: `.subtitle-panel`共通スタイル化、生徒はピンク系デフォルト
- [x] JS: `showSubtitle`が`avatar_id`で対象字幕をルーティング、フェードタイマー分離
- [x] 管理画面(index.html): 字幕（先生）・字幕（生徒）の2セクション追加
- [x] バックエンド: `subtitle2`のデフォルト値・スキーマ・デバッグAPI対応
- [x] 字幕位置: 中心基準配置（`translateX(-50%)`）で左右自由に移動可能
- [x] 字幕パネルは通常非表示、ホバー/選択時のみ薄く表示

## C#プレビューチャットのユーザー名を「あキら」に変更

- [x] control-panel.html: 表示名を「GM」→「あキら」に変更
- [x] comment_reader.py: respond_webuiのauthorを「あキら」に変更
- [x] ai_responder.py: 開発者判定を「GM」「あキら」両方に対応

## チャット・イベント応答のマルチキャラクター分担

- [x] DB: `avatar_comments`に`speaker`カラム追加（マイグレーション）
- [x] `save_avatar_comment`/`get_recent_avatar_comments`/`get_recent_timeline`にspeaker対応
- [x] `build_multi_system_prompt()`: 両キャラの性格・感情・応答分配ガイドライン含むプロンプト構築
- [x] `generate_multi_response()`: 単一Gemini呼び出しで配列形式のマルチキャラ応答生成
- [x] `generate_multi_event_response()`: イベント応答のマルチキャラ対応
- [x] `get_chat_characters()`: teacher+student設定取得
- [x] `apply_emotion()`に`character_config`パラメータ追加（キャラ別BlendShape）
- [x] CommentReader: `_respond`/`speak_event`/`respond_webui`/`_speak_segment`をマルチキャラ対応
- [x] タイムラインにspeaker情報を含め、会話履歴でキャラ名を区別
- [x] テスト22件追加（DB/ai_responder/prompt_builder）
- [x] キャラ1人の場合は既存動作を完全維持（後方互換）

## Step 4: レッスンランナーの対話再生

- [x] `_play_section()`をdialogues有無で分岐（`_play_dialogues` / `_play_single_speaker`）
- [x] `_play_dialogues()`: dialogueエントリごとに話者別voice/style/avatar_idで再生
- [x] 生徒キャラなしの場合は従来の単話者再生（後方互換）
- [x] dialogue用TTSキャッシュ（`section_XX_dlg_YY.wav`）
- [x] 授業開始時にキャラクター設定を取得
- [x] テスト: 対話再生・単話者フォールバック・student_cfg無し時の動作
- [x] プランファイル: [plans/student-character/04-lesson-runner.md](plans/student-character/04-lesson-runner.md)

## Step 3: スクリプト生成の対話化

- [x] DB: `lesson_sections`に`dialogues`カラム追加（マイグレーション + create_tables）
- [x] プロンプト: 先生・生徒の対話形式指示を自動構築（`_build_dialogue_prompt` / `_build_dialogue_output_example`）
- [x] 後処理: `_build_section_from_dialogues`でcontent/tts_text/emotionを自動構築
- [x] 生徒キャラなしの場合は従来の一人語り形式で生成
- [x] 英語モードでも対話スクリプト生成に対応
- [x] APIルート（teacher.py）でstudent_config伝搬・dialogues DB保存
- [x] テスト: DB dialogues CRUD + _build_section_from_dialogues + プロンプト構築
- [x] プランファイル: [plans/student-character/03-script-generation.md](plans/student-character/03-script-generation.md)

## 二人会話デモ（Debugタブ）

- [x] Debugタブに会話デモUI追加（テーマ入力 + 生成/再生ボタン分離）
- [x] LLMで先生・生徒の4往復会話スクリプト生成（DBのキャラ設定を使用）
- [x] TTS事前生成 + avatar_id付きで話者別に順次再生
- [x] SSEで生成進捗・会話ログをリアルタイム表示
- [x] 会話データをファイルに永続化（resources/audio/conv_demo/）、サーバー再起動後も復元
- [x] プランファイル: [plans/conversation-demo.md](plans/conversation-demo.md)

## キャラクター設定の改善

- [x] ボイスサンプル再生ボタン追加（キャラタブのvoice/style選択後に試聴、AI生成でバリエーション豊富）
- [x] TTS voice/style をキャラDBから自動取得（synthesize()でget_tts_config()参照、全発話パスで反映）
- [x] characters.name UNIQUE制約追加 + 重複キャラ・チャンネル自動削除マイグレーション
- [x] channel_id不一致時のフォールバック（get_character_by_channel/get_characters_by_channel）
- [x] 既存キャラにtts_voice/tts_styleデフォルト値を補完するマイグレーション
- [x] キャラクター設定の自動保存（保存ボタン廃止、フォーム変更時800msデバウンスで即保存）
- [x] ボイスサンプル再生でavatar_idを伝搬（生徒キャラのサンプルで生徒アバターが動くように）

## Step 2: TTS style パラメータ + WebUI設定

- [x] speech_pipeline.py に style 引数を伝搬（generate_tts / speak / _speak_impl → synthesize）
- [x] CharacterUpdate に tts_voice / tts_style を追加（Optional）
- [x] WebUIキャラ設定の第1層に voice ドロップダウン（Gemini TTS 30音声）+ style テキストエリア追加
- [x] character.js で voice/style の読み込み・保存に対応
- [x] サウンドテスト（ttsTest/emotionTest/ttsTestMulti）をキャラタブ・サウンドタブからDebugタブに集約移動
- [x] ライティングプリセットが初回表示されないバグ修正（loadCharacter完了後にloadLightingPresets呼び出し）
- [x] キャラクター名前フィールドをセリフサブタブ外のトップに移動

## 生徒役キャラクター追加（Step 1: マルチアバター表示）

- [x] avatar-renderer.js を AvatarInstance クラスにリファクタ（グローバル状態→クラス化、2体独立レンダリング）
- [x] broadcast.html に先生（avatar-area-1）+ 生徒（avatar-area-2）の2体表示
- [x] 生徒用VRMファイル管理（avatar2カテゴリ、独立したactive選択）
- [x] DB マイグレーション（avatar→avatar1リネーム、avatar2デフォルト追加）
- [x] overlay settings / broadcast_items のavatar1・avatar2対応
- [x] server_restart イベントで broadcast.html 自動リロード
- [x] window.avatarVRM / window.avatarLighting 後方互換維持
- [x] WebUIタブ順変更（会話モード→キャラクター→配信画面）
- [x] キャラクタータブにキャラクター切替セレクタ（先生/生徒）追加
- [x] VRM選択を配信画面タブ→キャラクタータブに移動
- [x] ライティングをアバター個別化（lighting_teacher / lighting_student）
- [x] 生徒選択時はセリフの第2〜5層・発話設定・テスト再生を非表示

## 生徒役キャラクター追加（Step 1: WebSocketアバター制御）

- [x] websocket.js に getAvatar() ヘルパー追加、blendshape/lipsync/lipsync_stop を avatar_id でルーティング
- [x] student_avatar_show / student_avatar_hide イベント追加
- [x] speech_pipeline.py の notify_overlay/apply_emotion/speak に avatar_id パラメータ追加（全イベント必須）
- [x] 字幕に data-speaker 属性設定、生徒字幕のスタイル（ボーダー色・テキストシャドウ）
- [x] Debug タブにアバター制御テストUI（Teacher/Student × 表情/口パク/字幕 の6ボタン）
- [x] POST /api/debug/avatar-test エンドポイント追加

## 生徒役キャラクター追加（Step 1: characters テーブル集約）

- [x] Phase 1: 生徒を characters テーブルに追加（role フィールド、`/api/characters` 一覧、`/api/character/{id}` 個別読み書き）
- [x] Phase 2: VRM選択を characters.config.vrm に移行（settings → characters.config、files.py 更新）
- [x] Phase 3: ライティングを characters.config.lighting に移行（overlay.py の読み書き先変更）
- [x] Phase 4: ライティングプリセットをキャラ別に（characters.config.lighting_presets、character_id パラメータ対応）
- [x] Phase 5: TTS設定を characters.config に追加（tts_voice / tts_style フィールド、synthesize() に style 引数追加）
- [x] Phase 6: 旧設定キーの掃除 + テスト（旧 settings キー自動削除、DB テスト 8件 + API テスト 5件追加）
- [x] WebUI キャラクターセレクタを API から動的生成（ハードコード廃止）

## 教師モード改善 v2

- [x] 英語のみモード対応（`plans/english-only-mode.md`）— prompt_builder/tts/ai_responder/lesson_generator の全プロンプトを primary≠ja で英語切替、TTSベース言語動的化
- [x] 授業の言語切替対応（`plans/teacher-mode-v2/05-lesson-language-switch.md`）— lesson_plans テーブル新設、lesson_sections に lang カラム追加、TTS キャッシュ言語別保存、WebUI に日英タブ追加、授業開始時に言語選択

- [x] 授業テキストパネルを次のセクションまで表示し続ける（発話完了直後のhideを削除、display_textがないセクションでのみ非表示）
- [x] 授業中に授業関連以外のパネル（カスタムテキスト等）を非表示にする
- [x] 授業テキストパネルを上に移動（top 50%→35%、max-height 70%→60%）字幕との重なり回避
- [x] 進捗パネルのセクション名を短くする改善（タイトル10文字以内のプロンプト指示 + 表示20文字切り詰め）
- [x] スクリプト生成で「テキストを見てください」等の教材参照表現を禁止（視聴者は配信画面のみ、display_textで補足）
- [x] 英語発音改善 Step 1-2: スクリプト生成プロンプトに [lang:en] タグ説明と英語発音ルールを追加
- [x] スクリプト再生成時に既存セクション・TTSキャッシュを生成前に削除（UIも即座にクリア）
- [x] スクリプト生成の進捗表示で (N/M) が重複する不具合を修正
- [x] 「プランに基づいて生成」ラベルを削除

## 教師モード Phase 1: DB + 画像/URL解析 + スクリプト生成 + 管理画面

- [x] DBテーブル追加（lessons, lesson_sources, lesson_sections）+ CRUD関数
- [x] 画像テキスト抽出（Gemini Vision）・URL取得・授業スクリプト生成（src/lesson_generator.py）
- [x] 教師モードAPI（scripts/routes/teacher.py）— コンテンツCRUD・画像アップロード・URL追加・スクリプト生成・セクション編集/並び替え/削除
- [x] 管理画面UI — 会話モードタブ追加（教師モード/雑談モードサブタブ）、コンテンツ一覧・詳細・ソース管理・スクリプト表示・インライン編集
- [x] テスト追加（test_api_teacher.py + test_db.py Lesson関連、全435テスト通過）

## 教師モード Phase 2: 授業再生エンジン

- [x] LessonRunner実装（src/lesson_runner.py）— セクション順次再生・一時停止/再開/停止・問いかけ待ち
- [x] CommentReaderにLessonRunner統合（lesson_runnerプロパティ、SpeechPipeline共有）
- [x] 授業制御API（start/pause/resume/stop/status）+ 管理画面に制御ボタン・進捗表示
- [x] テスト追加（test_lesson_runner.py + test_api_teacher.py 授業制御、全450テスト通過）

## 教師モード Phase 3: 配信画面に授業テキストパネル表示

- [x] broadcast.htmlに授業テキストパネル（#lesson-text-panel）追加
- [x] WebSocketイベント（lesson_text_show/lesson_text_hide）対応
- [x] CSS: フェードイン/アウトアニメーション付きパネルスタイル
- [x] JS: showLessonText/hideLessonText関数（panels.js）

## 教師モード Phase 4: チャット割り込み対応 + 視聴者への問いかけ

- [x] 授業コンテキスト付きチャット応答（CommentReaderがLessonRunner情報をstream_contextに追加）
- [x] prompt_builderに「現在の授業」セクション追加（授業名・現セクション・回答ガイドライン）
- [x] questionセクション再生（LessonRunner._handle_question: 問いかけ→待ち→回答）は Phase 2 で実装済み

## 教師モード Phase 5: ポリッシュ

- [x] プランファイル（plans/conversation-mode.md）ステータス「完了」に更新
- [x] CLAUDE.md ディレクトリ構成・テスト一覧更新
- [x] TODO.md から教師モード全フェーズ削除

## 教師モード改善

- [x] スクリプト生成のJSONパースにリトライ追加（最大3回）・エラーメッセージをUIに表示
- [x] 授業停止/完了/エラー時に授業テキストパネルを自動非表示
- [x] 授業テキストパネルを画面中央に配置・サイズ拡大（55%幅・70%高）
- [x] 授業中にTODOパネル・字幕を非表示にするレッスンモード追加（lesson_statusイベント連動）
- [x] 管理画面: 授業実行状態をページロード時に反映（ボタン・進捗表示）
- [x] 三者視点プラン生成（知識先生→エンタメ先生→監督の3段階LLM呼び出し）
- [x] プランベーススクリプト生成（generate_lesson_script_from_plan）
- [x] 間（ま）のスケール制御（pace_scale API + UIスライダー、0.5〜2.0x）
- [x] 言語タグ除去の多層防御（SSML `<lang>` タグ対応、speech_pipeline/state/panels.jsの3箇所）
- [x] テスト追加（TestLessonPlan + TestPaceScale、全460テスト通過）
- [x] TTS事前一括生成（セクション内パート間の間を大幅短縮、SpeechPipeline.generate_tts + wav_path渡し）
- [x] プラン/スクリプト生成のSSE進捗表示（StreamingResponse + EventSource、ステップごとにリアルタイム更新）
- [x] TTS音声の永続保存キャッシュ（resources/audio/lessons/に保存、再生時キャッシュヒット、編集・再生成・削除時に自動無効化）
- [x] スクリプト生成時にTTS音声も事前生成（「スクリプト+音声生成」に統合、SSE進捗表示付き）
- [x] TTSキャッシュAPI（GET/DELETE /api/lessons/{id}/tts-cache）+ WebUIにキャッシュ状態・再生リンク表示
- [x] 前工程ボタン押下時に後工程の表示を即座にクリア（ソース→プラン→スクリプト→授業の依存関係）
- [x] 授業テキストパネルをbroadcast_items編集システムに統合（data-editable + スキーマ + 管理画面UI）
- [x] 授業中の字幕を通常の字幕デザインで表示（setLessonModeから字幕非表示を削除）
- [x] 授業テキストパネルのデバッグAPI追加（テスト表示/非表示）
- [x] スキーマベースのデフォルト値システム（全パネル共通、未保存スライダーにもデフォルト表示）
- [x] 授業進捗サイドバー（画面左、セクション一覧+現在位置ハイライト+スクロール追従）
- [x] 授業パネルの位置・サイズをCSS固定化（applyCommonStyleで上書きしない）
- [x] 授業パネル文字の最低サイズ保証（0.8vw、既存パネル最小値に合わせたmax()適用）
- [x] 管理画面の授業パネルを独立カードに分離（配信画面カードの下に配置）

## トピック機能・授業モード完全削除

- [x] バックエンド: TopicTalker・トピックAPI・授業モード関連コード削除（state.py, comment_reader.py, ai_responder.py, db.py, prompt_builder.py, avatar.py, web.py, overlay.py, items.py）
- [x] フロントエンド: トピックパネル・管理画面タブ・CSS・JS全削除（broadcast.html, globals.js, panels.js, settings.js, edit-mode.js, websocket.js, init.js, index.html, topic.js）
- [x] DB: topics/topic_scriptsテーブルDROPマイグレーション追加
- [x] テスト: test_topic_talker.py, test_api_topic.py削除、関連テスト修正（404テスト全通過）
- [x] プラン → [plans/archive/remove-topic-rebuild-lesson.md](plans/archive/remove-topic-rebuild-lesson.md)

## 画像/URLで授業モード

- [x] ベース1: コンテンツソース抽象化（`analyze_images()` / `analyze_url()` → コンテキストテキスト生成）
- [x] ベース2: トピックへの画像URL/コンテキスト紐付け（`set_topic()` に `image_urls`/`context` 引数追加）
- [x] ベース3: 配信画面のトピック画像表示（`#topic-panel` に画像+ページ送り、`topic_image_index` WebSocketイベント）
- [x] ベース4: 教材ファイルアップロード（`files.py` に `teaching` カテゴリ追加）
- [x] 拡張5: 授業スクリプト生成（`generate_lesson_script()` — コンテキストからJSON配列ステップ生成）
- [x] 拡張6: WebUI操作（画像/URL入力タブ切り替え、授業開始/終了ボタン、`POST /api/topic/lesson`）
- [x] 共通7: テスト（472テスト全通過）
- [x] プラン → [plans/english-teacher-mode.md](plans/english-teacher-mode.md)

## 配信バッファリング（くるくる）対策

- [x] VBVバッファサイズ拡大（bitrate/2 → bitrate×2、Twitch推奨値に合わせ）
- [x] デフォルトビットレート引き上げ（2500k → 3500k、Twitch 720p推奨帯）
- [x] FFmpegフラグ追加（`-fflags +nobuffer -flush_packets 1`）
- [x] 音声パイプバッファ拡大（64KB → 256KB、タイマージッター吸収）
- [x] 高分解能タイマー導入（`timeBeginPeriod(1)` で1ms精度）
- [x] NV12変換遅延の警告ログ追加（フレーム間隔75%超でWarning）
- [x] エンコード速度監視（speed < 0.95xでWarning）
- [x] **効果検証**: 3500kではspeed 1.03x→0.87x低下（ネットワーク帯域不足）、2500kでspeed 1.01x安定を確認
- [x] デフォルトビットレートを2500kに変更（ネットワーク帯域に合わせ）
- [x] 診断ログ強化: 60秒サマリー、パイプ遅延警告、段階的speed警告、配信終了レポート
- [x] プラン → [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)

## 長文発話と句読点分割（連続発話機能）

- [x] AIの文字数制限を緩和（40字固定 → DB設定 `speech.max_chars` で30〜200字に変更可能）
- [x] 長文を全角句読点（。！？）で自動分割して順次再生（`SpeechPipeline.split_sentences()`）
- [x] コメント応答・トピック発話の両方で分割対応
- [x] 分割キューイング: 1文目は即再生、2文目以降は `_topic_queue` に入れる
- [x] コメント到着時に残りセグメントをキャンセル（`_topic_queue.clear()`）
- [x] WebUIキャラクタータブに「文字数上限」スライダー追加（30〜200字）
- [x] サウンドタブに「連続発話」テストボタン追加
- [x] プラン → [plans/archive/multi-part-speech.md](plans/archive/multi-part-speech.md)

## WebUI描画のファイル構成の最適化

- [x] broadcast-main.js（1,625行）を11ファイルに分割（`js/broadcast/`）
  - globals, style-utils, panels, capture, custom-text, child-panel, settings, settings-panel, edit-mode, websocket, init
- [x] index-app.js（2,098行）を16ファイルに分割（`js/admin/`）
  - utils, status, panel-items, character, language, sound, topic, db, todo, chat, markdown, lighting, debug, layout, files, init
- [x] broadcast.htmlのインラインスクリプト2つを外部ファイルに移動
- [x] テストの`read_js()`/`read_js_index()`を分割後のディレクトリ読み込みに更新
- [x] バンドラー不要、`<script>`タグベースで既存onclick互換維持
- [x] 全420テスト通過
- [x] プラン → [plans/archive/webui-file-optimization.md](plans/archive/webui-file-optimization.md)

## 配信言語設定の再設計

- [x] 言語モード5プリセット → 基本言語・サブ言語・混ぜ具合の3項目設定に再設計
- [x] テキスト生成プロンプトとTTSスタイルを分離（`build_language_rules()` / `build_tts_style()`）
- [x] `english` → `translation` フィールドリネーム（全レイヤー: AI出力・WebSocket・字幕・C#アプリ）
- [x] WebUIキャラクタータブをサブタブ分割（ビジュアル / セリフ）
- [x] 配信言語をセリフタブ内に配置
- [x] 言語テストをセリフタブに統合、6パターン化（言語選択UI廃止→配信言語設定を自動使用）
- [x] 読み上げテスト6パターン追加（挨拶・雑談・リアクション・質問・エピソード・解説）
- [x] 生成プロンプトプレビュー表示
- [x] 対応言語8種（日本語・English・한국어・Español・中文・Français・Português・Deutsch）
- [x] 他言語コメントには相手の言語で返答する固定ルール
- [x] DB保存を3キー方式に変更（stream_lang_primary/sub/mix）
- [x] テスト全420件更新・通過

## 右クリックメニュー設定編集（スキーマAPI＋フローティングパネル）

- [x] サーバ駆動スキーマAPI（`GET /api/items/schema`）を実装（共通＋アイテム固有プロパティ定義）
- [x] broadcast.htmlの右クリックメニューに「設定を編集...」を追加
- [x] フローティング設定パネル（ドラッグ移動・折り畳みグループ・スキーマからUI動的生成）
- [x] slider/color/toggle/select/text の全フィールドタイプ対応
- [x] デバウンス付きAPI保存（PUT /api/items/{id}）＋editSave()競合防止
- [x] スキーマAPIテスト9件追加
- [x] index.htmlの`_commonPropsHTML()`をスキーマAPIベースに統一（ハードコード排除）
- [x] C#アプリはWebView2経由で自動対応（追加実装不要）
- [x] 右クリック→設定パネル直接表示に変更（中間メニュー・Z値ダイアログ廃止）
- [x] 設定パネル上部に「テキスト子パネルを追加」/「削除」ボタン配置
- [x] C# WebView2のデフォルトコンテキストメニュー無効化
- [x] PUT /api/items/{id} でアイテム自動作成（upsert）
- [x] 設定パネルの値をDOMフォールバックで取得（broadcast_items未登録のキャプチャ対応）
- [x] settings_updateのWebSocketキー名修正（item_idリテラル→変数展開）
- [x] 設定変更のDOM即時反映（applyCommonStyle直接適用）
- [x] 設定パネルヘッダーをsticky固定（スクロール時にタイトル＋×が残る）
- [x] トグルスイッチのクリック修正（div→label化）＋サイズ固定

## WebUI TODOタブ復活＋外部ファイル対応＋複数選択

- [x] WebUIにTODOタブを復活（開発実況削除で巻き添えで消えていたHTML/タブ切替を復元）
- [x] 作業中TODOの解除機能追加（POST /api/todo/stop）
- [x] 外部TODO.mdファイルのアップロード・DB保存・切り替え対応
- [x] 複数TODOファイルをDBに保存してドロップダウンで切り替え可能
- [x] アップロード時にモーダルダイアログで名称入力（showModal汎用コンポーネント化）
- [x] 作業中タスクの複数選択対応（排他→追加方式に変更）
- [x] 全391テスト通過（新規テスト11件追加）

## 開発実況リポジトリ監視機能の完全削除

- [x] DevStreamManager・APIルート・テスト・UIタブ・JS関数を丸ごと削除
- [x] broadcast.htmlのdev-activity-panel・CSS・WebSocketハンドラを削除
- [x] overlay内のTODOソース切替（_todo_source dev:ルーティング）・/api/todo/sourceを削除
- [x] DBのdev_reposテーブル定義・全CRUD関数を削除＋DROP TABLEマイグレーション追加
- [x] repos/ディレクトリ・.gitignoreエントリを削除
- [x] 全380テスト通過

## ペルソナ生成の抽象化

- [x] generate_persona / generate_persona_from_prompt のプロンプトに抽象化ルール追加
- [x] 具体的な技術用語・固有名詞・フレーズ羅列を禁止し、性格特性として記述する指示に変更

## C#チャットのAI返信表示バグ修正

- [x] MainForm.cs: WSイベントのキー名不一致を修正（message→trigger_text, response→speech）
- [x] control-panel.html: C#→HTML受信側・fetch応答側の両方でspeechキーに修正
- [x] commentsテーブル再設計時にC#側が追従していなかったのが原因

## C#プレビューにTwitch配信情報設定＋Go Live時コメント削除＋不要なWeb preview削除

- [x] C#コントロールパネル（control-panel.html）のStreamタブにTwitch情報セクション追加（タイトル表示・編集UI）
- [x] Go Live時にcomments/avatar_commentsテーブルを自動クリア（db.clear_comments/clear_avatar_comments）
- [x] 不要なWeb版プレビューページ削除（static/preview.html + GET /preview ルート）
- [x] テスト追加（clear_comments/clear_avatar_comments）
- [x] 全433テスト通過

## commentsテーブル再設計（comments/avatar_comments分離）

- [x] commentsテーブルを視聴者コメント専用に簡素化（text, user_id, episode_id）
- [x] avatar_commentsテーブル新設（trigger_type, trigger_text, text, emotion）
- [x] 既存データのマイグレーション（RENAME COLUMN + DROP COLUMN + データコピー）
- [x] AI応答辞書のキー変更（response → speech）、Geminiプロンプト更新
- [x] 会話履歴をタイムライン形式に変更（get_recent_timeline: UNION ALL）
- [x] comment_reader: コメントとアバター発話を分離保存、_save_avatar_comment新設
- [x] WSイベントのフィールド名変更（message → trigger_text, response → speech）
- [x] APIエンドポイント更新（/api/chat/history タイムライン形式、DB viewer）
- [x] フロントエンド更新（broadcast.html, broadcast-main.js, index-app.js, CSS）
- [x] デバッグ字幕エンドポイント修正
- [x] 全431テスト通過

## キャラクター記憶システム改善

- [x] メモ更新ループのガード条件修正: ペルソナ・セルフメモの更新をユーザーコメント有無と独立に実行
- [x] セルフメモの時間情報対応: コメントにタイムスタンプ付与
- [x] ペルソナWebUI編集: PUT API追加＋編集/保存/キャンセルUI
- [x] ペルソナ初期生成: システムプロンプトからAI生成するAPI＋WebUI「AI初期生成」ボタン
- [x] セルフメモAI再生成: WebUI「AI再生成」ボタン＋API追加
- [x] ペルソナ漸進的更新: 既存ペルソナの90%を維持しつつ最近の応答で更新（400文字）
- [x] セルフメモ拡大: 直近2時間50件から生成、400文字
- [x] ユーザーメモ漸進的更新: 既存メモの90%を維持しつつ更新（200文字、直近2時間20件）
- [x] 視聴者メモWebUI表示・編集: 折りたたみ表示＋件数表示＋各メモに編集ボタン
- [x] 会話生成ドキュメント更新
- [x] テスト追加: API（layers/persona/viewer-note）+ generate_self_noteタイムスタンプ + generate_persona_from_prompt

## ちょびバージョン 0.2.0

- [x] VERSION 0.1.0 → 0.2.0（36コミット分の新機能蓄積: チャットログ・配信遅延解消・character_memory・TODO統合等）

## WebUIのTODOタブを開発実況タブに統合

- [x] TODOタブを廃止し、開発実況タブ内にTODO一覧を統合
- [x] ai-twitch-castリポジトリを先頭に常時表示（削除不可）
- [x] リポジトリクリックで選択→そのリポジトリのTODOを表示
- [x] 選択中リポジトリは紫ハイライト+「選択中」バッジ
- [x] `#todo` ハッシュは `#devstream` にリダイレクト
- [x] バックエンド変更なし（既存API再利用）

## ちょビの発話をチャットログとして表示（C#パネル + WebUI）

- [x] WebUIにチャットログタブ追加（DB履歴読み込み + WSリアルタイム追加）
- [x] `GET /api/chat/history` API追加（ページング対応、新しい順）
- [x] C#パネルにcommentイベント転送（broadcast.html → MainForm → control-panel）
- [x] コンパクト1行表示（日時 / 発言者 / コメント ← きっかけ）
- [x] 上下ページャー、URLにページ番号反映（`#chat:2`）

## Twitch配信遅延解消（NVENCハードウェアエンコーダ自動検出修正）

- [x] 遅延原因特定: FFmpegがlibx264（CPU）にフォールバックし、1080p30fpsでspeed 0.64x（19fps）しか出ず遅延蓄積
- [x] HWエンコーダprobeの改善: `nullsrc` → `color=black`、`-f null -` → `-f null NUL`（Windows互換性向上）
- [x] `-encoders` リストで事前チェック追加（probeの高速化）
- [x] FFmpegパス不在時のprobeスキップ（例外握りつぶし防止）
- [x] probe失敗時のログ出力追加（原因特定しやすく）
- [x] 結果: h264_nvenc（RTX 3090 Ti）が正常検出され、speed 0.64x → 1.01x（リアルタイム）に改善

## 会話生成ドキュメント + 5層プロンプトWebUI表示 + character_memoryテーブル

- [x] `docs/character-prompt.md` 作成（5層プロンプト構成・言語モード・感情システム等のドキュメント）
- [x] `mkdocs.yml` にキャラクターセクション追加
- [x] WebUIキャラクタータブに「会話生成の仕組み →」モーダルダイアログ（Markdown→HTML変換表示）
- [x] WebUIキャラクタータブに5層プロンプト表示（第1層〜第5層のグループ分け）
- [x] 第2〜4層のデータ表示API `GET /api/character/layers` 追加
- [x] `character_memory` テーブル新設（ペルソナ・セルフメモをキャラクターIDに紐付け）
- [x] 既存データ自動マイグレーション（settings.persona → character_memory、users.note → character_memory）
- [x] `comment_reader.py` の読み書き先を character_memory に切替（4箇所）
- [x] `db_viewer.py` の手動メモ更新も character_memory に切替
- [x] テスト追加（TestCharacterMemory 5件、全421テスト通過）

## Claude Code長時間実行時にちょびがコメント

- [x] `~/.claude/hooks/long-execution-timer.py` 作成（バックグラウンドタイマー、transcript解析）
- [x] `notify-prompt.py` にタイマー起動処理追加（マーカーファイル + Popen）
- [x] `notify-stop.py` にタイマー停止処理追加（マーカー削除 + pkill）
- [x] transcript_pathのJSONLからツール呼び出しを解析し、作業内容付きで報告
- [x] アイドル検知: transcript未更新2分でタイマー自動終了（Ctrl+C/Stopフック失敗のセーフガード）

## Claude Code実況フックのグローバル化（他リポジトリ対応）

- [x] `~/.claude/hooks/notify-stop.py` / `notify-prompt.py` をグローバルフックとして作成
- [x] `~/.claude/settings.json` にStop/UserPromptSubmitフックを `"async": true` で登録
- [x] プロジェクトローカルのフックスクリプト4ファイル（`.sh`/`.py` × 2）を削除
- [x] `.claude/settings.local.json` からStop/UserPromptSubmitフック定義を削除（PostToolUseは維持）
- [x] 他リポジトリではプロジェクト名付きで報告（例: 「作業報告（other-project）」）

## 字幕パネルの水平中央配置修正

- [x] `applySettings`の字幕中央揃えコードを常時適用に変更（`bottom != null`条件を除去）
- [x] ドラッグ時に字幕は垂直移動のみ（水平は常に中央固定、`transform: translateX(-50%)`を維持）
- [x] `editSave`で字幕の`positionX`を常に50に固定（ドラッグで不正な値が保存されるのを防止）

## WebUIポーリング負荷削減（84%削減）

- [x] `checkServerUpdate`ポーリング（3秒）をWebSocket push方式に置換（`server_restart`イベント）
- [x] `refreshStatus`ポーリング間隔を5秒→30秒に延長
- [x] `syncBgmVolumes`ポーリング間隔を3秒→30秒に延長
- [x] `captureRefreshSources`ポーリング間隔を10秒→30秒に延長
- [x] サーバー起動時に`server_restart` WebSocketイベントをbroadcast（`web.py`）
- [x] 夜の配信停止原因を特定: PCスリープによるWSL2停止（コード修正では解決不可、Windows電源設定変更が必要）

## バージョニングルール作成

- [x] `docs/versioning.md` 作成（バージョン基準: MAJOR/MINOR/PATCH/上げない、半自動提案フロー）
- [x] CLAUDE.md の開発ルールにバージョン更新ルール追記
- [x] `mkdocs.yml` の運用セクションにページ追加
- [x] `.git/hooks/post-commit` にバージョン提案ロジック追加（DONE.md変更検知 → `/api/avatar/speak` でちょびに提案依頼）

## ちょびの返信改善 Phase 1+2

- [x] A: キャラ設定全面書き直し（性格5項目+話し方5項目、AI身体体験捏造禁止）
- [x] B: 感情分布矯正（neutral 60%以上、joy乱用禁止ガイド追加）
- [x] C: 応答ルール厳格化（40文字以内、1文返し、感嘆符制限）
- [x] F: GM特別対応（開発者、敬語不要コンテキスト）
- [x] D: ペルソナ自動抽出（15分バッチ、DB保存、プロンプト注入）
- [x] G: temperature=1.0設定
- [x] E: 会話履歴5→10件、禁止パターン（直前3件の書き出し重複防止）
- [x] H: イベント応答バリエーション（直前応答を渡して繰り返し防止）
- [x] I: ユーザーメモ・自己メモに「事実のみ、キャラ口調禁止」ルール追加
- [x] J: 感情種類追加（excited/sad/embarrassed）+ BlendShapeマッピング
- [x] DB上のキャラクター設定も更新済み
- [x] プラン: plans/improve-ai-responses.md

## Claude Code 作業実況（Stopフック）

- [x] `.claude/hooks/notify-stop.py` / `notify-stop.sh` 作成（Stopフックで作業完了をちょびに自動報告）
- [x] `.claude/hooks/notify-prompt.py` / `notify-prompt.sh` 作成（UserPromptSubmitフックで指示受信をちょびに報告）
- [x] `settings.local.json` にStop/UserPromptSubmitフック追加
- [x] CLAUDE.md に実況機能セクション追加
- [x] 疎結合設計（stdlib only、サーバー側変更ゼロ、削除1手順）
- [x] shスクリプトのstdin空問題修正（`&`バックグラウンド実行でstdinが切れる→`INPUT=$(cat)`で先読みしてパイプ）
- [x] プラン: plans/claude-code-narration.md

## WebUIチャット欄追加（GM→アバター会話）

- [x] C#コントロールパネルのChatタブにチャットUI実装（メッセージ履歴+入力欄）
- [x] `POST /api/chat/webui` エンドポイント追加
- [x] `CommentReader.respond_webui()` 実装（AI応答→TTS→字幕、GMメッセージをTwitchチャット投稿）
- [x] CORSミドルウェア追加（C#パネル→WSLサーバー間の通信対応）
- [x] preview.htmlにもチャットUI追加
- [x] テスト追加（test_api_chat.py）
- [x] プラン: plans/webui-chat-input.md

## 表情・ジェスチャーシステム実装

- [x] 表情イージング遷移（300ms）実装
- [x] ジェスチャーアニメーション（AnimationMixer）実装（nod, surprise, head_tilt, happy_bounce, sad_droop, bow）
- [x] 感情→ジェスチャーのデフォルトマッピング（joy→nod, surprise→surprise等）
- [x] emotion_blendshapesをVRM 1.0名に修正（DB + DEFAULT_CHARACTER）
- [x] リップシンクと感情BlendShapeの競合修正（aa/blink/ear_standをスキップ）
- [x] WebUI感情テストボタン追加（joy/surprise/thinking/neutral）
- [x] 耳プルプル振り追加（15%確率、30-50Hz高速振動 + ear_stand/ear_droop交互 + happy表情連動）
- [x] broadcast.htmlにconsole.logキャプチャ→サーバー送信機能追加
- [x] デバッグ用API追加（expression直送・jslog保存）
- [x] プラン: plans/expression-gesture-implementation.md

## 子パネル（入れ子テキストパネル）機能

- [x] DBスキーマ拡張: broadcast_itemsにparent_idカラム追加、子パネルCRUD関数（create/get/delete + 連鎖削除）
- [x] API: POST /api/items/{parent_id}/children、GET /api/items で children ネスト、DELETE 連鎖削除
- [x] WebSocket: child_panel_add/update/remove イベント、settings_update で子パネル情報同期
- [x] broadcast.html: 子パネルのレンダリング・編集（ドラッグ＆リサイズ、相対座標、右クリックメニュー）
- [x] 管理UI: 固定パネル・カスタムテキストに子パネル管理UI（追加・編集・削除）
- [x] テスト: DB子パネルCRUD + API子パネルテスト追加
- [x] プラン: plans/child-panels.md

## パネルUI共通化（テキスト変数・テキスト編集UI）

- [x] テキスト変数定義を`lib/text-variables.js`に一元化（`replaceTextVariables()` + `TEXT_VARIABLE_HINT`）
- [x] テキスト編集UIを`panel-ui.js`に共通関数化（`renderTextEditUI()` + `injectChildPanelSection()`）
- [x] 子パネルに変数ヒント（{version} {date} 等）が表示されないバグ修正
- [x] broadcast-main.jsのバージョン再展開が`.child-text-content`にも適用されるよう修正

## 子パネルのスナップガイド対応

- [x] ドラッグ時: 親パネルの端・中央、兄弟子パネルの端・中央にスナップ吸着
- [x] リサイズ時: 同様に親パネル・兄弟子パネルにスナップ吸着
- [x] ガイド線を画面座標に変換して正しく表示

## 子パネルのスタイル適用バグ修正

- [x] `addChildPanel()`の手動スタイル適用を`applyCommonStyle()`に一本化（textStroke・backdrop等の適用漏れ修正）
- [x] `applyCommonStyle()`のtextAlign/verticalAlign/fontFamilyセレクタに`.child-text-content`を追加
- [x] `.child-text-content` CSSに`flex-direction: column`追加（垂直揃えが水平に効いていたバグ修正）

## Z値ダイアログ・コンテキストメニューの画面外はみ出し修正

- [x] 右クリックメニューとZ値ダイアログの表示位置をビューポート内にクランプ

## プレビューZ値ダイアログが9000を表示するバグ修正

- [x] 編集中のzIndex一時値(9000)がZ値ダイアログに表示される問題を修正
- [x] getElZIndex()が_savedZIndexを優先して返すよう変更
- [x] Z値変更時も_savedZIndexを更新し、編集中は常にz-index=9000を維持

## アバターVRM管理を配信画面タブに移動 + 素材タブ削除

- [x] アバターVRMのファイル追加・選択・削除を配信画面のアバターパネル内に移動（共通設定の下に「VRMファイル」セクション）
- [x] 素材タブを削除（背景・アバター両方が配信画面に移動済みのため）

## 背景画像管理を配信画面タブに移動

- [x] 素材タブの背景画像カードを配信画面タブの最上部に移動（折りたたみパネル形式）
- [x] 起動時に背景ファイル一覧を自動読み込み

## 配置画面の削除ボタンを折りたたみ時も表示

- [x] キャプチャ・テキストの削除ボタンをsummary行に移動（折りたたんだ状態でも常時表示）
- [x] summary-delete-btn CSSクラス追加（右寄せ・赤背景の小ボタン）

## WebUI右上の配信制御ボタン削除

- [x] 「配信開始」「配信停止」「再起動」ボタンをWebUIヘッダーから削除（C#パネル・preview.htmlに同等機能あり）
- [x] `/api/restart` エンドポイント削除（コミット時にpost-commit hookで自動再起動されるため不要）
- [x] 関連JS関数（doGoLive, doStop, doRestart, waitForRestart）削除

## テキストパネル フォント変更

- [x] fontFamilyを共通プロパティとして追加（DB migration、broadcast.html描画、WebUIセレクトボックス）
- [x] システムフォント6種＋Google Fonts 2種＋等幅の計9選択肢
- [x] Google Fonts（M PLUS Rounded 1c、小杉丸ゴシック）は選択時に動的読み込み

## テキストパネル文字揃え（水平・垂直）

- [x] textAlign（左/中央/右）・verticalAlign（上/中央/下）を共通プロパティとして追加
- [x] DB migration、broadcast.html描画、WebUIセレクトボックス対応

## テキストパネル変数ヘルプ表示

- [x] WebUIのテキストパネルtextarea下に使える変数一覧（{version} {date} {year} {month} {day}）を表示

## アイテム共通化バグ修正

- [x] applyCommonStyleを直接適用に変更（bgColor→background、border、textColor、textStroke、padding）
- [x] WebUI全面刷新: details廃止、共通UI(17項目)→固有UIの2段構成、配置/背景/文字のグループ化
- [x] 背景色: hex→rgba変換してbgOpacityと合成し直接適用
- [x] ふち枠: borderEnabled廃止→borderSize=0で非表示に統一
- [x] 文字色: custom-text-colorクラス+!importantでID詳細度に勝つCSS追加
- [x] 文字縁取り: 色/透明度をCSS変数に保存し全値読み出して合成適用
- [x] 幅/高さ/文字サイズを共通UIに移行、重複する固有スライダー削除
- [x] border_enabledをDB/デフォルト/マッピングから削除

## アイテム共通化 Phase 7: 動的アイテム移行

- [x] custom_textsのCRUDをbroadcast_items経由に全面書き換え（ID体系: customtext:{n}）
- [x] custom_texts/capture_windowsテーブル → broadcast_itemsへの自動マイグレーション
- [x] 旧テーブルはフォールバック用に残留（capture.pyの全面書き換えは別タスクに分離）
- [x] テスト10件追加（custom_text CRUD、API互換、マイグレーション）

## アイテム共通化 Phase 6: broadcast_itemsテーブル + 固定アイテム移行

- [x] broadcast_itemsテーブル作成（共通22カラム + properties JSON）
- [x] CRUD関数（get/upsert/update_layout + キー名↔カラム名自動マッピング）
- [x] overlay.* settings → broadcast_itemsマイグレーション（初回起動時自動実行）
- [x] 統合API `/api/items` (GET/PUT/{id}/layout/visibility)
- [x] 旧API `/api/overlay/settings` をbroadcast_items優先の互換レイヤーに更新
- [x] テスト15件追加（test_api_items.py）

## アイテム共通化 Phase 3: CSS統一

- [x] version-panel/dev-activity-panelのインラインスタイル全除去→CSSルールに移行
- [x] CSS変数（--item-border-radius, --item-padding, --item-text-color, --item-font-size）でPhase 2のapplyCommonStyleと接続
- [x] subtitle/todo/topicのborder-radiusをvar(--item-border-radius)に変更
- [x] テスト6件追加

## アイテム共通化 Phase 4: Web UI設定パネル

- [x] 全fieldsetに`data-section`属性追加、dev_activityフィールドセット新規追加
- [x] `_commonPropsHTML()`で折りたたみ「詳細設定」UI動的生成（visible, bgColor, borderRadius, border, textColor, textStroke, padding）
- [x] `onLayoutColor()`/`onLayoutToggle()`/`cssColorToHex()`ハンドラ追加
- [x] `loadLayout()`拡張（カラー・トグル初期値）、WebSocket同期にカラー・トグル対応追加
- [x] テスト6件追加

## アイテム共通化 Phase 5: 保存漏れバグ修正 + visible対応 + リアルタイム同期

- [x] editSave()保存漏れ修正: subtitle(bottom/fontSize/maxWidth/fadeDuration/bgOpacity), topic(maxWidth/titleFontSize), version(fontSize/strokeSize/strokeOpacity/format)
- [x] 全アイテムvisible対応: saveVisible(opt-in) → skipVisible(opt-out)に変更、dev_activity以外でvisible保存
- [x] プレビュー→WebUIリアルタイム反映: index-app.jsに/ws/broadcast WebSocket接続追加、settings_updateイベントでスライダー自動更新
- [x] テスト5件追加（visible保存・固有プロパティ保存・skipVisible検証）

## アイテム共通化 Phase 2: broadcast.html JS共通化

- [x] `ITEM_REGISTRY` で6アイテムをレジストリ定義（hasSize/saveVisible/defaultZ）
- [x] `applyCommonStyle()` で共通スタイル適用（position/zIndex/bgOpacity直接 + CSS変数で新規プロパティ）
- [x] `applySettings()` を applyCommonStyle + アイテム固有コードの2段階に統一
- [x] `editSave()` を ITEM_REGISTRY ループに統一（ハードコード個別保存を廃止）
- [x] dev-activity-panel に `data-editable="dev_activity"` 追加（ドラッグ・リサイズ可能に）
- [x] ソースコード解析テスト11件追加（test_broadcast_patterns.py）

## アイテム共通化 Phase 1: 共通プロパティのDB保存基盤

- [x] `_COMMON_DEFAULTS` (20プロパティ) 定義（visible, 配置, 背景, 文字）
- [x] `_make_item_defaults()` で共通デフォルト + アイテム固有オーバーライドをマージ
- [x] 全6ビジュアルアイテムに共通プロパティ追加（avatar, subtitle, todo, topic, version, dev_activity）
- [x] dev_activityをDB保存対応（`overlay.dev_activity.*` キー新設）
- [x] テスト8件追加（共通プロパティ・API・dev_activity）

## バージョン表示

- [x] VERSIONファイル新規作成（0.1.0）
- [x] /api/statusにversion・updated_at（gitコミット日時）を追加
- [x] WebUIヘッダーにバージョン・更新日付を表示

## WebUIウィンドウキャプチャ管理の改善

- [x] WebUI: キャプチャ一覧を保存済みウィンドウベースに変更、各項目にレイアウトスライダー統合
- [x] WebUI: アクティブなキャプチャは緑ボーダー+表示/非表示トグル、非アクティブは半透明表示
- [x] capture_windowsテーブル新設（settings JSONから専用テーブルに移行）
- [x] C#アプリ: キャプチャ追加/停止時にWebSocketでPython側に即時通知（BroadcastWsEvent）
- [x] サーバー: C# WebSocket接続時にキャプチャ自動復元（visible=falseはスキップ）
- [x] DB閲覧: 全テーブル自動検出対応（settingsテーブル等も閲覧可能に）
- [x] 前回のウィンドウキャプチャを覚えておき次回も最初から表示
- [x] staticファイルにno-cacheヘッダー追加

## テスト充実フェーズ1 — DB・設定・TTS・テスト基盤

- [x] conftest.py拡張: test_db / mock_gemini / mock_env フィクスチャ追加
- [x] test_db.py: 44テスト（スキーマ・チャンネル・キャラクター・番組・エピソード・ユーザー・コメント・設定・BGM・トピック・スクリプト）
- [x] test_scene_config.py: 12テスト（DB/JSON優先順位・保存読み込み）
- [x] test_tts.py: 11テスト（言語タグ変換・TTSスタイル取得）
- [x] plans/testing-strategy.md: テスト充実プラン作成
- [x] テスト数: 39 → 114（+75テスト）

## テスト充実フェーズ2+3 — AI応答・WSL・Git監視・トピック

- [x] test_ai_responder.py拡張: +22テスト（キャラクター管理・generate_response/event/notes/self_noteのGeminiモック）
- [x] test_wsl_path.py拡張: +10テスト（is_wsl・IP取得・パス変換）
- [x] test_git_watcher.py: 11テスト（コミット解析・バッチ通知・ライフサイクル）
- [x] test_topic_talker.py: 15テスト（プロパティ・should_speak・トピック管理・get_next）
- [x] conftest.py: mock_geminiがfrom import先にもパッチするよう改善
- [x] テスト数: 114 → 177（+63テスト）

## テスト充実フェーズ4 — APIエンドポイントテスト

- [x] conftest.py: api_clientフィクスチャ追加（FastAPI TestClient + stateモック）
- [x] test_api_character.py: 6テスト（キャラクター取得・更新・言語モード取得・変更）
- [x] test_api_topic.py: 11テスト（トピックCRUD・スクリプト・一時停止・設定）
- [x] test_api_stream.py: 13テスト（シーン切替・音量制御・アバター・ステータス・環境変数マスク）
- [x] テスト数: 177 → 207（+30テスト）

## 音声アーキテクチャ刷新: C#アプリ直接パイプ（WASAPI廃止）— 作業中

### 完了
- [x] TtsDecoder.cs: WAV（24kHz mono 16bit）→ 48kHz stereo f32le PCM変換 + 音量適用
- [x] FfmpegProcess.cs: タイマーベース音声ジェネレータ + TTS/BGMミキシング（WASAPI不要）
- [x] HttpServer.cs: `tts_audio`/`bgm_play`/`bgm_stop`/`bgm_volume` WebSocketアクション
- [x] MainForm.cs: TTS常時ローカル再生(PlayTtsLocally) + 配信時FFmpegパイプ
- [x] MainForm.cs: BGMダウンロード→キャッシュ→NAudioローカル再生 + パネルUI状態表示
- [x] broadcast.html: 全音声再生コード削除（`<audio>`要素・AudioContext・メーター全撤去）
- [x] comment_reader.py: 素材準備→同時発火フロー（字幕+リップシンク+TTS一斉送信）
- [x] state.py: BGMコマンドをC#アプリにWebSocket転送
- [x] capture.py: C#アプリWebSocket接続時にBGM自動復元
- [x] プラン: plans/direct-tts-audio-pipe.md

### バグ修正
- [x] BGM配信パイプ: DecodeBgmToPcmに相対WebURLを渡していた→キャッシュファイルパスを使用
- [x] TTS音声ガビガビ: AudioWriterLoopとタイマーの両方でMixTtsIntoを呼んでいた→タイマーのみに統一
- [x] BGM音量変更がFFmpegに未反映: SetBgmVolume()追加、OnBgmVolumeから転送
- [x] 配信バッファリング: 音声ジェネレータが固定10msチャンクだがWindowsタイマー解像度15.6msで発火→音声65%供給→FFmpeg speed 0.69x。壁時計時間ベースのチャンクサイズ動的計算で1.01x安定化
- [x] ボリューム調整: waveOutSetVolumeがアプリセッション共有でBGM⇔TTS干渉→WaveChannel32でサンプルレベル音量制御に移行。パネル/Web UI/起動時取得の全経路でC#音声パイプラインに即時反映。TTS/BGM再生中のリアルタイム音量変更対応。FFmpegミキサーもSetTtsVolume/SetBgmVolumeでリアルタイム反映
- [x] 音量メーター: MeteringWaveProviderでBGM/TTS再生パイプラインのRMS/peakをリアルタイム測定。配信中はFfmpegProcess.MeasureLevelで実測。50msタイマーでパネルに送信。JS側ピークホールド1.5秒

- [x] リップシンク同期: 配信時は字幕・口パクをlipsyncDelay(ms)遅延させて音声と同期。非配信時はリアルタイム(0ms)。遅延値はcontrol-panel/Web UIから設定可能、DB永続化。broadcast.htmlが設定の真のソース（_volumeSync経由でパネルに転送）
- [x] 音声先行送信: TTS音声をC#アプリに先に送信しFFmpegキュー投入完了を待ってから字幕・口パクを発火するよう変更。lipsyncDelayを500ms→100msに削減（音声パイプライン遅延が大幅に縮小）

## Go Live / Stop ボタンの即時フィードバック

- [x] ボタン押下直後にテキスト変更（「準備中…」「停止中…」）+ CSSスピナー + disabled化で押した感を実現
- [x] C#側から処理完了/失敗時に `streamResult` メッセージをパネルに送信してボタン復帰
- [x] 処理完了後 `OnTrayUpdate` 即時呼び出しでステータス即時反映（3秒タイマー待ち解消）
- [x] プラン: plans/button-instant-feedback.md

## リップシンクと音声の4秒ずれ修正（暫定対応）

- [x] 原因特定: 映像（WGC即座キャプチャ）と音声（WASAPI Loopback回収、~500ms遅延）の経路差
- [x] Phase 1: broadcast.htmlリップシンク同期修正 — 口パク開始を`play().then()`に同期（WebSocketイベント受信時ではなく音声再生開始時）
- [x] Phase 2: 音声パイプバッファ縮小 — 1MB→64KB（遅延2.7秒→170ms）
- [x] Phase 3: 初期サイレンス縮小 — 3秒→300ms（パイプバッファ満杯防止）
- [x] FFmpegエンコード開始検知→音声キューフラッシュ（起動時蓄積50チャンクの遅延を除去）
- [x] `LIPSYNC_DELAY_MS = 500` で口パク開始を遅延（音声パイプライン遅延と一致させる暫定補正）
- [x] `AudioOffset` 設定をStreamConfigに追加（CLI `--audio-offset` / 環境変数 `AUDIO_OFFSET` で調整可能）
- [x] 根本解消プラン作成: TTS音声を直接FFmpegパイプに書き込み、WASAPI迂回を解消 → plans/direct-tts-audio-pipe.md
- [x] プラン: plans/lipsync-delay-fix.md

## 配信開始後の音声途切れ修正

- [x] 原因特定: FFmpegのRTMP接続確立中（speed=0.45x→1.0x、約40秒）にパイプ書き込みがブロック → WASAPIコールバック停止 → 音声データ消失
- [x] 音声書き込みを非同期化: ConcurrentQueue + バックグラウンドスレッド（AudioPipeWriter）でWASAPIコールバックを絶対にブロックしない設計に変更
- [x] キュー上限500チャンク（約5秒）超過時は古いデータを破棄（最新音声を優先）
- [x] FFmpeg thread_queue_size 512→1024に増大
- [x] 初期サイレンス1秒→3秒に増量（AAC encoder + resamplerプライミング）
- [x] WASAPI開始前に500ms待機（FFmpegパイプ読み取り安定化）
- [x] AudioLoopback統計ログを起動後30秒間は2秒間隔に変更（診断用）
- [x] FFmpeg stderr起動後60秒間をSerilogにも出力（診断用）
- [x] AudioWriterLoop停止時のOperationCanceledException catchで停止クラッシュ修正
- [x] StopAsync順序改善: パイプ閉鎖→スレッドJoin（ブロック解除を先に行う）
- [x] プラン: plans/audio-startup-fix.md

## コントロールパネルStopボタン修正

- [x] StopStreamingAsyncでフィールド（_ffmpeg/_audio/_activeStreamKey）を即座にクリア→UI即時反映
- [x] OnFrameReady=nullを_ffmpeg=nullより先に実行（キャプチャコールバックのNREクラッシュ防止）
- [x] FrameCapture.csのOnFrameReady呼び出しにローカル変数キャプチャ+NRE catchガード追加
- [x] AudioLoopback.Stop()のManualResetEventパターン除去（using早期disposeによるクラッシュ修正）
- [x] AudioLoopback.Stop()で_silenceTimerをnull先行設定（DataAvailableとのレース防止）
- [x] DataAvailableの_silenceTimer.Change()をtry-catch(ObjectDisposedException)で防御
- [x] AudioLoopback.Dispose()でNAudioのCOM Disposeをスキップ+GC.SuppressFinalize（ハング/クラッシュ回避）
- [x] WebView2にバックグラウンドスロットリング無効化フラグ追加（音声途切れ対策）
- [x] 未処理例外ハンドラ追加（AppDomain/ThreadException/UnobservedTaskException）
- [x] 診断ログ追加（Panel送受信・Stop各ステップ・Audio統計）
- [x] プラン: plans/post-electron-bugs.md

## Twitch配信音声途切れ修正

- [x] サイレンスタイマーの二重書き込み防止（lastDataTickフラグで実データ受信200ms以内はサイレンス送信スキップ）
- [x] _silenceTimer.Change()リセット廃止（フラグ方式に置換）
- [x] WebView2バックグラウンドスロットリング無効化（--disable-background-timer-throttling等3フラグ追加）
- [x] Audio統計ログ追加（10秒ごとdata/silence/bytesカウント）
- [x] プラン: plans/post-electron-bugs.md

## Electron完全削除（Phase 8）

- [x] win-capture-app/ ディレクトリ削除
- [x] capture.py からElectronビルド・デプロイ・管理コードを削除（1362行→約500行）
- [x] stream_control.py 簡素化（_use_native_app()・Electron分岐削除）
- [x] index.html からElectron UI要素削除（サーバー起動/停止・ビルド進捗・ワンクリックプレビュー）
- [x] broadcast.html からElectron IPC死コード削除（audioCapture・captureReceiver・setupDirectCapture）
- [x] .env.example から USE_NATIVE_APP 設定削除
- [x] .gitignore から win-capture-app 関連行削除
- [x] CLAUDE.md・README.md をネイティブアプリに統一更新

## プロセス終了しない問題の修正

- [x] HttpServer.Dispose に _listenTask.Wait(2000) 追加（ListenLoopが残り続ける問題）
- [x] FfmpegProcess.StopAsync で Kill() 後に WaitForExit(3000) 追加
- [x] FfmpegProcess.LogStderrAsync に _stopping チェックと EOF break 追加
- [x] AudioLoopback.Stop でタイマーコールバック完了を待機（ManualResetEvent）
- [x] MainForm.OnFormClosing をタイムアウト付き同期処理に変更 + Environment.Exit(0) で確実終了

## コントロールパネルをタブ化（Stream / Sound / Chat）

- [x] タブバー追加（Stream / Sound / Chat の3タブ）
- [x] Stream タブ: 配信制御 + キャプチャ + ログ
- [x] Sound タブ: 音量スライダー + 音量メーター
- [x] Chat タブ: プレースホルダー（Coming soon）
- [x] UIラベルを英語表記に統一
- [x] C#側の変更不要（WebView2メッセージインターフェース維持）
- [x] プラン: plans/control-panel-tabs.md

## 音量メーター危険ゾーン表示

- [x] control-panel.htmlにHot(-12dB〜-3dB)・Danger(-3dB〜0dB)ゾーン背景と境界ラインを追加
- [x] ピークが-3dB超でメーター枠が赤く光るクリッピング警告を追加
- [x] プラン作成: plans/volume-danger-zone.md

## UIラベル「TTS」→「Voice」に変更

- [x] control-panel.html（音量スライダー・メーターソース）とpreview.html（メーターソース）の表示を「Voice」に統一

## アバターライティング起動時復元修正

- [x] broadcast.htmlの`<script type="module">`（Three.js+VRM）と`<script>`（init/applySettings）の実行順序レースコンディションを修正。module scriptのCDN読み込み遅延により`window.avatarLighting`未定義のままライティング適用がスキップされていた問題を、pending settingsパターンで解決

## ウィンドウ閉じ時の音声ミュート

- [x] ×ボタンでウィンドウ非表示後もWebView2の音声（BGM/TTS）が鳴り続ける問題を修正。Hide()直後にCoreWebView2.IsMutedで即座にミュート

## ビュワー×ボタンの閉じ遅延修正

- [x] ×クリック時にHide()を即座に呼び出し、クリーンアップはバックグラウンドで実行するよう変更（WebView2/HTTP/WGCの同期破棄によるUI遅延を解消）

## ウィンドウキャプチャ永続化 + キャプチャタブ

- [x] キャプチャ設定をDB永続化（window_nameで保存、次回起動時にウィンドウ名マッチングで自動復元）
- [x] 保存済み設定API追加（GET/DELETE /api/capture/saved、POST /api/capture/restore）
- [x] Electron起動時・ワンクリックプレビュー時にキャプチャ自動復元
- [x] レイアウト変更時に保存済み設定も同期更新
- [x] Web UIに「キャプチャ」タブ追加（サーバー管理・キャプチャ操作・保存済み設定管理）
- [x] キャプチャUI を「配信画面」タブから「キャプチャ」タブに移動

## TTS英語発音改善

- [x] 英語の発音をちゃんと英語っぽく（AI生成時に言語タグ分離+スタイルプロンプト英語化+発音ヒント挿入、サウンドテスト言語選択対応）

## C#ネイティブアプリに音量メーター追加・音量カーブ改善

- [x] broadcast.html → WebView2 postMessage → C# → control-panel.html の音量レベル転送パイプライン追加
- [x] control-panel.htmlに音量メーターUI（レベルバー・ピーク・dB表示・BGM/Voiceソース表示）
- [x] AnalyserNodeをmasterGainの後に移動し、マスター音量変更がメーターに反映されるよう修正
- [x] 全音量チャンネル（Master/TTS/BGM）に二乗カーブ（perceptualGain）適用。人間の聴覚特性に合わせた知覚的音量制御

## プレビューウィンドウに音量メーター追加

- [x] broadcast.htmlにAudioContext+AnalyserNodeで音量測定（BGM+Voice合成RMS→dBFS）
- [x] postMessageでiframe親（preview.html）にリアルタイム送信（50ms間隔）
- [x] preview.html右パネルに音量セクション追加（グラデーションバー、ピークホールド、BGM/Voiceタグ）
- [x] Electronオフスクリーン配信時はメインプロセスミキサー用の/audio/levelsエンドポイントも追加

## Live2D/VTube Studio関連コードの完全削除

- [x] VTSコントローラー・デプロイスクリプト・対話式コンソール削除
- [x] VTSエンドポイント・接続ロジック・状態変数をコードから除去
- [x] pyvts依存・VTS環境変数・AVATAR_APP設定を削除
- [x] Live2D関連ドキュメント・リソースディレクトリ削除
- [x] VRM機能は影響なし（broadcast.html内Three.js+three-vrm）

## ライティング設定の永続化

- [x] ライティング設定（明るさ・コントラスト・色温度・彩度・環境光・指向性光・ライト方向）をDB保存し、次回起動時に自動反映（broadcast.html init()で/api/overlay/settings読み込み→applySettings適用）

## アバター色味改善

- [x] ACESFilmicToneMapping → NoToneMapping（トーンマッピングなし）
- [x] ライティング調整（AmbientLight 2.0→0.75、DirectionalLight 1.5→1.0、方向修正）
- [x] Web UIにライト直接制御（環境光・指向性光・ライト方向X/Y/Z）追加
- [x] ライティングプリセット保存・読込・削除機能（DB永続化）
- [x] 汎用確認ダイアログ（showConfirm）を実装し、全confirm()を置換

## Electron配信パイプライン（Phase 1+2）

- [x] Electronオフスクリーンレンダリング＋FFmpegでTwitch直接配信（xvfb/PulseAudio不要）
- [x] broadcast.htmlをoffscreen BrowserWindowで描画→paint event→rawvideo→FFmpeg→RTMP
- [x] Electron側HTTP/WebSocket API追加（stream start/stop/status, broadcast open/close）
- [x] WSL2側API追加（POST /api/capture/stream/start|stop, GET /api/capture/stream/status）
- [x] 無音音声（anullsrc）でTwitch音声要件対応
- [x] Phase 3: TTS/BGM音声キャプチャ（AudioContext+ScriptProcessorNode→PCM→IPC→Named Pipe→FFmpeg）
- [x] broadcast-preload.js追加（contextBridge経由でaudioCapture API公開）
- [x] Windows Named Pipe経由のPCMデータ中継（非WindowsはanullsrcフォールバックFFmpeg）
- [x] Phase 5: 配信制御API統合（go-liveからElectron配信開始、統合ステータスAPI）
- [x] WSL2配信パイプライン削除（stream_controller.py全削除、xvfb/PulseAudio/Chromium依存排除、Electron一本化）
- [x] stream_control.py/state.py/index.html/preview.htmlをElectron専用に簡略化
- [x] docs/obs-free-streaming.md削除、CLAUDE.md/README.md/.env.example/mkdocs.yml更新
- [x] Phase 6: MJPEG排除（キャプチャフレームをIPC直接転送、MJPEG HTTPエンドポイント廃止、タイミング競合修正）

## 字幕デバッグ・レイアウト修正

- [x] Web UIに字幕テスト表示/非表示ボタンを追加（デバッグ用API: POST /api/debug/subtitle, /api/debug/subtitle/hide）
- [x] 字幕のbottomパラメータがドラッグ後にリアルタイム反映されないバグ修正（style.topとbottomの競合解消）

## WebSocket統合（Step 1-3）

- [x] TODO表示をWebSocket push化（30秒ポーリング廃止、mtime監視+API変更時に即座ブロードキャスト）
- [x] キャプチャ映像をMJPEG→WebSocketバイナリ送信に変更（1byte index+JPEG、バックプレッシャー制御、MJPEG互換維持）
- [x] Electron↔WSL2間の制御をWebSocket常時接続に変更（HTTPフォールバック維持、リクエスト-レスポンスマッチング）
- [x] ビルドログをbuild.logに出力＋API（`/api/capture/build-log`）追加
- [x] dist権限エラー時にPowerShellでdist削除するフォールバック追加

## プレビュー確認→配信開始UX

- [x] プレビュー起動ワンクリック化（ビルド確認→ビルド→デプロイ→起動→プレビュー表示を自動実行、進捗バー付き）
- [x] ワンクリックプレビューを毎回フルビルド方式に変更（mtime差分チェック廃止→毎回asar再パック・デプロイ・再起動で確実に反映）
- [x] package.jsonハッシュをDBに保存し、古いexeの再ビルドを自動検知
- [x] capture_launch()をヘルパー関数にリファクタ（_deploy_to_windows, _launch_electron, _wait_for_server）
- [x] Electronキャプチャアプリのビルドテスト（ワンクリックプレビューでビルド→起動確認済み）
- [x] WEB UI読み込み時にElectronプレビューを自動起動
- [x] broadcast.htmlの編集モードにGo Live/配信停止ボタン+状態表示を追加
- [x] POST /api/broadcast/go-live（Setup+配信開始をワンステップ化）
- [x] broadcast-ui.htmlをindex.htmlにリネーム、/broadcast-uiルート削除
- [x] xvfb ChromiumでVRMアバター表示（--use-gl=angle --use-angle=swiftshaderで解決）
- [x] Electron環境での配信テスト（プレビュー確認→Go Live→Twitch配信成功）
- [x] ウィンドウキャプチャの動作テスト（Electronアプリ起動→キャプチャ→broadcast.html表示確認）
- [x] Electronプレビューウィンドウのメニューバー削除（Menu.setApplicationMenu(null) + setMenu(null)）
- [x] asar再パックのサイレント失敗を修正（権限修正+mtime検証+デプロイ検証）
- [x] 各要素のZ順序変更機能（右クリックメニュー→Z値ダイアログ、WEB UIレイアウトタブにも追加）
- [x] preview.html: iframe+コントロールパネル方式でツールバーとコンテンツの重なり解消
- [x] broadcast.htmlのembeddedモード（iframe内でツールバー非表示）
- [x] ワンクリックプレビューでasar更新時にElectronアプリを自動再起動（/quit API + フォールバック）

## Electronプレビューウィンドウ改善

- [x] プレビューウィンドウの位置・サイズを永続化（preview-bounds.json、move/resize時に自動保存）
- [x] 編集モードを常時有効化（?editパラメータ廃止、ツールバー常時表示、編集終了ボタン削除）

## 設定DB移行

- [x] scenes.json設定をDB優先に移行（scene_config.pyにload_config_value/load_config_json/save_config_value/save_config_json追加）
- [x] bgm.py: BGMトラック設定のDB化
- [x] avatar.py: アバターデフォルト設定のDB化
- [x] character.py: language_mode保存のDB化
- [x] stream_control.py: avatar_capture_url・音量設定のDB化
- [x] overlay.py: 音量・オーバーレイデフォルト設定のDB化
- [x] state.py: アバターデフォルト設定読込のDB化
- [x] web.py: startup言語モード復元のDB化

## Web UI整理

- [x] 「レイアウト」タブを「配信画面」にリネーム（分かりやすい名前に変更）
- [x] ウィンドウキャプチャのカードを「配信」タブから「配信画面」タブに移動
- [x] 「ダッシュボード」タブと「配信」タブを削除（TODO/Twitch情報/シーン/診断のUI・JS・CSS含む）
- [x] キャプチャウィンドウのレイアウト設定（X/Y位置・幅・高さ・Z順序）をWeb UIの配信画面タブに追加
- [x] キャプチャレイヤーの四隅リサイズ修正（重複ハンドル防止＋overflow:hidden除去）
- [x] Go LiveでElectron未起動時にワンクリックプレビューを自動起動してから配信開始
- [x] Electron WebSocket /ws/control接続不可修正（noServerモード+手動upgrade振り分けで複数WebSocket.Server共存）
- [x] serverUrl方向修正（get_windows_host_ip→get_wsl_ip: Electron→WSL2へのアクセスに正しいIPを使用）
- [x] FFmpeg自動ダウンロード機能追加（getFfmpegPath強化+downloadFfmpeg: PowerShellでBtbN FFmpeg Buildsから自動取得）
- [x] FFmpeg起動失敗の即座検出修正（spawn後500ms待機で即座終了を検知、エラーを正しく返す）
- [x] _ws_requestにtimeoutパラメータ追加（start_streamは120秒タイムアウトでFFmpegダウンロード対応）

## プロジェクト整理

- [x] OBS関連ファイル・コード完全削除（obs_controller.py, routes/obs.py, routes/stream.py, start_stream.py, stop_stream.py, overlay.html, audio-tts.html, audio-bgm.html, index.html, design-proposal.html, OBS関連ドキュメント3件, tests/test_scene_config.py）
- [x] state.py: OBSController/overlay_clients/tts_clients/bgm_clients削除、broadcast_clientsのみに統合
- [x] overlay.py: /ws/overlay, /ws/tts, /ws/bgm WebSocket削除、OBS用ページルート削除
- [x] bgm.py: _apply_bgm_volume()（OBS音量反映）削除
- [x] console.py: OBSコマンド・stream・init全削除、アバター専用に簡素化
- [x] scene_config.py: PREFIX/SCENES/MAIN_SCENE/_load_config()/_resolve_browser_url()削除、設定値のみに簡素化
- [x] scenes.json: avatar/main_scene/scenes OBS専用キー削除
- [x] requirements.txt: obsws-python削除
- [x] CLAUDE.md/mkdocs.yml/console-commands.md/メモリファイル全更新

## 調査タスク

- [x] OBSの機能調査（WebSocket API、シーン管理、ソース操作、フィルタ、配信制御等）
- [x] アバター表示・アニメーションの調査（PNGtuber / Live2D + VTube Studio / VRM等）
- [x] 3Dモデル調査（VRM形式、表示ソフト比較、VMC Protocol制御、モデル入手方法）

## 動作確認タスク

- [x] OBSを起動してTwitchで仮配信（画面には背景画像だけ表示）
- [x] Live2D + VTube Studio + OBS で配信テスト（アバターのデモ動作確認済み）
  - Bluetoothヘッドホン使用時、OBSがマイクを掴むとHFPプロファイルに切り替わり音質劣化する問題を確認 → マイク音声を無効にして解決

## 開発タスク

- [x] OBS制御プログラムの作成（Python + obsws-python）
- [x] VTube Studio制御プログラムの作成（Python + pyvts）
- [x] 対話式コンソールの作成（OBS・VTS・配信制御）
- [x] リソース管理方針の策定（WSL一元管理、デプロイスクリプト）
- [x] コードからシーンとソースを追加する（setup/teardown、個別add/remove）
- [x] ゲームキャプチャでVTube Studioのアバターを透過表示
- [x] システム作成のシーン・ソースに「[ATC] 」プレフィックスを付与してユーザー作成物と区別
- [x] VRM形式の3Dキャラ表示に対応（ブラウザVRMビューア + scene_config切替）
- [x] console.py相当のWebインターフェースを作成（FastAPI + HTML）
- [x] シーンの設定をJSONで設定できるように（scenes.json）
- [x] アバターの配置位置を設定可能に（scenes.jsonのavatar.transform）
- [x] セットアップ後にメインシーンへ自動切替（scenes.jsonのmain_scene設定）
- [x] シーンごとのアバター位置オーバーライド対応
- [x] Webインターフェースでアバター位置調整・scenes.jsonへの保存機能
- [x] Web UIにSetup/配信開始・停止ボタン、.env設定表示を追加
- [x] Twitchコメント読み上げ機能（Gemini 2.5 Flash TTS + twitchio）
- [x] AIコメント応答システム（character.jsonでキャラ設定・ルール定義、表情連動）
- [x] コメント・配信データのDB化（SQLite: チャンネル/キャラクター/番組/エピソード/ユーザー/コメント/アクション）
- [x] AIがどのようにコメントに対応するかをルール付けする方法を構築（character.json + ai_responder）
- [x] キャラクター設定をDBに移行し、Web UIから編集可能に（character.jsonはシード用として残存）
- [x] web.pyルート分割リファクタリング（514行→118行、5つのルートモジュール+共有state）
- [x] OBSController._clientカプセル化修正（get_scene_items追加、外部からの_client直接アクセス排除）
- [x] Geminiモデル名を.env設定可能に（GEMINI_CHAT_MODEL / GEMINI_TTS_MODEL）
- [x] print()→logging置換（src/全ファイル、エントリポイントにbasicConfig追加）
- [x] Geminiクライアント共通化（ai_responder/tts重複→src/gemini_client.py抽出）
- [x] db.py update_character SQLホワイトリスト化
- [x] comment_reader._respond()分割（AI応答・DB保存・オーバーレイ・TTS再生を個別メソッドに）
- [x] vts_controller WS接続コード重複解消（_establish_websocket抽出）
- [x] TODO.mdを配信画面中央にオーバーレイ表示（Web UIからトグル）
- [x] Twitch配信情報管理（タイトル・カテゴリ・タグの取得・更新をWeb UIから操作）
- [x] ターミナルウィンドウキャプチャ対応（window_captureソース追加、メインシーンに配置）
- [x] VRMにモデル変換（FBX→VRM 0.x変換パイプライン構築、MToonシェーダ修正、サムネイル埋め込み）
- [x] Twitchコメント応答でユーザー表示名を使用（display_name優先）
- [x] ターミナルウィンドウ自動選択（window_matchキーワードマッチング）
- [x] ターミナル位置をWeb UIから調整・scenes.jsonに保存可能に
- [x] scenes.jsonのSetup時リロード対応（保存した設定が次回Setupで反映）
- [x] TODOパネルをオーバーレイ起動時に自動表示
- [x] BGM再生機能（OBSメディアソース経由、Web UIから選曲・音量調整・試聴対応）
- [x] アバターが話した内容を表示（履歴表示・英語訳・コメント見やすく・キャラ名削除）
- [x] コミットや作業開始に合わせてアバターが発話（Git監視・配信開始挨拶・手動発話API）
- [x] TODOパネルをオーバーレイに再実装（Web UIから位置・サイズ・フォント設定可能）
- [x] Git監視をSetupボタンでも起動するよう修正（配信開始ボタンのみだった問題を修正）
- [x] 現在の作業パネル（CURRENT TASK）をオーバーレイに追加（Claude Codeフック連携）
- [x] 多言語コメント対応（相手の言語で返答、英語は日本語訳・その他は英語訳）
- [x] アバターの耳ぴくぴくアニメーション（Hair_ear_1.L/Rボーン、ランダム間隔・片耳/両耳）
- [x] コメント履歴をオーバーレイから削除し、AI応答をTwitchチャットに投稿するよう変更
- [x] TODO表示が消える問題を修正（setup/teardownの安定性改善で解決）
- [x] 声を変更（Leda→Despina、スタイルプロンプト「にこにこ」追加、全30ボイス×5スタイルの比較ページ作成）
- [x] キャラクター設定をDB一本化（character.json削除、デフォルト値をai_responder.pyの定数に移動）
- [x] Web UIデザイン刷新（Lavenderライトテーマ、ヘッダー+ステータスバー+5タブ分割、15テーマ切替付きデザイン提案ページ作成）
- [x] 最初の挨拶を削除（Setup時・配信開始時の自動発話を除去）
- [x] キャラクター名を「ちょび」に全箇所統一
- [x] アバターのセリフがチャット欄に表示されない問題を解消（再起動で解決、デバッグログ追加）
- [x] Gitコミット読み上げにクールダウン60秒+バッチ通知を追加
- [x] Claude Code作業中にアバターの動きが止まる問題を修正（idle animationをasyncio taskから専用スレッドに移行）
- [x] サーバー再起動方式を改善（--reload廃止、コミット時のみ再起動、startup自動復旧）
- [x] TODO表示の作業中アイテム強調（グロー+▶矢印+ボーダー）＆左上を汎用情報パネルに刷新
- [x] BGM再生機能（overlay audio経由、Web UIから選曲・音量調整・試聴、YouTube URLダウンロード対応）
- [x] BGM再生状態の永続化・再生中ハイライト表示
- [x] OBS音声モニタリングをオフに変更（配信出力のみ、ローカルモニターなし）
- [x] TTS/BGM音声ソース分離（独立ブラウザソース化でOBSミキサー個別制御、OBS SetInputVolume APIで音量制御、scenes.json audio_volumesに保存）
- [x] マスター音量追加（master × 個別 × 曲音量の実効値をOBSに適用、Web UIでカード分離表示）
- [x] 曲別音量復活（DB保存、再生・変更時にOBSへ即反映）
- [x] 音量スライダー0〜200%対応（OBS vol_mul上限2.0）
- [x] run.sh二重起動防止（PIDファイル+ポート使用チェック、kill -9で確実停止）
- [x] ACTIVITYパネルを一時非表示（display: none、コードは保持）
- [x] 作業中タスクをTODOリストの先頭に「作業中」セクションとして表示
- [x] イベント発話（コミット・作業開始等）もTwitchチャットに投稿
- [x] 字幕と音声の同期修正（TTS生成後に字幕と音声を同時送信するよう変更）
- [x] リップシンク実装（WAV振幅解析→30fpsで口BlendShape「A」を駆動、idle loop統合）
- [x] チャット投稿と音声再生の同期（TTS生成後にまとめて発火するよう変更）
- [x] トピック自発的発話機能（コメントがない時にトピックについて自動発話、スクリプト事前生成・補充、Web UI対応）
- [x] Web UIにDB閲覧タブ追加（テーブル選択・ページング・全テーブル対応）
- [x] トピック自発的発話をSetup/配信開始では開始せず、明示的にトピック設定した時のみ開始するよう変更
- [x] トピックパネルを常に表示（会話中以外は「----」表示）
- [x] 直近2時間の会話履歴を考慮したAI応答（配信またぎ対応、マルチターン形式）
- [x] アバター発話（トピック・イベント）をDBに保存して会話履歴に含める
- [x] 配信コンテキスト（タイトル・トピック・作業中タスク）をAIプロンプトに追加
- [x] 視聴者メモ機能（15分バッチでAIがユーザー特徴を自動メモ化、応答時にメモを反映）
- [x] 視聴者への挨拶を1配信1回に制限（エピソード内コメント数でAIに挨拶済みフラグを渡す）
- [x] 言語モード切替機能（日本語/英語メイン/英語+日本語混ぜ/マルチリンガルの4プリセット、Web UIから切替、scenes.jsonに永続化）
- [x] アバター画面のUI文字がOBSに表示される問題を修正（cropTop/cropLeftでトリミング）
- [x] アバターアイドルモーションのかくつき修正（まばたきをフレームベース化、フレームタイミング安定化）
- [x] イベント発話（コミット・実装通知）が言語モード設定に従うよう修正
- [x] Web UIリロード時のタブ復元（location.hashでアクティブタブを永続化）
- [x] TTS発音を言語モードに連動（英語モード時は英語スタイルプロンプトでネイティブ発音に）
- [x] テスト基盤構築（pytest + pre-commitフック、Phase 1: 純粋ロジック30テスト）
- [x] トピック自発的発話を改善（事前一括生成→リアルタイム1件生成、前回発話の続き、30文字制限、言語モード対応）
- [x] トピック自動ローテーション（10分経過+5回発話でAIが会話・配信状況から新トピック生成）
- [x] アバター自身の記憶メモ（会話履歴からAIが自動生成、応答時にシステムプロンプトに含めて一貫性を保つ）
- [x] トピック自動生成（トピック未設定時にAIが自動生成、会話ベース50%+キャラ記憶ベース50%の混合）
- [x] アバター発話のDB保存修正（comment_count未加算、トピック発話の保存漏れ、デバッグログ追加）
- [x] 手動メモ更新ボタンでアバター自身のnoteも更新するよう修正
- [x] Web UIのBGMトラック削除ボタン追加（確認ダイアログ付き、再生中は自動停止）
- [x] 英語+日本語混合の単調パターン改善（語尾だけ日本語→文中どこでも配置、ローマ字禁止、履歴5件に削減、多様性指示追加）
- [x] OBS不要配信システム構築（xvfb+Chromium+PulseAudio+FFmpegによるWSL2完結配信）
- [x] 配信合成ページ broadcast.html（overlay+TTS+BGM+VRMアバター統合、WebSocket統合接続）
- [x] 配信制御UI broadcast-ui.html（Setup/Start/Stop/Scene/Volume/Diag）
- [x] StreamController（xvfb/Chromium/PulseAudio/FFmpegプロセス管理、WSLg自動検出）
- [x] 配信制御API stream_control.py（/api/broadcast/*エンドポイント群）
- [x] ブラウザVRMアバター（Three.js+three-vrm、アイドルアニメーション移植）
- [x] VRMアバターWebSocket連携（blendshape/lipsync/lipsync_stopイベントでブラウザ側アバター制御）
- [x] レイアウトエディタ（broadcast-ui.htmlにアバター/字幕/TODO/トピックの位置・サイズ・透明度をスライダー+数値入力で調整、DB自動保存、リアルタイムプレビュー反映）
- [x] レイアウト設定をDB移行（scenes.jsonは初期値のみ、overlay.*キーでDB保存）
- [x] レイアウト単位を%/vwに全面変換（px→%/vw、解像度非依存）
- [x] アバター位置を中心座標+スケール方式に変更（right/bottom→positionX/Y+scale）
- [x] アバターライティング調整（明るさ/コントラスト/色温度/彩度、ACESトーンマッピング+ライト比率制御）
- [x] VRMレンダリング画質改善（pixelRatio最低2倍、SRGBColorSpace、ACESFilmicToneMapping）
- [x] 配信プレビューを別ウィンドウ化（iframe埋め込み廃止、ポップアップウィンドウ+別タブリンク）
- [x] パネル背景透明度をCSS変数化（--bg-opacity、字幕/TODO/トピック個別制御）
- [x] broadcast-ui.htmlをルート（/）に変更
- [x] サーバー再起動ボタン+更新検知ダイアログ（server_started_atポーリング、コミット再起動も検知）
- [x] DB名をcomments.db→app.dbにリネーム（実態に合わせて改名）
- [x] WEBUI全機能移植（OBS版→broadcast-ui統合：タブ化、TODO表示、Twitch配信情報、トピック管理、キャラクター設定、サウンド詳細、DB閲覧、環境変数表示、リンクバー整理）
- [x] Windowsウィンドウキャプチャシステム（Electronアプリ: desktopCapturer+MJPEGサーバー、WSL2側API+WebSocket連携、broadcast.htmlドラッグ&リサイズ編集モード、broadcast-ui.htmlキャプチャ管理UI）
- [x] レイアウト編集にスナップガイド線追加（ドラッグ・リサイズ時に画面中央・他パーツ端/中央への補助線表示+自動スナップ、グロー付き目立つデザイン）
- [x] プレビュー画面でカーソルキーによる要素移動（通常0.1%、Shift+1.0%、500msデバウンスDB保存）
- [x] プレビュー画面で辺リサイズハンドル追加（上下左右の辺中央につまみ、1軸のみリサイズ可能）
- [x] カスタムテキストアイテム（WebUIから自由に追加・編集・削除、broadcast.htmlでドラッグ＆リサイズ、DB永続化、WebSocketリアルタイム同期）
- [x] プレビューウィンドウの配信画面を16:9レターボックス表示（ウィンドウ自由リサイズ対応）
- [x] Electronプレビューウィンドウの検証ウィンドウ（DevTools）自動表示を削除
- [x] 配信音声: FFmpegの音声入力をanullsrc→ローカルHTTPストリーム（broadcast.htmlのPCM音声）に変更、backgroundThrottling無効化+AudioContext監視+診断ログ追加
- [x] 配信音声: メインプロセス直接WAVバイパス（broadcast.html AudioContext不使用、IPC経由でmain.jsが直接WAV取得→リサンプル→FFmpegストリーム書き込み）
- [x] 音声診断ログAPI追加（Electron側 `/audio/log`、WSL2プロキシ `/api/broadcast/audio-log`）
- [x] 配信遅延改善: FFmpeg低遅延フラグ追加（`-flush_packets 1`, `-flags +low_delay`, `-fflags nobuffer`, bufsize半減, thread_queue_size縮小, バックプレッシャー閾値8MB化）
- [x] 配信解像度を1920x1080→1280x720に変更（ビットレート2500kに調整、エンコード負荷軽減で遅延改善）
- [x] 配信BGM音声修正: createScriptProcessorNode→createScriptProcessor修正（WebSocket接続阻害の根本原因）、MP3デコード対応、BGM+TTSミキサー、pendingBgmUrlタイミング問題解決、broadcastWindow embedded修正
- [x] 配信定期停止修正: ミキサーを壁時計追従+自己補正タイマーに改修（setInterval→setTimeout）、常時データ書き込み（無音時もギャップなし）、AudioCapture無効化、初期サイレンス縮小、TCP Nagle無効化

## 開発配信機能 Phase 1-3: リポジトリ管理 + DevStreamManager + AI実況連携

- [x] dev_reposテーブル追加（name, url, local_path, branch, last_commit_hash, active, timestamps）
- [x] CRUD関数実装（add_dev_repo, get_dev_repos, get_active_dev_repos, get_dev_repo, update_dev_repo_commit, toggle_dev_repo, delete_dev_repo）
- [x] DevStreamManager実装（src/dev_stream.py: clone・remove・fetch・diff分析・監視ループ）
- [x] shallow clone（--depth 100）、上限10リポジトリ、diff 500文字制限
- [x] state.pyにdev_stream_manager統合（コールバック→speak_event("開発実況", ...)でTTS・字幕・チャット連動）
- [x] web.pyのsetup/startup復旧/shutdownにDevStreamManager統合
- [x] APIルート実装（scripts/routes/dev_stream.py: repos CRUD・toggle・check・status・start/stop）
- [x] WebUI「開発実況」タブ追加（監視ON/OFF・リポジトリ追加フォーム・一覧表示・toggle/check/削除）
- [x] TODOソース切り替え（自プロジェクト/外部リポジトリ選択、overlay.py汎用化、WebUIセレクトボックス）
- [x] Overlay開発アクティビティパネル（broadcast.htmlにDEV ACTIVITYパネル、15秒表示→フェードアウト）
- [x] テスト追加（test_db.py: 12、test_dev_stream.py: 20、test_api_dev_stream.py: 11）
- [x] CLAUDE.mdにテストセクション追加（実行方法・構成一覧・規約）
- [x] プラン: plans/dev-stream.md

## BGMトラックにYouTubeソースURLリンク追加

- [x] bgm_tracksテーブルにsource_urlカラム追加（マイグレーション付き）
- [x] YouTubeダウンロード時にソースURLをDBに保存（既存トラックへの再ダウンロードでも補完）
- [x] BGM一覧APIがsource_urlを返すよう変更
- [x] Web UIのBGMトラック名をYouTubeリンク化（source_urlがある場合のみ、点線下線付き）

## 素材ファイル管理（著作権物のWebUI管理）

- [x] 素材管理API追加（`scripts/routes/files.py`: アバターVRM・背景画像のアップロード/一覧/選択/削除）
- [x] Web UIに「素材」タブ追加（複数ファイルアップロード、プレビュー付き一覧、使用中表示、選択・削除）
- [x] broadcast.htmlで選択された素材を動的読み込み（起動時API確認＋WebSocketリアルタイム切替）
- [x] `python-multipart`依存追加（ファイルアップロード対応）
- [x] 著作権物（アバターVRM・背景画像）は`.gitignore`で既にgit管理から除外済み
- [x] git履歴にも著作権物が含まれていないことを確認済み（一度もコミットされていない）

## C#ネイティブ配信アプリ（Phase 1: 基盤）

- [x] .NET 8 SDK インストール（Windows側 dotnet.exe 8.0.419）
- [x] C# WinFormsプロジェクト作成（WebView2 + Vortice.Direct3D11 + Serilog）
- [x] WebView2オフスクリーンレンダリング（隠しウィンドウ -32000,-32000 で正常描画確認）
- [x] WGCフレームキャプチャ実装（TryCreateFromWindowId + Direct3D11CaptureFramePool で1920x1080/30fps取得）
- [x] D3D11テクスチャ→BGRA→PNG保存パイプライン（CsWinRT COM interop解決）
- [x] シンボリックリンクでgit管理統合（/mnt/c/Users/akira/Downloads/win-native-app → win-native-app/）

## C#ネイティブ配信アプリ（Phase 2: FFmpeg配信パイプライン）

- [x] FfmpegProcess: FFmpeg子プロセス管理（rawvideo stdin + 名前付きパイプ音声入力 → RTMP出力）
- [x] AudioLoopback: NAudio WasapiLoopbackCapture によるシステム音声キャプチャ
- [x] FrameCapture改修: OnFrameReadyコールバック、FPSスロットル、ステージングテクスチャ再利用
- [x] StreamConfig: 環境変数ベースの配信設定（STREAM_KEY/STREAM_RESOLUTION/STREAM_FPS/STREAM_BITRATE/FFMPEG_PATH）
- [x] MainForm統合: --stream フラグで自動配信パイプライン開始（WGC→FFmpeg stdin、WASAPI→named pipe→FFmpeg）
- [x] FFmpeg stderr → logs/ffmpeg.log 自動保存

## C#ネイティブ配信アプリ（Phase 3: ウィンドウキャプチャ）

- [x] WindowEnumerator: Win32 EnumWindows P/Invokeでウィンドウ一覧取得（自プロセス・最小化・タイトルなし除外）
- [x] WindowCapture: WGC CreateFreeThreadedで任意HWND→D3D11テクスチャ→BGRA→JPEG変換（FPSスロットル付き）
- [x] CaptureManager: ConcurrentDictionaryで複数キャプチャセッション管理（スレッドセーフ）
- [x] HttpServer: HttpListenerベースのHTTP API（/status, /windows, /capture, /captures, /snapshot/{id}）
- [x] MainForm統合: WebView2 JS injection（addCaptureLayer/removeCaptureLayer）でbroadcast.htmlにキャプチャ表示
- [x] stream.sh: Server/ディレクトリのビルドコピー追加

## C#ネイティブ配信アプリ（Phase 4: サーバー通信）

- [x] WebSocket `/ws/control` 実装（HttpListenerベースのWebSocketアップグレード、JSON RPCプロトコル）
- [x] 制御アクション実装（status, windows, start_capture, stop_capture, captures, start_stream, stop_stream, stream_status, screenshot, quit）
- [x] Electron互換レスポンス（broadcast/preview系アクションに互換応答、配列は{data:[...]}形式）
- [x] HTTPストリーミング制御エンドポイント追加（POST /stream/start|stop, GET /stream/status, POST /quit）
- [x] MainForm: WebSocket経由の動的streamKey配信開始、WebView2 CapturePreviewAsyncスクリーンショット
- [x] WSL2 FastAPIサーバーとの通信互換確認（既存の`_ws_request()`がそのまま動作）

## C#ネイティブ配信アプリ（Phase 5: 統合・移行）

- [x] stream_control.py: Electron固有コード→アプリ非依存化（`_ensure_capture_app()`でネイティブ/Electron自動選択）
- [x] ネイティブアプリ自動起動（`USE_NATIVE_APP=1`時にstream.sh経由で自動起動、90秒タイムアウト）
- [x] Electron自動起動はフォールバックとして維持（`USE_NATIVE_APP=0`で既存ワンクリックプレビュー）
- [x] Go Live/Stop/Status APIをアプリ非依存に統一（WebSocketプロトコルは既に共通）
- [x] システムトレイアイコン追加（NotifyIcon: 配信状態表示、右クリックメニューで配信開始/停止/終了）
- [x] トレイアイコン定期更新（3秒間隔: 配信中=赤、待機中=緑、uptime/frames/captures表示）
- [x] トレイからの配信開始/停止（バルーン通知付き）
- [x] .env.example に `USE_NATIVE_APP` 設定追加
- [x] FFmpegパス解決確認（stream.shがElectronダウンロード済FFmpegを`--ffmpeg-path`で渡す、PATHフォールバック有り）
- [x] Twitch配信テスト成功（Go Live API→FFmpeg→RTMP→Twitch映像確認）
- [x] UIスレッドエラー修正（HandleStartStream/StopStreamをBeginInvokeでマーシャリング）
- [x] WGCフレーム停止修正（Direct3D11CaptureFramePool.Create→CreateFreeThreadedに変更）
- [x] オフスクリーン描画停止修正（ウィンドウを-32000,-32000から画面中央CenterScreenに移動）
- [x] FFmpeg stdin書き込みブロック修正（WriteVideoFrameを非同期バックグラウンドスレッドに変更）
- [x] FFmpeg音声入力不足修正（初期サイレンス1秒送信 + WASAPIデータ未着時100msサイレンスフォールバックタイマー）
- [x] FFmpegに`-y -nostdin`フラグ追加（プロンプト防止）
- [x] stream.sh: `--ffmpeg-path`を常に渡すよう変更（配信モード以外でもGo Live API対応）
- [x] StreamConfigデフォルト解像度を1280x720に変更

## フレームレート最適化 Step 1-3（4fps → 18fps）

- [x] 映像入力をstdin匿名パイプ→名前付きパイプ（8MBバッファ）に変更（パイプ書き込み250ms→1ms）
- [x] BGRA→NV12 CPU変換追加（ColorConverter.cs新規、パイプ転送量3.7MB→1.4MBで63%削減）
- [x] HWエンコーダ自動検出（NVENC→AMF→QSV→libx264の優先順probe、`--encoder`オプション追加）
- [x] ダブルバッファ方式でGCプレッシャー回避（毎フレームnew byte[]廃止）
- [x] `-flush_packets 1`除去（RTMP出力のフレーム毎フラッシュが全体を0.748xに制限していた）
- [x] サイレンスフォールバック修正（10ms/100ms→100ms/100ms、音声不足でFFmpegが0.1x speedに制限されていた根本原因）
- [x] デフォルトフレームレートを30→20fpsに変更（GPU readbackが55ms/frameのため暫定対応）
- [x] フレームレート最適化プラン作成（plans/framerate-optimization.md）

## フレームレート最適化 Step 4（18fps → 30fps達成）

- [x] ダブルステージングテクスチャ・パイプライン化（CopyResourceとMapを1フレームずらし、GPU readback 55ms→0msに解消）
- [x] RowPitch一括コピー最適化（行ごとMemoryCopy 720回→一括コピー1回）
- [x] FPSスロットルを固定間隔ベースに変更（スレッドプールジッターによる30fps→22fps低下を解消）
- [x] デフォルトフレームレートを20fps→30fpsに復帰
- [x] Map計測ログ追加（Map=0ms readback=0ms を確認）
- [x] 結果: 30fps / speed=1.01x / drops固定（初期のみ）/ パイプwrite=1ms安定

## C#ネイティブ配信アプリ（Phase 6: プレビューウィンドウ統合）

- [x] FormBorderStyle.None → FixedSingle に変更（タイトルバー＋閉じる/最小化ボタン表示、リサイズ不可）
- [x] MaximizeBox = false（最大化ボタン無効化）
- [x] ウィンドウタイトルに配信状態をリアルタイム表示（「待機中」「配信中 HH:MM:SS」、トレイ更新タイマーで同期）
- [x] 配信中の閉じるボタン → トレイに最小化（誤終了防止、バルーン通知付き）
- [x] トレイの「終了」メニューとQuit APIは _forceClose フラグで強制終了を維持
- [x] トレイアイコンダブルクリックでウィンドウ復元（Show + Normal + Activate）
- [x] アプリ表示名を「WinNativeApp」→「AI Twitch Cast」に変更（ウィンドウタイトル・トレイ・バルーン・ログ・HTTPバージョン文字列）
- [x] タイトルバーをダークモードに変更（DwmSetWindowAttribute DWMWA_USE_IMMERSIVE_DARK_MODE）
- [x] broadcast.htmlからウィンドウ追加UI（セレクトボックス・追加ボタン・editLoadWindows/editAddCapture関数・10秒ポーリング）を完全削除
- [x] ClientSize修正（Size→ClientSize: タイトルバー分のクライアント領域縮小を解消）
- [x] 検証完了: FixedSingleウィンドウでWGCキャプチャ正常動作
- [x] 検証完了: ClientSize修正後、WebView2描画サイズが正確に1280x720
- [x] 検証完了: ウィンドウが最背面でもキャプチャ継続

## C#ネイティブ配信アプリ（Phase 7: UIパネル検証・修正）

- [x] ビルド成功確認（stream.sh でビルドエラーなし）
- [x] ウィンドウが1680x720で表示される（左1280: broadcast.html、右400: パネル）
- [x] パネルがダークテーマで表示される（control-panel.html読み込み成功）
- [x] WGCクロップ修正: クライアント領域オフセット計算（GetWindowRect+ClientToScreen）でタイトルバー・枠を除外
- [x] 配信制御: Go Liveボタンで配信開始 → Stopボタンで停止
- [x] 配信制御: 配信中にステータス表示（uptime）が更新される
- [x] ストリームキーをstream.shで常に渡すよう修正（パネルGo Live対応）
- [x] キャプチャ: ↻ボタンでウィンドウ一覧取得 → 開始 → broadcast.htmlに表示（layout null修正）
- [x] キャプチャ: 各アイテムに✕ボタンで個別停止（選択式UI廃止）
- [x] ログエリアのテキスト選択・コピー対応（user-select: text）
- [x] 音量スライダー: パネル操作でbroadcast.htmlの音量が変わる（JS変数名修正: broadcastState→volumes）
- [x] 音量スライダー: サーバーAPI経由でDB保存・WebSocket配信（共有HttpClient+デバウンス）
- [x] 音量スライダー: パネル初期表示でサーバーから現在値を取得
- [x] 音量スライダー: Web UI→パネル同期（broadcast.html applyVolumeからWebView2 postMessage通知）
- [x] Master音量200%対応（AudioContext GainNode経由、TTS/BGMは100%上限）
- [x] WebView2 autoplay音声許可（--autoplay-policy=no-user-gesture-required）
- [x] WebView2 JSコンソールログをアプリログに転送（console.log/error → postMessage → Serilog）
- [x] frames/drops表示をパネルから削除
- [x] 音量スライダー: HTTP POST→WebSocket経由に変更（POSTタイムアウト問題を解消、broadcast.htmlのWebSocket接続を利用してDB保存）
- [x] トレイアイコン: 既存のトレイ機能（配信開始/停止/最小化）が正常動作確認
- [x] Go Live API: WebSocket /ws/control経由での配信開始が正常動作確認
- [x] ウィンドウ閉じ修正: OnFormClosingにtry-catch追加+CleanupResourcesで_ffmpeg強制クリーンアップ（配信停止失敗時もウィンドウが閉じるように）

## FFmpegビルド時自動ダウンロード・同梱

- [x] ビルド前にffmpeg.exeが無ければBtbN/FFmpeg-Buildsから自動DL（download-ffmpeg.ps1）
- [x] csprojのMSBuild TargetでDL→ビルド出力にコピー（resources/ffmpeg/ffmpeg.exe）
- [x] FindFfmpeg()が自動検出するためstream.shの--ffmpeg-path指定不要に
- [x] Electron FFmpegフォールバック（ハードコードパス）を削除
- [x] .gitignoreにresources/ffmpeg/追加

## WebSocket SendAsync同時呼び出しエラー修正

- [x] SendWsResponseにSemaphoreSlimによる排他制御を追加（起動時の同時リクエストによるSendAsync競合を解消）

## バージョニング Step 3: 検証&部分改善API

- [x] `src/lesson_generator/improver.py`: 検証・改善・学習結果注入のコアロジック（verify_lesson, improve_sections, load_learnings）
- [x] `POST /api/lessons/{id}/verify`: 元教材との整合性チェック（coverage/contradictions JSON）、最新バージョン自動選択、プロンプト全文+raw_output返却
- [x] `POST /api/lessons/{id}/improve`: source_version→target_sectionsのみ再生成→新バージョン作成、未変更セクション・プランはソースからコピー
- [x] `prompts/lesson_verify.md`, `prompts/lesson_improve.md`: 検証用・改善用プロンプト
- [x] テスト+20件追加（TestVerifyAPI 8件、TestImproveAPI 9件、TestLoadLearnings 3件）、全670通過

## Phase 0: 環境構築・基盤

- [x] GitHubリポジトリ作成
- [x] CLAUDE.md 作成
- [x] GitHub Pages自動デプロイ環境構築（MkDocs + GitHub Actions）
- [x] OGP設定
