# テストスイートの棚卸し（不要削除・不足補完）

## ステータス: 進行中（Step 4-a 完了）

## 背景

`tests/` 配下には 27 ファイル・916 テスト・合計 12,551 行がある（2026-04-18 時点）。全テストは pass するが、次の課題がある:

- **スイート全体の実行時間が 532 秒（8:52）** と長く、開発フローで回しづらい
- **一部ファイルが肥大化**（`test_api_teacher.py` 2,651 行 / `test_lesson_runner.py` 1,513 行 / `test_claude_watcher.py` 1,239 行 / `test_db.py` 1,199 行）しており、重複・死んだケースが混ざっていないか定期的に検証できていない
- **新規モジュールに対するカバレッジが欠けている**（`character_manager.py` / `lesson_generator/improver.py` / `routes/avatar.py` / `routes/capture.py` 等）
- **ドキュメント（`CLAUDE.md`）の「テスト構成」表が古い** — `test_claude_watcher.py` / `test_comment_reader.py` / `test_tts_pregenerate.py` など表に載っていないファイルがある一方、実在しない記述はなさそうだが未確認
- **pattern検証テスト**（`test_broadcast_patterns.py` / `test_native_app_patterns.py`）は「危険パターン再発防止」という特殊な位置づけで、一般的なユニットテストとは評価基準が違う。生かすか見直すか判断が必要
- **5件の `DeprecationWarning`**（FastAPI `on_event` → lifespan 移行）が積み残っており、テスト実行のノイズになっている

コードが `CLAUDE.md` の「機能変更時の必須チェック（リグレッション防止）」で中心的な役割を果たしている以上、テストスイートを信頼できる状態に保つ価値は高い。

## 目的

1. **不要なテストを削除する** — 重複・デッドコード追従で意味を失ったケース・実装と乖離したケースを洗い出して削除
2. **欠けているテストを補う** — 新規モジュール / 重要ルートでテストが無いものを特定し、最低限の unit/API テストを追加
3. **スイートを高速化する** — 遅いテストを特定し、原因（実I/O・`sleep`・大量モック生成）を削るか `@pytest.mark.slow` に退避
4. **`CLAUDE.md` のテスト構成表を実体と一致させる**
5. **DeprecationWarning を解消する**（FastAPI lifespan 移行。`scripts/web.py` の `on_event` を lifespan ハンドラに書き換え）

## 方針

- **まず台帳を作る**。各テストファイルについて「対象モジュール」「テスト数」「所要時間」「最終変更コミット」「判断（keep/prune/refactor/add）」を表で管理する。判断材料が揃うまで削除しない
- **コードを正とする**。テストが落ちるのは「実装が正しい / テストが古い」ケースが多いので、`rg` でテスト内の関数・シンボルが実在するかを必ず確認
- **段階的に進める**。「削除 → 追加 → 高速化」を別コミットに分け、各段階で `python3 -m pytest tests/ -q` が通ることを確認
- **テストを消す基準を明確にする**（以下の「削除候補の判定基準」参照）
- **pattern 検証テスト（`test_broadcast_patterns.py` / `test_native_app_patterns.py`）は原則維持**。どちらも過去バグの再発防止を目的としたものなので、個別ケースごとに「対応するバグがまだ存在し得るか」を確認して残す／削るを判定
- **遅いテストは削除ではなく markerで仕分け**（`@pytest.mark.slow`）。CIで別ジョブにする前提。今回はマーカー導入までで止める

## 削除候補の判定基準

次のいずれかに該当するテストは削除候補とする:

1. **同じ入力に対して同じ挙動を確認している重複テスト**（別ファイルに同等のものが存在）
2. **テスト対象の関数/クラスが既に存在しない**（`rg` で該当名が実装側に見つからない）
3. **実装に追従しておらず、常に `mock.patch` 一式を組み立てるだけで I/O もロジック検証も実質していない**（たとえば「関数が呼ばれたこと」だけを確認するケース）
4. **同じ内容を parametrize で十分表現できる手書きの個別ケース**（冗長行数だけの価値）

削除はファイル単位ではなく**ケース単位**で行い、該当テストが「なぜ書かれたか」を git blame で確認したうえで判断する。

## 追加候補（現時点で把握しているカバレッジギャップ）

### src/ 配下
| モジュール | 行数 | 備考 |
|-----------|------|------|
| `character_manager.py` | 365 | キャラDB操作・キャッシュ・初期化の責務。`ai_responder` 側から分離されたのでテストもこちらに移すべき |
| `lesson_generator/extractor.py` | 223 | 画像/URLテキスト抽出。LLM呼び出しをモックすればテスト可能 |
| `lesson_generator/improver.py` | 834 | **最大の未テスト領域**。`improve_sections` / `evaluate_lesson_quality` / `analyze_learnings` / `evaluate_category_fit` / `determine_targets` / `improve_prompt` / `apply_prompt_diff` は教師モードの品質を握る関数群。最低でも各関数の正常系＋モックLLMでの分岐を抑える |
| `lesson_generator/utils.py` | 146 | 共有ユーティリティ |
| `gemini_client.py` | 18 | 小さすぎるのでスキップ可 |
| `twitch_api.py` | 92 | aiohttp呼び出しが絡むので優先度中 |
| `twitch_chat.py` | 78 | twitchio依存。conftest の既存スタブで書ける |

### scripts/routes/ 配下
| ルート | 行数 | 備考 |
|-------|------|------|
| `avatar.py` | 540 | アバター制御API（`/api/avatar/speak` など発話の入口）。優先度最高 |
| `capture.py` | 522 | キャプチャ制御API。配信アプリとのインテグレーション。優先度高 |
| `bgm.py` | 198 | BGM制御API。優先度中 |
| `files.py` | 224 | ファイル一覧API。優先度中 |
| `prompts.py` | 186 | プロンプト編集API。優先度中 |
| `db_viewer.py` | 129 | 閲覧用なので優先度低 |
| `twitch.py` | 39 | 小さいが配信制御の一部 |

※ ルートテストは `conftest.py` の `api_client` フィクスチャで書けるので参考実装は既にある。

## 実装ステップ

### Step 1: 現状棚卸し（判定材料の収集）

**1-a. 実行時間プロファイル**
- `python3 -m pytest tests/ --durations=30 -q` で最遅テスト上位 30 を抽出
- 結果を本プランの「計測結果」セクションに転記

**1-b. 未使用シンボル検出**
- 各テストファイルで import している実装側のシンボルを `rg` で確認し、実装に存在しないものを列挙

**1-c. 重複検出**
- `ai_responder` と `character_manager` のようにモジュール分離が起きたものについて、旧テストが分離後の新モジュール側にも存在しないかを確認

**1-d. CLAUDE.md の表と実体のdiff**
- `CLAUDE.md` の「テスト構成」表にあるファイル vs 実在ファイルを突き合わせ

### Step 2: 不要テストの削除

- Step 1 の結果をもとに、ケース単位で削除
- 削除ごとに `python3 -m pytest tests/ -q` が通ることを確認
- コミットは「カテゴリ別」に分ける（例: `tests: 実装から消えたシンボルのテストを削除`、`tests: ai_responder→character_manager 分離に伴う重複を整理`）

### Step 3: 欠けているテストの追加

優先度順に着手（最高 → 低）:
1. `lesson_generator/improver.py`（授業品質の中核）
2. `routes/avatar.py`（発話APIの入口）
3. `routes/capture.py`（配信アプリ連携）
4. `character_manager.py`
5. `lesson_generator/extractor.py` / `utils.py`
6. `routes/bgm.py` / `files.py` / `prompts.py`
7. `twitch_api.py` / `twitch_chat.py`

各ステップで:
- 既存の `conftest.py` フィクスチャ（`api_client` / `test_db` / `mock_gemini`）を活用
- LLM呼び出しは `mock_gemini` または `monkeypatch` でスタブ化
- 「正常系1〜2本＋代表的な異常系1本」を最小ターゲットとし、網羅率は求めない
- 1モジュールごとにコミットを切る

