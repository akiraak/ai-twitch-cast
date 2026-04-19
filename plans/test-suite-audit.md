# テストスイートの棚卸し（不要削除・不足補完）

## ステータス: 未着手

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
