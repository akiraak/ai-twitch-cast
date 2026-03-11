# OBS不要配信ガイド

OBSなしでWSL2上のみで完結するTwitch配信システム。

## アーキテクチャ

```
broadcast.html（VRMアバター + 字幕 + TODO + TTS + BGM）
       ↓  WebSocket
Chromium（xvfb仮想ディスプレイ :99 上で全画面描画）
       ↓
FFmpeg（x11grab映像 + PulseAudio音声 → RTMP）
       ↓
Twitch
```

## 必要パッケージ

```bash
sudo apt install xvfb pulseaudio chromium-browser ffmpeg
```

## 使い方

### 1. Webサーバー起動

```bash
./run.sh
```

### 2. 配信制御UIを開く

```
http://localhost:8080/broadcast-ui
```

### 3. 配信操作

| ボタン | 説明 |
|--------|------|
| **Setup** | xvfb + Chromium + PulseAudio を起動 |
| **Start** | FFmpegでRTMP配信開始 + コメント読み上げ + Git監視 開始 |
| **Scene切替** | main / start / end シーンの切替 |
| **Volume** | master / TTS / BGM の音量調整 |
| **Stop** | 配信停止 |
| **Teardown** | 全プロセス停止 |

### 4. 配信プレビュー

```
http://localhost:8080/broadcast
```

ブラウザで直接開くと、実際の配信画面（1920x1080）を確認できる。

## ファイル構成

| ファイル | 役割 |
|----------|------|
| `static/broadcast.html` | 配信合成ページ（overlay + audio + VRMアバター統合） |
| `static/broadcast-ui.html` | 配信制御Web UI |
| `src/stream_controller.py` | xvfb/Chromium/PulseAudio/FFmpegプロセス管理 |
| `scripts/routes/stream_control.py` | 配信制御APIルート |

## VRMアバター

broadcast.html内でThree.js + three-vrmを使い、ブラウザ上でVRMモデルを直接レンダリングする。VSeeFaceやWindowsアプリは不要。

- **モデル**: `/resources/vrm/Shinano.vrm`
- **アイドルアニメーション**: 呼吸・体揺れ・頭の動き・腕揺れ・まばたき・耳ぴくぴく
- **感情表現**: コメント応答時にAIが判定した感情のBlendShapeをWebSocket経由で適用
- **リップシンク**: TTS音声のWAV振幅を解析し、30fpsの口パクフレームデータをWebSocket送信

### アバター制御WebSocketイベント

| type | データ | 説明 |
|------|--------|------|
| `blendshape` | `{shapes: {Joy: 1.0}}` | 表情BlendShape設定 |
| `lipsync` | `{frames: [0.0, 0.5, ...]}` | リップシンク開始（30fps振幅データ） |
| `lipsync_stop` | `{}` | リップシンク停止 |

## APIエンドポイント

| Endpoint | Method | 用途 |
|----------|--------|------|
| `/api/broadcast/setup` | POST | 環境構築（xvfb+Chromium+PulseAudio） |
| `/api/broadcast/teardown` | POST | 環境破棄 |
| `/api/broadcast/start` | POST | 配信開始（FFmpeg+Reader+GitWatcher） |
| `/api/broadcast/stop` | POST | 配信停止 |
| `/api/broadcast/scene` | POST | シーン切替 `{name: "main"\|"start"\|"end"}` |
| `/api/broadcast/scenes` | GET | シーン一覧 |
| `/api/broadcast/volume` | GET/POST | 音量取得/設定 `{source, volume}` |
| `/api/broadcast/status` | GET | 配信状態 |
| `/api/broadcast/avatar` | GET/POST | アバターURL取得/設定 |
| `/api/broadcast/avatar/stop` | POST | アバターストリーム停止 |
| `/api/broadcast/diag` | GET | プロセスヘルスチェック |

## 既存OBS配信との共存

既存のOBS関連コード（`index.html`, `obs_controller.py`等）はそのまま残っている。

| 方式 | UI | URL |
|------|-----|-----|
| OBS版 | index.html | `http://localhost:8080/` |
| OBS不要版 | broadcast-ui.html | `http://localhost:8080/broadcast-ui` |

## 音量制御

OBS版では`SetInputVolume` APIで制御していたが、OBS不要版では`HTMLAudioElement.volume`を直接制御する。

```
実効音量 = master × 個別(tts/bgm) × 曲音量(BGMのみ)
```

WebSocketの`volume`イベントでリアルタイム変更可能。

## WSLg PulseAudio

WSL2ではWSLgの`/mnt/wslg/PulseServer`を自動検出し、`PULSE_SERVER`環境変数に設定する。Chromium・FFmpeg・pactlすべてに適用される。
