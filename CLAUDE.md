# AI Twitch Cast

AIを活用し、プログラムで全自動Twitch配信を行うプロジェクト。

## プロジェクト概要

C#ネイティブ配信アプリ（Windows側でbroadcast.htmlをオフスクリーンレンダリング→FFmpegでTwitch直接配信）、Twitch API連携、画像生成・収集、テキスト生成、音声合成など、配信に必要な要素をすべてプログラムで生成・制御する。

## 主要コンポーネント

- **C#ネイティブ配信アプリ** - Windows側C#アプリ（`win-native-app/`）でbroadcast.htmlをWebView2でレンダリング→FFmpegでTwitch直接配信（OBS/xvfb不要）
- **ウィンドウキャプチャ** - 同アプリでWindows Graphics Capture APIによりウィンドウをキャプチャ→MJPEGストリーム配信→broadcast.htmlで表示
- **Twitch API** - チャット読み取り・配信管理・視聴者インタラクション
- **テキスト生成** - LLMによる台本・コメント・ナレーション生成
- **音声合成** - TTS（Text-to-Speech）によるナレーション音声生成
- **レイアウト編集** - `/broadcast` でドラッグ＆リサイズによる配信画面レイアウト調整（常時編集可能）

## 開発ルール

- 言語: Python
- コミットメッセージ: 日本語可
- コード内コメント: 日本語可
- ドキュメント: 日本語
- **コミット前に必ずTODO.mdとDONE.mdを更新すること（最優先ルール）**
  - 実装した機能・修正したバグはDONE.mdに追加
  - 完了したタスクはTODO.mdから削除（`[x]`を残さない）
  - 新たに見つかった課題はTODO.mdに追加
- TODO.mdには未完了タスク（`[ ]`）と作業中タスク（`[>]`）のみを置く
- **バージョン更新**: 機能追加・大きな変更時は `VERSION` ファイルを更新する。基準は [docs/versioning.md](docs/versioning.md) を参照。コミット時にちょびが自動提案する
- **ファイルの所有者**: Claude Code（root）が編集したファイルは PostToolUse フックで自動的に `ubuntu:ubuntu` に修正される（`.claude/hooks/fix-permissions.sh`）

## リソース管理

- リソース（画像・VRMモデル・音声・動画）は `resources/` 配下で一元管理
- 詳細は [docs/resource-management.md](docs/resource-management.md) を参照

## ドキュメント

- `docs/` 配下のMarkdownがGitHub Pages（MkDocs + material）で自動公開される
- mainブランチへのpush時に `.github/workflows/deploy-pages.yml` で自動ビルド・デプロイ
- 公開URL: https://akiraak.github.io/ai-twitch-cast/

## ディレクトリ構成