### Step 4: スイート高速化

**4-a. 遅いテストへのマーカー付与**
- Step 1-a で特定した上位テストに `@pytest.mark.slow` を付与
- `pytest.ini` に `markers = slow: long-running tests` を追記
- 通常実行は `pytest -q -m "not slow"`、CI/フル実行時のみ `pytest -q` で全量

**4-b. 実I/O/sleep の削除**
- `time.sleep` を使っているテストがあれば `freezegun` or 非同期の `asyncio.wait_for` に置換可能か検討

### Step 5: DeprecationWarning 解消

- `scripts/web.py:167` / `:302` の `@app.on_event("startup")` / `@app.on_event("shutdown")` を FastAPI lifespan ハンドラに書き換え
- 既存の startup 復旧フロー（アバター・Reader・GitWatcher）を壊さないことを `test_api_*.py` で確認
- これはテスト側ではなく実装側の修正なので、本プランでは実施のみ行い、関連する新規テストは書かない（既存の起動系テストでカバーされている前提）

### Step 6: ドキュメント更新

- `CLAUDE.md` の「テスト構成」表を現行ファイルと完全一致させる
- 増減したファイル・マーカー運用（`-m "not slow"`）を README 相当の箇所に追記
- `DONE.md` に完了記録、本プランを「ステータス: 完了」に更新

## リスク・留意点

- **削除はリスクが高い**。「通っているテストを消す」ことは、将来の再発検知を弱めるトレードオフを含む。本当に不要か迷ったら残す。迷った場合は削除ではなく `@pytest.mark.skip(reason=...)` で一時無効化して PR コメントで議論対象にする
- **pattern 検証テストは特殊**。`test_broadcast_patterns.py` / `test_native_app_patterns.py` は「実装が変わっても危険パターンを再発させない」ためのガードなので、「テストと実装の乖離」を理由に消すと本来の役割を失う
- **新規テストで実I/O（DB/ファイル/ネットワーク）を増やさない**。`conftest.py` のモック方針を踏襲
- **`lesson_generator/improver.py` は LLM プロンプト依存度が高い**。テストで検証するのは「入出力の整形」「分岐ロジック」までに留め、LLM応答の質そのものは検証しない
- **lifespan 移行は副作用範囲が広い**。startup で走る処理（`state.py` のコントローラー初期化、GitWatcher など）が lifespan のスコープに正しく入ること、shutdown もちゃんと呼ばれることを確認
- **一つのPRに詰めすぎない**。削除・追加・高速化・lifespan移行は別コミット／別PRに分けたほうが review しやすい

## 完了条件

- [ ] `python3 -m pytest tests/ -q` が全件 pass（DeprecationWarning なし）
- [ ] 通常実行（`-m "not slow"`）が 60 秒以内に収まる（現状 532 秒 → 目標は 60秒）
- [ ] カバレッジギャップ表で「優先度最高〜高」としたモジュールすべてに最低1ケースのテストが存在
- [ ] 不要と判定したテストが削除され、削除理由がコミットメッセージに残っている
- [ ] `CLAUDE.md` の「テスト構成」表が実体と一致
- [ ] `DONE.md` に完了記録、本プランを「ステータス: 完了」に更新

## 計測結果（Step 1 で埋める）

### 実行時間プロファイル

#### 計測1: 2026-04-18 初回（`--durations=15`）
スイート総時間: **532秒**／記録は下記の計測2に統合した（初回の詳細は git 履歴参照）。

#### 計測2: 2026-04-18 Step 1-a 正式計測（`--durations=30`）

- 実行コマンド: `python3 -m pytest tests/ --durations=30 -q`
- **スイート総時間: 526.91 秒（8:46）／ 916 passed / 5 warnings**
- 上位 call 6件で **261.7 秒（約 49.7%）** を占める。残りの 24 件（setup 中心）は合計約 15 秒で、「遅いのは一部の call、setup はフィクスチャコストが薄く広がっている」という構図。

| # | 時間(s) | フェーズ | テスト |
|--:|-------:|---------|-------|
| 1 | 66.97 | call  | `test_lesson_runner.py::TestSendAllAndPlay::test_sends_lesson_load_with_all_sections` |
| 2 | 63.83 | call  | `test_lesson_runner.py::TestPlaybackPersistence::test_send_all_and_play_saves_state` |
| 3 | 60.67 | call  | `test_lesson_runner.py::TestSendAllAndPlay::test_resume_from_saved_index` |
| 4 | 60.21 | call  | `test_lesson_runner.py::TestSendAllAndPlay::test_tts_progress_notification` |
| 5 | 5.01  | call  | `test_speech_pipeline.py::TestSpeak::test_speak_with_tts_failure` |
| 6 | 5.00  | call  | `test_speech_pipeline.py::TestSpeak::test_speak_no_chat_callback` |
| 7 | 1.11  | call  | `test_tts_pregenerate.py::TestPregenerateSectionTts::test_retry_on_failure` |
| 8 | 1.00  | call  | `test_claude_watcher.py::TestClaudeWatcherPlayConversation::test_comment_interrupt_cancels_batch` |
| 9 | 0.98  | setup | `test_lesson_runner.py::TestPlaybackPersistence::test_stop_clears_playback_state` |
| 10 | 0.80 | setup | `test_lesson_runner.py::TestLessonLifecycle::test_start_and_stop` |
| 11 | 0.79 | setup | `test_lesson_runner.py::TestRestore::test_restore_no_sections` |
| 12 | 0.78 | setup | `test_db.py::TestLessonLearnings::test_get_latest_nonexistent` |
| 13 | 0.77 | setup | `test_db.py::TestLessonLearnings::test_get_learnings_all` |
| 14 | 0.72 | setup | `test_api_docs_viewer.py::TestListDocFiles::test_list_docs` |
| 15 | 0.72 | setup | `test_lesson_runner.py::TestLessonLifecycle::test_pause_and_resume` |
| 16 | 0.72 | setup | `test_lesson_runner.py::TestLessonLifecycle::test_start_no_sections` |
| 17 | 0.71 | setup | `test_api_teacher.py::TestPaceScale::test_set_pace_scale` |
| 18 | 0.70 | setup | `test_lesson_runner.py::TestVersionedTtsCache::test_get_tts_cache_info_versioned` |
| 19 | 0.70 | setup | `test_api_stream.py::TestVolume::test_set_volume` |
| 20 | 0.69 | setup | `test_api_docs_viewer.py::TestListDocFiles::test_list_plans` |
| 21 | 0.67 | setup | `test_api_items.py::TestCustomTextViaBroadcastItems::test_api_get_list` |
| 22 | 0.67 | setup | `test_db.py::TestLessonLearnings::test_get_learnings_by_category` |
| 23 | 0.66 | setup | `test_api_teacher.py::TestPaceScale::test_pace_scale_clamped` |
| 24 | 0.64 | setup | `test_api_teacher.py::TestTtsCacheAPI::test_get_tts_cache_empty` |
| 25 | 0.64 | setup | `test_api_character.py::TestListCharacters::test_returns_all_characters` |
| 26 | 0.63 | setup | `test_lesson_runner.py::TestTtsCache::test_get_tts_cache_info` |
| 27 | 0.63 | setup | `test_db.py::TestSectionVersionNumber::test_default_version` |
| 28 | 0.63 | setup | `test_api_items.py::TestItemsAPI::test_post_item_layout` |
| 29 | 0.63 | setup | `test_api_teacher.py::TestLessonCRUD::test_get_lesson` |
| 30 | 0.63 | setup | `test_db.py::TestComments::test_get_recent_avatar_comments_includes_speaker` |

