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

### 実行時間プロファイル（初期計測 2026-04-18）

`--durations=15` の上位（単位: 秒）:

| 時間 | フェーズ | テスト |
|-----:|---------|-------|
| 66.96 | call | `test_lesson_runner.py::TestSendAllAndPlay::test_sends_lesson_load_with_all_sections` |
| 63.83 | call | `test_lesson_runner.py::TestPlaybackPersistence::test_send_all_and_play_saves_state` |
| 60.68 | call | `test_lesson_runner.py::TestSendAllAndPlay::test_resume_from_saved_index` |
| 60.23 | call | `test_lesson_runner.py::TestSendAllAndPlay::test_tts_progress_notification` |
| 5.01 | call | `test_speech_pipeline.py::TestSpeak::test_speak_no_chat_callback` |
| 5.01 | call | `test_speech_pipeline.py::TestSpeak::test_speak_with_tts_failure` |
| 1.11 | call | `test_tts_pregenerate.py::TestPregenerateSectionTts::test_retry_on_failure` |
| 1.03 | setup | `test_db.py::TestBgmTracks::test_upsert_volume` |
| 1.01 | call | `test_claude_watcher.py::TestClaudeWatcherPlayConversation::test_comment_interrupt_cancels_batch` |

**観察**:
- 上位4件（合計 ≈ 251秒）がすべて `test_lesson_runner.py` の `TestSendAllAndPlay` / `TestPlaybackPersistence` 配下。**532秒の約半分がこの4テストに集中**。`lesson_runner.py` の再生ループ内の `asyncio.sleep` 等を実時間で待っている可能性が高い → `asyncio.sleep` をモックするか `@pytest.mark.slow` 退避の最有力候補
- `test_speech_pipeline.py::TestSpeak::test_speak_no_chat_callback` / `test_speak_with_tts_failure` の5秒も同様に `_wait_tts_complete()` のポーリング待機を実時間で回している疑い
- setup が1秒超えているケースは `api_client` フィクスチャ生成コストの可能性 → session スコープ化で短縮できるか要確認

### CLAUDE.md 表との差分
（Step 1-d で転記）

### 削除候補一覧
（Step 1-b, 1-c の結果をもとに作成）

## 参考

- 現行テスト一覧: `tests/` 配下 27 ファイル
- テスト方針: `CLAUDE.md` の「テスト」「機能変更時の必須チェック（リグレッション防止）」セクション
- 既存フィクスチャ: `tests/conftest.py`（`test_db` / `api_client` / `mock_gemini` / `mock_env`）
