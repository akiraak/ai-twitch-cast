# リファクタリングプラン (2026-03-30)

## ステータス: Phase 4 完了

## 背景

コードベースが成長し、いくつかの巨大ファイルが保守性を下げている。
主要な問題:
- `src/lesson_generator.py` (2,666行) — 28関数・5つの責務が単一ファイルに混在
- `src/db.py` (2,138行) — 80+関数のGodオブジェクト
- `src/ai_responder.py` (1,149行) — キャラクター管理とレスポンス生成が混在、multi/single の重複
- `scripts/routes/overlay.py` (861行) — TODO操作ロジックがルートに直書き・重複

## 方針

- **段階的に実施**: 一度に全部やらず、フェーズごとに進める
- **テスト先行**: リファクタ前に既存テストが通ることを確認し、リファクタ後も通ることを保証
- **外部インターフェース維持**: API エンドポイントや WebSocket イベントは変更しない
- **import パス互換**: `__init__.py` で re-export し、既存の import を壊さない

---

## Phase 1: lesson_generator.py の分割（最優先・最大効果）

**対象**: `src/lesson_generator.py` (2,666行・28関数) → パッケージ化

### 検証結果

- 公開関数 9個、内部関数 19個（全28関数の依存関係を確認済み）
- **循環参照なし** — 依存グラフは一方向
- 3つのスクリプト生成関数は**全て使用中**（dead code ではない）
  - `generate_lesson_script`: 直接テキスト→対話（最速・最シンプル）
  - `generate_lesson_script_from_plan`: プラン入力（バランス型）
  - `generate_lesson_script_v2`: フルパイプライン＋ディレクター評価（最高品質）
- `avatar.py` が private 関数 `_format_character_for_prompt` を直接 import している → re-export 必須

### 分割先

```
src/lesson_generator/
├── __init__.py              # 公開関数9個 + _format_character_for_prompt を re-export
├── utils.py                 # モデル選択、JSONパース、共通ヘルパー
│                            #   _is_english_mode, _get_model, _get_*_model (5個)
│                            #   _parse_json_response, _guess_mime
│                            #   _build_image_parts ← 3+モジュールから使われるため utils に配置
│                            #   _format_main_content_for_prompt ← structure と director の両方から使用
├── extractor.py             # テキスト抽出・前処理
│                            #   clean_extracted_text, _normalize_roles
│                            #   extract_main_content, extract_text_from_image, extract_text_from_url
├── structure.py             # 構造生成（utils から _format_main_content_for_prompt を import）
│                            #   _build_structure_prompt
├── dialogue.py              # 対話生成
│                            #   get_lesson_characters, _format_character_for_prompt
│                            #   _build_dialogue_prompt, _build_dialogue_output_example
│                            #   _generate_single_dialogue, _generate_section_dialogues
├── script.py                # スクリプト生成（v1 + from_plan）
│                            #   _build_section_from_dialogues
│                            #   generate_lesson_script, generate_lesson_script_from_plan
├── director.py              # ディレクター評価（utils から _format_main_content_for_prompt を import）
│                            #   _director_review
├── planner.py               # レッスンプラン生成（utils から _build_image_parts を import）
│                            #   generate_lesson_plan
└── v2.py                    # v2パイプライン（structure, dialogue, director, utils を使用）
                             #   _build_adjacent_sections, generate_lesson_script_v2
```

### 依存方向（循環なし）

```
utils.py          ← 基盤層（内部依存なし）
  ↑
extractor.py      ← utils のみ
structure.py      ← utils のみ
dialogue.py       ← utils のみ
director.py       ← utils のみ
planner.py        ← utils のみ
  ↑
script.py         ← dialogue + utils
  ↑
v2.py             ← structure + dialogue + director + utils
```

### 元プランからの修正点

| 修正 | 理由 |
|------|------|
| `_build_image_parts` を utils に移動 | 3+モジュール（planner, script, v2）から呼ばれるため structure に置くと結合度が高い |
| `_format_main_content_for_prompt` を utils に移動 | structure と director の両方から使われ、structure に置くと director→structure の依存が発生 |
| `planner.py` を追加（structure.py から分離） | generate_lesson_plan は structure 生成とは別の責務（3expert方式のプランニング） |
| 3つのスクリプト生成関数を残す | 全て teacher.py から使用中。用途が異なるため dead code ではない |