**観察**:
- **上位4件（合計 251.68 秒）がすべて `test_lesson_runner.py` の `TestSendAllAndPlay` / `TestPlaybackPersistence` 配下**。526秒中の約 47.8% がこの4テストに集中。`lesson_runner.py` の再生ループ内 `asyncio.sleep` 等を実時間で待っている可能性が高く、`asyncio.sleep` のモックor `@pytest.mark.slow` 退避の最有力候補
- `test_speech_pipeline.py::TestSpeak::test_speak_no_chat_callback` / `test_speak_with_tts_failure` の 5 秒も同様に `_wait_tts_complete()` のポーリング待機を実時間で回している疑い
- **setup が 0.6〜1.0 秒の帯域に 22 件並んでいる**のは `api_client` / `test_db` フィクスチャ生成コストの可能性が濃厚。そのほとんどが `test_lesson_runner.py` / `test_api_*.py` / `test_db.py`。session-scoped フィクスチャ化や `scripts.web` import 遅延で削れる余地がある（Step 4 で要検討）
- 初回計測（532秒）と今回（526.91秒）はほぼ一致。計測ノイズは ±1% 程度で、削減効果の判定はこのベースラインを基準にする
- 5件の `DeprecationWarning` は `scripts/web.py:167 / :302` の `@app.on_event("startup"/"shutdown")` 由来（Step 5 の lifespan 移行で解消対象）

**Step 4 へのインプット（優先度順）**:
1. `test_lesson_runner.py` の上位4件を `@pytest.mark.slow` or `asyncio.sleep` モック化で短縮 — 期待削減 ≈ 250秒
2. `test_speech_pipeline.py::TestSpeak` の 2件（`_wait_tts_complete` ポーリング）を短縮 — 期待削減 ≈ 10秒
3. setup の帯域（`api_client` フィクスチャ生成）を session スコープ化で均す — 期待削減 ≈ 10〜20秒
4. 上記3点で目標 60 秒以内（526 → ≈ 250秒削減で 280秒前後まで → さらに上位以外の累積短縮が必要）に近づけられるかを評価

### Step 1-d: CLAUDE.md 表との差分（2026-04-18）

- 実施内容: `CLAUDE.md:252-267` の「テスト構成」表（16ファイル記載）と `tests/` 配下の実在ファイル（`conftest.py` / `__init__.py` 除く27ファイル）を照合。
- 結果:
  - **表の項目で対象パスが古くなっているもの（2件）**:
    - `test_db.py` — 表は `src/db.py` とあるが、`src/db.py` は既に削除済み。現行は **`src/db/` パッケージ**（`audio.py` / `core.py` / `items.py` / `lessons.py`。62a2666 でパッケージ化）。
    - `test_capture_client.py` — 表は `src/capture_client.py` とあるが実在せず。現行は **`scripts/services/capture_client.py`**（bf913d1 で移設）。
  - **実在するが表に載っていない（11件）**:
    | ファイル | 実テスト対象 | 備考 |
    |---------|-------------|------|
    | `test_api_chat.py` | `scripts/routes/chat`（POST /api/chat/webui 等） | reader.respond_webui のモック |
    | `test_api_custom_text.py` | `/api/overlay/custom-texts` | カスタムテキスト（broadcast_items系） |
    | `test_api_docs_viewer.py` | `scripts/routes/docs_viewer` | plans/docs ファイル一覧API |
    | `test_api_items.py` | `src/db` + broadcast_items API | テーブルCRUD＋API両方含む |
    | `test_api_se.py` | `scripts/routes/se` | SE一覧・アップロード |
    | `test_broadcast_patterns.py` | `static/broadcast.html` + `static/js/broadcast/*` | アイテム共通化（ITEM_REGISTRY等）の再発防止。`test_native_app_patterns.py` と同性質 |
    | `test_claude_watcher.py` | `src/claude_watcher` | TranscriptParser / ClaudeWatcher |
    | `test_comment_reader.py` | `src/comment_reader` | 並列TTS事前生成（3ee4773 の分離後残存機能） |
    | `test_json_utils.py` | `src/json_utils` | parse_llm_json |
    | `test_se_resolver.py` | `src/se_resolver` | カテゴリ別SE解決 |
    | `test_tts_pregenerate.py` | `src/tts_pregenerate` | セクションTTS事前生成（授業系） |
- **Step 6 で反映する更新方針**:
  1. 上記2件の対象パスを最新に修正（`src/db/` パッケージ表記、`scripts/services/capture_client.py`）
  2. 上記11件を表に追加
  3. 表全体を `src/` 配下 → `scripts/routes/` 配下 → `static/` 系 → 統合テスト の順に並べ替えると見通しが良くなる（Step 6 で検討）

### Step 1-c: モジュール分離に伴う重複テスト検出（2026-04-18）

- 実施内容: git log で `src/` 配下の主要な分離・分割コミットを抽出し、旧モジュール側テストと分離後テストの重複可能性を照合。
- 対象とした分離コミット（5件）:
  1. `305177b`（2026-03-30）: `ai_responder.py` → `character_manager.py` 切り出し（12関数）
  2. `62a2666`: `db.py` → `src/db/` パッケージ分割
  3. `eeb1a26`: `lesson_generator.py` → `src/lesson_generator/` パッケージ分割
  4. `3ee4773`（2026-03-16）: `comment_reader.py` → `speech_pipeline.py` 抽出（SpeechPipeline/25テスト追加）
  5. `54cf5c2`（2026-03-16）: `ai_responder.py` → `prompt_builder.py` 抽出（LANGUAGE_MODES/build_system_prompt）
- 結果: **同内容のケースを2ファイルでテストしている重複は無い**。分離コミットごとに対応する test ファイルも同時に分離済み（`test_speech_pipeline.py` / `test_prompt_builder.py` 新設、`test_comment_reader.py` は並列TTS事前生成のみに縮退）。
- **検出された「位置ずれ」（削除対象ではなく Step 2/Step 3-4 での移動対象）**:
  - `test_ai_responder.py::TestCharacterManagement`（5ケース）
  - `test_ai_responder.py::TestGetChatCharacters`（1ケース）
  - `test_ai_responder.py::TestGetTtsConfig`（3ケース）
  - いずれも実対象は `src/character_manager.py`。`src/ai_responder.py` は re-export しているのでテストは pass するが、責務分離後の所在としては `tests/test_character_manager.py` が自然。
  - 判断: **重複ではないので Step 2（削除）対象外**。Step 3-4（`character_manager.py` のテスト追加）で新設する `tests/test_character_manager.py` に**移動**するのが妥当。ただし新規ケースの追加が先で、移動は付随作業とする。
- **特殊な `TestModuleSeparation` クラス（2ファイルに分散）**:
  - `test_prompt_builder.py:416-466`（6ケース）: `src/prompt_builder.py` と `src/ai_responder.py` の import 境界を `inspect.getsource` で文字列検査
  - `test_speech_pipeline.py:636-672`（4ケース）: `src/comment_reader.py` → `src/speech_pipeline.py` の import 方向と、旧メソッド名（`_speak` 等）が残っていないことを検査
  - 判断: **維持**。`test_broadcast_patterns.py` / `test_native_app_patterns.py` と同じ「再発防止ガード」系で、過去に一度成立した境界が崩れるとすぐ落ちる設計。ただし **Step 6 の CLAUDE.md 表更新時に「パターン検証テスト群」のカテゴリとして明記**しておくと方針が一貫する。
- **重複削除候補**: **なし**。Step 2 の削除対象は Step 1-a/1-b/1-c からはゼロ件。Step 2 は「削除ゼロのままスキップ」し、Step 3（追加）と Step 4（高速化）に進むのが妥当。



### Step 1-b: 未使用シンボル検出（2026-04-18）

