# サーバ↔Electronアプリ間のWebSocket統合

## 背景・動機

現在、WSL2サーバとWindows Electronアプリ間の通信は複数のプロトコルが混在している:
- **キャプチャ映像**: MJPEG over HTTP（multipart/x-mixed-replace）15fps連続ストリーム
- **キャプチャ制御**: HTTP REST（httpxプロキシ経由、毎回TCP接続）
- **TODO取得**: HTTP GET 30秒ポーリング
- **オーバーレイ更新**: WebSocket `/ws/broadcast`（サーバ→broadcast.htmlのみ）

問題点:
- **MJPEGのHTTPヘッダオーバーヘッド**: 各フレームにHTTPマルチパートヘッダが付く
- **TODOの無駄なポーリング**: 変更がなくても30秒ごとにHTTPリクエスト
- **接続状態が不明**: Electronアプリの切断をサーバ側で即座に検知できない
- **制御コマンドが毎回新規TCP接続**: httpxプロキシで都度接続

## 現状

### 通信パス一覧
| パス | プロトコル | 方向 | データ | 頻度 |
|------|-----------|------|--------|------|
| キャプチャ映像 | MJPEG HTTP | Electron→broadcast.html | JPEG | 15fps |
| キャプチャ制御 | HTTP REST proxy | WSL2→Electron | JSON | オンデマンド |
| オーバーレイ | WebSocket | WSL2→broadcast.html | JSON | イベント駆動 |
| TODO | HTTP GET | broadcast.html→WSL2 | JSON | 30秒ポーリング |
| プレビュー制御 | HTTP REST | WSL2→Electron | JSON | オンデマンド |

### 関連ファイル
- `win-capture-app/main.js` - Electron HTTP サーバ（port 9090）
- `scripts/routes/capture.py` - WSL2側キャプチャプロキシ
- `scripts/routes/overlay.py` - WebSocket `/ws/broadcast` + TODO API
- `scripts/state.py` - broadcast_clients管理
- `static/broadcast.html` - WebSocket接続 + MJPEG `<img>` + TODO fetch

## 方針

3段階で段階的にWebSocket化する。既存HTTP APIは互換性のため残し、WebSocketを優先経路として追加する。

## 実装ステップ

### Step 1: TODO → WebSocket push化（実装コスト: 小）

既存の`/ws/broadcast` WebSocketに`todo_update`イベントを追加。

#### サーバ側（overlay.py）
1. TODO.mdの変更を検知する仕組みを追加
   - 方式A: `watchfiles`パッケージでinotify監視（推奨）
   - 方式B: TODO更新API（`/api/todo/start`等）の実行後にbroadcast
2. `todo_update`イベントをbroadcast:
   ```python
   await broadcast_overlay({"type": "todo_update", "items": [...]})
   ```

#### クライアント側（broadcast.html）
1. WebSocket `onmessage`に`todo_update`ハンドラ追加
2. `setInterval(loadTodo, 30000)` を削除（または長いフォールバック間隔に変更）
3. 初回読み込みは従来どおりHTTP GETで取得

#### 変更対象ファイル
- `scripts/routes/overlay.py` - todo_updateブロードキャスト関数追加
- `static/broadcast.html` - WebSocketハンドラ追加、ポーリング削除

---

### Step 2: MJPEG → WebSocket バイナリ送信（実装コスト: 中）

Electron→broadcast.html間のMJPEGストリームをWebSocketバイナリフレームに置き換え。

#### Electron側（main.js）
1. `ws`パッケージでWebSocketサーバを追加（port 9091 or 既存9090と共存）
2. キャプチャフレームをバイナリWebSocketメッセージとして送信:
   ```javascript
   // 現在: HTTP multipart/x-mixed-replace でJPEG送信
   // 変更後: WebSocket binary frameでJPEG送信
   wss.clients.forEach(client => {
     if (client.readyState === WebSocket.OPEN) {
       // captureId(2byte) + jpeg data
       const header = Buffer.alloc(2);
       header.writeUInt16BE(captureIndex);
       client.send(Buffer.concat([header, jpegBuffer]));
     }
   });
   ```
