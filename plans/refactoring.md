# リファクタリングプラン

## ステータス: 作業中

## 概要

プロジェクトのコード品質・保守性を段階的に改善する。各ステップは小さく、動作確認→コミットのサイクルで進める。

**方針**: 分割すること自体を目的にしない。本当に責務が異なる部分だけを抽出し、小さすぎるファイル（100行以下）の乱立を避ける。

---

## 現状分析

### ファイルサイズ（行数）

| ファイル | 行数 | 問題 |
|---------|------|------|
| static/index.html | 1,780 | CSS+JS+HTML全部入りモノリス |
| static/broadcast.html | 1,687 | Three.js+WS+UI+CSS全部入り |
| src/ai_responder.py | 691 | プロンプト生成+キャラ管理+AI呼び出し混在 |
| scripts/routes/capture.py | 665 | WS通信+HTTP proxy+レイアウト+スクショ混在 |
| src/db.py | 537 | 50+関数、CRUDパターン重複 |
| src/comment_reader.py | 503 | God class（TTS+感情+チャット+DB+メモ更新） |
| scripts/routes/stream_control.py | 374 | アプリ管理+配信+音量+診断混在 |
| scripts/routes/overlay.py | 371 | WS+TODO監視+設定+ライティング混在 |

### アーキテクチャ問題（優先度順）

1. **レイヤー違反**: `src/comment_reader.py` が `scripts/routes/capture.py` をインポート（ビジネスロジック→ルーティング層）
2. **ルート間の密結合**: stream_control.py → capture.py に6箇所、web.py → capture.py に1箇所、state.py → capture.py に1箇所の関数インポート
3. **WebSocket管理の分散**: capture.py, state.py, overlay.py に別々のWS管理
4. **グローバル状態**: `_is_streaming`, `_capture_ws`, `_todo_last_mtime` がモジュールレベルに散在
5. **設定ソースの分散**: scenes.json + SQLite DB + ハードコード定数

---

## Phase 1: Python バックエンド整理（低リスク・高効果）

### Step 1-1: CaptureAppClient 抽出 ★最優先 ✅完了

**目的**: capture.py のWS/HTTP通信を独立クラスに抽出し、レイヤー違反・ルート間密結合を解消

**背景**: comment_reader.py（src/）→ capture.py（scripts/routes/）のレイヤー違反は構造的負債の核心。capture.py の `_ws_request()` は9箇所以上から参照されており、ルート層に置くべきではない。

**作業内容**:
- `scripts/services/capture_client.py` を新規作成
- capture.py の `_capture_base_url()`, `_capture_ws_url()`, `_ensure_capture_ws()`, `_read_capture_ws()`, `_ws_request()`, `_proxy_request()`, `_restore_bgm_to_app()`, `_PATH_TO_ACTION` を移動
- `CaptureAppClient` クラスとして再構成（接続管理・リクエスト送信・再接続・BGM復元）
- 以下の全インポート箇所を `CaptureAppClient` に置換:
  - stream_control.py（6箇所: `_ws_request`, `_capture_base_url`）
  - comment_reader.py（1箇所: `_ws_request` — レイヤー違反解消）
  - web.py（1箇所: `_ws_request` in `_restore_session`）
  - state.py（1箇所: `broadcast_bgm` 内の `_ws_request`）
  - tests/test_capture_proxy.py（import先変更）

**対象ファイル**:
- scripts/services/capture_client.py（新規 ~180行）
- scripts/routes/capture.py（665→~450行に削減）
- scripts/routes/stream_control.py（capture依存解消）
- src/comment_reader.py（レイヤー違反解消）
- scripts/state.py（CaptureAppClient インスタンス保持）
- scripts/web.py（import先変更）

### Step 1-2: prompt_builder.py 抽出 ✅完了

**目的**: ai_responder.py からプロンプト組み立てロジックを分離

**背景**: ai_responder.py は691行。プロンプト組み立て（システムプロンプト構築・言語モードプリセット）はAI呼び出しとは独立した責務。ただしキャラクター管理は ai_responder.py の本質的機能なので分離しない。

**作業内容**:
- `src/prompt_builder.py` を新規作成
  - `_build_system_prompt()` (61行) を移動
  - `LANGUAGE_MODES` 定義 (89行) を移動
  - `get_language_mode()`, `set_language_mode()` (9行) を移動
- ai_responder.py はgenerate_*関数+キャラクター管理のみ残す
- 外部import先の変更: tts.py, scripts/routes/character.py, scripts/web.py, テスト2ファイル（`LANGUAGE_MODES`, `get/set_language_mode` の参照先を prompt_builder に変更）

**対象ファイル**:
- src/ai_responder.py（691→~440行に削減）
- src/prompt_builder.py（新規 ~200行）

**やらないこと**:
- `character_manager.py` の新規作成（キャラクター読み込み・キャッシュはai_responderの本質的機能。120行の小ファイルにする意義が薄い）

### Step 1-3: speech_pipeline.py 抽出 ✅完了

**目的**: comment_reader.py のGod classから音声パイプラインを分離