- 実施内容: `tests/` 27 ファイル全てについて、`from src.X import ...` / `from scripts.X import ...`（複数行 `( ... )` 形式含む）および `patch("src.X.Y")` / `patch("scripts.X.Y")` の参照シンボルを抽出し、対象モジュール側に定義（`def` / `async def` / `class` / 変数代入 / `__all__` 経由の再エクスポート）が実在するかを `rg` で照合。
- 結果: **未定義・消失シンボルはゼロ**。確認したモジュール:
  - src: `ai_responder` / `claude_watcher` / `comment_reader` / `db`（パッケージ）/ `git_watcher` / `json_utils` / `lesson_generator`（パッケージ。`extractor` / `improver` / `utils`）/ `lesson_runner` / `lipsync` / `prompt_builder` / `scene_config` / `se_resolver` / `speech_pipeline` / `tts` / `tts_pregenerate` / `wsl_path`
  - scripts: `routes/docs_viewer` / `routes/overlay` / `routes/stream_control` / `routes/teacher` / `services/capture_client` / `services/todo_service` / `state`
- 補足:
  - `from src.ai_responder import DEFAULT_CHARACTER / get_character / load_character / seed_character / invalidate_character_cache / get_chat_characters / get_tts_config` 等は `character_manager.py` からの再エクスポート（`src/ai_responder.py:10-63`）で解決される。分離後もテスト互換が維持されている
  - `patch("src.lesson_runner.analyze_amplitude")` / `patch("src.speech_pipeline.{get_character, synthesize, analyze_amplitude}")` は各モジュールが `from ... import` で取り込んだエイリアス経由。正しくモジュール属性として存在する
  - `patch("scripts.services.todo_service.TODO_PATH")` / `patch("scripts.routes.overlay.state")` も module-level 変数として実在
- 判断: **Step 2（不要テスト削除）において「対象シンボルが存在しない」を理由に削除できるテストは無い**。削除判定は 1-c（モジュール分離に伴う重複）および 1-d（CLAUDE.md 差分）の結果に依拠する。

### 削除候補一覧
（Step 1-c, 1-d の結果をもとに作成）

### Step 4-a 実装結果: 遅いテストへの `@pytest.mark.slow` 付与（2026-04-18）

- 実施内容:
  - `pytest.ini` の `[pytest]` セクションに `markers = slow: long-running tests (除外するには -m "not slow")` を追記
  - Step 1-a で特定した遅い call 上位6件に `@pytest.mark.slow` を付与:
    - `tests/test_lesson_runner.py::TestPlaybackPersistence::test_send_all_and_play_saves_state`（63.81s）
    - `tests/test_lesson_runner.py::TestSendAllAndPlay::test_sends_lesson_load_with_all_sections`（66.98s）
    - `tests/test_lesson_runner.py::TestSendAllAndPlay::test_resume_from_saved_index`（60.67s）
    - `tests/test_lesson_runner.py::TestSendAllAndPlay::test_tts_progress_notification`（60.22s）
    - `tests/test_speech_pipeline.py::TestSpeak::test_speak_with_tts_failure`（5.01s）
    - `tests/test_speech_pipeline.py::TestSpeak::test_speak_no_chat_callback`（5.01s）
- 計測結果:
  - **`-m "not slow"`**: 1264 passed / 6 deselected / **358.81 秒（5:58）** — 元 526.91 秒から **約168秒削減（≒32%短縮）**
  - **`-m "slow"`**: 6 passed / 1264 deselected / **263.72 秒（4:23）** — 上位 4 件で 251.68 秒、speech_pipeline 2 件で 10.02 秒。Step 1-a 計測と完全一致しており、付与漏れ無し
  - 通常実行と slow を分けたことで、開発フローでは `-m "not slow"` を回せば 6 分弱で済む（元 9 分弱）
- 注意点:
  - 完了条件「通常実行 60 秒以内」は Step 4-a 単独では達成不可（358 秒で打ち止め）。残りの削減は **`api_client` フィクスチャ生成コスト**（setup の 0.6〜1.0 秒帯 22 件）と Step 4-b（`asyncio.sleep` モック化）による。Step 4-a の責務はマーカー仕分けまでで、この後の高速化は別ステップで取り組む
  - 5 件の `@app.on_event` `DeprecationWarning` は引き続き残存（Step 5 の lifespan 移行で解消予定）
  - **マーカー運用ルール**:
    - 開発中の通常実行: `python3 -m pytest tests/ -q -m "not slow"`
    - フル実行（コミット前 / CI）: `python3 -m pytest tests/ -q`
    - `-m "slow"` 単独実行: 遅いテスト群が壊れていないかピンポイント確認用
  - Step 6 の CLAUDE.md 更新時に「テスト実行方法」セクションへ `-m "not slow"` の使い分けを明記する
- 結果: マーカー付与＋計測のみで実装変更なし。将来 lesson_runner.py の `asyncio.sleep` ループをフェイクタイマー化すれば、slow マーカーを外して通常実行に戻せる候補

### Step 3-7 実装結果: `twitch_api.py` / `twitch_chat.py` のテスト追加（2026-04-18）

- 実施内容:
  - `tests/test_twitch_api.py` を新規作成（**17ケース**）。`src/twitch_api.py` の全メソッド＋ヘッダ整形をカバー
  - `tests/test_twitch_chat.py` を新規作成（**18ケース**）。`src/twitch_chat.py` の `TwitchChat` / `_ChatClient` をカバー
  - `tests/conftest.py` の外部モジュールスタブを「インストール済みなら実体を優先、未インストール時のみ MagicMock」に変更
- カテゴリ別内訳（twitch_api, 17ケース）:
  - **`_headers`**（3ケース）: `oauth:` 接頭辞の除去＋Bearer変換、接頭辞無しトークンの passthrough、環境変数 `TWITCH_TOKEN` / `TWITCH_CLIENT_ID` の読み込み
  - **`get_broadcaster_id`**（4ケース）: 成功（`/users?login=...`）、キャッシュ（2回目はHTTP未呼び出し）、チャンネル未発見で `ValueError`、`raise_for_status` 由来の例外伝搬
  - **`get_channel_info`**（3ケース）: データあり（title/game_id/game_name/tags）、空データで `{}`、全フィールド欠落時のデフォルト空値
  - **`update_channel_info`**（5ケース）: title 単独 PATCH、全フィールド同時、body 空で PATCH 短絡、PATCH エラー伝搬、None フィールドのスキップ
  - **`search_categories`**（2ケース）: `box_art_url` 有無の正規化（`first=10` 固定）、空データで `[]`
- カテゴリ別内訳（twitch_chat, 18ケース）:
  - **`__init__`**（2ケース）: env 読み込み、明示引数の優先
  - **`start`**（1ケース）: `_ChatClient` 作成 + `client.start()` の asyncio.Task 化
  - **`stop`**（3ケース）: 正常停止（close＋task cancel＋フィールド None化）、タスク内例外の握りつぶし、start前の no-op
  - **`send_message`**（4ケース）: 未接続時の warning、通常送信、チャンネル未発見時の warning、`channel.send` 例外の error ログ化（再スローしない）
  - **`is_running`**（3ケース）: None/pending/完了 の3状態
  - **`_ChatClient.event_message`**（4ケース）: `echo=True` 無視、`display_name` 優先、空時 `name` fallback、`author=None` で `"unknown"`
  - **`_ChatClient.event_ready`**（1ケース）: ログ出力確認