3. 既存MJPEG HTTPエンドポイント(`/stream/:id`)は互換性のため残す

#### broadcast.html側
1. ElectronのWebSocketに接続
2. バイナリメッセージ受信 → Blob URL生成 → `<img>`のsrcを更新:
   ```javascript
   captureWs.onmessage = (e) => {
     const data = new Uint8Array(e.data);
     const captureId = (data[0] << 8) | data[1];
     const blob = new Blob([data.slice(2)], {type: 'image/jpeg'});
     const url = URL.createObjectURL(blob);
     captureImages[captureId].src = url;
     URL.revokeObjectURL(prevUrl);  // メモリリーク防止
   };
   ```

#### メリット
- HTTPマルチパートヘッダ（約200byte/frame）の排除
- WebSocketフレームヘッダは2-6byte
- 15fps × 200byte ≈ 3KB/s の節約（帯域よりもパース負荷の削減が主）
- 複数キャプチャを1つのWebSocket接続で多重化可能

#### 変更対象ファイル
- `win-capture-app/main.js` - WebSocketサーバ追加
- `win-capture-app/package.json` - `ws`パッケージ追加
- `static/broadcast.html` - WebSocket受信+img更新ロジック
- `scripts/routes/capture.py` - stream_urlをws://に変更

---

### Step 3: Electron↔WSL2間の制御WebSocket（実装コスト: 中）

HTTPプロキシをWebSocket常時接続に置き換え。

#### WSL2サーバ側
1. `/ws/capture-control` エンドポイントを新設（overlay.pyまたはcapture.py）
2. Electronからの接続を受け付け、`capture_client`として管理
3. 制御コマンドをWebSocketメッセージとして送受信:
   ```python
   # 送信（WSL2→Electron）
   await capture_client.send_json({"action": "start_capture", "sourceId": "...", "id": "cap_0"})
   # 受信（Electron→WSL2）
   {"event": "capture_started", "id": "cap_0"}
   {"event": "frame_count", "id": "cap_0", "count": 1234}
   {"event": "error", "id": "cap_0", "message": "..."}
   ```

#### Electron側
1. 起動時にWSL2サーバのWebSocketに接続
2. 制御コマンドをWebSocket経由で受信・実行
3. 自発的なイベント通知が可能に:
   - キャプチャ対象ウィンドウが閉じられた
   - フレームレート低下
   - エラー発生

#### メリット
- **接続状態の即座な検知**: WebSocket切断で即座にサーバ側で検知
- **双方向通知**: Electronからの自発的イベント送信が可能
- **httpxプロキシの排除**: 毎回のTCP接続オーバーヘッドがなくなる

#### 変更対象ファイル
- `scripts/routes/capture.py` - WebSocketエンドポイント追加、httpxプロキシをWS送信に置換
- `scripts/state.py` - capture_client管理追加
- `win-capture-app/main.js` - WebSocketクライアント追加、HTTP APIは互換維持

## リスク・注意点

- **互換性**: 既存HTTPエンドポイントは削除せず残す。WebSocket接続がない場合はHTTPフォールバック
- **再接続**: WebSocket切断時の自動再接続ロジックが必要（exponential backoff）
- **メモリリーク**: Step 2のBlob URL生成で`URL.revokeObjectURL()`を忘れるとメモリリーク
- **バッファリング**: WebSocketバイナリ送信でバックプレッシャー制御が必要（送信が追いつかない場合にフレームを間引く）
- **Step 1を先に**: Step 1は独立して実装可能で効果も即座に出る。Step 2/3はElectron側の変更が必要

## ステータス
- 作成日: 2026-03-12
- 優先度: 中
- 状態: Step 1完了、Step 2-3未着手