**背景**: comment_reader.py は503行で TTS+感情+チャット+DB+メモ更新を全て担当。TTS呼び出し→リップシンク→WebSocket送信の一連フローはオーケストレーション層として分離可能。

**作業内容**:
- `src/speech_pipeline.py` を新規作成（TTS生成+リップシンク解析+WS経由の音声送信オーケストレーション）
  - `_strip_lang_tags()` (4行) を移動
  - `_notify_overlay()` (12行), `_notify_overlay_end()` (4行) を移動
  - `_speak()` (84行) を移動 — コアのTTSオーケストレーション
  - `_send_tts_to_native_app()` (30行) を移動
  - `_apply_emotion()` (17行) を移動
- CommentReader は キュー管理+チャット処理+メモ更新 に集中
- 移動するステート: `_current_audio` のみ。キュー・ライフサイクル変数は残留
- 依存方向: speech_pipeline → {tts, lipsync, ai_responder}（一方向、循環なし）

**対象ファイル**:
- src/comment_reader.py（503→~300行に削減）
- src/speech_pipeline.py（新規 ~150行）

**やらないこと**:
- `note_updater.py` の新規作成（80行の小ファイルにする意義が薄い。comment_reader.py 内のprivateメソッドのまま残す）

### Step 1-4: コード品質改善

**目的**: 非推奨パターン・不十分なエラーハンドリングを修正

**作業内容**:
- `asyncio.ensure_future` → `asyncio.create_task` に置換（web.py, avatar.py, overlay.py）
- `except Exception: pass` → 具体的な例外キャッチ+ログ出力（comment_reader.py 3箇所, overlay.py, capture.py）

**対象ファイル**:
- scripts/web.py, scripts/routes/overlay.py, scripts/routes/capture.py
- src/comment_reader.py
- scripts/routes/avatar.py（存在する場合）

---

## Phase 2: フロントエンド整理（中リスク・高効果）

### Step 2-1: CSS外部化

**目的**: 全HTMLファイルからCSSを外部ファイルに抽出（最もリスクが低いフロントエンド変更）

**作業内容**:
- `static/css/broadcast.css` — broadcast.html から ~381行のスタイル抽出
- `static/css/index.css` — index.html から ~139行のスタイル抽出
- 各HTMLは `<link rel="stylesheet">` で参照

**対象ファイル**:
- static/broadcast.html（CSS部分のみ削減）
- static/index.html（CSS部分のみ削減）

**やらないこと**:
- preview.html のCSS抽出（430行の小ファイルなので不要）

### Step 2-2: 共通JSユーティリティ抽出

**目的**: 複数HTMLで重複するfetchパターンを統一

**作業内容**:
- `static/js/lib/api-client.js` — fetch ラッパー、エラーハンドリング（index.htmlの`api()`関数をベースに統一）
- オプション `{ useToast, useLog }` で環境差を吸収（index.html: toast+log有効、broadcast.html: toast無効）

**対象ファイル**:
- static/index.html（`api()` を外部参照に変更）
- static/broadcast.html（散在する`fetch()`を`api()`に置換）

**やらないこと**:
- `ui-toast.js`, `ui-modal.js`, `dom-utils.js` の独立ファイル化（index.htmlでしか使わないため、Step 2-4のindex.html分割時にまとめて外部化する）

### Step 2-3: broadcast.html JS分割

**目的**: 1,231行のインラインJSをモジュール分割

**注意**: broadcast.html は配信中にリアルタイムで使用される。リグレッションは配信事故に直結するため、段階的に進める。

**作業内容**（段階的に実施）:
1. `static/js/avatar-renderer.js` — Three.js VRMレンダラ+idle animation（~280行、独立性が最も高い）
2. `static/js/broadcast-ws.js` — WebSocket接続・メッセージルーティング
3. `static/js/broadcast-ui.js` — ドラッグ&リサイズ・編集モード・設定適用（UIとSettingsは密結合なのでまとめる）
- broadcast.html はHTML構造+初期化+各モジュール呼び出し

**対象ファイル**:
- static/broadcast.html（1,687→~300行に削減）

**やらないこと**:
- `broadcast-settings.js` の独立ファイル化（broadcast-ui.js と密結合なのでまとめる）
- 100行を目標にしない（300行程度が現実的なゴール）

### Step 2-4: index.html JS分割

**目的**: 1,238行のインラインJSをタブごとに分割

**背景**: 87関数が8タブ分のロジックを1ファイルに持つ。タブごとの分割は自然な境界があり、リスクが低い。

**作業内容**:
- `static/js/tabs/tab-layout.js` — 配信画面タブ
- `static/js/tabs/tab-character.js` — キャラクタータブ
- `static/js/tabs/tab-sound.js` — サウンドタブ
- `static/js/tabs/tab-topic.js` — トピックタブ
- `static/js/tabs/tab-db.js` — DB閲覧タブ
- `static/js/tabs/tab-files.js` — 素材タブ
- `static/js/index-app.js` — メイン初期化+タブ切替+共通ユーティリティ（toast/modal/escape等）
- index.html はHTML構造+タブコンテナのみに