- 設計上のポイント:
  - **conftest.py のスタブ挙動変更**: 従来は無条件に `sys.modules['twitchio'] = MagicMock()` としていたが、インストール済み環境では `__import__` で実体を読み込む方式に変更。これにより `_ChatClient(Client)` の本物の継承関係が成立し、直接 `event_message` を呼び出すテストが書けるようになった。他テストへの副作用は `src.twitch_api.aiohttp.ClientSession` / `src.twitch_chat._ChatClient` を必要箇所で直接 patch しているため無し
  - **aiohttp.ClientSession のモック化ヘルパー**: `session.get` / `session.patch` は `async with` のネスト（`ClientSession()` と `session.get()` の両方）。`_make_session()` ヘルパーで `MagicMock` + `AsyncMock(__aenter__/__aexit__)` を組み合わせ、`resp.json` を `AsyncMock`、`raise_for_status` を `MagicMock(side_effect=...)` に分けて組み立てる
  - **`_ChatClient.event_message` 直接呼び出し**: MagicMock の `.echo` / `.author` / `.content` 属性を手動で設定し、twitchio の WebSocket 層は迂回
  - **task ライフサイクル**: `stop` のテストで `asyncio.create_task(_long())` を作って cancel を検証。例外握り潰しは、`asyncio.create_task(_bad())` → `await asyncio.sleep(0)` で task に例外を溜めてから stop に渡す
  - **ログ検証**: `caplog.at_level("WARNING"/"ERROR")` で `"チャット未接続"` / `"見つかりません"` / `"チャット送信失敗"` を assert
- 注意点・学び:
  - 無条件 MagicMock スタブだと `from twitchio import Client` で Client が MagicMock 化し、`class _ChatClient(Client)` の時点で `_ChatClient` 自体が MagicMock 属性になる（type ではなくなる）。その結果 `client.event_message(...)` が MagicMock を返して `TypeError: object MagicMock can't be used in 'await' expression` になる。インストール済みなら実体を使う切り替えで解決
  - `_headers` は `self.token.removeprefix("oauth:")` で、接頭辞が無ければトークンを変形しない
  - `update_channel_info` は `body` 構築時に None 値を除外 → `body` が空なら PATCH を呼ばない（無意味な更新リクエストを避ける）
- 結果: `python3 -m pytest tests/ -q` → **1270 passed / 4 warnings / 10:36**（1235 → 1270 / +35件・リグレッションなし）。warnings は Step 5 対象の `@app.on_event` DeprecationWarning（5→4 に減ったが残り4件は lifespan 移行でまとめて消える想定）

### Step 3-6 実装結果: `routes/bgm.py` / `files.py` / `prompts.py` のテスト追加（2026-04-18）

- 実施内容:
  - `tests/test_api_bgm.py` を新規作成（**33ケース**）。`scripts/routes/bgm.py` の全エンドポイント＋内部ヘルパーをカバー
  - `tests/test_api_files.py` を新規作成（**32ケース**）。`scripts/routes/files.py` の全エンドポイント＋アバターVRM関連ヘルパーをカバー
  - `tests/test_api_prompts.py` を新規作成（**33ケース**）。`scripts/routes/prompts.py` の全エンドポイント＋ユーティリティをカバー
- カテゴリ別内訳（bgm, 33ケース）:
  - **GET `/api/bgm/list`**（5ケース）: 空ディレクトリ、対応拡張子フィルタ（mp3/wav/ogg/m4a のみ）、DB保存の volume / source_url マージ、settings 経由の現在曲、BGM_DIR 自動作成
  - **POST `/api/bgm`**（4ケース）: play で `bgm_play` broadcast＋曲別volume適用＋settings保存、未設定時はデフォルト1.0、stop で `bgm_stop` broadcast＋track クリア、不明action のエラー
  - **POST `/api/bgm/track-volume`**（3ケース）: DB保存、再生中なら `bgm_volume` broadcast、非再生中なら broadcast しない
  - **DELETE `/api/bgm/track`**（3ケース）: ファイル＋DBレコード削除、再生中なら停止してから削除、存在しないファイルはエラー
  - **POST `/api/bgm/youtube`**（5ケース）: 空URL エラー、正常ダウンロード（sanitize後の名前でMP3保存＋source_url DB保存）、既存ファイルはダウンロードせずURLのみ補完、ダウンロード失敗（例外伝搬）、ファイル未生成時のエラー
  - **ヘルパー**（13ケース）: `_get_youtube_title`（yt-dlp 成功/失敗）、`_download_youtube_audio`（コマンド構築/失敗例外）、`_sanitize_filename`（禁止文字/前後空白/空文字→untitled/100文字切詰/Unicode保持）、`load_bgm_settings`（未設定で空、DB保存値）、`_save_bgm`（DB保存、None で no-op）
- カテゴリ別内訳（files, 32ケース）:
  - **GET `/api/files/{cat}/list`**（7ケース）: 不明カテゴリエラー、空リスト、拡張子フィルタ、active フラグ、アバターは characters.config.vrm から、characters 無し時は settings fallback、ディレクトリ自動作成
  - **POST `/api/files/{cat}/upload`**（4ケース）: 不明カテゴリ、対応外拡張子、sanitize 適用＋保存、同名衝突時の連番付与、大文字拡張子 → lower
  - **POST `/api/files/{cat}/select`**（5ケース）: 不明カテゴリ、存在しないファイル、background で `background_change` broadcast＋settings保存、avatar で characters.config.vrm 更新＋`avatar_vrm_change` broadcast、avatar2 で student 側に反映＋`avatar2_vrm_change`、teaching は broadcast しない
  - **DELETE `/api/files/{cat}`**（5ケース）: 不明カテゴリ、存在しないファイル、ファイル削除、active 削除時の settings クリア、avatar 削除時の characters.config.vrm クリア
  - **ヘルパー**（11ケース）: `_sanitize_filename`（禁止文字/空/前後ドット/200文字切詰）、`_get_active_vrm`（characters 優先 / settings fallback / 非対応カテゴリで空）、`_set_active_vrm`（characters 更新 / characters 無し時 settings fallback）
- カテゴリ別内訳（prompts, 33ケース）:
  - **`_validate_name`**（6ケース）: 正常 .md、ネストパス、空文字却下、`..` 含む却下、非 .md 拒否、絶対パス（PROMPTS_DIR 外）却下
  - **GET `/api/prompts`**（5ケース）: PROMPTS_DIR 無しで空リスト、空ディレクトリ、メタ情報付き一覧（title は先頭行 `# ...`）、ネストファイル含む、非 .md は除外
  - **GET `/api/prompts/{name}`**（5ケース）: 本文返却、ネストパス、非 .md で400、`..` で400、存在しないで404
  - **PUT `/api/prompts/{name}`**（4ケース）: 上書き保存、不正名エラー、存在しないファイルエラー、update 専用（新規作成しない）
  - **`_escape_html`**（2ケース）: 基本文字（<, >, &, "）、`&` 先行エスケープ（二重エスケープ回避）
  - **`_make_diff_html`**（4ケース）: 追加/削除行のクラス付与、`@@` ハンクヘッダの紫色 ctx、同一入力で空、HTMLエスケープ適用
  - **POST `/api/prompts/ai-edit`**（7ケース）: 空指示エラー、不正名、存在しないファイル、LLM 差分プレビュー（ファイル自体は書き換えない）、``` ``` コードブロック剥がし、LLM 例外伝搬、contents / system_instruction の検証
- 設計上のポイント:
  - **scenes.json フォールバック対策**: `load_config_value("bgm.track", "")` は DB空時に scenes.json の実ファイルを読みに行くため、`bgm.track` の既定値がテストに混入する。affected tests では `monkeypatch.setattr(sc, "CONFIG_PATH", empty_config)` で空JSONに差し替え
  - **BGM_DIR / PROMPTS_DIR / CATEGORIES の module-level パス差し替え**: `monkeypatch.setattr(mod, "BGM_DIR", tmp_path/...)` / `monkeypatch.setattr(mod, "PROMPTS_DIR", ...)` / `monkeypatch.setattr(mod, "CATEGORIES", new_cats)` で resources/ 配下への副作用を全て隔離
  - **yt-dlp のモック**: `_get_youtube_title` / `_download_youtube_audio` 両方をモジュール属性として差し替え（`asyncio.to_thread` 経由なので直接差し替えで届く）。単体テストのみ `subprocess.run` を `patch.object` で差し替え
  - **Path.stem の挙動**: `files_upload` は `Path(filename).stem + ext` で保存名を構築するため、`/` を含むテスト文字列はパス分離で消える。`_sanitize_filename` が弾く文字（`?`, `*`, `|`）で検証
  - **ai-edit の LLM モック**: `mock_gemini.models.generate_content.return_value.text` を直接差し替え。例外テストは `get_client` 自体を例外スロー版に差し替え
  - **`_seed_character` ヘルパー**: files テストで teacher/student を characters テーブルに作成する際に `get_or_create_character` + config JSON を直接叩く
  - **assert でアサーションする broadcast 回数**: 1テスト内で broadcast が呼ばれる経路と呼ばれない経路を明示的に `assert_called_once()` / `assert_not_called()` で検証
