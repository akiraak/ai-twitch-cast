# Electron削除後バグ調査プラン

## ステータス: 調査中

## 概要

以下の3つのコミット以降に発生した2つのバグを調査・修正する。

| コミット | 内容 | 変更ファイル（C#関連） |
|---------|------|----------------------|
| `b94952e` | FFmpegビルド時自動DL・同梱 | csproj, download-ffmpeg.ps1（ロジック変更なし） |
| `ea63845` | 閉じるボタンでプロセスが残る問題を修正 | **MainForm.cs, AudioLoopback.cs, FfmpegProcess.cs** |
| `275e1e8` | Electron完全削除（Phase 8） | HttpServer.cs, broadcast.html, stream_control.py |

---

## コミット `ea63845` の変更詳細（最重要容疑者）

### MainForm.cs: OnFormClosing大幅変更
- **Before**: `async void OnFormClosing` → `await StopStreamingAsync()` → `CleanupResources()` → `Close()`
- **After**: `void OnFormClosing`（同期化）
  - `e.Cancel = true` でフォーム閉じをキャンセル
  - `Hide()` で即座に非表示
  - **安全タイマー**: 5秒後に `Environment.Exit(1)` で強制終了（バックグラウンドTask）
  - `Task.Run(async () => await StopStreamingAsync())` → `.Wait(3000)` でスレッドプール実行（最大3秒）
  - `CleanupResources()` → `Environment.Exit(0)` で確実終了
- **影響**: ランタイムの配信停止（HandlePanelStopStream）には直接影響しないはず。ただしStopStreamingAsync内の`Text = "AI Twitch Cast - 待機中"`がTask.Runスレッドから呼ばれるとクロススレッドUI操作例外が発生する

### AudioLoopback.cs: Stop()のタイマー破棄待機追加
- **Before**: `_silenceTimer?.Dispose(); _silenceTimer = null;`
- **After**:
  ```csharp
  using var waitHandle = new ManualResetEvent(false);
  _silenceTimer.Dispose(waitHandle);
  waitHandle.WaitOne(1000);  // ← 最大1秒ブロック
  _silenceTimer = null;
  ```
- **影響**: `StopStreamingAsync()` → `_audio.Stop()` が最大1秒間UIスレッドをブロックする。HandlePanelStopStreamからの呼び出しでUIがフリーズする可能性あるが、停止自体は成功するはず

### FfmpegProcess.cs: StopAsync堅牢化
- **Kill部分**: `_process.Kill()` → `try { _process.Kill(); } catch { }` + `try { _process.WaitForExit(3000); } catch { }` 追加
- **LogStderrAsync**: `while (_process is { HasExited: false })` → `while (_process is { HasExited: false } && !_stopping)` + `if (line == null) break;` 追加
- **影響**: `_stopping = true` 設定後にLogStderrAsyncがループを抜ける。ランタイムには影響なし（ログ出力が止まるだけ）

---

## バグ1: コントロールパネルのStopボタンが効かない

### 症状
- control-panel.htmlのStopボタンをクリックしても配信が停止しない
- `stopStream`メッセージが`OnPanelMessage`で処理されない

### 現在のコードフロー（正常に見える）
1. `control-panel.html:393` — `stopStream()` → `send({action:'stopStream'})`
2. `send()` → `wv?.postMessage(msg)` （`wv = window.chrome?.webview`）
3. `MainForm.cs:507` — `_panelView.CoreWebView2.WebMessageReceived += OnPanelMessage`
4. `MainForm.cs:304` — `case "stopStream": await HandlePanelStopStream()`
5. `MainForm.cs:361` — `await StopStreamingAsync()`

### StopStreamingAsync内部フロー（UIスレッドで実行）
```
1. _capture.OnFrameReady = null     ← 即座
2. _audio.Stop()                    ← ManualResetEvent WaitOne(1000) ★最大1秒ブロック★
3. _audio.Dispose()                 ← 即座
4. await _ffmpeg.StopAsync()        ← パイプ閉じ→FFmpeg終了待ち（最大5秒、async）
5. _ffmpeg.Dispose()                ← 即座
6. Text = "AI Twitch Cast - 待機中" ← UIスレッドOK（HandlePanelStopStreamからの場合）
```

### `ea63845`で追加された影響
- `_audio.Stop()` が最大1秒ブロックする（ManualResetEvent）。これ自体は停止を妨げないが、UIスレッドが1秒フリーズする
- ボタンクリックイベント自体がブロックされる可能性は低い（async voidで制御返却済み）

### 変更されていない箇所
- `control-panel.html`: 3コミットとも変更なし
- `MainForm.cs`: OnPanelMessage/HandlePanelStopStream/StopStreamingAsync自体は変更なし
- `HttpServer.cs`: WebSocket Dispose時のCloseAsync→Abort変更のみ（ランタイム影響なし）

### 調査仮説（優先度順）

