# AI Twitch Cast

AIを活用し、プログラムで全自動Twitch配信を行うプロジェクト。

## プロジェクト概要

OBS制御、Twitch API連携、画像生成・収集、テキスト生成、音声合成など、配信に必要な要素をすべてプログラムで生成・制御する。

## 主要コンポーネント（予定）

- **OBS制御** - OBS WebSocket経由でシーン切替・ソース操作を自動化
- **Twitch API** - チャット読み取り・配信管理・視聴者インタラクション
- **画像生成/収集** - AI画像生成やWebからの素材収集
- **テキスト生成** - LLMによる台本・コメント・ナレーション生成
- **音声合成** - TTS（Text-to-Speech）によるナレーション音声生成

## 開発ルール

- 言語: Python
- コミットメッセージ: 日本語可
- コード内コメント: 日本語可
- ドキュメント: 日本語
- コミット前にTODO.mdとDONE.mdを更新する
- **TODO.mdに完了タスク（`[x]`）を残さないこと。完了したら即座にDONE.mdに移動する**
- TODO.mdには未完了タスク（`[ ]`）と作業中タスク（`[>]`）のみを置く
- **ファイルの所有者に注意**: uvicornは`ubuntu`ユーザーで動作する。Claude Codeは`root`で実行されるため、作成・編集したファイルが`root:root`になる。TODO.mdなどWebサーバーから書き込むファイルが`root`所有だと500エラーになる。ファイルを作成・編集した後は `chown ubuntu:ubuntu <file>` で所有者を修正すること

## リソース管理

- リソース（画像・Live2Dモデル・音声・動画）は `resources/` 配下で一元管理
- OBSからはWSLパス（`\\wsl.localhost\`）経由で参照
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
│   ├── obs-automation-guide.md  # OBS自動制御ガイド
│   ├── obs-research.md       # OBS機能調査レポート
│   ├── avatar-research.md   # アバター表示・アニメーション調査
│   ├── 3d-model-research.md # 3Dモデル調査
│   └── vrm-conversion-log.md # VRM変換作業ログ
├── src/                      # ソースコード
│   ├── obs_controller.py     # OBS WebSocket制御
│   ├── vts_controller.py     # VTube Studio API制御（Live2D）
│   ├── vsf_controller.py     # VSeeFace VMC Protocol制御（VRM）
│   ├── scene_config.py       # シーン構成の定義（scenes.jsonから読み込み）
│   ├── tts.py                # TTS音声合成（Gemini 2.5 Flash TTS）
│   ├── twitch_chat.py        # Twitchチャット受信
│   ├── ai_responder.py       # AI応答生成（DB管理のキャラクター設定ベース）
│   ├── comment_reader.py     # コメント読み上げサービス
│   ├── git_watcher.py        # Gitコミット監視
│   ├── db.py                 # データベース管理（SQLite）
│   └── wsl_path.py           # WSL関連ユーティリティ
├── scripts/                  # 実行スクリプト
│   ├── start_stream.py       # 配信開始
│   ├── stop_stream.py        # 配信停止
│   ├── console.py            # 対話式コンソール
│   ├── web.py                # Webインターフェース
│   ├── deploy_model.py       # Live2Dモデルデプロイ
│   ├── convert_to_vrm.py     # FBX→VRM変換（Blenderスクリプト）
│   ├── fix_vrm_mtoon.py      # VRM MToonシェーダ修正
│   └── comment_reader.py     # Twitchコメント読み上げ
├── static/                   # Webインターフェース静的ファイル
│   └── index.html
├── resources/                # リソース（画像・モデル・音声・動画）
│   ├── images/
│   ├── live2d/
│   ├── vrm/                  # VRMモデル
│   ├── audio/
│   └── video/
├── run.sh                    # サーバー起動スクリプト（.envのWEB_PORT自動読み込み）
├── scenes.json               # シーン構成設定（シーン・ソース・アバター配置）
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

- **開発はWSL2上で行い、OBS・VTube Studio・VSeeFaceはWindows上で動作する**
- WebサーバーはWSL2内で起動するが、OBSのブラウザソースはWindows側からアクセスする
- そのため、ブラウザソースのURLは `localhost` ではなくWSL2のIPアドレスを使う必要がある
- **`scenes.json` にはURLのパス部分のみ記載**（例: `"url": "overlay"`）。`scene_config.py` の `_resolve_browser_url()` がWSL2 IPとポートを自動付与する
- **コード内で `localhost` を定数として使わないこと**。WSL2環境では `get_wsl_ip()` / `resolve_host()` を使って動的に解決する
- **WSL2のIPアドレスは再起動のたびに変わる可能性がある**。OBS再起動後にブラウザソースが表示されない場合は、Setupを再実行してURLを更新すること
- OBS WebSocketもWindows上のOBSに接続するため、`OBS_WS_HOST` にWindowsのIPを設定する（`wsl_path.py` の `resolve_host()` で解決）
- Webサーバーのポートは環境変数 `WEB_PORT` で設定（デフォルト: 8080）。`scene_config.py` と `web.py` が同じ値を参照する

## Webサーバー運用注意

- Webサーバーは `./run.sh` で起動（`.env` の `WEB_PORT` を自動読み込み、デフォルト8080）
- **Pydanticモデルやルートの変更後は `--reload` では反映されないことがある。その場合はuvicornプロセスを手動で再起動すること**
- OBSのブラウザソースはHTMLをキャッシュするため、overlay.html等を変更した場合はSetupボタン押下またはOBS側でブラウザソースの「キャッシュを無視してページをリフレッシュ」が必要

## 機能変更時の必須チェック（リグレッション防止）

**コードを変更したら、以下を必ず確認すること。過去に何度もオーバーレイが壊れている。**

### 1. サーバー起動確認
```bash
curl -s http://localhost:$WEB_PORT/api/status  # サーバーが応答するか
curl -s http://localhost:$WEB_PORT/api/todo    # TODOが返るか
curl -s http://localhost:$WEB_PORT/overlay | grep todo-panel  # overlay HTMLが正常か
```

### 2. scene_config確認（特にURL周り）
```bash
python -c "from src.scene_config import SCENES; import json; print(json.dumps(SCENES, indent=2, default=str))"
```
- ブラウザソースのURLが `http://<WSL2 IP>:<WEB_PORT>/overlay` になっているか（`localhost` は不可）
- `[ATC]` プレフィックスが全ソースに付いているか

