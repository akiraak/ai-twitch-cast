# AI Twitch Cast

AIを活用し、プログラムで全自動Twitch配信を行うプロジェクト。

## プロジェクト概要

Twitch API連携、画像生成・収集、テキスト生成、音声合成など、配信に必要な要素をすべてプログラムで生成・制御する。独自の配信パイプライン（xvfb + Chromium + FFmpeg）により、OBSなしで完結する。

## 主な機能

- **独自配信パイプライン** - xvfb + Chromium + PulseAudio + FFmpegでOBS不要の配信
- **AIアバター** - VRM/Live2Dアバターが感情連動で表情変化、TTS音声で発話
- **Twitchコメント応答** - チャットをAIが読み取り、キャラクター設定に基づいて応答・読み上げ
- **配信オーバーレイ** - TODO表示・字幕・情報パネルを配信画面に合成
- **Git監視** - コミット検知時にアバターがコミット内容について発話
- **Web UI** - アバター・オーバーレイ・キャラクター設定・配信制御をGUIで操作
- **Twitch配信管理** - タイトル・カテゴリ・タグをWeb UIから変更

## セットアップ

### 前提条件

- Python 3.10以上
- WSL2環境（Ubuntu）
- xvfb, Chromium, PulseAudio, FFmpeg

### インストール

```bash
pip install -r requirements.txt
```

### 環境変数の設定

```bash
cp .env.example .env
```

`.env` を編集して接続情報を設定:

```
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
./run.sh
```

ブラウザで http://127.0.0.1:8080 にアクセス。ポートは `.env` の `WEB_PORT` で変更可能（デフォルト: 8080）。

- **Setup** - 配信準備・アバター接続・コメント読み上げ開始・Git監視開始
- **配信開始/停止** - Twitchへの配信制御
- **オーバーレイ設定** - 字幕・履歴・TODOパネルの位置/サイズ/フォント調整
- **キャラクター設定** - AIの性格・ルール・感情・表情マッピング編集

### 対話式コンソール

```bash
python scripts/console.py
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

- [アバター表示・アニメーション調査](https://akiraak.github.io/ai-twitch-cast/avatar-research/)