- 注意点・学び:
  - `Path(filename).suffix.lower()` で比較 → 大文字 `.JPG` も対応リスト `{.jpg}` と一致するが、最終ファイル名は lower 済みの `.jpg` で保存される
  - `_validate_name` は絶対パスを `.startswith()` で弾くが、先に `".."` チェックが無いパスも resolve 後に PROMPTS_DIR 外になれば None を返す
  - `_make_diff_html` の同一入力は `unified_diff` が空を返すので html_parts も空 → 結果は空文字列
  - `test_api_bgm.py` の `bgm.track` テストで、scenes.json のデフォルト値が `"Morning Cafe Jazz - Piano & Guitar Bossa Nova Music for Study, Work.mp3"` になっており、これに気づかずに `== ""` を assert すると fail する
- 結果: `python3 -m pytest tests/ -q` → **1235 passed / 5 warnings / 10:18**（1137 → 1235 / +98件・リグレッションなし）。warnings は Step 5 で解消予定の `@app.on_event` DeprecationWarning のみ

### Step 3-5 実装結果: `lesson_generator/extractor.py` / `utils.py` のテスト追加（2026-04-18）

- 実施内容:
  - `tests/test_lesson_extractor.py` を新規作成（**31ケース**）。`src/lesson_generator/extractor.py` の全公開・プライベート関数（`clean_extracted_text` / `_normalize_roles` / `extract_main_content` / `extract_text_from_image` / `extract_text_from_url`）をカバー
  - `tests/test_lesson_utils.py` を新規作成（**37ケース**）。`src/lesson_generator/utils.py` の全公開・プライベート関数（`_is_english_mode` / `_get_model` / `_parse_json_response` / `_guess_mime` / `_build_image_parts` / `get_lesson_characters` / `_format_character_for_prompt` / `_format_main_content_for_prompt`）をカバー
- カテゴリ別内訳（extractor, 31ケース）:
  - **`clean_extracted_text`**（10ケース）: 空文字・None passthrough、HTMLエンティティ6種（`&nbsp;` / `&amp;` / `&lt;` / `&gt;` / `&quot;` / `&#39;` / `&apos;`）置換、3個以上のハイフン→改行・等号/アスタリスク/チルダ/アンダースコアの3個以上連続除去、装飾記号（★☆●○■□◆◇▲△▼▽◎※♪♫♬♩）の3個以上連続除去、2個の`--`保持、4行以上の空行→3行圧縮、先頭末尾strip
  - **`_normalize_roles`**（10ケース）: 空入力、main ゼロ時の先頭昇格＋他 sub 補完、main 複数時の先頭以外を sub へ降格、main 1個保持、read_aloud デフォルト（main+conversation/passage→True、word_list→False、sub→False）、明示 read_aloud 値の保持、role キー欠落時の sub デフォルト
  - **`extract_main_content`**（5ケース）: 空文字・ブランク時のLLM呼び出しスキップ、list応答の正規化、dict応答の`[item]`ラップ＋role="main"付与、壊れJSONでの空配列フォールバック、list/dict以外の応答で空配列
  - **`extract_text_from_image`**（3ケース）: 存在しないファイルで `FileNotFoundError`、正常系で Vision呼び出し + `clean_extracted_text` 経由、`.jpg` 拡張子 → `image/jpeg` MIME
  - **`extract_text_from_url`**（3ケース）: HTML取得→LLM送信（User-Agent付与・HTMLエンティティ解除）、`raise_for_status` 例外伝搬（LLM未呼び出し）、50000文字HTMLの30000文字切り詰め
- カテゴリ別内訳（utils, 37ケース）:
  - **`_is_english_mode`**（3ケース）: `set_stream_language("ja", ...)` で False、`"en"` / `"ko"` で True（primary が ja 以外ならすべて英語モード扱い）
  - **`_get_model`**（3ケース）: 環境変数 `GEMINI_CHAT_MODEL` 使用、未設定時の `"gemini-3-flash-preview"` フォールバック、**モジュールレベル `_CHAT_MODEL` キャッシュ挙動**（初回読み込み後は環境変数変更が反映されない）
  - **`_parse_json_response`**（3ケース）: 素のJSONパース、````json ... ``` コードブロック剥がし、末尾カンマ/シングルクォートの `json_repair` 修復
  - **`_guess_mime`**（6ケース）: png/jpg/jpeg/webp/gif、大文字拡張子、未知拡張子のpngフォールバック
  - **`_build_image_parts`**（5ケース）: None/空リスト、存在ファイルの`Part`変換（mime+bytesまで検証）、存在しないパスのスキップ、複数ファイルの順序・MIME維持
  - **`get_lesson_characters`**（4ケース）: teacher/student 同時取得（`seed_all_characters`経由で自動作成）、config に `name` が注入、`update_character_persona` / `update_character_self_note` 経由で persona/self_note が反映、未設定時は空文字
  - **`_format_character_for_prompt`**（6ケース）: 最小config整形（`### role: name (speaker: "role")` ヘッダ）、`name`欠落時の role_label フォールバック、emotions の日本語/英語ラベル、emotions 無しで該当セクション省略、空 `system_prompt` で本文行を出さない
  - **`_format_main_content_for_prompt`**（7ケース）: 空入力、main+conversation+read_aloud の全文表示（🔊マーカー付き）、sub の200文字切り詰め、main+read_aloud の2000文字切り詰め、英語モード（`★ PRIMARY` / `🔊 READ ALOUD`）、複数アイテム番号付け、role キー欠落時のデフォルト（1件目 main / 2件目 sub）
- 設計上のポイント:
  - **`mock_gemini` フィクスチャを活用**: `conftest.py:63-64` で `src.lesson_generator.utils.get_client` をパッチ済み。`extractor.py` は `from . import utils` → `utils.get_client()` で取得しているので追加パッチ不要
  - **`httpx.AsyncClient` のスタブ化**: `monkeypatch.setattr(extractor.httpx, "AsyncClient", _FakeClient)` で置換。`__aenter__`/`__aexit__`/`get` を持つ簡易モック
  - **`_CHAT_MODEL` グローバルキャッシュ**: `setup_method`/`teardown_method` で `lg_utils._CHAT_MODEL = None` にリセット。キャッシュ挙動そのものを検証するテストも別途追加
  - **`test_db` フィクスチャ + 実DB**: `get_lesson_characters` は本物の `seed_all_characters` / `get_character_by_role` / `update_character_persona` を通す（モックせず挙動を検証）
  - **channel_id は int**: `get_character_by_role` は `db.get_or_create_channel(name)` が返す int id を要求。テスト側で `get_channel_id()` を呼んで取得
  - **label文字列による `.count()` ずれ**: 切り詰めテストの `count("y")` で label `"body"` の `y` も計上されて +1 ずれた。`z` + label `"本文"` に変更して回避
