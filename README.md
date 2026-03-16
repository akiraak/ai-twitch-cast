# AI Twitch Cast

AIを活用し、プログラムで全自動Twitch配信を行うプロジェクト。

## プロジェクト概要

Twitch API連携、画像生成・収集、テキスト生成、音声合成など、配信に必要な要素をすべてプログラムで生成・制御する。C#ネイティブアプリ（Windows）でbroadcast.htmlをWebView2でレンダリングし、FFmpegでTwitchに直接配信する。

## 主な機能

- **C#ネイティブ配信アプリ** - Windows側C#アプリでbroadcast.htmlをWebView2でレンダリング→FFmpegでTwitch直接配信（OBS/xvfb不要）
- **AIアバター** - VRMアバターが感情連動で表情変化、TTS音声で発話
- **Twitchコメント応答** - チャットをAIが読み取り、キャラクター設定に基づいて応答・読み上げ
- **配信オーバーレイ** - TODO表示・字幕・情報パネルを配信画面に合成
- **ウィンドウキャプチャ** - Windows側のウィンドウ（VSCode等）をキャプチャし配信画面に表示
- **レイアウト編集** - 配信画面の各要素をマウスでドラッグ＆リサイズして配置調整
- **Git監視** - コミット検知時にアバターがコミット内容について発話
- **Web UI** - アバター・オーバーレイ・キャラクター設定・配信制御をGUIで操作
- **Twitch配信管理** - タイトル・カテゴリ・タグをWeb UIから変更

## セットアップ

### 前提条件

- Python 3.10以上
- WSL2環境（Ubuntu）

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
./server.sh
```

ブラウザで http://127.0.0.1:8080 にアクセス。ポートは `.env` の `WEB_PORT` で変更可能（デフォルト: 8080）。

- **Go Live** - Twitch配信開始（コメント読み上げ・Git監視も自動開始）
- **配信停止** - 配信を停止
- **オーバーレイ設定** - 字幕・履歴・TODOパネルの位置/サイズ/フォント調整
- **ウィンドウキャプチャ** - Windows側ウィンドウのキャプチャ開始/停止
- **レイアウト編集** - `/broadcast?edit` で配信画面の要素をドラッグ＆リサイズ
- **キャラクター設定** - AIの性格・ルール・感情・表情マッピング編集

### 配信アプリ（Windows側配信+キャプチャ）

`stream.sh` でC#ネイティブ配信アプリを起動。Go Liveボタンからも自動起動される。詳細は [docs/window-capture.md](docs/window-capture.md) を参照。

## ドキュメント

GitHub Pagesで公開: https://akiraak.github.io/ai-twitch-cast/

ローカルで表示:

```bash
mkdocs serve -a localhost:8001
```

- [アバター表示調査](https://akiraak.github.io/ai-twitch-cast/avatar-research/)
- [ウィンドウキャプチャシステム](docs/window-capture.md)
