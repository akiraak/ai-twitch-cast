# トピック機能・授業モード完全削除プラン

**作成日**: 2026-03-21
**ステータス**: 完了

## 背景

トピック機能（自発的発話・ローテーション・スクリプト管理）と授業モードを完全に削除する。
授業モードは将来改めて設計・実装する。

---

## Phase 1: バックエンド削除

### Step 1.1: state.py — TopicTalker除去
- `from src.topic_talker import TopicTalker` 削除
- `topic_talker = TopicTalker()` 削除
- `CommentReader(topic_talker=topic_talker)` → `CommentReader(on_overlay=_dispatch_event)` に修正

### Step 1.2: comment_reader.py — トピック依存除去
- コンストラクタから `topic_talker` パラメータ削除
- `_topic_queue` → `_segment_queue` にリネーム（コメント応答の長文分割用として残す）
- `_should_auto_speak()` 削除
- `_auto_speak()` 削除
- `_speak_topic_segment()` → `_speak_segment()` にリネーム（trigger_typeを `"segment"` に変更）
- `_process_loop()` からトピック分岐削除（コメントキュー + セグメントキューのみ）
- `mark_spoken()` 呼び出しを全箇所から削除（respond_webui, _respond, speak_event）
- `_get_stream_context()` からトピック関連（line 278-287）を削除

### Step 1.3: ai_responder.py — トピック・授業関数削除
削除する関数:
- `generate_topic_line()` (line 455-559)
- `generate_topic_title()` (line 638-717)
- `_make_image_part()` (line 723-736)
- `analyze_images()` (line 739-756)
- `analyze_url()` (line 759-800)
- `generate_lesson_script()` (line 803-855)

### Step 1.4: db.py — テーブル・関数削除
`_create_tables()` から削除:
- `topics` テーブルのCREATE TABLE文
- `topic_scripts` テーブルのCREATE TABLE文

マイグレーション追加:
```sql
DROP TABLE IF EXISTS topic_scripts;
DROP TABLE IF EXISTS topics;
DELETE FROM broadcast_items WHERE id = 'topic';
DELETE FROM settings WHERE key LIKE 'overlay.topic.%';
```

削除する関数:
- `create_topic`, `get_active_topic`, `deactivate_topic`, `deactivate_all_topics`
- `add_topic_scripts`, `get_next_unspoken_script`, `mark_script_spoken`
- `count_unspoken_scripts`, `get_spoken_scripts`, `get_all_scripts`

### Step 1.5: ルーター削除
- `scripts/routes/topic.py` ファイル削除
- `scripts/web.py` から `topic_router` のimport・`app.include_router(topic_router)` 削除

### Step 1.6: avatar.py — tts_test_multi修正
- `generate_topic_line` のimport削除
- `tts_test_multi()` を `generate_event_response` ベースに書き換え（長文テスト用に detail を長めに指示）
- `_speak_topic_segment` → `_speak_segment`、`_topic_queue` → `_segment_queue` に修正

### Step 1.7: prompt_builder.py
- `stream_context.get("topic")` の行（line 177-178）を削除

### Step 1.8: ファイル削除
- `src/topic_talker.py` 削除

---

## Phase 2: フロントエンド削除

### Step 2.1: broadcast.html
- `#topic-panel` HTML要素を削除

### Step 2.2: broadcast JS群
- `globals.js`: `topicPanelEl`, ITEM_REGISTRY の topic エントリ削除
- `init.js`: `loadTopicPanel()` 呼び出しと setInterval 削除
- `websocket.js`: `topic_update`, `topic_image_index` のcase削除
- `panels.js`: `_topicImageUrls`, `_topicImageIndex`, `updateTopicPanel()`, `showTopicImage()`, `loadTopicPanel()` 削除
- `settings.js`: `s.topic` セクション削除
- `edit-mode.js`: `overlaySettings.topic` セクション削除