- 注意点・学び:
  - `clean_extracted_text` の `---` 処理は単純な置換（`\n`）で、結果がさらに空行圧縮に掛かるため、assert は「除去されたこと」と「周辺文字が残っていること」に留めるのが安全
  - `extract_main_content` の dict応答は `result["role"] = "main"` 代入のみで `_normalize_roles` を通さない — 仕様通りでテストもその前提で書く
  - `httpx.HTTPStatusError` は `raise_for_status` で発生。`request=None, response=None` を渡して mock 用に簡略化
- 結果: `python3 -m pytest tests/ -q` → **1137 passed / 5 warnings / 9:41**（1069 → 1137 / +68件・リグレッションなし）。warnings は Step 5 で解消予定の `@app.on_event` DeprecationWarning のみ

### Step 3-4 実装結果: `character_manager.py` のテスト追加（2026-04-18）

- 実施内容: `tests/test_character_manager.py` を新規作成（**32ケース**）。`src/character_manager.py` の全12関数＋DEFAULT_*定数を10のテストクラスに分けて網羅
- カテゴリ別内訳:
  - **モジュール定数**（3ケース）: `DEFAULT_CHARACTER` / `DEFAULT_STUDENT_CHARACTER` の必須キー確認（`role` / `tts_voice` / `tts_style` / `system_prompt` / `emotions` / `emotion_blendshapes`）、先生と生徒の `tts_voice` が異なることを保証
  - **`get_channel_id`**（2ケース）: `TWITCH_CHANNEL` 環境変数での解決、未設定時の `"default"` フォールバック
  - **`seed_character`**（3ケース）: 作成・冪等・**他チャンネル由来のフォールバック行を採用しない**（`get_character_by_channel` が他chのキャラを返すため、channel_id 一致確認で二度作りしないロジック）。name UNIQUE 制約ゆえ他ch でも既存「ちょビ」が返る挙動を明示
  - **`seed_all_characters`**（5ケース）: 先生＋生徒の同時作成、冪等、既存teacher の config に role が無い場合の補填、**「まなび」→「なるこ」マイグレーション**（name rename + `system_prompt` 文字列の「「まなび」→「なるこ」」置換）、生徒既存時に追加作成しない
  - **`load_character` / `get_character` / `get_character_id` / `invalidate_character_cache`**（5ケース）: DB ロード、モジュールレベルキャッシュ（`_character` / `_character_id`）の lazy load、無効化後の再ロード
  - **`build_character_context`**（5ケース）: teacher/student の `{id, name, role, config, persona, self_note}` 返却、未知role で None、`update_character_persona` / `update_character_self_note` 経由で persona/self_note が次回取得時に反映、config dict に `name` が注入される
  - **`build_all_character_contexts`**（1ケース）: teacher/student が同時取得できる
  - **`get_all_characters`**（2ケース）: teacher+student が含まれる、各エントリに `id` と展開後の config キー（`role` / `system_prompt` 等）が両方ある
  - **`get_chat_characters`**（1ケース）: teacher/student 両方の config が返る
  - **`get_tts_config`**（5ケース）: 言語別（ja/en/bilingual）の style 選択、`character_id` 指定時にそのキャラの voice/style を返す、**存在しないIDなら現行キャラ（先生）にフォールバック**
- 設計上のポイント:
  - `test_db` のインメモリSQLite上で **実DBを使ってマイグレーションロジックを検証**（モックせず `get_or_create_character` / `update_character` などの本物の挙動を通す）
  - `invalidate_character_cache()` を各クラスの `setup_method` で呼び、テスト間のモジュール状態汚染を防止
  - `get_tts_config` のstyle分岐は `src.prompt_builder.set_stream_language` のグローバル状態に依存するので `setup/teardown` で `("ja", "en", "low")` に戻す
  - `build_character_context` のテストは `update_character_persona` / `update_character_self_note` を直接呼び出して次回 build 時に反映されることを確認（`get_character_memory` の lazy upsert 挙動も兼ねてカバー）
- **テスト整理（Step 1-c 指摘への対応）**:
  - Step 1-c で「位置ずれ」として識別された既存ケースを `tests/test_ai_responder.py` から `tests/test_character_manager.py` に吸収:
    - `TestCharacterManagement`（5ケース）
    - `TestGetChatCharacters`（1ケース）
    - `TestGetTtsConfig`（3ケース）
  - これらは実対象が `src/character_manager.py`（`ai_responder` は re-export のみ）だったので、責務分離後の所在として test_character_manager 側に集約。旧ファイルからは重複削除した上で未使用 import（`MagicMock` / `patch` / `DEFAULT_CHARACTER_NAME` / `DEFAULT_STUDENT_CHARACTER_NAME` / `get_character` / `get_chat_characters` / `get_tts_config` / `load_character` / `seed_character`）も掃除
  - 吸収＋新規33ケース相当だが、旧9ケースと新規ケースで重複する内容（seed idempotent / load / lazy load / invalidate / get_chat_characters / get_tts_config 言語分岐）は新規側に統合し直し、**最終的に test_character_manager.py は 32ケース**になった
- 結果: `python3 -m pytest tests/ -q` → **1069 passed / 5 warnings / 9:47**（1046 → 1069 / +23件・リグレッションなし）。warnings は Step 5 で解消予定の `@app.on_event` DeprecationWarning のみ

### Step 3-3 実装結果: `scripts/routes/capture.py` のテスト追加（2026-04-18）

- 実施内容: `tests/test_api_capture.py` を新規作成（595行 / 53ケース）。サーバー状態・ウィンドウ一覧・保存済み設定CRUD・復元・キャプチャ開始/停止/一覧/レイアウト・スクリーンショット・配信ストリーミング・内部ヘルパーを網羅
- エンドポイントごとの内訳:
  - **`/api/capture/status`**（2ケース）: proxy成功時の `{running: True, ...}`、失敗時の `{running: False}` フォールバック
  - **`/api/capture/windows`**（2ケース）: 一覧、接続失敗時502
  - **`/api/capture/saved`** GET（2ケース）: 空、DB保存行のAPI形式（`window_name` / `label` / `layout`）変換
  - **`/api/capture/saved`** DELETE（2ケース）: `window_name` 指定削除、空bodyでの短絡
  - **`/api/capture/saved/layout`**（2ケース）: 部分更新（未指定カラムは据え置き）、`window_name` 欠落時の短絡
  - **`/api/capture/restore`**（4ケース）: 保存ゼロ時の `message`、windows取得失敗時の `ok=false`、完全一致マッチ＋`broadcast_to_broadcast`、visible=false/active重複のskip
  - **`/api/capture/start`**（5ケース）: レイアウト永続化＋broadcast、保存済みレイアウト再利用、502（proxy失敗）、400（ok=false）、nameなし時の `/captures` フォールバック
  - **`/api/capture/{id}`** DELETE（2ケース）: `capture_remove` broadcast、proxy失敗でもクライアント側同期
  - **`/api/capture/sources`**（3ケース）: 保存済みレイアウトマージ、proxy失敗時[]、未保存エントリのデフォルトレイアウト
  - **`/api/capture/{id}/layout`**（2ケース）: None除外、`window_name` 経由の永続テーブル同期
  - **`/api/capture/screenshot`**（3ケース）: WS成功時のbase64デコード＋ファイル書き出し、502/400
  - **`/api/capture/screenshots`** GET一覧（2ケース）: ディレクトリ無しで空、mtime降順
  - **`/api/capture/screenshots/{filename}`**（6ケース）: GET存在/404/パストラバーサル（parametrize 3件）、DELETE成功/404/バックスラッシュ400
  - **`/api/capture/stream/start`**（4ケース）: env TWITCH_STREAM_KEY + `get_windows_host_ip` 由来の `serverUrl`、body優先、未設定時400、ws失敗時502
  - **`/api/capture/stream/{stop,status}`**（4ケース）: ws結果passthrough、失敗時502
  - **内部ヘルパー**（6ケース）: `_save_capture_layout` / `_load_capture_sources` / `_update_capture_layout` / `_remove_capture_layout` のSQLite経由roundtrip、壊れたJSON耐性、`_row_to_layout` の visible→bool キャスト
