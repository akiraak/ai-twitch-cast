# AI Twitch Cast

AIを活用し、プログラムで全自動Twitch配信を行うプロジェクト。

## プロジェクト概要

独自配信パイプライン（xvfb + Chromium + FFmpeg）、Twitch API連携、画像生成・収集、テキスト生成、音声合成など、配信に必要な要素をすべてプログラムで生成・制御する。

## 主要コンポーネント

- **独自配信パイプライン** - xvfb + Chromium + PulseAudio + FFmpegによる配信
- **ウィンドウキャプチャ** - Windows側Electronアプリ（`win-capture-app/`）でウィンドウをキャプチャ→MJPEGストリーム配信→broadcast.htmlで表示
- **Twitch API** - チャット読み取り・配信管理・視聴者インタラクション
- **テキスト生成** - LLMによる台本・コメント・ナレーション生成
- **音声合成** - TTS（Text-to-Speech）によるナレーション音声生成
- **レイアウト編集** - `/broadcast?edit` でドラッグ＆リサイズによる配信画面レイアウト調整

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
- **ファイルの所有者**: Claude Code（root）が編集したファイルは PostToolUse フックで自動的に `ubuntu:ubuntu` に修正される（`.claude/hooks/fix-permissions.sh`）

## リソース管理

- リソース（画像・Live2Dモデル・音声・動画）は `resources/` 配下で一元管理
- VTube Studioにはデプロイスクリプトでコピー/クリーンアップ
- 詳細は [docs/resource-management.md](docs/resource-management.md) を参照

## 対話式コンソール

`python scripts/console.py` で起動。コマンド詳細は [docs/console-commands.md](docs/console-commands.md) を参照。

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
│   ├── avatar-research.md   # アバター表示・アニメーション調査
│   ├── 3d-model-research.md # 3Dモデル調査
│   ├── vrm-conversion-log.md # VRM変換作業ログ
│   ├── obs-free-streaming.md # 配信パイプラインガイド
│   └── window-capture.md   # ウィンドウキャプチャシステム設計
├── win-capture-app/          # Windows側Electronキャプチャアプリ
│   ├── main.js              # メインプロセス（HTTPサーバー+キャプチャ管理）
│   ├── preload.js           # IPC bridge
│   ├── capture.html         # 非表示レンダラーページ
│   ├── capture-renderer.js  # レンダラー（getUserMedia+canvas+JPEG書き出し）
│   ├── package.json         # Electron+electron-builder設定
│   └── build.sh             # ビルドスクリプト
├── src/                      # ソースコード
│   ├── stream_controller.py  # 配信プロセス管理（xvfb/Chromium/PulseAudio/FFmpeg）
│   ├── vts_controller.py     # VTube Studio API制御（Live2D）
│   ├── vsf_controller.py     # VSeeFace VMC Protocol制御（VRM）
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
│   ├── console.py            # 対話式コンソール（アバター制御）
│   ├── web.py                # Webインターフェース（startup自動復旧・shutdownハンドラ付き）
│   ├── state.py              # 共有状態（コントローラー・WebSocket・GitWatcher・StreamController）
│   ├── routes/               # ルートモジュール（avatar/capture/character/overlay/twitch/topic/bgm/db_viewer/stream_control）
│   ├── deploy_model.py       # Live2Dモデルデプロイ
│   ├── convert_to_vrm.py     # FBX→VRM変換（Blenderスクリプト）
│   ├── fix_vrm_mtoon.py      # VRM MToonシェーダ修正
│   ├── avatar_capture.py     # Windows側VSeeFaceキャプチャ（MJPEGストリーム、非推奨）
│   └── comment_reader.py     # Twitchコメント読み上げ
├── static/                   # Webインターフェース静的ファイル
│   ├── broadcast.html        # 配信合成ページ（overlay+audio+VRMアバター+キャプチャ統合、?editで編集モード）
│   └── index.html            # 配信制御UI（キャプチャ管理含む）
├── resources/                # リソース（画像・モデル・音声・動画）
│   ├── images/
│   ├── live2d/
│   ├── vrm/                  # VRMモデル
│   ├── audio/
│   └── video/
├── run.sh                    # サーバー起動スクリプト（再起動ループ+PIDファイル管理+二重起動防止）
├── scenes.json               # 設定ファイル（オーバーレイ・音量・BGM・アバター設定）
├── mkdocs.yml                # MkDocs設定
├── requirements.txt          # Python依存パッケージ
├── .env.example              # 環境変数テンプレート
├── CLAUDE.md                 # このファイル
├── DONE.md                   # 完了タスク
├── TODO.md                   # タスク一覧
├── LICENSE
└── README.md
```

※ プロジェクト進行に応じて更新する

## WSL2環境について

- **開発はWSL2上で行い、VTube Studio・VSeeFaceはWindows上で動作する**
- WebサーバーはWSL2内で起動し、broadcast.htmlはxvfb内のChromiumで表示する
- Webサーバーのポートは環境変数 `WEB_PORT` で設定（デフォルト: 8080）

## Webサーバー運用注意

- Webサーバーは `./run.sh` で起動（`.env` の `WEB_PORT` を自動読み込み、デフォルト8080）
- **二重起動防止**: `run.sh` は起動時に既存プロセスをPIDファイル＋ポート使用チェックで自動停止する
- **`--reload` は使わない**。コード変更はコミット時に自動反映される（post-commit hookがサーバーを再起動）
- コミット時の動作: post-commit hook → `.pending_commit` にコミット情報保存 → サーバーkill → run.shが自動再起動 → startup復旧（アバター・Reader・Git監視） → コミット読み上げ
- **Setup済みの状態は `.server_state` ファイルで管理**。このファイルが存在する場合、サーバー起動時に自動復旧する

## 音声アーキテクチャ

- **broadcast.html** が音声再生を統合管理（WebSocket `/ws/broadcast` で全イベント受信）
- **音量制御**: broadcast.html内のJavaScriptで `master × tts` / `master × bgm × 曲音量` を計算
- **保存先**: マスター・TTS・BGM音量 → SQLite DB（`volume.*`キー）、デフォルト → `scenes.json` の `audio_volumes`、曲別音量 → SQLite DB

## 機能変更時の必須チェック（リグレッション防止）

**コードを変更したら、以下を必ず確認すること。**

### 1. サーバー起動確認
```bash
curl -s http://localhost:$WEB_PORT/api/status  # サーバーが応答するか
curl -s http://localhost:$WEB_PORT/api/todo    # TODOが返るか
```

### 2. 壊れやすいポイント（要注意）
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
| ウィンドウキャプチャ | Electronアプリ起動→ウィンドウ選択→broadcast.htmlにMJPEGストリーム表示 |
| レイアウト編集 | `/broadcast?edit` でドラッグ＆リサイズ→保存→配信画面に反映 |
| WebSocket接続 | broadcast.htmlがWebSocketで接続している |
| Web UI Setup | Setupボタンでトースト通知が出る（成功=緑、エラー=赤） |

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
