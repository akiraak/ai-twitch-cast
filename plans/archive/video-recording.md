# Electron画面の動画撮影

## 背景・動機

現在、配信画面のスクリーンショット（静止画）撮影機能がある:
- `broadcastWindow.webContents.capturePage()` → PNG → `/tmp/screenshots/` に保存
- Web UIのDebugタブから撮影・一覧・ダウンロード・削除が可能

配信のハイライト保存やデバッグ用に、**動画としても録画できる機能**が欲しい。
既存のFFmpeg配信パイプライン（rawvideo+PCM音声→FFmpeg→RTMP）の仕組みを流用し、出力先をファイルに変えることで実現する。

## 現状

### 配信パイプライン（参考）
```
broadcastWindow (offscreen BrowserWindow)
  │
  ├─ paint event → NativeImage.toBitmap() → BGRA rawvideo
  │                                           ↓
  │                                     FFmpeg stdin (pipe:0)
  │                                           ↓
  ├─ broadcast.html AudioContext              │
  │   └─ PCM (s16le 44100Hz stereo)           │
  │       → IPC → Named Pipe ──────→    FFmpeg -i pipe (audio)
  │                                           ↓
  │                                     H.264 + AAC → RTMP → Twitch
```

### スクリーンショット機能（参考）
```
POST /api/capture/screenshot
  → WebSocket → Electron {action: 'screenshot'}
  → broadcastWindow.webContents.capturePage()
  → PNG Base64 → WSL2サーバ
  → /tmp/screenshots/screenshot_YYYYMMDD_HHMMSS.png
```

## 方針

**既存のpaintイベント+音声パイプラインを利用し、2つ目のFFmpegプロセスでファイルに録画する。**

- 配信中でも独立して録画可能（配信FFmpegとは別プロセス）
- 配信していなくても録画可能（broadcastWindowさえ開いていれば）
- 保存先: `/tmp/recordings/` （スクリーンショットと同様の一時ストレージ）
- 形式: MP4 (H.264 + AAC)

### アーキテクチャ
```
broadcastWindow
  │
  ├─ paint event → rawvideo frames ──┬──→ [配信FFmpeg] → RTMP (既存)
  │                                  └──→ [録画FFmpeg] → MP4ファイル (新規)
  │
  └─ PCM audio ──────────────────────┬──→ [配信FFmpeg] audio (既存)
                                     └──→ [録画FFmpeg] audio (新規)
```

## 実装ステップ

### Phase 1: Electron側 録画FFmpegプロセス管理

**ファイル: `win-capture-app/main.js`**

1. 録画用の状態管理を追加
   ```javascript
   let recordingProcess = null;  // FFmpegプロセス
   let recordingAudioPipe = null; // 音声用Named Pipe
   let recordingStartTime = null;
   let recordingFilePath = null;
   let recordingFrameCount = 0;
   ```

2. 録画開始関数 `startRecording(options)`
   - broadcastWindowが存在しない場合はエラー
   - 録画用Named Pipeを作成（`\\.\pipe\atc_recording_audio_{pid}`）
   - FFmpegプロセスをspawn:
     ```
     ffmpeg -y
       -f rawvideo -pixel_format bgra -video_size 1280x720 -framerate 30
       -i pipe:0
       -f s16le -ar 44100 -ac 2
       -i \\.\pipe\atc_recording_audio_{pid}
       -c:v libx264 -preset fast -crf 23
       -c:a aac -b:a 128k
       -movflags +faststart
       output.mp4
     ```
   - paintイベントハンドラに録画FFmpegへの書き込みを追加（既存配信パイプラインと並行）
   - PCMデータも録画用Named Pipeに並行書き込み

3. 録画停止関数 `stopRecording()`
   - FFmpegにSIGINT送信（正常終了でmoovアトム書き込み）
   - ファイルパスと録画時間を返す

4. HTTP/WebSocketエンドポイント追加
   - `POST /recording/start` → `{filePath}` で録画開始
   - `POST /recording/stop` → 録画停止、ファイル情報を返す
   - `GET /recording/status` → 録画中かどうか、経過時間、フレーム数
   - WebSocket `/ws/control`: `start_recording`, `stop_recording`, `recording_status`

### Phase 2: WSL2サーバ側 API + ファイル管理

**ファイル: `scripts/routes/capture.py`**

1. 録画制御APIを追加
   - `POST /api/capture/recording/start` - 録画開始
     - Electron WebSocketで `start_recording` を送信
     - ファイル名は自動生成: `recording_YYYYMMDD_HHMMSS.mp4`
     - 保存先はElectronアプリのtempディレクトリ（Windows側）
   - `POST /api/capture/recording/stop` - 録画停止
     - Electron WebSocketで `stop_recording` を送信
     - 完了後、録画ファイルをWSL2側 `/tmp/recordings/` に転送（HTTP経由）
   - `GET /api/capture/recording/status` - 録画状態

2. 録画ファイル管理API（スクリーンショットと同様のパターン）
   - `GET /api/capture/recordings` - 録画一覧（ファイル名・サイズ・作成日時・再生時間）
   - `GET /api/capture/recordings/{filename}` - ファイルダウンロード
   - `DELETE /api/capture/recordings/{filename}` - ファイル削除

### Phase 3: Web UI

**ファイル: `static/index.html`**