```
ai-twitch-cast/
├── .github/workflows/
│   └── deploy-pages.yml     # GitHub Pages自動デプロイ
├── docs/                     # ドキュメント（GitHub Pagesで公開）
│   ├── assets/images/        # 画像素材（OGP等）
│   ├── overrides/            # MkDocsテーマオーバーライド（OGP設定等）
│   ├── index.md              # トップページ
│   ├── avatar-research.md   # アバター表示調査
│   ├── 3d-model-research.md # 3Dモデル調査
│   ├── vrm-conversion-log.md # VRM変換作業ログ
│   └── window-capture.md   # ウィンドウキャプチャシステム設計
├── win-native-app/           # C#ネイティブ配信アプリ
│   └── WinNativeApp/        # .NET 8 WinForms + WebView2 + WGC
│       ├── Program.cs       # エントリポイント（Serilog初期化）
│       ├── MainForm.cs      # WebView2フォーム + キャプチャ管理 + HTTPサーバー + システムトレイ
│       ├── Capture/         # WGCフレームキャプチャ + ウィンドウキャプチャ管理
│       ├── Server/          # HTTP/WebSocket API（キャプチャ・配信制御・/ws/control）
│       └── Streaming/       # FFmpeg配信パイプライン（FfmpegProcess + AudioLoopback + TtsDecoder + StreamConfig）
├── src/                      # ソースコード
│   ├── scene_config.py       # 設定の定義（scenes.jsonから読み込み）
│   ├── tts.py                # TTS音声合成（Gemini 2.5 Flash TTS）
│   ├── twitch_chat.py        # Twitchチャット受信
│   ├── ai_responder.py       # AI応答生成（会話履歴・配信コンテキスト・ユーザーメモ対応）
│   ├── comment_reader.py     # コメント読み上げサービス（15分バッチでユーザーメモ更新）
│   ├── topic_talker.py       # トピック管理と自発的発話
│   ├── git_watcher.py        # Gitコミット監視（クールダウン60秒+バッチ通知）
│   ├── db.py                 # データベース管理（SQLite）
│   └── wsl_path.py           # WSL関連ユーティリティ
├── scripts/                  # 実行スクリプト
│   ├── web.py                # Webインターフェース（startup自動復旧・shutdownハンドラ付き）
│   ├── state.py              # 共有状態（コントローラー・WebSocket・GitWatcher）
│   ├── routes/               # ルートモジュール（avatar/capture/character/overlay/twitch/topic/bgm/db_viewer/stream_control）
│   ├── convert_to_vrm.py     # FBX→VRM変換（Blenderスクリプト）
│   ├── fix_vrm_mtoon.py      # VRM MToonシェーダ修正
│   └── comment_reader.py     # Twitchコメント読み上げ
├── static/                   # Webインターフェース静的ファイル
│   ├── broadcast.html        # 配信合成ページ（overlay+audio+VRMアバター+キャプチャ統合、常時編集モード）
│   └── index.html            # 配信制御UI（キャプチャ管理含む）
├── resources/                # リソース（画像・モデル・音声・動画）
│   ├── images/
│   ├── vrm/                  # VRMモデル
│   ├── audio/
│   └── video/
├── tests/                    # pytestテスト（271テスト）
│   ├── conftest.py           # 共通フィクスチャ（test_db, api_client, mock_gemini）
│   ├── test_db.py            # DB CRUD テスト
│   ├── test_ai_responder.py  # AI応答生成テスト
│   ├── test_api_*.py         # APIエンドポイントテスト
│   └── ...                   # 各モジュールのユニットテスト
├── server.sh                 # Webサーバー起動（再起動ループ+PIDファイル管理+二重起動防止）
├── stream.sh                 # C#ネイティブ配信アプリ起動（.envからSTREAM_KEY読み込み）
├── scenes.json               # 設定ファイル（オーバーレイ・音量・BGM・アバター設定）
├── mkdocs.yml                # MkDocs設定
├── requirements.txt          # Python依存パッケージ
├── .env.example              # 環境変数テンプレート
├── CLAUDE.md                 # このファイル
├── DONE.md                   # 完了タスク
├── TODO.md                   # タスク一覧
├── plans/                    # 作業プラン（詳細な実装計画）
│   └── websocket-optimization.md # サーバ↔配信アプリ WebSocket統合プラン
├── LICENSE
└── README.md
```

※ プロジェクト進行に応じて更新する

## 作業プラン（plans/）

- 詳細な実装計画は `plans/` ディレクトリにMarkdownで保存する
- TODO.mdには1行サマリ + plansへのリンクを書く
- プランファイルには背景・方針・実装ステップ・リスク・ステータスを含める
- 完了したプランは `ステータス: 完了` に更新し、DONE.mdにも記録する

