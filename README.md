# AI Twitch Cast

AIを活用し、プログラムで全自動Twitch配信を行うプロジェクト。

## プロジェクト概要

OBS制御、Twitch API連携、画像生成・収集、テキスト生成、音声合成など、配信に必要な要素をすべてプログラムで生成・制御する。

## 主な機能

- **OBS自動制御** - WebSocket経由でシーン切替・ソース操作・配信開始/停止
- **AIアバター** - VRM/Live2Dアバターが感情連動で表情変化、TTS音声で発話
- **Twitchコメント応答** - チャットをAIが読み取り、キャラクター設定に基づいて応答・読み上げ
- **TODOオーバーレイ** - TODO.mdの内容を配信画面に表示（位置・サイズをWeb UIから設定可能）
- **Git監視** - コミット検知時にアバターがコミット内容について発話
- **Web UI** - OBS・アバター・オーバーレイ・キャラクター設定をGUIで操作
- **Twitch配信管理** - タイトル・カテゴリ・タグをWeb UIから変更

## セットアップ

### 前提条件

- Python 3.10以上
- OBS Studio 28.0以上（obs-websocket同梱）
- VSeeFace（VRMアバター）またはVTube Studio（Live2Dアバター）

### インストール

```bash
pip install -r requirements.txt
```

### OBS側の設定

1. OBS Studioを起動
2. **ツール** → **obs-websocket設定** を開く
3. **WebSocketサーバーを有効にする** にチェック
4. サーバーパスワードを設定（または確認）
5. ポート番号を確認（デフォルト: 4455）

### 環境変数の設定

```bash
cp .env.example .env
```

`.env` を編集して接続情報を設定:

```
# WSL2の場合は "wsl" でWindows側IPを自動取得
OBS_WS_HOST=wsl
OBS_WS_PORT=4455
OBS_WS_PASSWORD=your_password_here

# アバター (vsf or vts)
AVATAR_APP=vsf
VSF_OSC_HOST=wsl
VSF_OSC_PORT=39539

# Twitch
TWITCH_TOKEN=oauth:xxx
TWITCH_CLIENT_ID=xxx
TWITCH_CHANNEL=your_channel

# AI / TTS
GEMINI_API_KEY=xxx
TTS_VOICE=Aoede
```

## 使い方

### Web UI（推奨）

```bash
uvicorn scripts.web:app --reload --host 0.0.0.0 --port 8080
```

ブラウザで http://127.0.0.1:8080 にアクセス。ポートは環境変数 `WEB_PORT` で変更可能（デフォルト: 8080）。

- **Setup** - OBS接続・シーン構築・アバター接続・コメント読み上げ開始・Git監視開始
- **配信開始/停止** - Twitchへの配信制御
- **オーバーレイ設定** - 字幕・履歴・TODOパネルの位置/サイズ/フォント調整
- **キャラクター設定** - AIの性格・ルール・感情・表情マッピング編集

### 対話式コンソール

```bash
python scripts/console.py
```

OBS・VTube Studioの操作を対話的に実行できます。

```
> obs connect                  # OBSに接続
> obs setup                    # シーン・ソースを一括作成
> obs scene メイン              # シーン切り替え
> stream start                 # 配信開始
> stream stop                  # 配信停止
> help                         # 全コマンド表示
```

コマンド一覧は [docs/console-commands.md](docs/console-commands.md) を参照。

### 個別スクリプト

```bash
python scripts/start_stream.py       # 配信開始
python scripts/stop_stream.py        # 配信停止
python scripts/deploy_model.py       # Live2DモデルをVTSにデプロイ
```

## ドキュメント

GitHub Pagesで公開: https://akiraak.github.io/ai-twitch-cast/

ローカルで表示:

```bash
mkdocs serve -a localhost:8001
```

- [OBS自動制御でできること](https://akiraak.github.io/ai-twitch-cast/obs-automation-guide/)
- [OBS Studio 機能調査](https://akiraak.github.io/ai-twitch-cast/obs-research/)
- [アバター表示・アニメーション調査](https://akiraak.github.io/ai-twitch-cast/avatar-research/)
