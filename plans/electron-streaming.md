# Electron配信への移行

## 背景・動機

現在の配信パイプラインはWSL2内で完結している（xvfb + Chromium + PulseAudio + FFmpeg）。
Windowsのウィンドウキャプチャ映像はElectronアプリからMJPEGでWSL2に転送し、broadcast.html内の`<img>`で表示→xvfbでレンダリング→FFmpegでx11grab再キャプチャという流れ。

この構成には以下の問題がある:
- **MJPEG二重エンコード**: JPEG圧縮→HTTP転送→デコード→再レンダリング→x11grab再キャプチャで画質劣化
- **CPU負荷**: WSL2側（xvfb+Chromium+FFmpeg）とWindows側（Electron）の両方でCPUを消費
- **WSLg依存**: PulseAudioがWSLgに依存しており不安定な場合がある
- **ネットワーク帯域**: MJPEG 15fpsがWSL2↔Windows間のネットワークを流れる

## 現状

```
Windows (Electron)                    WSL2
  desktopCapturer                       Xvfb :99
  canvas→JPEG ──── MJPEG HTTP ────→    Chromium (broadcast.html)
  port 9090                               └─ <img src="mjpeg">
                                        PulseAudio (broadcast sink)
                                          └─ Chromium音声出力
                                        FFmpeg
                                          入力: x11grab :99 + pulse
                                          出力: H.264+AAC → RTMP → Twitch
```

### 関連ファイル
- `src/stream_controller.py` - xvfb/Chromium/PulseAudio/FFmpegプロセス管理
- `static/broadcast.html` - 配信合成ページ
- `win-capture-app/main.js` - Electronキャプチャアプリ
- `scripts/routes/stream_control.py` - 配信制御API

## 方針

**Electron内でbroadcast.htmlをレンダリングし、FFmpeg(Windows)で直接Twitchに配信する。**

WSL2のxvfb/PulseAudioを排除し、Windows側で映像合成→エンコード→配信を完結させる。
WSL2サーバーはAPI/TTS/AI生成のバックエンドとして残す。

### 移行後のアーキテクチャ
```
Windows (Electron)
  BrowserWindow (broadcast.html, offscreen: true)
    ├─ overlay, avatar, 字幕
    └─ desktopCapturerで他ウィンドウ直接合成（MJPEG不要）
  ↓
  paint event → NativeImage.toBitmap() → BGRA raw frames
  ↓
  FFmpeg.exe (child_process.spawn)
    入力: rawvideo pipe:0 (BGRA) + lavfi anullsrc (Phase 3で実音声に置換)
    出力: H.264+AAC → RTMP → Twitch
        ↑ WebSocket制御 (/ws/control)
WSL2 (FastAPI Server)
  TTS/BGM/AI生成/Twitch API
  → POST /api/capture/stream/start でElectron配信を制御
```

## 実装ステップ

### Phase 1+2: FFmpeg統合 + オフスクリーンキャプチャ ✅ 実装済み
1. ✅ FFmpegをPATHから参照（`child_process.spawn`）
2. ✅ `BrowserWindow({ offscreen: true })` でbroadcast.htmlをレンダリング
3. ✅ `paint`イベントで`NativeImage.toBitmap()` → BGRA rawvideo → FFmpeg stdin
4. ✅ HTTP/WebSocketエンドポイント追加（start/stop/status）
5. ✅ WSL2側API追加: `POST /api/capture/stream/start|stop`, `GET /api/capture/stream/status`
6. ✅ 無音音声（`anullsrc`）でTwitch要件を満たす
7. ✅ フレームドロップ検知、グレースフルシャットダウン

#### Electron側API（port 9090）
- `POST /stream/start` - `{streamKey, serverUrl, resolution?, framerate?, videoBitrate?}`
- `POST /stream/stop`
- `GET /stream/status`
- `POST /broadcast/open` - `{serverUrl}` （配信ウィンドウのみ開く）
- `POST /broadcast/close`
- WebSocket `/ws/control`: `start_stream`, `stop_stream`, `stream_status`, `broadcast_open`, `broadcast_close`

#### WSL2側API
- `POST /api/capture/stream/start` - Electron経由で配信開始（TWITCH_STREAM_KEYを自動送信）
- `POST /api/capture/stream/stop` - 配信停止
- `GET /api/capture/stream/status` - 配信状態

### Phase 3: 音声キャプチャ ✅ 実装済み
1. ✅ `broadcast-preload.js`: contextBridgeで`window.audioCapture.sendPCM()` API公開
2. ✅ broadcast.html: AudioContext + ScriptProcessorNode でTTS/BGMのPCMキャプチャ
   - `createMediaElementSource()` でTTS/BGMの`<audio>`をルーティング
   - Float32 stereo → Int16 interleaved (s16le) 変換
   - スピーカー出力は無効（gain=0）、AudioContextグラフは維持
3. ✅ main.js: Windows Named Pipe (`\\.\pipe\atc_audio_{pid}`) でPCMデータをFFmpegに中継
   - IPC(`audio-pcm`) → Named Pipe → FFmpeg `-f s16le -ar 44100 -ac 2 -i \\.\pipe\...`
   - 非Windowsではanullsrcフォールバック
4. ✅ `window.audioCapture` が無い環境（WSL2 Chromium等）では従来通りPulseAudio経由

### Phase 4: WSL2サーバーとの連携変更
1. Electron↔WSL2間にWebSocket常時接続を確立
2. TTS音声URL、BGM制御、字幕等のイベントをWebSocket経由で受信
3. broadcast.htmlのWebSocket接続先をWSL2サーバーに向ける（現状と同じ）

### Phase 5: 配信制御API統合 ✅ 実装済み
1. ✅ 配信モード設定（`stream.mode` DB保存、`GET/POST /api/broadcast/mode`）
2. ✅ `/api/broadcast/go-live` にモード分岐（electron/wsl2）
3. ✅ `/api/broadcast/start`, `/api/broadcast/stop` がモードに応じてElectron or WSL2を制御
4. ✅ `/api/broadcast/status` が統合ステータスを返す（アクティブモード・Electron状態含む）
5. ✅ 配信中はモード変更不可（409エラー）
6. ✅ preview.html/index.htmlにモード選択UI追加

### Phase 6: MJPEG排除
1. ウィンドウキャプチャをElectron内で直接合成（broadcast.htmlに直接描画）
2. MJPEG HTTP streaming コードを廃止（または互換モードとして残す）

## リスク・注意点

- **音声ルーティングの複雑さ**: Web Audio API→FFmpegパイプの実装が最も技術的に難しい部分
- **Electronのメモリ使用量**: 画面キャプチャ+エンコードでメモリ消費が増加する可能性
- **デバッグの困難さ**: WSL2では`DISPLAY=:99`で別のChromiumからbroadcast.htmlを確認できたが、Electronでは確認方法が変わる
- **段階的移行**: 一度にすべてを移行せず、Phase単位で動作確認しながら進める
- ~~**フォールバック**: WSL2パイプラインは削除せず、切替可能にしておく~~ → WSL2パイプライン削除済み（Electron一本化）

## ステータス
- 作成日: 2026-03-12
- 更新日: 2026-03-12
- 優先度: 中
- 状態: Phase 1+2+3+5 実装済み + WSL2パイプライン削除完了（Electron一本化）。Phase 6（MJPEG排除）が次のステップ
