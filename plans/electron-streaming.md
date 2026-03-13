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

#### 現状のデータフロー（3経路が並存）

**経路A: MJPEG HTTP（レガシー）**
```
capture-renderer.js (getUserMedia → canvas → JPEG blob)
  → IPC 'capture-frame' → main.js
  → main.js: session.clients (HTTP multipart/x-mixed-replace)
  → broadcast.html: <img src="http://host:9090/stream/{id}"> (フォールバック)
```

**経路B: WebSocket バイナリ（現行メイン）**
```
capture-renderer.js (getUserMedia → canvas → JPEG blob)
  → IPC 'capture-frame' → main.js
  → main.js: wss (WebSocket /ws/capture, 1byte index + JPEG)
  → broadcast.html: WebSocket → Blob → ObjectURL → <img>.src
```

**経路C: HTTP snapshot（補助）**
```
main.js: GET /snapshot/:id → session.latestFrame (単一JPEG)
```

**問題**: broadcast.htmlが同じElectronアプリ内で動作しているのに、ネットワーク経由で映像を転送している。

#### 設計方針

broadcast.htmlがElectronのオフスクリーンウィンドウ内で動作している場合、**IPC経由でフレームデータを直接渡す**。

- `broadcast-preload.js` に `window.captureReceiver` APIを追加
- `main.js` で `capture-frame` → `broadcastWindow.webContents.send()` で直接転送
- `broadcast.html` でIPC受信 → `<img>` にObjectURLで設定

#### 2つのコンテキスト

| コンテキスト | 使用場所 | window.captureReceiver | キャプチャ表示 |
|---|---|---|---|
| **Electronオフスクリーン** | broadcastWindow (配信用) | **あり** | IPC直接受信 |
| **Electronプレビュー** | previewWindow → iframe | **なし** | WebSocket経由(既存) |

broadcastWindowには`broadcast-preload.js`がpreload設定済み → 新APIを追加可能。
previewWindowはiframe内broadcast.htmlにpreload未設定 → `window.captureReceiver`不在 → 自動的にWebSocketフォールバック。

#### Step 1: broadcast-preload.js にキャプチャ受信API追加

`win-capture-app/broadcast-preload.js` を拡張:

```javascript
contextBridge.exposeInMainWorld('captureReceiver', {
  isAvailable: true,
  onFrame(callback) {
    // callback(captureId, jpegArrayBuffer)
    ipcRenderer.on('capture-frame-to-broadcast', (event, { id, jpeg }) => {
      callback(id, jpeg);
    });
  },
  onCaptureAdd(callback) {
    ipcRenderer.on('capture-add-to-broadcast', (event, data) => callback(data));
  },
  onCaptureRemove(callback) {
    ipcRenderer.on('capture-remove-to-broadcast', (event, data) => callback(data));
  },
});
```

#### Step 2: main.js でbroadcastWindowへフレーム直接送信

`ipcMain.on('capture-frame', ...)` ハンドラを拡張:

```javascript
// broadcastWindowへIPC直接送信
if (broadcastWindow && !broadcastWindow.isDestroyed()) {
  broadcastWindow.webContents.send('capture-frame-to-broadcast', { id, jpeg });
}
```

キャプチャ開始/停止時にも通知:
```javascript
// startCaptureSession内:
broadcastWindow.webContents.send('capture-add-to-broadcast', { id, name });

// stopCapture内:
broadcastWindow.webContents.send('capture-remove-to-broadcast', { id });
```

broadcastWindow起動時に既存キャプチャ一覧をIPCで送信する初期化処理も必要。

#### Step 3: broadcast.html でIPC受信の分岐

`addCaptureLayer()` を修正:
- `window.captureReceiver` が存在 → IPC直接受信（WebSocket接続不要）
- 存在しない → 既存のWebSocket/MJPEGフォールバック

```javascript
function setupDirectCapture() {
  if (!window.captureReceiver?.isAvailable) return false;

  window.captureReceiver.onFrame((id, jpegBuffer) => {
    const img = captureImgMap[id];
    if (!img) return;
    const blob = new Blob([jpegBuffer], { type: 'image/jpeg' });
    const url = URL.createObjectURL(blob);
    const prevUrl = img._blobUrl;
    img.src = url;
    img._blobUrl = url;
    if (prevUrl) URL.revokeObjectURL(prevUrl);
  });

  window.captureReceiver.onCaptureAdd((data) => { /* ... */ });
  window.captureReceiver.onCaptureRemove((data) => { /* ... */ });

  return true;
}
```

#### Step 4: MJPEG HTTPストリーミングコードの整理

動作確認後に段階的廃止:

**残すもの（プレビュー互換のため）:**
- WebSocket `/ws/capture` によるフレーム配信
- `/snapshot/:id` エンドポイント（デバッグ用）

**廃止するもの:**
- `/stream/:id` MJPEG HTTPエンドポイント
- `session.clients` (MJPEG HTTP接続管理)
- `capture-frame` IPC内のMJPEGクライアント送信部分

#### 実装順序

```
Step 1 (broadcast-preload.js拡張)
  ↓
Step 2 (main.jsフレーム転送)
  ↓
Step 3 (broadcast.html分岐)
  ↓
動作確認: Electron配信でIPC直接転送 + プレビューでWebSocket転送
  ↓
Step 4 (MJPEGコード整理)
```

#### 変更ファイル一覧

| ファイル | 変更内容 | 影響度 |
|---|---|---|
| `win-capture-app/broadcast-preload.js` | captureReceiver API追加 | 小 |
| `win-capture-app/main.js` | broadcastWindowへのIPC送信追加、MJPEG整理 | 中 |
| `static/broadcast.html` | IPC直接受信モード追加、WebSocketフォールバック維持 | 中 |
| `scripts/routes/capture.py` | コメント修正のみ | 極小 |

#### リスク・注意点

- **IPC転送の帯域**: `webContents.send()` で大量フレーム送信時にIPCチャネルが詰まる可能性。バックプレッシャー制御を検討
- **broadcastWindow生存期間**: キャプチャ開始時にbroadcastWindowが未起動の場合がある。起動時に既存キャプチャ一覧を送信する初期化処理が必要
- **preview.htmlとの互換性**: previewWindow内のiframeにはpreload未設定なので自動的にWebSocketフォールバック。両コンテキストでテスト必須

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
- 状態: Phase 1+2+3+5 実装済み + WSL2パイプライン削除完了（Electron一本化）。Phase 6（MJPEG排除）プラン策定済み、実装着手待ち