#### 仮説A: WebView2 postMessageの送受信が機能していない
- `window.chrome?.webview`がnullの可能性
- パネルの読み込みURL `http://localhost:{port}/panel` とWebView2のpostMessage互換性
- **検証方法**: パネルHTMLにデバッグログを追加。`send()`呼び出し時に`console.log`を出力、MainForm.csの`OnPanelMessage`冒頭にもログ追加

#### 仮説B: OnPanelMessageハンドラが例外で失敗している
- `msg.GetProperty("action")`がJSONパースに失敗
- `HandlePanelStopStream()`内のawait中にUIスレッドデッドロック
- **検証方法**: `OnPanelMessage`のcatchブロックにログ追加、try内の各ステップにログ追加

#### 仮説C: パネルWebView2の初期化タイミング問題
- `_panelView.EnsureCoreWebView2Async`が完了前にメッセージが送られている
- `WebMessageReceived`イベント登録前にページが読み込み完了する可能性
- **検証方法**: `_panelView.CoreWebView2.NavigationCompleted`イベントでログ出力

#### 仮説D: Stopボタンがdisabledのまま有効化されない
- `OnTrayUpdate`が3秒ごとにstatus送信しているはずだが、パネルに届いていない可能性
- `SendPanelMessage`が`_panelView.CoreWebView2 == null`チェックで弾かれている
- **検証方法**: `SendPanelMessage`にログ追加、パネル側`updateStatus`にもログ追加

#### 仮説E: ビルドが古い
- `ea63845`以前のバイナリが残っている
- stream.shがビルドせずに古いexeを起動している可能性
- **検証方法**: stream.shの動作確認、ビルド出力のタイムスタンプ確認

### 修正ステップ
1. **診断ログ追加**: MainForm.csの`OnPanelMessage`冒頭、`SendPanelMessage`、control-panel.htmlの`send()`/`updateStatus()`にデバッグログを追加
2. **ビルド・テスト**: C#アプリをビルドして実際にStopボタンを押してログ確認
3. **原因特定後の修正**: 仮説に応じた修正を実施

---

## バグ2: Twitch配信時に音声がとぎれとぎれになる

### 症状
- Twitch配信中、音声（TTS/BGM）が途切れ途切れになる
- WASAPI→FFmpegの音声パイプライン問題

### 現在の音声パイプライン
```
broadcast.html (WebView2)
  └─ AudioContext → GainNode → AnalyserNode → destination (システムスピーカー)
       ↓ (システム音声出力)
WASAPI Loopback Capture (AudioLoopback.cs)
  └─ DataAvailable event → byte[] data
       ↓ (直接書き込み)
Named Pipe (winnative_audio_{pid}, 1MB buffer)
       ↓
FFmpeg (-f f32le -ar 48000 -ac 2 → -c:a aac -ar 44100)
       ↓
Twitch RTMP
```

### Electron時代との違い（重要）
**Electron時代**: 直接PCMパイプライン
```
broadcast.html AudioContext → ScriptProcessorNode → IPC → Named Pipe → FFmpeg
```
- ブラウザ内で直接PCMデータをキャプチャしてFFmpegに送信
- システム音声スタックを経由しない

**現在（C#ネイティブ）**: WASAPIループバック方式
```
broadcast.html AudioContext → システムスピーカー → WASAPI → Named Pipe → FFmpeg
```
- システム音声出力を経由するため、追加のレイテンシとバッファリングが発生
- WASAPIの特性に依存

### `ea63845`で追加された影響

#### AudioLoopback.cs: サイレンスタイマー破棄待機
- Stop()にManualResetEvent WaitOne(1000)を追加
- **ランタイム影響**: なし（Stop時のみ）。配信中の音声フローには影響しない

#### FfmpegProcess.cs: _stoppingフラグチェック追加
- `LogStderrAsync`で`!_stopping`条件追加
- **ランタイム影響**: なし（Stop時のみ）。配信中は`_stopping = false`

#### 結論: `ea63845`は音声とぎれの直接原因ではない可能性が高い
- 変更はすべてStop/Cleanup系。配信中の音声データフローに変更なし
- ただし、`ea63845`と同時期（テスト環境の変更等）で発症した可能性あり

### 調査仮説（優先度順）

#### 仮説A: WASAPIループバックとサイレンスタイマーの競合
- サイレンスタイマー（100ms間隔）と実データが交互に書き込まれ、FFmpegに不安定なデータが届く
- `DataAvailable`で`_silenceTimer.Change(100, 100)`を呼んでリセットしているが、タイマーコールバックが既に実行中の場合、サイレンスと実データが混在する可能性
- **具体的な競合シナリオ**:
  1. WASAPIが10ms分のデータを送信
  2. `_silenceTimer.Change(100, 100)` でリセット
  3. 80ms後、まだWASAPIデータが来ない
  4. タイマーが発火し100ms分のサイレンスデータを書き込み
  5. 直後にWASAPIデータ到着 → サイレンスと実データが混ざる