### 手順

1. テスト実行（ベースライン確認）
2. `src/lesson_generator/` 作成、`utils.py` から順に移動
3. `__init__.py` で全公開関数 + `_format_character_for_prompt` を re-export
4. 未使用 import `base64` を削除
5. テスト実行（`test_lesson_generator.py` + 全テスト）

### リスク

| リスク | 対策 |
|--------|------|
| `routes/teacher.py` が8関数を直接 import | `__init__.py` の re-export で対応（変更不要） |
| `avatar.py` が private 関数を import | `__init__.py` で re-export |
| テストが14関数（内部含む）を import | `__init__.py` で re-export（テスト変更不要） |

---

## Phase 2: db.py の分割

**対象**: `src/db.py` (2,138行・80+関数) → 安全に分離可能なドメインのみ抽出

### 検証結果

- **安全に分離可能**: lessons, audio (BGM/SE), items の3ドメイン
- **分離不可**: 以下はコアに残す必要がある
  - **characters + character_memory**: lazy initialization で相互結合
  - **comments + avatar_comments + timeline**: `get_recent_timeline()` が UNION 結合
  - **settings**: 全ドメインから横断的に使用
  - **migrations**: 起動時に実行、複数ドメインを横断的に読み書き
  - **channels, shows, episodes, users, actions**: 小規模かつ相互参照あり

### 分割先

```
src/db/
├── __init__.py              # get_connection + 全公開関数を re-export（既存 import 互換）
├── core.py                  # 元の db.py のコア部分（約1,200行）
│                            #   get_connection, _create_tables, _now, 全 migrations
│                            #   channels, characters, character_memory
│                            #   shows, episodes, users
│                            #   comments, avatar_comments, timeline, actions
│                            #   settings
├── lessons.py               # レッスン CRUD（約150行）
│                            #   create_lesson, get_lesson, get_all_lessons, update_lesson, delete_lesson
│                            #   add_lesson_source, get_lesson_sources, delete_lesson_source
│                            #   add/get/update/delete/reorder_lesson_section(s)
│                            #   get/upsert/delete_lesson_plan(s)
├── audio.py                 # BGM・SE CRUD（約80行）
│                            #   get/set/delete_bgm_track_*, get_all_bgm_tracks
│                            #   get_all_se_tracks, get_se_tracks_by_category, upsert/delete_se_track
└── items.py                 # ブロードキャストアイテム CRUD（約200行）
                             #   get/upsert/delete_broadcast_item*, get/create/delete_child_item
                             #   get/create/update/delete_custom_text*
                             #   get/upsert/update/delete_capture_window*
```

### 元プランからの修正点

| 修正 | 理由 |
|------|------|
| characters, settings, migrations をコアに残す | characters↔memory は lazy init で結合、settings は全ドメインが使用、migrations は起動時に複数ドメインを横断 |
| comments + avatar_comments + timeline をコアに残す | `get_recent_timeline()` が UNION で両テーブルを結合、`_migrate_comments_split()` が横断 |
| schema.py を作らない | `_create_tables()` が migrations を呼ぶため分離すると循環リスク |
| 分離対象を3ドメインに限定 | 安全性を優先。残りは将来のフェーズで検討 |

### 手順

1. テスト実行（ベースライン確認）
2. `src/db/` 作成、`core.py` に元のコードを配置
3. lessons, audio, items を各ファイルに移動（`from .core import get_connection` で接続取得）
4. `__init__.py` で全公開関数を re-export
5. テスト実行（`test_db.py` + 全テスト）
6. `conftest.py` の `test_db` フィクスチャが動作することを確認

### リスク

| リスク | 対策 |
|--------|------|
| test_db フィクスチャがモジュール丸ごと yield | `__init__.py` の re-export で対応（テスト変更不要） |
| `routes/character.py` が `db.get_connection()` で直接 SQL 実行 | core.py に残るため問題なし |
| migration が items テーブルに書き込み | migration は core.py に残すため問題なし |

---

## Phase 3: ai_responder.py のキャラクター管理分離

