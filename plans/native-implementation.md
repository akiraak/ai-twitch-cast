# Electronをネイティブ実装に変更

## 背景

現在のWindows側配信アプリはElectron（`win-capture-app/main.js` 約1600行）で実装されている。
Electronはバイナリ150-300MB、メモリ150-300MBを消費し、Node.js + Chromium のフルスタックが同梱される。

[Electron代替検討](electron-alternative.md) と [ネイティブレンダリング調査](native-rendering-research.md) の結果を踏まえ、
**C# / .NET + WebView2** による Windows ネイティブ実装への移行を計画する。

## 方針

**WebView2方式（ブラウザエンジンはWebView2で維持）** を採用する。

- broadcast.html はそのまま活用（Three.js/VRM/CSS をネイティブで再実装しない）
- Electronが担っている「画面外でHTMLをレンダリング → フレーム取得 → FFmpegに渡す」部分をWindows APIに置き換える
- 音声パイプラインをWASAPIループバックで簡素化

### 完全ネイティブレンダリング（VRM/MToon自力実装）を選ばない理由

- VRM + MToonシェーダーの再実装だけで3-6ヶ月かかる
- broadcast.html との二重メンテが発生する
- Three.js/three-vrm のエコシステムを捨てるメリットが薄い

## 現行 → 新アーキテクチャ比較

```
【現行: Electron】
  Electron BrowserWindow (offscreen: true)
    → paint イベント → toBitmap() → BGRA
    → Node.js 音声ミキサー (TTS+BGM → PCM)
    → Express HTTP/WS サーバー
    → FFmpeg 子プロセス → RTMP → Twitch

【新: C# + WebView2】
  WebView2 CompositionController (隠しウィンドウ)
    → Windows.Graphics.Capture → D3D11テクスチャ → BGRA
    → WASAPI ループバック (WebView2プロセスの音声出力)
    → HTTP/WS サーバー (ASP.NET Minimal API)
    → FFmpeg 子プロセス → RTMP → Twitch
```

### 主な改善点

| 項目 | Electron | C# + WebView2 |
|------|---------|----------------|
| バイナリサイズ | 150-300MB | 数MB（WebView2はOS標準） |
| メモリ使用量 | 150-300MB | 30-50MB |
| 音声パイプライン | Node.js PCMデコード → リサンプル → ミキシング → HTTP → FFmpeg | WASAPI ループバック → FFmpeg（直接キャプチャ） |
| ウィンドウキャプチャ | desktopCapturer (Chromium API) | Windows.Graphics.Capture (OS標準API、GPU効率◎) |
| フレーム取得 | paint イベント + toBitmap() | WGC CreateFromVisual() → D3D11テクスチャ |

## 移行対象の機能マッピング

| Electron機能 | Windows API / ライブラリ | 実装難易度 |
|-------------|------------------------|-----------|
| `BrowserWindow({offscreen: true})` | **WebView2 CompositionController** + 画面外ウィンドウ配置 | 中 |
| `paint` イベント → `toBitmap()` | **Windows.Graphics.Capture** `CreateFromVisual()` → D3D11テクスチャ | 中 |
| `desktopCapturer` ウィンドウキャプチャ | **Windows.Graphics.Capture** `CreateForWindow(HWND)` | 低（標準API） |
| Node.js 音声ミキサー（BGM+TTS→PCM） | **WASAPI Application Loopback**（WebView2プロセスの音声をキャプチャ） | 中 |
| Express HTTP サーバー | **ASP.NET Minimal API** or Kestrel | 低 |
| ws WebSocket サーバー | **ASP.NET WebSocket** | 低 |
| `child_process.spawn` FFmpeg | **System.Diagnostics.Process** | 低 |
| Electron IPC（broadcast.html通信） | **WebView2 `ExecuteScriptAsync()`** + `WebMessageReceived` | 低 |
| electron-builder パッケージング | **dotnet publish** (single file) | 低 |

## 実装ステップ

### Phase 1: 基盤（WebView2 + フレーム取得）

1. C# .NET プロジェクト作成（WinForms or WPF、ウィンドウは非表示前提）
2. WebView2 CompositionController でbroadcast.htmlを表示
3. Windows.Graphics.Capture でWebView2の描画内容をD3D11テクスチャとして取得
4. テクスチャ → BGRA → ファイル保存で映像取得を検証