- **検証方法**: サイレンス書き込み時とデータ書き込み時にカウンタ/タイムスタンプをログ出力

#### 仮説B: WebView2バックグラウンドスロットリング
- WebView2は`--autoplay-policy=no-user-gesture-required`のみ設定
- `--disable-background-timer-throttling`等のフラグが未設定
- ウィンドウが非フォーカスや他のウィンドウの背面にある時、AudioContextの処理が間引かれる可能性
- **Electron時代との違い**: Electronではオフスクリーンレンダリング用にbackgroundThrottling無効化していた可能性
- **検証方法**: WebView2環境オプションに以下を追加してテスト
  ```
  --disable-background-timer-throttling
  --disable-renderer-backgrounding
  --disable-backgrounding-occluded-windows
  ```

#### 仮説C: Named Pipeバッファ不足・書き込みブロック
- 映像パイプは8MBバッファだが、音声パイプは1MBバッファ
- FFmpegがエンコードに時間がかかると、パイプが一杯になり書き込みがブロック→データ欠落
- **検証方法**: `WriteAudioData`の実行時間をログ出力、パイプバッファサイズを増加

#### 仮説D: WASAPIバッファサイズ不足
- `WasapiLoopbackCapture`のデフォルトバッファサイズが小さい
- 短いバッファだとアンダーラン発生
- **検証方法**: NAudioの`WasapiLoopbackCapture`にバッファサイズを明示的に設定

#### 仮説E: 48kHz→44.1kHzリサンプリングの負荷
- FFmpegが48kHzから44.1kHzへリサンプリング（`-ar 44100`指定）
- リサンプリングがCPU負荷を増加させ、処理が追いつかない
- **検証方法**: 出力のサンプルレートを48kHzに変更してテスト

### 修正ステップ
1. **診断ログ追加**: AudioLoopback.csのDataAvailable/サイレンスタイマー、FfmpegProcess.csのWriteAudioDataにタイミングログ追加
2. **WebView2フラグ追加**: `--disable-background-timer-throttling`等のバックグラウンドスロットリング対策フラグ追加
3. **ビルド・テスト**: 配信して音声の途切れを確認
4. **原因特定後の修正**: 仮説に応じた対策実施

---

## 共通原因の可能性

### `ea63845`の変更がランタイムに影響する可能性
- `AudioLoopback.Stop()` のManualResetEvent → **ランタイム影響なし**（Stop時のみ）
- `FfmpegProcess._stopping`フラグチェック → **ランタイム影響なし**（Stop時のみ）
- `OnFormClosing`のEnvironment.Exit → **ランタイム影響なし**（閉じる時のみ）

### ありえる共通要因
- **ビルド・デプロイの問題**: `ea63845`/`275e1e8`後にC#アプリの再ビルドが正しく行われていない、古いバイナリが残っている
- **HttpServer.cs WebSocket Abort変更**（`275e1e8` + `ea63845`両方で変更）: WSL2からのWebSocket `/ws/control` 接続が不安定になっている場合、ステータス更新やGoLive/Stop操作に影響する可能性
- **broadcast.htmlのElectron IPC削除**（`275e1e8`）: 削除自体は正しいが、残ったコードに未使用変数`useDirectCapture`が残っている等、副作用がないか確認

---

## 実施順序

1. **ステップ1**: 診断ログをMainForm.cs + control-panel.html + AudioLoopback.csに追加してビルド
2. **ステップ2**: C#アプリを起動してStopボタンをテスト → ログでバグ1の原因特定
3. **ステップ3**: 配信テストで音声途切れを確認 → ログでバグ2の原因特定
4. **ステップ4**: 原因に応じた修正を実施
5. **ステップ5**: 再テストで修正確認

## ファイル一覧

| ファイル | 役割 | `ea63845`での変更 |
|---------|------|------------------|
| `win-native-app/WinNativeApp/MainForm.cs` | WebView2パネルメッセージ処理、配信制御 | OnFormClosing大幅変更 |
| `win-native-app/WinNativeApp/control-panel.html` | UIパネル（Stop/GoLive/Volume） | 変更なし |
| `win-native-app/WinNativeApp/Server/HttpServer.cs` | HTTP/WebSocket API | WebSocket CloseAsync追加 |
| `win-native-app/WinNativeApp/Streaming/AudioLoopback.cs` | WASAPIループバックキャプチャ | Stop()にWaitOne追加 |
| `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs` | FFmpegプロセス管理・パイプ | Kill堅牢化、LogStderr改善 |
| `win-native-app/WinNativeApp/Streaming/StreamConfig.cs` | 配信設定 | 変更なし |
| `static/broadcast.html` | 配信合成ページ（AudioContext音声出力） | Electron IPC削除（`275e1e8`） |
