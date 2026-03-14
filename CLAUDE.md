# AI Twitch Cast

AIを活用し、プログラムで全自動Twitch配信を行うプロジェクト。

## プロジェクト概要

Electron配信パイプライン（Windows側でbroadcast.htmlをオフスクリーンレンダリング→FFmpegでTwitch直接配信）、Twitch API連携、画像生成・収集、テキスト生成、音声合成など、配信に必要な要素をすべてプログラムで生成・制御する。

## 主要コンポーネント

- **Electron配信パイプライン** - Windows側Electronアプリ（`win-capture-app/`）でbroadcast.htmlをオフスクリーンレンダリング→FFmpegでTwitch直接配信（OBS/xvfb不要）
- **ウィンドウキャプチャ** - 同Electronアプリでウィンドウをキャプチャ→MJPEGストリーム配信→broadcast.htmlで表示
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
├── win-capture-app/          # Windows側Electronキャプチャ＋配信アプリ（現行）
│   ├── main.js              # メインプロセス（HTTPサーバー+キャプチャ管理+FFmpeg配信）
│   ├── preload.js           # IPC bridge
│   ├── capture.html         # 非表示レンダラーページ
│   ├── capture-renderer.js  # レンダラー（getUserMedia+canvas+JPEG書き出し）
│   ├── package.json         # Electron+electron-builder設定
│   └── build.sh             # ビルドスクリプト
├── win-native-app/           # C#ネイティブ配信アプリ（Electron後継、開発中）→ symlink to Windows FS
│   └── WinNativeApp/        # .NET 8 WinForms + WebView2 + WGC
│       ├── Program.cs       # エントリポイント
│       ├── MainForm.cs      # WebView2フォーム（オフスクリーン）+ 配信パイプライン制御
│       ├── Capture/         # WGCフレームキャプチャ
│       └── Streaming/       # FFmpeg配信パイプライン（FfmpegProcess + AudioLoopback + StreamConfig）
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
│   ├── electron-streaming.md  # Electron配信移行プラン
│   └── websocket-optimization.md # サーバ↔Electron WebSocket統合プラン
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

## WSL2環境について

- **開発はWSL2上で行い、配信はWindows側Electronアプリが担当する**
- WebサーバーはWSL2内で起動（API/TTS/AI生成のバックエンド）
- Electronアプリがbroadcast.htmlをオフスクリーンレンダリングし、FFmpegでTwitchに直接配信
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
| レイアウト編集 | `/broadcast` でドラッグ＆リサイズ→保存→配信画面に反映（常時編集可能） |
| WebSocket接続 | broadcast.htmlがWebSocketで接続している |
| Go Live | Go Liveボタンで配信開始（Electron経由）、トースト通知が出る |

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
