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
- VTube Studio（アバター表示時）

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

VTS_HOST=wsl
VTS_PORT=8001
VTS_MODELS_DIR=C:\Program Files (x86)\Steam\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels
```

## 使い方

### 対話式コンソール（推奨）

```bash
python scripts/console.py
```

OBS・VTube Studioの操作を対話的に実行できます。

```
> obs connect                  # OBSに接続
> vts connect                  # VTube Studioに接続
> obs setup                    # シーン・ソースを一括作成
> obs scene メイン              # シーン切り替え
> vts demo                     # アバターデモ動作
> stream start                 # 配信開始
> stream stop                  # 配信停止
> obs teardown                 # シーン・ソースを一括削除
> help                         # 全コマンド表示
```

コマンド一覧は [docs/console-commands.md](docs/console-commands.md) を参照。

### 個別スクリプト

```bash
python scripts/start_stream.py       # 配信開始
python scripts/stop_stream.py        # 配信停止
python scripts/deploy_model.py       # Live2DモデルをVTSにデプロイ
python scripts/deploy_model.py --clean  # デプロイしたモデルを削除
```

### Pythonコードから使う

```python
from src.obs_controller import OBSController

with OBSController() as obs:
    obs.start_stream()   # 配信開始
    obs.stop_stream()    # 配信停止
```

```python
import asyncio
from src.vts_controller import VTSController

async def main():
    async with VTSController() as vts:
        await vts.set_parameter("MouthOpen", 1.0)  # 口を開く
        await vts.trigger_hotkey("hotkey_id")       # 表情切替

asyncio.run(main())
```

### Web UI

```bash
uvicorn scripts.web:app --reload
```

ブラウザで http://127.0.0.1:8000 にアクセス。OBS・アバター操作やキャラクター設定をGUIで行えます。

### ドキュメントサーバ（ローカル）

```bash
mkdocs serve
```

http://127.0.0.1:8000 でドキュメントをプレビューできます。Web UIと同時に使う場合はポートを変更してください:

```bash
mkdocs serve -a 127.0.0.1:8001
```

## ドキュメント

GitHub Pagesで公開: https://akiraak.github.io/ai-twitch-cast/

- [OBS自動制御でできること](https://akiraak.github.io/ai-twitch-cast/obs-automation-guide/)
- [OBS Studio 機能調査](https://akiraak.github.io/ai-twitch-cast/obs-research/)
- [アバター表示・アニメーション調査](https://akiraak.github.io/ai-twitch-cast/avatar-research/)