### 3. OBS Setup後の確認（OBS接続時）
```bash
curl -s http://localhost:$WEB_PORT/api/obs/diag | python -m json.tool
```
- `overlay_source.url` がWSL2のIPを使っているか
- `overlay_url_reachable.status` が200か
- `overlay_url_reachable.has_todo_panel` がtrueか
- `all_sources` に `[ATC] オーバーレイ` が存在し `enabled: true` か

### 4. 壊れやすいポイント（要注意）
- **overlay.html**: CSS/JSの変更でTODOパネルの表示が消えることがある
- **scenes.json**: URLに `localhost` を書かないこと（`_resolve_browser_url` が自動解決する）
- **scene_config.py**: ソース解決ロジックの変更でブラウザソースが生成されなくなることがある
- **uvicorn再起動**: `--port` を `WEB_PORT` と一致させること（不一致だとブラウザソースからアクセス不能）
- **OBSブラウザソースのキャッシュ**: overlay.htmlを変更したらSetup再実行またはOBSでキャッシュクリア必須

### チェック対象の全機能一覧
| 機能 | 確認方法 |
|------|----------|
| TODO表示 | OBS画面にTODOリストが表示される |
| ステータス表示 | 左上に「NOW WORKING」パネルが表示される |
| 字幕表示 | コメント応答時に下部に字幕が出る |
| TTS音声 | コメント応答時に音声が再生される |
| アバター表示 | OBS画面にアバターが表示される |
| ターミナル表示 | OBS画面にターミナルが表示される |
| WebSocket接続 | overlay.htmlがWebSocketで接続している（ブラウザDevToolsで確認） |
| Web UI Setup | Setupボタンでトースト通知が出る（成功=緑、エラー=赤） |

## メモリ（実装記録）

- 実装した機能は `.claude/projects/-home-ubuntu-ai-twitch-cast/memory/` に記録する
- **機能を追加・変更・削除したら、必ず対応するメモリファイルも更新すること**
- メモリファイルの一覧:
  - `MEMORY.md` - インデックス・主要パターン・ユーザー設定
  - `overlay.md` - オーバーレイのパネル構成・WebSocketイベント・音声再生
  - `obs.md` - OBS制御・自動再接続・ブラウザソース音声設定
  - `avatar.md` - アバター制御・idle animation・耳ぴくぴく・感情BlendShape
  - `tts-audio.md` - TTS設定・ブラウザソース経由の音声再生フロー
  - `api-endpoints.md` - 全APIエンドポイント一覧
  - `scene-config.md` - scenes.json構造・PREFIX・パス変換
- セッションをまたいでも実装が消えないよう、これらのメモリを参照してから作業すること
- 新しいファイルや機能を作る前に、既に実装済みでないかメモリを確認すること