- 設計上のポイント:
  - `capture.py` は `from scripts.services.capture_client import proxy_request, ws_request, capture_base_url` で import しているので、`monkeypatch.setattr(cap_mod, "proxy_request", AsyncMock(...))` とモジュール属性レベルで差し替える。ヘルパー関数 `_patch_capture_client(monkeypatch, *, proxy=None, ws=None, base_url="...")` に集約
  - `SCREENSHOT_DIR` は module-level `Path` なので `monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path)` で `/tmp/screenshots/` への書き込み漏洩を防止
  - `test_db` フィクスチャのインメモリSQLiteで `capture_windows` テーブルと `capture.sources` 設定JSONを実体込みで検証（モックせず本物のDB関数を叩く）
  - `state.broadcast_to_broadcast` は `api_client` で AsyncMock 済み。呼び出し内容の辞書一致を `call_args.args[0]` で検証
  - パストラバーサルは `parametrize` で `"../etc/passwd"` / `"..\\windows"` / `"sub/dir.png"` を流し込み。FastAPIのルーティング仕様上 `/` 入りは 404 になるので assert は `status_code in (400, 404)` で両受け
- **副産物バグ修正**: テスト追加時に `scripts/routes/capture.py:488` の `capture_stream_start` で `get_windows_host_ip()` を呼んでいるのに import が無いことを発見（bf913d1 の CaptureAppClient 抽出リファクタで `from src.wsl_path import get_windows_host_ip` が削除されたまま復帰していなかった）。`/api/capture/stream/start` 実行時に `NameError` になる隠れバグだったため、import を復活させて修正
- 結果: `python3 -m pytest tests/ -q` → **1046 passed / 5 warnings / 9:18**（993 → 1046 / +53件・リグレッションなし）。warnings は Step 5 で解消予定の `@app.on_event` DeprecationWarning のみ

### Step 3-2 実装結果: `scripts/routes/avatar.py` のテスト追加（2026-04-18）

- 実施内容: `tests/test_api_avatar.py` を新規作成（452行 / 27ケース）。発話・TTSテスト・会話デモ・Claude Watcher制御・チャット履歴を一通りカバー
- エンドポイントごとの内訳:
  - **`/api/avatar/speak`**（2ケース）: overlay `current_task` 通知 + `speak_event` 入口検証、`event_type` / `voice` のpassthrough
  - **`/api/tts/test`**（3ケース）: 既知pattern の文言確認、未知patternのランダムフォールバック、`sub=none` 時の単一言語指示
  - **`/api/tts/test-emotion`**（2ケース）: `character.emotions` からの説明文取得、未登録感情のフォールバック
  - **`/api/tts/voice-sample`**（2ケース）: `ensure_reader` 呼び出し + voice/style/avatar_id の伝搬、空文字をNone扱い
  - **`/api/tts/test-multi`**（1ケース）: `generate_event_response` の応答を句読点分割、segments と count の整合性
  - **`/api/claude-watcher/status`**（1ケース）: watcher.status 辞書をそのまま返す
  - **`/api/claude-watcher/config`**（5ケース）: interval最小60秒クランプ、全フィールド更新、`max_utterances` 上限8、enable時start呼び出し、disable時stop呼び出し
  - **`/api/chat/send`**（1ケース）: `_chat.send_message` 呼び出し
  - **`/api/chat/history`**（3ケース）: 空DB、pagination引数echo、avatar_comments混在
  - **`/api/tts/audio`**（2ケース）: 音声なし時の `{"error": "no audio"}`、ファイル存在時のFileResponse + Cache-Control
  - **`/api/debug/conversation-demo/status`**（2ケース）: meta未存在 / meta+wav揃い（speaker/wav_url整形）
  - **`/api/debug/conversation-demo/play`**（2ケース）: meta未存在のエラー、meta在でplayスケジュール成功
  - **`/api/debug/conversation-demo/generate`**（1ケース）: 先生・生徒キャラ未登録時のSSEエラー経路
- 設計上のポイント:
  - `asyncio.create_task(reader.speak_event(...))` 経路は、`AsyncMock.__call__` が呼び出しを即座に記録する性質を利用して、TestClient 同期ブロック内でも `assert_called_once()` が成立することを確認
  - `_CONV_DEMO_DIR`（module-level Path）は `monkeypatch.setattr(avatar_mod, "_CONV_DEMO_DIR", tmp_path / ...)` で差し替え、`resources/audio/conv_demo/` への漏洩を防止
  - `state.ensure_reader` は呼び出す経路では AsyncMock 化して、本番の `db.get_or_create_channel` / `reader.start()` を走らせない
  - `/api/debug/conversation-demo/generate` のSSEはフル生成（Gemini + TTS + ファイルI/O）を再現せず、先生・生徒キャラ未登録エラーの入口のみ検証（`src.lesson_generator.get_lesson_characters` を直接monkeypatch。関数内 `from src.lesson_generator import ...` なのでモジュール属性差し替えで届く）
  - `/api/chat/webui` は既存の `tests/test_api_chat.py` がカバー済みなので対象外
- 注意点・学び:
  - `SUPPORTED_LANGUAGES["ja"]` は `"日本語"`（カタカナ表記なし）なので、detail文言アサートは `"日本語"` で行う
  - `SpeechPipeline.split_sentences` は30文字以下のテキストを分割しない — test-multi のモック応答は長文を用意
  - conv-demo/generate のキャラ未登録エラーメッセージは `"先生・生徒キャラがDBに登録されていません"`（「キャラクター」ではなく「キャラ」）
- 結果: `python3 -m pytest tests/ -q` → **993 passed / 5 warnings / 10:06**（966 → 993 / +27件・リグレッションなし）。warnings は `scripts/web.py` の `@app.on_event` DeprecationWarning 5件で Step 5 の対象

### Step 3-1 実装結果: `lesson_generator/improver.py` のテスト追加（2026-04-18）

- 実施内容: `tests/test_lesson_improver.py` を新規作成し、improver.py の15関数を4カテゴリに分けて計50ケースのテストを追加
- カテゴリ別内訳:
  - **純粋ロジック系（14ケース）**: `_format_sections_for_prompt` / `determine_targets` / `apply_prompt_diff` / `_format_annotated_for_prompt`
  - **ファイルI/O系（9ケース）**: `_load_prompt` / `load_learnings` / `save_learnings_to_files`（`PROMPTS_DIR` / `LEARNINGS_DIR` を `monkeypatch` で `tmp_path` 配下に差し替え）
  - **LLM呼び出し系（17ケース）**: `verify_lesson` / `evaluate_lesson_quality` / `evaluate_category_fit` / `improve_sections` / `analyze_learnings` / `improve_prompt` / `create_category_prompt`（既存 `mock_gemini` フィクスチャの `generate_content.return_value.text` を差し替えて応答制御）
  - **DB系（4ケース）**: `_collect_annotated_sections`（`test_db` フィクスチャ + `create_lesson` / `create_lesson_version` / `add_lesson_section` / `update_section_annotation`）
- 注意点（他テストへの影響）:
  - 初回 `asyncio.run()` 利用で `test_tts_pregenerate.py` の `asyncio.get_event_loop()` が失敗（Python3.12で非推奨挙動）
  - 対策として全LLM系テストを `async def` に変更し、`pytest.ini` の `asyncio_mode = auto` に委ねる形に統一
- 結果: `python3 -m pytest tests/ -q` で **966 passed**（916 → 966 / +50件・リグレッションなし）


## 参考

- 現行テスト一覧: `tests/` 配下 27 ファイル
- テスト方針: `CLAUDE.md` の「テスト」「機能変更時の必須チェック（リグレッション防止）」セクション
- 既存フィクスチャ: `tests/conftest.py`（`test_db` / `api_client` / `mock_gemini` / `mock_env`）