**対象**: `src/ai_responder.py` (1,149行) → キャラクター管理を抽出

### 検証結果

- 元プランの「context/generator/multi/character」分割は**実際の責務境界と合わない**
  - コンテキスト構築はレスポンス生成の中にインラインで組み込まれている
  - multi と single で同じコンテキスト構築ロジックが重複している
- **キャラクター管理**は明確に分離可能（11関数 + モジュールレベルキャッシュ）
- `_get_channel_id()` が外部（comment_reader, lesson_generator）から呼ばれている → 公開 API にすべき

### 分割方針（2ファイル構成）

```
src/character_manager.py     # NEW: キャラクターライフサイクル管理
  _get_channel_id() → get_channel_id()  # 公開化
  seed_character()
  seed_all_characters()
  build_character_context()
  build_all_character_contexts()
  load_character()
  get_all_characters()
  get_character()
  get_character_id()
  get_chat_characters()
  get_tts_config()
  invalidate_character_cache()
  [モジュール状態: _character, _character_id]

src/ai_responder.py          # 既存ファイル（レスポンス生成に集中）
  # character_manager から import
  generate_response()
  generate_multi_response()
  generate_event_response()
  generate_multi_event_response()
  generate_user_notes()
  generate_self_note()
  generate_persona_from_prompt()
  generate_persona()
```

### 元プランからの修正点

| 修正 | 理由 |
|------|------|
| 4ファイル分割 → 2ファイル分割に縮小 | context と generator は深く絡み合っており、分離すると逆に可読性が下がる |
| multi.py を作らない | multi/single の重複はコンテキスト構築の共通化で解消すべきだが、ファイル分割では解決しない |
| character_manager.py を新設 | キャラクター管理は明確な責務境界がある（DB操作・キャッシュ・初期化） |
| `_get_channel_id()` を公開化 | comment_reader.py と lesson_generator.py から外部呼び出しされている |

### 追加改善: multi/single コンテキスト構築の重複解消

`generate_response()` (lines 361-393) と `_build_multi_context()` (lines 859-932) で
ほぼ同じコンテキスト構築ロジックが重複している。分割後に `ai_responder.py` 内で共通化:

```python
def _build_context_string(user_name, comment_count, user_note, already_greeted, ...):
    """single/multi 共通のコンテキスト文字列構築"""
    ...
```

### 手順

1. テスト実行（ベースライン確認）
2. `src/character_manager.py` 作成、キャラクター関連11関数を移動
3. `ai_responder.py` で `from src.character_manager import ...` に変更
4. 外部呼び出し元の import 互換のため `ai_responder.py` で re-export
5. `_get_channel_id()` → `get_channel_id()` に改名（外部呼び出し元も更新）
6. multi/single のコンテキスト構築を共通関数に抽出
7. テスト実行

### リスク

| リスク | 対策 |
|--------|------|
| 外部から `ai_responder.get_character()` 等を呼ぶコードが多い | ai_responder.py で re-export して互換維持 |
| comment_reader が `_get_channel_id()` を import | 公開化 + import 元を character_manager に変更 |
| キャラクターキャッシュのグローバル状態 | character_manager.py にそのまま移動（動作は変えない） |

---

## Phase 4: overlay.py の TODO 操作ロジック抽出

**対象**: `scripts/routes/overlay.py` (861行) の TODO 管理部分

### 検証結果

- `/api/todo/start` と `/api/todo/stop` で**ほぼ同じファイル解析・修正ロジックが重複**
- 正規表現によるファイル解析、DB操作、ファイル書き戻しがルートハンドラに直書き
- WebSocket メッセージルーティングもインラインだが、こちらは小規模なので現状維持

### 抽出先

```
scripts/services/todo_service.py    # NEW: TODO操作ロジック
  class TodoManager:
    get_items(source_id) → list       # ファイル or DB から取得
    start_task(source_id, task_text)   # [ ] → [>] に変更
    stop_task(source_id, task_text)    # [>] → [ ] に変更
    _parse_todo_file(path) → list
    _modify_todo_file(path, task_text, from_mark, to_mark)
    _get_in_progress(source_id) → list
    _set_in_progress(source_id, list)
```

### 手順