### Step 2.3: broadcast CSS
- `#topic-panel` と `.topic-*` 関連スタイル全削除

### Step 2.4: 管理画面
- `static/index.html`: トピックタブ全体（`id="tab-topic"`）、タブボタン、レイアウトのtopic項目、DB説明のtopics/topic_scripts、`topic.js`スクリプトタグ削除
- `static/js/admin/topic.js` ファイル削除
- `static/js/admin/utils.js`: `TAB_NAMES` から `'topic'` 削除
- `static/js/admin/init.js`: パネル初期化の `'topic'` 削除

### Step 2.5: overlay/items/scenes設定
- `scripts/routes/overlay.py`: `_OVERLAY_DEFAULTS` と `fixed_items` から `"topic"` 削除
- `scripts/routes/items.py`: `_SCHEMA_ITEM_FIELDS`, `_SCHEMA_ITEM_LABELS`, `_get_item_type()`, `_settings_prefix()` から `"topic"` 削除
- `scenes.json`: `"topic"` セクション削除

---

## Phase 3: テスト更新

### Step 3.1: テストファイル削除
- `tests/test_topic_talker.py` 削除
- `tests/test_api_topic.py` 削除

### Step 3.2: テスト修正
| ファイル | 修正内容 |
|---------|---------|
| `tests/conftest.py` | TopicTalkerのimport・モンキーパッチ削除 |
| `tests/test_db.py` | topics/topic_scripts関連テスト削除、テーブル名リスト更新 |
| `tests/test_overlay.py` | `"topic"` パネル参照削除 |
| `tests/test_broadcast_patterns.py` | topic関連パターン検証削除 |
| `tests/test_prompt_builder.py` | stream_contextの `"topic"` キー削除 |
| `tests/test_ai_responder.py` | `generate_lesson_script` のimport・テスト削除 |
| `tests/test_api_items.py` | topic型アイテムテスト削除 |

### Step 3.3: テスト全パス確認
```bash
python3 -m pytest tests/ -q
```

---

## Phase 4: ドキュメント・メモリ更新

### Step 4.1: TODO.md/DONE.md
- TODO.mdから授業モード関連タスクを削除
- DONE.mdに「トピック機能・授業モード完全削除」を追加

### Step 4.2: メモリファイル
- MEMORY.mdからtopic_talker参照を削除

### Step 4.3: plans/
- `plans/topic-operation.md` → ステータス: 削除済み（不要）
- `plans/english-teacher-mode.md` → ステータス: 削除済み（不要）

### Step 4.4: CLAUDE.md
- ディレクトリ構成からトピック関連の記述を更新

---

## 削除ファイル一覧（7ファイル）
- `src/topic_talker.py`
- `scripts/routes/topic.py`
- `static/js/admin/topic.js`
- `tests/test_topic_talker.py`
- `tests/test_api_topic.py`

## 修正ファイル一覧（22ファイル）
- `scripts/state.py`
- `scripts/web.py`
- `src/comment_reader.py`
- `src/ai_responder.py`
- `src/db.py`
- `src/prompt_builder.py`
- `scripts/routes/avatar.py`
- `scripts/routes/overlay.py`
- `scripts/routes/items.py`
- `static/index.html`
- `static/broadcast.html`
- `static/css/broadcast.css`
- `static/js/broadcast/globals.js`
- `static/js/broadcast/init.js`
- `static/js/broadcast/websocket.js`
- `static/js/broadcast/panels.js`
- `static/js/broadcast/settings.js`
- `static/js/broadcast/edit-mode.js`
- `static/js/admin/utils.js`
- `static/js/admin/init.js`
- `scenes.json`
- `tests/conftest.py`
- `tests/test_db.py`
- `tests/test_overlay.py`
- `tests/test_broadcast_patterns.py`
- `tests/test_prompt_builder.py`
- `tests/test_ai_responder.py`
- `tests/test_api_items.py`