**検証ポイント:**
- WebView2の隠しウィンドウで描画が止まらないか（`put_IsVisible(FALSE)` 問題 [#1077](https://github.com/MicrosoftEdge/WebView2Feedback/issues/1077)）
- WebGLが正常に動作するか（VRMアバターが描画されるか）
- フレームレートが30fps出るか

### Phase 2: FFmpeg配信パイプライン

5. FFmpegを子プロセスとして起動、BGRA生フレームをstdinにパイプ
6. WASAPI Application Loopbackで WebView2プロセスの音声出力をキャプチャ
7. 音声PCMをFFmpegの音声入力に接続（名前付きパイプ or stdin）
8. RTMP出力でTwitch配信を検証

### Phase 3: ウィンドウキャプチャ

9. Windows.Graphics.Capture でHWND指定のウィンドウキャプチャ実装
10. キャプチャフレーム → JPEG → broadcast.htmlに転送（WebView2 JS injection）
11. キャプチャ管理API（追加・削除・一覧）

### Phase 4: サーバー通信

12. HTTP/WebSocket サーバー実装（ASP.NET Minimal API）
13. WSL2 FastAPIサーバーとの `/ws/control` 通信
14. キャプチャフレーム配信用 `/ws/capture`
15. broadcast.html との通信（Electron IPC → WebView2 JS injection）

### Phase 5: 統合・移行

16. 管理UIからの Go Live / Stop 制御
17. システムトレイアイコン（NotifyIcon）
18. 自動起動・エラー回復
19. Electronアプリとの並行テスト → 切り替え

## リスクと対策

| リスク | 深刻度 | 対策 |
|--------|:---:|------|
| WebView2 隠しウィンドウで描画停止 | **高** | 画面外(-32000,-32000)に配置 / 最小化せず1x1ピクセルウィンドウ / CompositionController活用 |
| WASAPI ループバックの Win11 要件 | **中** | Win10 build 20348+ が必要。対象環境を確認。代替: NAudio直接ミキシング（Electron方式と同等） |
| WebView2 プロセスPID特定 | **中** | `CoreWebView2Environment.BrowserProcessId` で取得可能 |
| WGC フレームレート制御 | **中** | WGCはVSync依存。タイマー+フレームドロップで30fps調整 |
| broadcast.html の Electron IPC 依存 | **低** | `window.audioCapture` / `window.captureReceiver` を WebView2 JS injection で互換実装 |

## 先行事例（実証済み）

| プロジェクト | 内容 |
|-------------|------|
| [GStreamer webview2src](https://gstreamer.freedesktop.org/documentation/webview2/index.html) | WebView2 → DirectComposition → WGC → GStreamerパイプライン。**本アプローチと同じ構成** |
| [pabloko/WebView2 D3D11 Gist](https://gist.github.com/pabloko/5b5bfb71ac52d20dfad714c666a0c428) | WebView2 → DirectComposition → WGC → D3D11テクスチャ。C++完全実装例 |
| [robmikh/Win32CaptureSample](https://github.com/robmikh/Win32CaptureSample) | WGC公式リファレンス実装 |
| [MS ApplicationLoopback Sample](https://github.com/microsoft/windows-classic-samples/tree/main/Samples/ApplicationLoopback) | WASAPIプロセス別ループバック公式サンプル |

## GStreamer ショートカット（オプション）

GStreamerの`webview2src`を活用すれば、映像パイプラインのコードをほぼ省略できる:

```bash
gst-launch-1.0 \
  webview2src location="http://localhost:8080/broadcast?token=xxx" ! \
  videoconvert ! x264enc tune=zerolatency bitrate=5000 ! \
  flvmux name=mux ! rtmpsink location="rtmp://live-tyo.twitch.tv/app/{KEY}" \
  wasapisrc loopback=true ! audioconvert ! voaacenc ! mux.
```

ただし、ウィンドウキャプチャ統合とWSL2制御通信は別途C#アプリが必要。

## 開発言語

**C# / .NET 8** を採用。

理由:
- WebView2 公式SDKがC#対応
- Windows.Graphics.Capture の WinRT interop が容易
- WASAPI は NAudio ライブラリで簡潔に扱える
- ASP.NET で HTTP/WebSocket サーバーが標準
- dotnet publish で単一バイナリ配布可能

## WSL2からのビルド

開発はWSL2上で行い、ビルド対象はWindows GUIアプリ（C# + WebView2 + WinRT API）。
WSL2 Linux上の .NET SDK ではWindowsデスクトップアプリのビルドに制約があるため、
**Windows側の `dotnet.exe` をWSL2から呼び出す方式**を採用する。

### 方式の比較

| 方式 | 動作 | WinForms/WPF | WinRT/COM | 速度 | 判定 |
|------|:---:|:---:|:---:|:---:|------|
| WSL2で `dotnet publish -r win-x64` | △ | NETSDK1100エラー | 未保証 | 良好 | **不採用** |
| ↑ + `EnableWindowsTargeting=true` | △ | ビルドは通るが差異あり | 未保証 | 良好 | **不安定** |
| **WSL2から `dotnet.exe` (Windows側) を呼ぶ** | **○** | **完全対応** | **完全対応** | 良好 | **推奨** |
| Docker (Linux) | × | 不可 | 不可 | — | 不可 |
| Docker (Windows) | ○ | 対応 | 対応 | 遅い | CI/CDのみ |

### 推奨: Windows側 dotnet.exe をWSL2から呼ぶ

WSL2はWindows実行ファイルを直接呼び出せる（`.exe` を付けるだけ）。
Windows側に .NET SDK がインストールされていれば、WSL2からビルドを完全に制御できる。

```bash
# パス変換
WIN_PATH=$(wslpath -w /mnt/c/Projects/win-native-app)

# ビルド
dotnet.exe build "$WIN_PATH" -c Release

# 公開（単一exe）
dotnet.exe publish "$WIN_PATH" -c Release -r win-x64 --self-contained -o "$WIN_PATH\\publish"
```

### ファイル配置の重要ポイント

**C#プロジェクトのソースはWindowsファイルシステム上に置く。**

| 配置場所 | dotnet.exe からのアクセス | ビルド速度 |
|---------|-------------------------|-----------|
| `/home/ubuntu/...` (WSL2 FS) | `\\wsl$\Ubuntu\...` (9Pプロトコル) | **非常に遅い** |
| `/mnt/c/Projects/...` (Windows FS) | `C:\Projects\...` (ネイティブ) | **高速** |

WSL2ファイルシステム上のファイルにWindows側dotnet.exeがアクセスすると、9Pプロトコル経由になり
ビルドが数倍〜10倍遅くなる。C#プロジェクトは `/mnt/c/` 以下に配置すること。

### ディレクトリ構成

```
/home/ubuntu/ai-twitch-cast/          ← WSL2 FS（Python/サーバー側、git管理）
  ├── src/
  ├── scripts/
  ├── static/broadcast.html
  ├── win-native-app -> /mnt/c/Users/akira/Downloads/win-native-app  ← シンボリックリンク
  └── ...

/mnt/c/Users/akira/Downloads/win-native-app/  ← Windows FS（C#プロジェクト）
  └── WinNativeApp/
      ├── WinNativeApp.csproj
      ├── Program.cs
      ├── MainForm.cs
      ├── Capture/
      │   ├── Direct3DInterop.cs
      │   └── FrameCapture.cs
      └── bin/Release/                         ← ビルド成果物（.gitignore）
```

### post-commit ビルド統合

既存のワークフロー（post-commit hook → サーバー再起動）に、C#ビルドを追加できる。

```bash
#!/bin/bash
# .git/hooks/post-commit (追記)

# C#プロジェクトのビルド（変更があった場合のみ）
if git diff --name-only HEAD~1 HEAD | grep -q "win-native-app/"; then
    echo "[post-commit] Windows ネイティブアプリをビルド中..."
    WIN_PROJECT=$(wslpath -w /mnt/c/Projects/win-native-app)
    dotnet.exe publish "$WIN_PROJECT" -c Release -r win-x64 --self-contained -o "$WIN_PROJECT\\publish" 2>&1
    echo "[post-commit] ビルド完了"
fi
```

### Git管理

C#プロジェクトが `/mnt/c/` にある場合、2つの方式が考えられる:

**方式A: 同一リポジトリ（シンボリックリンク）**
```bash
# WSL2側のリポジトリからシンボリックリンク
ln -s /mnt/c/Projects/win-native-app /home/ubuntu/ai-twitch-cast/win-native-app
```
- git管理は一元化できる
- ただしWSL2 ↔ Windows FS間のシンボリックリンクは注意が必要

**方式B: 同一リポジトリ（Windows FS上にclone）**
```bash
# リポジトリ全体をWindows FSに置く
git clone ... /mnt/c/Projects/ai-twitch-cast
```
- Python側のファイルI/OがWSL2 FSより遅くなる（サーバー起動等に影響）

**方式C: サブモジュール or 別リポジトリ**
- C#プロジェクトを独立したリポジトリとして管理
- ai-twitch-cast からはサブモジュールとして参照
- ビルドスクリプトで同期

**推奨: 方式A（シンボリックリンク）** が最もシンプル。
現行の `win-capture-app/` と同じ位置に置き換える形で移行できる。

### デバッグ

- **開発/デバッグ**: Windows側のVisual Studio / VS Code で直接開く
- **WSL2からの操作**: ビルド・テスト実行・プロセス起動停止はすべて `.exe` 呼び出しで可能
- **ログ確認**: `dotnet.exe run` の標準出力はWSL2ターミナルにそのまま表示される

### CI/CD (GitHub Actions)

```yaml
# .github/workflows/build-windows.yml
jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '8.0'
      - run: dotnet publish win-native-app -c Release -r win-x64 --self-contained
```

## ログ設計

Claude Codeからログファイルを読んで問題を特定するワークフローのため、
**全コンポーネントでファイルへのログ出力を最初から組み込む**。

### ログファイル配置

```
/mnt/c/Users/akira/Downloads/win-native-app/
  └── logs/
      ├── app.log            ← アプリ全体のログ（Serilog ローリングファイル）
      ├── webview.log        ← WebView2 関連（ナビゲーション・JS エラー・IPC）
      ├── capture.log        ← WGC フレームキャプチャ（fps・ドロップ・テクスチャサイズ）
      ├── audio.log          ← WASAPI / 音声パイプライン（バッファ・レベル・エラー）
      └── ffmpeg.log         ← FFmpeg の stderr 出力をそのまま保存
```

### コンポーネント別ログ内容

| コンポーネント | ログ内容 |
|---------------|---------|
| **WebView2** | ページロード完了/失敗、WebGL初期化、JS例外、`WebMessageReceived` の内容 |
| **WGC (フレーム取得)** | フレームレート実測値、フレームドロップ数、テクスチャサイズ、GPU readback 時間 |
| **WASAPI (音声)** | キャプチャ開始/停止、バッファサイズ、サンプルレート、RMS レベル、プロセスPID |
| **FFmpeg** | 起動コマンド全文、stderr の全出力（エンコード速度・ドロップフレーム・エラー） |
| **HTTP/WS サーバー** | 接続・切断、受信コマンド、送信レスポンス |
| **制御フロー** | Go Live / Stop、各 Phase の開始・完了・エラー |

### 実装方針

```csharp
// Serilog でコンソール + ファイル同時出力
Log.Logger = new LoggerConfiguration()
    .MinimumLevel.Debug()
    .WriteTo.Console()
    .WriteTo.File("logs/app.log",
        rollingInterval: RollingInterval.Day,
        retainedFileCountLimit: 7,
        outputTemplate: "{Timestamp:HH:mm:ss.fff} [{Level:u3}] {SourceContext} {Message:lj}{NewLine}{Exception}")
    .CreateLogger();
```

- **Serilog** を採用（`Microsoft.Extensions.Logging` 経由）
- ローリングファイル（日次、7日保持）でディスク圧迫を防止
- タイムスタンプはミリ秒精度（フレーム処理のタイミング問題を追跡するため）
- `SourceContext` でコンポーネント名を出力（`WebView`, `Capture`, `Audio` 等）
- FFmpeg の stderr は別途リダイレクトで `ffmpeg.log` に書き出し

### Claude Code からの確認方法

WSL2側からWindows FS上のログを直接読める:

```bash
# 最新ログを確認
cat /mnt/c/Users/akira/Downloads/win-native-app/logs/app.log

# FFmpegエラーを確認
cat /mnt/c/Users/akira/Downloads/win-native-app/logs/ffmpeg.log

# Claude Code の Read ツールでも直接読める
# → /mnt/c/Users/akira/Downloads/win-native-app/logs/app.log
```

### ビルド時のログ

`dotnet.exe` の出力もファイルに保存して、ビルドエラーをClaude Codeから確認可能にする:

```bash
dotnet.exe publish "$WIN_PROJECT" -c Release 2>&1 | tee /mnt/c/Users/akira/Downloads/win-native-app/logs/build.log
```

## ディレクトリ構成（実際）

```
/home/ubuntu/ai-twitch-cast/win-native-app/   ← git管理（ソースはここ）
  └── WinNativeApp/
      ├── WinNativeApp.csproj
      ├── Program.cs                           ← エントリポイント（Serilog初期化）
      ├── MainForm.cs                          ← WebView2フォーム + キャプチャ管理 + HTTPサーバー統合
      ├── Capture/
      │   ├── Direct3DInterop.cs               ← D3D11/WinRT/WGC COM interop
      │   ├── FrameCapture.cs                  ← WGCフレームキャプチャ（配信用BGRA出力）
      │   ├── WindowCapture.cs                 ← 任意ウィンドウのWGCキャプチャ → JPEG出力
      │   ├── WindowEnumerator.cs              ← Win32 EnumWindowsでウィンドウ一覧取得
      │   └── CaptureManager.cs                ← 複数WindowCaptureセッション管理
      ├── Server/
      │   └── HttpServer.cs                    ← HTTP API（/windows, /capture, /snapshot等）
      └── Streaming/
          ├── FfmpegProcess.cs                 ← FFmpeg子プロセス管理
          ├── AudioLoopback.cs                 ← WASAPIループバック
          └── StreamConfig.cs                  ← 配信設定

/mnt/c/Users/akira/AppData/Local/win-native-app/ ← Windows FSビルドディレクトリ
  └── WinNativeApp/                              （stream.shがソースをコピーしてビルド）
```

## ステータス
- 作成日: 2026-03-14
- 状態: Phase 4 完了
- Phase 1 完了日: 2026-03-14
- Phase 1 検証結果:
  - WebView2: 隠しウィンドウ(-32000,-32000)で正常描画 (**問題なし**)
  - WGC: `TryCreateFromWindowId` + `Direct3D11CaptureFramePool` で1920x1080フレーム取得成功
  - フレームレート: 約30fps
  - CsWinRT interop: `MarshalInterface<T>.FromAbi()` + `IWinRTObject.NativeObject.ThisPtr` で解決
  - Vortice.Direct3D11 3.8.3 でD3D11テクスチャ操作
- Phase 2 完了日: 2026-03-14
- Phase 2 実装内容:
  - FFmpegProcess: 子プロセス管理（video stdin + audio named pipe → RTMP）
  - AudioLoopback: NAudio WasapiLoopbackCapture（システムワイドループバック、TODO: プロセス別に変更）
  - FrameCapture改修: OnFrameReadyコールバック + FPSスロットル + ステージングテクスチャ再利用
  - StreamConfig: 環境変数ベースの配信設定（STREAM_KEY/STREAM_RESOLUTION/STREAM_FPS/STREAM_BITRATE）
  - MainForm: --stream フラグで自動配信開始、StartStreamingAsync/StopStreamingAsync
  - ビルド確認: dotnet.exe build Release 成功
- Phase 3 完了日: 2026-03-14
- Phase 3 実装内容:
  - WindowEnumerator: Win32 EnumWindows P/Invokeでウィンドウ一覧取得（自プロセス・最小化・タイトルなし除外）
  - WindowCapture: WGC CreateFreeThreadedで任意HWND→D3D11テクスチャ→BGRA→JPEG変換（FPSスロットル付き）
  - CaptureManager: ConcurrentDictionaryで複数キャプチャセッション管理（スレッドセーフ）
  - HttpServer: HttpListenerベースのHTTP API（/status, /windows, /capture, /captures, /snapshot/{id}）
  - MainForm統合: WebView2 JS injection（addCaptureLayer/removeCaptureLayer）でbroadcast.htmlにキャプチャ表示
  - stream.sh: Server/ディレクトリのビルドコピー追加
  - ビルド確認: dotnet.exe build Release 成功
- Phase 4 完了日: 2026-03-14
- Phase 4 実装内容:
  - WebSocket `/ws/control`: HttpListenerベースのWebSocketアップグレード、JSON RPCプロトコル（requestIdマッチング）
  - 制御アクション: status, windows, start_capture, stop_capture, captures, start_stream, stop_stream, stream_status, screenshot, quit
  - Electron互換アクション: broadcast_open/close/status（常にtrue）、preview_open/close/status（C#では未使用）
  - HTTPストリーミング制御: POST /stream/start, POST /stream/stop, GET /stream/status, POST /quit
  - /stream/{id} → /snapshot/{id} 互換ルート追加
  - MainForm: 動的streamKey対応（WebSocket経由でstreamKeyを受け取り配信開始）
  - MainForm: WebView2 CapturePreviewAsync でスクリーンショット（PNG base64）
  - WSL2 FastAPIサーバーとの通信: 既存の `_ws_request()` がそのまま動作（同じプロトコル）
  - ビルド確認: dotnet.exe build Release 成功
