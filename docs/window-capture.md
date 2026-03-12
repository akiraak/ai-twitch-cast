# Windowsウィンドウキャプチャシステム

配信画面にWindows側のウィンドウ（VSCode、ブラウザ等）を表示するためのシステム。

## アーキテクチャ

```
Windows (Electron .exe)                    WSL2 (FastAPI)
┌────────────────────────┐                ┌──────────────────────┐
│ win-capture-app.exe    │  HTTP API      │ scripts/routes/      │
│                        │◄──────────────►│   capture.py         │
│ desktopCapturer API    │  localhost:9090 │                      │
│ Express HTTPサーバー    │                │ broadcast_to_broadcast│
│ MJPEGストリーム配信    │                │   (WebSocket)        │
└────────────────────────┘                └──────────┬───────────┘
        │ MJPEGストリーム                             │ WebSocket
        │                                             ▼
        │                                  ┌──────────────────────┐
        └─────────────────────────────────►│ broadcast.html       │
           <img src="http://host:9090/     │  キャプチャ表示      │
            stream/cap_0">                 │  編集モード          │
                                           └──────────────────────┘
```

## Electronアプリ（Windows側）

### 特徴

- **スタンドアロン .exe**: Windows側にPython等のインストール不要
- **desktopCapturer API**: Electron組み込みのウィンドウキャプチャ機能を使用
- **WSL2からビルド**: `electron-builder --win --dir` でクロスビルド可能
- **WSL2から起動**: `cmd.exe /C` で .exe を起動

### ディレクトリ構成

```
win-capture-app/
├── package.json              # Electron + electron-builder設定
├── main.js                   # メインプロセス: HTTPサーバー + キャプチャ管理
├── preload.js                # IPC bridge（contextBridge）
├── capture.html              # 非表示レンダラーページ（キャプチャ実行）
├── capture-renderer.js       # レンダラー: getUserMedia + canvas + フレーム書き出し
├── build.sh                  # ビルドスクリプト
└── dist/win-unpacked/        # ビルド成果物
    └── win-capture-app.exe
```

### HTTP API

| Method | Path | 説明 |
|--------|------|------|
| GET | /windows | 可視ウィンドウ一覧（id, name, thumbnailサイズ） |
| POST | /capture | キャプチャ開始 `{sourceId, id?, fps?, quality?}` |
| DELETE | /capture/:id | キャプチャ停止 |
| GET | /captures | アクティブキャプチャ一覧 |
| GET | /stream/:id | MJPEGストリーム |
| GET | /snapshot/:id | 単一JPEGフレーム |
| GET | /status | ヘルスチェック |

### キャプチャの仕組み

1. `desktopCapturer.getSources({types: ['window']})` でウィンドウ列挙（メインプロセス）
2. キャプチャ開始時、非表示 `BrowserWindow` を作成
3. レンダラーで `navigator.mediaDevices.getUserMedia({video: {chromeMediaSource: 'desktop', chromeMediaSourceId}})` を呼び出し
4. `MediaStream` → `<video>` → `<canvas>` → JPEG書き出し（指定FPS）
5. IPC経由でメインプロセスにフレーム送信
6. Express `/stream/:id` エンドポイントでMJPEGとして配信

### デフォルト設定

| 設定 | デフォルト | 環境変数 |
|------|-----------|---------|
| ポート | 9090 | WIN_CAPTURE_PORT |
| FPS | 15 | WIN_CAPTURE_FPS |
| JPEG品質 | 70 | WIN_CAPTURE_QUALITY |

## WSL2側 API

`scripts/routes/capture.py` に実装。

| Method | Path | 説明 |
|--------|------|------|
| POST | /api/capture/launch | Electronアプリを起動 |
| POST | /api/capture/shutdown | Electronアプリを停止 |
| GET | /api/capture/status | サーバー状態確認 |
| GET | /api/capture/windows | ウィンドウ一覧（プロキシ） |
| POST | /api/capture/start | キャプチャ開始 + DB保存 + WebSocket通知 |
| DELETE | /api/capture/{id} | キャプチャ停止 + DB削除 + WebSocket通知 |
| GET | /api/capture/sources | アクティブソース一覧（レイアウト情報付き） |
| POST | /api/capture/{id}/layout | レイアウト更新 + WebSocket通知 |

### レイアウトデータ

DBに `capture.sources` キーでJSON保存:

```json
[
  {
    "id": "cap_0",
    "label": "Claude Code",
    "layout": {
      "x": 5,        // 左端からの位置（%）
      "y": 10,       // 上端からの位置（%）
      "width": 40,   // 幅（%）
      "height": 50,  // 高さ（%）
      "zIndex": 10,  // 重ね順
      "visible": true
    }
  }
]
```

### WebSocketイベント

`/ws/broadcast` 経由で broadcast.html に通知:

| type | データ | 説明 |
|------|--------|------|
| capture_add | id, stream_url, label, layout | キャプチャ追加 |
| capture_remove | id | キャプチャ削除 |
| capture_layout | id, layout | レイアウト変更 |

## broadcast.html

### キャプチャ表示

```html
<div id="capture-container">
  <div class="capture-layer" style="left:5%; top:10%; width:40%; height:50%;">
    <img src="http://{windows_ip}:9090/stream/cap_0">
  </div>
</div>
```

### 編集モード（`/broadcast?edit`）

- ツールバー表示（ウィンドウ追加、保存、終了）
- 各パネルをマウスでドラッグ＆リサイズ
- 変更は自動保存（500ms debounce）
- 配信用のChromiumは `?edit` なしで開くため、編集モードは影響しない

## Web UI (index.html)

「配信」タブに「ウィンドウキャプチャ」カードを追加:

- サーバー起動/停止ボタン
- ウィンドウ一覧 + キャプチャ開始ボタン
- アクティブキャプチャ一覧 + 停止ボタン
- レイアウト編集画面へのリンク

## ビルドと配置

### ビルド（WSL2上で実行）

```bash
cd win-capture-app
npm install
npm run build
# → dist/win-unpacked/win-capture-app.exe
```

### 起動（WSL2からの自動起動）

Web UIの「サーバー起動」ボタン → `/api/capture/launch` → `cmd.exe /C start "" <exe_path>`

### 注意事項

- Windowsファイアウォールでポート9090の受信を許可する必要がある場合あり
- MJPEG CORSヘッダー（`Access-Control-Allow-Origin: *`）を全レスポンスに付与
- 1920x1080 @ 15fpsでJPEG品質70の場合、1ストリームあたり約5-10Mbps（localhost通信なので問題なし）