1. `scripts/services/` ディレクトリ作成（既に存在するか確認）
2. TODO 操作ロジックを `todo_service.py` に抽出
3. overlay.py のルートハンドラを薄くする
4. テスト実行

---

## Phase 5: 未使用 import の削除（随時実施）

他のフェーズと独立して随時実施可能。

| ファイル | import | 備考 |
|---------|--------|------|
| `src/lesson_generator.py` | `base64` | Phase 1 で削除 |
| `src/ai_responder.py` | `Path` | Phase 3 で削除 |
| `scripts/routes/teacher.py` | `LESSON_AUDIO_DIR` | 単独で削除可能 |

---

## 元プランで提案されていたが不要と判定した項目

### 言語設定ヘルパーの統一 → 不要

検証の結果、言語設定は既に `src/prompt_builder.py` に一元化されており、各ファイルは
`from src.prompt_builder import get_stream_language, SUPPORTED_LANGUAGES` で正しく import している。
コードの重複ではなく、正しい関数の利用。

### JSON パースの標準化 → 一部不要

検証の結果、JSON パースは用途ごとに異なるパターンを**意図的に**使い分けている:

| パターン | 用途 | 場所 |
|---------|------|------|
| `parse_llm_json()` (修復あり) | LLM 出力の壊れた JSON | json_utils.py（既に共通化済み） |
| `try-except + silent pass` | 欠損しうるデータ | content_analyzer.py |
| `try-except + fallback list` | デフォルト値のある設定 | overlay.py |
| エラーハンドリングなし | スキーマで保証されたデータ | db.py の config パース |

フォールバックの挙動が異なるため、無理に統一するとかえって分かりにくくなる。

### ブロードキャスト関数の統一 → 不要

検証の結果、各 broadcast 関数は**意図的に異なる**:

| 関数 | 送信先 | 特殊処理 |
|------|--------|----------|
| `broadcast_overlay` | Web クライアント | 言語タグ除去 |
| `broadcast_tts` | Web クライアント | なし |
| `broadcast_bgm` | Web + C# アプリ | C# API 呼び出し |
| `broadcast_se` | C# アプリのみ | C# API 呼び出し |
| `broadcast_to_broadcast` | broadcast.html のみ | なし |

送信先と処理が異なるため、統一すると条件分岐が増えて可読性が下がる。

### Gemini API 呼び出しの共通化 → 不要

config 構造（JSON/Audio/Text）、モデル選択、エラーハンドリング、リトライ戦略が
呼び出しごとに異なるため、抽象化するとかえって複雑になる。

---

## 実施順序と依存関係

```
Phase 1 (lesson_generator 分割)  ← 最大効果・独立して実施可能
Phase 2 (db 分割)                ← Phase 1 と並行実施可能
Phase 3 (ai_responder 整理)      ← Phase 1, 2 と独立
Phase 4 (overlay TODO 抽出)      ← Phase 1-3 と独立
Phase 5 (未使用 import 削除)      ← 各フェーズと同時に実施
```

全フェーズが独立しているため、どの順番でも実施可能。
ただし Phase 1 が最大の行数削減効果があるため最優先推奨。

---

## 今回のスコープ外（将来検討）

以下は今回のリファクタリングでは扱わない。必要に応じて別プランで検討:

- **teacher.py のサービス層抽出**: lesson_service.py へのオーケストレーション移動（Phase 1 完了後に検討）
- **state.py のクラス化**: サービスロケータ → 明示的な依存注入（大規模変更のため別プラン）
- **グローバル言語状態のリクエストスコープ化**: `_stream_lang` の並行リクエスト時の競合（配信は単一ユーザーなので実害は低い）
- **キャラクターキャッシュの改善**: モジュールスコープ → DB バックドキャッシュ（現状で動作しているため優先度低）
- **db.py コアのさらなる分割**: characters, comments 等の分離（Phase 2 完了後に効果を評価して判断）

---

## 完了条件

各フェーズ共通:
- [ ] 全テスト（`pytest tests/ -q`）がパス
- [ ] サーバー起動確認（`/api/status` 応答）
- [ ] 既存の import パスが壊れていない（re-export で互換維持）
- [ ] 配信機能に影響なし