```

## 作業実況（Claude Code → ちょび）

Claude Codeの作業状況を、ちょびが配信で自動実況する仕組み。

### 仕組み
- **Stopフック**: Claude Codeの応答完了時にグローバルフックが自動発火
- `last_assistant_message` を `POST /api/avatar/speak` に送信 → ちょびが要約して発話
- 短い応答（10文字未満）はスキップ
- **他リポジトリ対応**: `CLAUDE_PROJECT_DIR` からプロジェクト名を抽出し、ai-twitch-cast以外なら「作業報告（リポジトリ名）」として報告
- **長時間実行タイマー**: UserPromptSubmitでバックグラウンドタイマー起動、3分以上かかるとtranscript_pathから直近の作業内容を読み取り「○分作業中、直近の作業: ○○」と報告（3分間隔で繰り返し）。Stopで自動停止。transcript未更新2分でアイドル判定→タイマー自動終了

### 疎結合設計
- フックは **`"async": true`** で非ブロッキング実行
- **stdlib only**（プロジェクトモジュールのimportなし）
- サーバー未起動時は静かに失敗（エラー出力なし）
- **無効化**: `~/.claude/settings.json` の該当フックを削除するだけ

### 関連ファイル
- `~/.claude/hooks/notify-stop.py` — Stopフック（作業完了報告 + タイマー停止、グローバル）
- `~/.claude/hooks/notify-prompt.py` — UserPromptSubmitフック（指示受信報告 + タイマー起動、グローバル）
- `~/.claude/hooks/long-execution-timer.py` — 長時間実行タイマー（バックグラウンド、transcript解析）
- `~/.claude/settings.json` — グローバルフック設定

## WSL2環境について

- **開発はWSL2上で行い、配信はWindows側C#ネイティブアプリが担当する**
- WebサーバーはWSL2内で起動（API/TTS/AI生成のバックエンド）
- C#ネイティブアプリがbroadcast.htmlをWebView2でレンダリングし、FFmpegでTwitchに直接配信
- Webサーバーのポートは環境変数 `WEB_PORT` で設定（デフォルト: 8080）

## Webサーバー運用注意

- Webサーバーは `./server.sh` で起動（`.env` の `WEB_PORT` を自動読み込み、デフォルト8080）
- **二重起動防止**: `server.sh` は起動時に既存プロセスをPIDファイル＋ポート使用チェックで自動停止する
- **`--reload` は使わない**。コード変更はコミット時に自動反映される（post-commit hookがサーバーを再起動）
- コミット時の動作: post-commit hook → `.pending_commit` にコミット情報保存 → サーバーkill → server.shが自動再起動 → startup復旧（アバター・Reader・Git監視） → コミット読み上げ
- **Setup済みの状態は `.server_state` ファイルで管理**。このファイルが存在する場合、サーバー起動時に自動復旧する

## 音声アーキテクチャ

- **broadcast.html** が音声再生を統合管理（WebSocket `/ws/broadcast` で全イベント受信）
- **音量制御**: broadcast.html内のJavaScriptで `master × tts` / `master × bgm × 曲音量` を計算
- **保存先**: マスター・TTS・BGM音量 → SQLite DB（`volume.*`キー）、デフォルト → `scenes.json` の `audio_volumes`、曲別音量 → SQLite DB

## テスト

### 実行方法
```bash
python3 -m pytest tests/ -q          # 全テスト実行
python3 -m pytest tests/test_db.py   # 特定ファイルのみ
```

### テスト構成（`tests/`）
| ファイル | 対象 | 備考 |
|---------|------|------|
| `conftest.py` | 共通フィクスチャ | `test_db`(インメモリSQLite), `api_client`(FastAPI TestClient), `mock_gemini`, `mock_env` |
| `test_db.py` | `src/db.py` | テーブル作成・全CRUD関数のテスト |
| `test_ai_responder.py` | `src/ai_responder.py` | キャラクター管理・AI応答生成・ユーザーメモ |
| `test_prompt_builder.py` | `src/prompt_builder.py` | 言語モード・システムプロンプト構築 |
| `test_speech_pipeline.py` | `src/speech_pipeline.py` | TTS・リップシンク・オーバーレイ・感情連動 |
| `test_tts.py` | `src/tts.py` | 言語タグ変換・TTSスタイル |
| `test_topic_talker.py` | `src/topic_talker.py` | トピック管理・自発的発話 |
| `test_git_watcher.py` | `src/git_watcher.py` | コミット検出・ライフサイクル・バッチ通知 |
| `test_scene_config.py` | `src/scene_config.py` | 設定読み書き |
| `test_wsl_path.py` | `src/wsl_path.py` | WSLパス変換・IP取得 |
| `test_overlay.py` | `scripts/routes/overlay.py` | TODOパース・ブロードキャスト |
| `test_capture_client.py` | `src/capture_client.py` | URL生成・WS通信・プロキシ |
| `test_lipsync.py` | リップシンク | 振幅解析 |
| `test_native_app_patterns.py` | C#ソースコード | 危険パターンの再発防止（ソース解析のみ） |
| `test_api_character.py` | キャラクターAPI | CRUD・言語モード |
| `test_api_stream.py` | 配信制御API | シーン・音量・アバター |
| `test_api_topic.py` | トピックAPI | CRUD・スクリプト・一時停止 |

### テスト規約
- **新しいDB関数を追加したら `test_db.py` にテストを追加すること**
- **新しいAPIエンドポイントを追加したら対応する `test_api_*.py` にテストを追加すること**
- フィクスチャ `test_db` はインメモリSQLiteを使用（本番DBに影響しない）
- フィクスチャ `api_client` は全外部依存（Gemini/Twitch/WebSocket）をモック化
- 外部モジュール（twitchio, aiohttp）は `conftest.py` でスタブ化済み

## 機能変更時の必須チェック（リグレッション防止）

**コードを変更したら、以下を必ず確認すること。**

### 1. テスト実行
```bash
python3 -m pytest tests/ -q          # 全テスト通ることを確認
```

### 2. サーバー起動確認
```bash
curl -s http://localhost:$WEB_PORT/api/status  # サーバーが応答するか
curl -s http://localhost:$WEB_PORT/api/todo    # TODOが返るか
```

### 3. 壊れやすいポイント（要注意）
- **broadcast.html**: CSS/JSの変更でTODOパネルの表示が消えることがある
- **uvicorn再起動**: `--port` を `WEB_PORT` と一致させること

### チェック対象の全機能一覧
| 機能 | 確認方法 |
|------|----------|
| TODO表示 | 配信画面にTODOリストが表示される |
| 情報パネル | 左上にACTIVITYパネルが表示される（汎用ログ） |
| 字幕表示 | コメント応答時に下部に字幕が出る |
| TTS音声 | コメント応答時にbroadcast.html経由で音声が再生される |
| アバター表示 | 配信画面にアバターが表示される |
| ウィンドウキャプチャ | 配信アプリ起動→ウィンドウ選択→broadcast.htmlにMJPEGストリーム表示 |
| レイアウト編集 | `/broadcast` でドラッグ＆リサイズ→保存→配信画面に反映（常時編集可能） |
| WebSocket接続 | broadcast.htmlがWebSocketで接続している |
| Go Live | Go Liveボタンで配信開始、トースト通知が出る |

## メモリ（実装記録）

- 実装した機能は `.claude/projects/-home-ubuntu-ai-twitch-cast/memory/` に記録する
- **機能を追加・変更・削除したら、必ず対応するメモリファイルも更新すること**
- メモリファイルの一覧:
  - `MEMORY.md` - インデックス・主要パターン・ユーザー設定
  - `overlay.md` - オーバーレイのパネル構成・WebSocketイベント・音声再生
  - `avatar.md` - アバター制御・idle animation・耳ぴくぴく・感情BlendShape
  - `tts-audio.md` - TTS設定・音声再生フロー
  - `api-endpoints.md` - 全APIエンドポイント一覧
  - `scene-config.md` - scenes.json構造
- セッションをまたいでも実装が消えないよう、これらのメモリを参照してから作業すること
- 新しいファイルや機能を作る前に、既に実装済みでないかメモリを確認すること