Debugタブのスクリーンショットセクションの下に録画セクションを追加:

```
┌─────────────────────────────────────┐
│ 動画撮影                              │
│ [● 録画開始]  or  [■ 録画停止 (00:32)] │
│ 録画中: recording_20260313_150000.mp4  │
│                                       │
│ 保存済み録画                            │
│ ┌──────────────────────────────────┐  │
│ │ ▶ recording_20260313_150000.mp4  │  │
│ │   12.3 MB | 00:32 | 2026-03-13  │  │
│ │   [ダウンロード] [削除]            │  │
│ └──────────────────────────────────┘  │
│ ┌──────────────────────────────────┐  │
│ │ ▶ recording_20260313_143000.mp4  │  │
│ │   45.1 MB | 01:58 | 2026-03-13  │  │
│ │   [ダウンロード] [削除]            │  │
│ └──────────────────────────────────┘  │
└─────────────────────────────────────┘
```

機能:
- 録画開始/停止ボタン（録画中は経過時間を表示）
- 録画一覧（ファイル名・サイズ・再生時間・日時）
- ダウンロードリンク
- 削除ボタン（確認ダイアログ付き）

### Phase 4: ファイル転送の最適化（オプション）

録画ファイルはWindows側で生成されるため、WSL2からアクセスする方法:

**方式A: Windows→WSL2ファイル転送（推奨）**
- 録画停止後、ElectronがHTTPでファイルをWSL2に送信
- `POST /api/capture/recording/upload` で受信→`/tmp/recordings/` に保存
- メリット: WSL2からのパスマウント不要

**方式B: WSLパスでWindows側ファイルを直接参照**
- `/mnt/c/Users/.../AppData/Local/Temp/` 経由でアクセス
- メリット: コピー不要
- デメリット: パス解決が複雑、Windowsファイルシステムのパフォーマンス

**方式C: Electron HTTP経由でストリーミングダウンロード**
- `GET /recording/file/{filename}` エンドポイントをElectron側に追加
- WSL2サーバがプロキシ（スクリーンショットの`/snapshot`と同じパターン）
- メリット: ファイルコピー不要、オンデマンドアクセス
- デメリット: 大きなファイルでタイムアウトの可能性

→ **方式Cを基本とし、方式Aをフォールバック**とする。
小さいファイルはHTTPプロキシで直接配信。大きなファイル（100MB超）は転送を検討。

## 変更ファイル一覧

| ファイル | 変更内容 | Phase |
|---|---|---|
| `win-capture-app/main.js` | 録画FFmpegプロセス管理、API追加 | 1 |
| `scripts/routes/capture.py` | 録画制御API、ファイル管理API | 2 |
| `static/index.html` | 録画UI（Debugタブ） | 3 |

## 技術的な考慮事項

### paintイベントの並行書き込み
既存の配信FFmpegと録画FFmpegに同じフレームデータを書き込む。
`paint`イベントハンドラ内で:
```javascript
const frame = image.toBitmap();
// 配信中なら配信FFmpegに書き込み
if (streamProcess?.stdin?.writable) {
  streamProcess.stdin.write(frame);
}
// 録画中なら録画FFmpegに書き込み
if (recordingProcess?.stdin?.writable) {
  recordingProcess.stdin.write(frame);
}
```

### 音声の並行書き込み
PCMデータは現在Named Pipe経由で配信FFmpegに送られている。
録画用に2つ目のNamed Pipeを作成し、PCMデータを両方に書き込む:
```javascript
ipcMain.on('audio-pcm', (event, buffer) => {
  // 配信用
  if (audioPipe) audioPipe.write(buffer);
  // 録画用
  if (recordingAudioPipe) recordingAudioPipe.write(buffer);
});
```

### MP4のmovflags +faststart
`-movflags +faststart` を指定し、moovアトムをファイル先頭に配置。
これによりダウンロード後すぐに再生可能になる。
ただし、FFmpegが正常終了しないとmoovが書き込まれずファイルが壊れるため、
停止時は必ず `SIGINT` → graceful shutdown を行う。

### ファイルサイズの目安
- 1280x720 H.264 CRF23 + AAC 128kbps: 約20-30MB/分
- 10分録画で200-300MB程度
- `/tmp/recordings/` の容量に注意（tmpfsの場合メモリを消費）

### 配信なし録画
broadcastWindowが開いていれば配信していなくても録画可能。
ただしbroadcastWindowが閉じている場合は録画開始をエラーにする。

## リスク・注意点

- **FFmpeg正常終了**: SIGINTで正常終了しないとMP4が壊れる。タイムアウト後にSIGKILLする保険が必要
- **ディスク容量**: 長時間録画でディスクが逼迫する可能性。録画時間の上限（30分等）を設定することも検討
- **CPU負荷**: 配信+録画で2つのFFmpegエンコードが同時実行される。配信時はGPUエンコード（h264_nvenc）の検討も
- **paintイベントの負荷**: 2つのプロセスへの書き込みでバックプレッシャーが発生しうる。writable確認+フレームドロップで対処
- **Windows側のtemp領域**: 録画ファイルはWindows側に保存されるため、WSL2からのアクセス方法に注意

## ステータス
- 作成日: 2026-03-13
- 優先度: 中
- 状態: Phase 1-3 実装済み（Electron録画FFmpeg・WSL2 API・Web UI）
