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

## セットアップ

### 前提条件

- Python 3.10以上
- OBS Studio 28.0以上（obs-websocket同梱）

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

`.env` を編集してOBS WebSocketの接続情報を設定:

```
OBS_WS_HOST=localhost
OBS_WS_PORT=4455
OBS_WS_PASSWORD=your_password_here
```

## 使い方

### 配信開始

```bash
python scripts/start_stream.py
```

### 配信停止

```bash
python scripts/stop_stream.py
```

### Pythonコードから使う

```python
from src.obs_controller import OBSController

with OBSController() as obs:
    obs.start_stream()   # 配信開始
    obs.stop_stream()    # 配信停止

    status = obs.get_stream_status()  # 配信状態の確認
    print(status["active"])  # True/False
```

## ドキュメント

GitHub Pagesで公開: https://akiraak.github.io/ai-twitch-cast/

- [OBS自動制御でできること](https://akiraak.github.io/ai-twitch-cast/obs-automation-guide/)
- [OBS Studio 機能調査](https://akiraak.github.io/ai-twitch-cast/obs-research/)