**対象ファイル**:
- static/index.html（1,780→~300行に削減）

**やらないこと**:
- `tab-router.js` の独立ファイル化（index-app.js にまとめる。タブ切替ロジックだけで独立ファイルにする意義が薄い）

---

## スキップしたステップ（理由付き）

| 旧ステップ | スキップ理由 |
|-----------|-------------|
| 旧1-1: 定数・設定の集約 (`scripts/config.py`) | `scene_config.py` が既に設定集約の役割を担当。CAPTURE_PORT等は1箇所でしか使わない定数を別ファイルに移すと間接参照が増えるだけ |
| 旧1-3: web.py の分割 | 267行は十分管理可能なサイズ。startup/restore_sessionはライフサイクルと密接に結合しており、分離するとコードの流れが追いにくくなる |
| 旧1-4の一部: character_manager.py | 120行の小ファイル。キャラクター管理はai_responderの本質的機能で、分離すると凝集度が下がる |
| 旧1-5の一部: note_updater.py | 80行の小ファイル。comment_reader.py 内のprivateメソッドのまま十分 |
| 旧1-6: ルートファイル整理 (capture_layout, screenshots, lighting) | Step 1-1でcapture.pyが~450行になれば管理可能。100行以下の小ファイル乱立を避ける |
| 旧2-4: preview.html の分割 | 430行は管理可能なサイズ。一貫性のためだけに分割する意義が薄い |
| 旧3-3: TTS→VOICE リネーム | リファクタリングではなくUI変更。別タスクとして管理すべき |

---

## リスク管理

### 各ステップの確認項目

1. **テスト実行**: `pytest tests/` が全パス
2. **サーバー起動**: `curl http://localhost:$WEB_PORT/api/status` が応答
3. **WebSocket接続**: broadcast.html がWS接続可能
4. **TTS再生**: コメント応答で音声再生
5. **配信画面**: broadcast.html のアバター・TODO・字幕が表示

### 特にリスクが高いステップ

- **Step 2-3（broadcast.html JS分割）**: 配信中にリアルタイムで使用されるファイル。Three.js ES modules と通常スクリプトの混在に注意。各サブステップごとに動作確認必須
- **Step 1-1（CaptureAppClient抽出）**: 複数ファイルにまたがる変更。WS接続管理のステート移行に注意

### やらないこと

- DB構造の変更（マイグレーションリスク）
- APIエンドポイントのURL変更（C#アプリ互換性）
- WebSocketメッセージフォーマットの変更（broadcast.html互換性）
- 外部ライブラリの追加・変更

---

## ディレクトリ構成（リファクタリング後）

```
ai-twitch-cast/
├── scripts/
│   ├── web.py                      # FastAPIアプリ（変更なし）
│   ├── state.py                    # 共有状態（CaptureAppClient追加）
│   ├── services/                   # サービス層（新規）
│   │   └── capture_client.py       # C#アプリWS/HTTP通信
│   └── routes/
│       ├── capture.py              # キャプチャCRUD（スリム化 ~450行）
│       ├── overlay.py              # WebSocket+設定+ライティング
│       ├── stream_control.py       # 配信制御（capture依存解消）
│       ├── bgm.py / topic.py / ...
│       └── ...
├── src/
│   ├── ai_responder.py             # AI呼び出し+キャラ管理（スリム化 ~440行）
│   ├── prompt_builder.py           # プロンプト組み立て（新規 ~200行）
│   ├── comment_reader.py           # キュー+チャット+メモ（スリム化 ~300行）
│   ├── speech_pipeline.py          # TTS+リップシンク オーケストレーション（新規 ~150行）
│   ├── db.py / tts.py / ...
│   └── ...
├── static/
│   ├── broadcast.html              # HTML構造+初期化（スリム化 ~300行）
│   ├── index.html                  # HTML構造+タブコンテナ（スリム化 ~300行）
│   ├── preview.html                # 変更なし（430行）
│   ├── css/
│   │   ├── broadcast.css           # broadcast画面スタイル（新規 ~381行）
│   │   └── index.css               # Web UIスタイル（新規 ~139行）
│   └── js/
│       ├── lib/
│       │   └── api-client.js       # fetch ラッパー（新規）
│       ├── avatar-renderer.js      # VRMレンダラ（新規 ~280行）
│       ├── broadcast-ws.js         # WS接続（新規）
│       ├── broadcast-ui.js         # ドラッグ&リサイズ+設定（新規）
│       ├── tabs/
│       │   ├── tab-layout.js       # 配信画面タブ（新規）
│       │   ├── tab-character.js    # キャラクタータブ（新規）
│       │   ├── tab-sound.js        # サウンドタブ（新規）
│       │   ├── tab-topic.js        # トピックタブ（新規）
│       │   ├── tab-db.js           # DB閲覧タブ（新規）
│       │   └── tab-files.js        # 素材タブ（新規）
│       └── index-app.js            # メイン初期化+タブ切替+共通util（新規）
└── ...
```

**新規ファイル数**: 旧プラン 22ファイル → 修正後 **13ファイル**（約40%削減）
