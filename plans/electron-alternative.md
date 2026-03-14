# Electron代替検討

## 背景・動機

現在のWindows側アプリはElectronで実装されている（`win-capture-app/main.js` 約1600行）。
Electronは全機能を単一フレームワークで実現できているが、以下の観点で代替を検討する。

- **軽量化**: Electronはバイナリ150-300MB、メモリ150-300MB消費
- **柔軟な実装**: Electron固有のAPIに縛られず、より自由度の高い実装が可能か

## 現行Electronアプリの機能一覧

| 機能 | 使用API | 代替難易度 |
|------|---------|-----------|
| オフスクリーンHTML/WebGLレンダリング | `BrowserWindow({offscreen: true})` + `paint`イベント | **高** |
| ウィンドウキャプチャ | `desktopCapturer.getSources()` + `getUserMedia` | **中** |
| FFmpegへのフレームパイプ | `child_process.spawn` + stdin書き込み | **低** |
| 音声ミキシング（BGM+TTS→PCM） | Node.js内でPCMデコード・リサンプル・ミキシング | **中** |
| 音声のHTTP PCMストリーム配信 | Express `/audio-pcm-stream` → FFmpeg | **低** |
| HTTPサーバー（API/MJPEG） | Express | **低** |
| WebSocket（制御/フレーム配信） | ws | **低** |
| IPC（broadcast.htmlとの通信） | `ipcMain`/`contextBridge` | **中** |
| スクリーンショット | `webContents.capturePage()` | **低** |
| FFmpegバイナリ自動取得 | PowerShellスクリプト | **低** |

## 代替候補の評価

### 1. Tauri（Rust + システムWebView）

| 項目 | 評価 |
|------|------|
| オフスクリーンWebGLレンダリング | **不可**。WRY（TauriのWebViewラッパー）は未サポート。[tao #289](https://github.com/tauri-apps/tao/issues/289)で要望あり、Servo統合で実験中だが未実装 |
| ウィンドウキャプチャ | 可能。[tauri-plugin-screenshots](https://github.com/ayangweb/tauri-plugin-screenshots)がxcap経由で提供 |
| WebGL安定性 | 問題あり。WebView2でのWebGLコンテキストロスト・ラグ・WebGL2未対応の報告([#6559](https://github.com/tauri-apps/tauri/issues/6559), [#8020](https://github.com/tauri-apps/tauri/issues/8020)) |
| バイナリ/メモリ | **大幅に小さい**: アプリ10MB以下、メモリ30-40MB |
| 開発言語 | Rust（バックエンド）+ JavaScript（フロントエンド） |
| **判定** | **不適合** — オフスクリーンレンダリング不可が致命的 |

### 2. Puppeteer + Headless Chrome（Node.js）

| 項目 | 評価 |
|------|------|
| オフスクリーンWebGLレンダリング | **可能**。CDP `HeadlessExperimental.beginFrame` で制御可能。[puppeteer-capture](https://www.npmjs.com/package/puppeteer-capture)が実証済み |
| FFmpegパイプ | **可能**。[node-puppeteer-rtmp](https://github.com/MyZeD/node-puppeteer-rtmp)がTwitch配信を実証済み |
| ウィンドウキャプチャ | **不可**（Chromium単体）。Win32 API `Windows.Graphics.Capture` のネイティブヘルパーが別途必要 |
| 音声ミキシング | 別途実装が必要（現行のNode.jsコードは流用可能） |
| システムトレイ | Puppeteer単体には無い。Node.js用トレイライブラリが必要 |
| バイナリ/メモリ | Chromium同梱ならElectronと同等。システムChromeを利用すれば追加バイナリ0 |
| パフォーマンス | `page.screenshot()` は~18fps。`beginFrame`方式は30fps可能だがチューニング必要 |
| 開発言語 | Node.js（現行と同じ） |
| **判定** | **最有望だが課題あり** — オフスクリーン+FFmpegは可能。ウィンドウキャプチャ・トレイ・音声が別途必要 |

#### Puppeteer方式の利点
- broadcast.htmlをそのまま利用可能（コード変更なし）
- Node.jsベースなので既存の音声ミキシングコードを流用可能
- システムにインストール済みChromeを利用すれば追加バイナリ不要
- IPC不要（CDPで直接ページとやりとり）

#### Puppeteer方式の課題
- ウィンドウキャプチャに別途ネイティブモジュールが必要（`Windows.Graphics.Capture` APIのNode.js addon等）
- `beginFrame`によるフレーム制御はExperimentalなCDP API
- システムトレイ等のUI要素を別ライブラリで実装する必要あり
- Electron preloadで提供していた`window.captureReceiver`、`window.audioCapture`の代替が必要

### 3. CEF（Chromium Embedded Framework, C++）

| 項目 | 評価 |
|------|------|
| オフスクリーンWebGLレンダリング | **最良**。OSRモードが最も成熟。`OnPaint()`/`OnAcceleratedPaint()`コールバック、D3D11共有テクスチャ対応 |
| ウィンドウキャプチャ | C++からWin32 API直接呼び出しで容易 |
| FFmpeg統合 | C++からFFmpegライブラリをリンクまたはサブプロセス起動 |
| バイナリ/メモリ | Electronと同等（Chromiumベース） |
| Pythonバインディング | [cefpython3](https://pypi.org/project/cefpython3/)は**メンテナンス停止**。最新Python非対応 |
| 開発言語 | C++（CefSharpなら.NET） |
| **判定** | **技術的に最適だが開発コストが高い** — C++移行が必要で、既存JS資産を活かせない |

### 4. NW.js

| 項目 | 評価 |
|------|------|
| オフスクリーンWebGLレンダリング | 可能（v0.29以降、MediaStream API） |
| ウィンドウキャプチャ | Electronと同様にChromiumのgetUserMedia利用可能 |
| バイナリ/メモリ | Electronと同等（Chromium+Node.jsバンドル） |
| エコシステム | Electronに比べ大幅に縮小。npmパッケージ互換性も限定的 |
| **判定** | **メリットが薄い** — Electronとほぼ同じアーキテクチャで軽量化にならない |

### 5. その他（不適合）

| 候補 | 不適合理由 |
|------|-----------|
| Neutralinojs | オフスクリーンレンダリング不可、他ウィンドウキャプチャ不可 |
| WebView2 (.NET) | オフスクリーンレンダリング公式未サポート（[#547](https://github.com/MicrosoftEdge/WebView2Feedback/issues/547)） |
| Flutter Desktop | HTML/WebGLのオフスクリーンレンダリング要件外。broadcast.htmlの全面書き直しが必要 |
| Playwright (Python) | Puppeteerと同種だがCDP低レベル制御はPuppeteerが成熟。次点 |

## 総合比較

| 代替案 | オフスクリーンWebGL | ウィンドウキャプチャ | バイナリ/メモリ | 開発コスト | 既存コード流用 |
|--------|:---:|:---:|:---:|:---:|:---:|
| **Electron（現行）** | ○ | ○ | 大 | - | - |
| **Windowsネイティブ (C#)** | ○（WGC経由） | ◎（WGC標準） | **小** | 高 | 低 |
| **Puppeteer + Chrome** | ○ | △（要ネイティブ） | 同等～小 | 中 | 高 |
| **CEF (C++)** | ◎ | ○ | 同等 | 高 | 低 |
| **Tauri** | × | ○ | 小 | 中 | 中 |
| **NW.js** | ○ | ○ | 同等 | 低 | 高 |

## Windowsネイティブで全て実装する場合

Electronもブラウザエンジンも使わず、Windows APIだけで実装するアプローチ。

### アーキテクチャ

```
┌────────────────────────────────────────────────┐
│  WebView2 (隠しウィンドウ)                       │
│  broadcast.html を表示（Three.js/WebGL/VRM）     │
│  ※ Windows 10/11標準搭載のEdge WebView          │
└──────────┬─────────────────────────────────────┘
           │ DirectComposition (WinRT Visual)
┌──────────▼─────────────────────────────────────┐
│  Windows.Graphics.Capture                       │
│  CreateFromVisual() → D3D11テクスチャ(BGRA)      │
│  ※ GPU上で完結、CPUコピー不要                     │
└──────────┬─────────────────────────────────────┘
           │ D3D11テクスチャ → CPU readback
┌──────────▼─────────────────────────────────────┐
│  FFmpeg (子プロセス)                             │
│  stdin: rawvideo BGRA → H.264エンコード          │
│  audio: 名前付きパイプ or stdin → AACエンコード    │
│  出力: FLV → RTMP → Twitch                      │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│  WASAPI アプリケーションループバック               │
│  WebView2プロセスの音声出力をキャプチャ            │
│  ※ Windows 10 build 20348+ (実質 Win11)         │
│  BGM + TTS → WebView2が再生 → WASAPIで取得       │
└──────────┬─────────────────────────────────────┘
           │ PCM (s16le/f32le)
           └──→ FFmpegの音声入力へ

┌────────────────────────────────────────────────┐
│  Windows.Graphics.Capture (別セッション)          │
│  他アプリのウィンドウキャプチャ                    │
│  HWND指定 → D3D11テクスチャ → JPEG変換           │
│  → WebView2内のbroadcast.htmlにJS注入で渡す       │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│  HTTP/WebSocketサーバー                          │
│  WSL2のFastAPIサーバーとの通信                    │
│  制御API・キャプチャ管理・ストリーム状態           │
└────────────────────────────────────────────────┘
```

### 各機能のWindows API対応

| 機能 | Windows API / ライブラリ | 実現性 |
|------|------------------------|--------|
| HTMLレンダリング | **WebView2** (Edge WebView, OS標準搭載) | ○ |
| フレーム取得 | **WebView2 CompositionController** + **Windows.Graphics.Capture** `CreateFromVisual()` | ○（実証済み） |
| ウィンドウキャプチャ | **Windows.Graphics.Capture** `CreateForWindow(HWND)` | ○（標準API） |
| 音声キャプチャ | **WASAPI Application Loopback** (プロセスID指定) | ○（Win10 20348+） |
| FFmpeg配信 | **child_process** (FFmpeg.exe) | ○ |
| HTTP/WSサーバー | 言語標準ライブラリ or 軽量フレームワーク | ○ |

### 実証済みの先行事例

| プロジェクト | 内容 |
|-------------|------|
| [GStreamer webview2src](https://gstreamer.freedesktop.org/documentation/webview2/index.html) | WebView2 → DirectComposition → WGC → GStreamerパイプライン。**本アプローチと同じ構成を本番品質で実装済み** |
| [pabloko/WebView2 D3D11 Gist](https://gist.github.com/pabloko/5b5bfb71ac52d20dfad714c666a0c428) | WebView2 → DirectComposition → WGC → D3D11テクスチャ。C++で完全な実装例 |
| [cantetfelix/WebViewToolkit](https://github.com/cantetfelix/WebViewToolkit) | WebView2 → DirectX テクスチャ。Unity向けだが~30fps達成 |
| [robmikh/Win32CaptureSample](https://github.com/robmikh/Win32CaptureSample) | WGC公式リファレンス実装（ウィンドウキャプチャ） |
| [MS ApplicationLoopback Sample](https://github.com/microsoft/windows-classic-samples/tree/main/Samples/ApplicationLoopback) | WASAPIプロセス別ループバックの公式サンプル |

### 開発言語の選択

| 言語 | WebView2 | WGC | WASAPI | HTTP/WS | 総合 |
|------|:---:|:---:|:---:|:---:|------|
| **C# / .NET** | ◎ 公式SDK | ◎ WinRT interop | ○ NAudio | ○ | **推奨** — API対応・開発速度のバランスが最良 |
| **C++/WinRT** | ◎ 公式 | ◎ ネイティブ | ◎ 直接COM | △ | 最高パフォーマンスだが開発コスト高 |
| **Rust** | ○ webview2-rs | ○ windows crate | ○ | ○ | 安全だがWindows固有APIのバインディングが薄い |
| **Python** | × バインディング無し | △ | △ | ◎ | WebView2が使えず不適合 |

### メリット

1. **Electronバイナリ不要**: WebView2はWindows 10/11に標準搭載。アプリ自体は数MB
2. **メモリ大幅削減**: Node.jsランタイム+Electronフレームワークが不要（概算: 150MB → 30-50MB）
3. **音声パイプラインの簡素化**: 現行のNode.js PCMデコード・ミキシング・HTTP PCMストリームが不要。WASAPIでWebView2の音声出力を直接キャプチャ → FFmpegへ
4. **ウィンドウキャプチャの改善**: WGCはElectronの`desktopCapturer`よりGPUフレンドリー
5. **柔軟性**: Windows APIを直接使えるため、Electronの制約に縛られない

### リスク・課題

| 課題 | 深刻度 | 詳細 |
|------|:---:|------|
| WebView2の隠しウィンドウ問題 | **高** | `put_IsVisible(FALSE)`で描画が止まる報告あり（[#1077](https://github.com/MicrosoftEdge/WebView2Feedback/issues/1077)）。画面外に配置する等のワークアラウンドが必要 |
| フレームレート制御 | **中** | WGCはVSyncに依存。独立したフレームレート制御にはタイマー+フレームドロップが必要 |
| WebView2フォーカス問題 | **中** | CompositionControllerでクリック時にOSレベルのフォーカスを奪う |
| WASAPI要件 | **中** | アプリケーションループバックはWindows 10 build 20348+（実質Win11）が必要 |
| WebView2プロセスPID追跡 | **中** | WebView2は複数プロセスを生成。WASAPI用に正しいPIDを特定する必要あり |
| 開発言語の変更 | **中** | 既存のNode.js/JavaScriptコード（main.js 1600行）をC#等で書き直す必要 |
| broadcast.htmlとの通信 | **低** | Electron IPCの代わりにWebView2の`ExecuteScriptAsync`やDevToolsProtocol等で対応可能 |

### 最短経路: GStreamerパイプライン方式

GStreamerの`webview2src`プラグインを使えば、映像パイプラインはほぼゼロコードで実現可能:

```bash
gst-launch-1.0 \
  webview2src location="http://localhost:8080/broadcast?token=xxx" ! \
  videoconvert ! x264enc tune=zerolatency bitrate=2500 ! \
  flvmux name=mux ! rtmpsink location="rtmp://live-tyo.twitch.tv/app/{KEY}" \
  wasapisrc loopback=true ! audioconvert ! voaacenc ! mux.
```

ただし:
- `webview2src`は音声非対応 → WASAPI別途キャプチャが必要
- ウィンドウキャプチャの統合は別途実装
- WSL2サーバーとの制御通信も別アプリが必要

### 実装コスト見積もり

| 項目 | Electronからの移行工数 |
|------|---------------------|
| WebView2 + WGC映像パイプライン | 大（新規C#実装） |
| WASAPIループバック音声 | 中（新規実装） |
| ウィンドウキャプチャ管理 | 小（WGC APIは直接的） |
| HTTP/WebSocketサーバー | 中（Node.js→C#移植） |
| FFmpeg制御 | 小（子プロセス起動は共通） |
| broadcast.htmlとの通信 | 中（IPC→WebView2 JS injection） |
| **合計** | **2-4週間**（C#経験者が専任の場合） |

### 判定

**技術的には実現可能で、軽量化の効果は大きい。** ただし:

- 全てC#（またはC++/Rust）で書き直す必要があり、開発コストは高い
- WebView2の隠しウィンドウ問題が最大のリスク（ワークアラウンドの安定性が不明）
- 音声キャプチャのWin11要件が環境を限定する
- GStreamer `webview2src`を活用すれば映像部分のコストは大幅に削減可能

**Electron維持 vs Windowsネイティブ（WebView2）の選択基準:**
- Electronの重さ（メモリ・バイナリ）が実際に問題になっているなら、移行する価値あり
- 現状で十分動いているなら、移行コストに見合わない

## WebViewなし — 完全ネイティブレンダリング

WebView2もブラウザエンジンも使わず、DirectXで直接レンダリングするアプローチ。
broadcast.htmlの全機能をネイティブコードで再実装する。

### broadcast.htmlが描画している全要素

現在broadcast.htmlがレンダリングしている内容の棚卸し:

| 要素 | 技術 | 複雑度 |
|------|------|--------|
| **VRMアバター** | Three.js + three-vrm（WebGL） | 高 |
| ├ アイドルアニメーション | sine波ベース（呼吸・体揺れ・頭・腕） | 中 |
| ├ まばたき | BlendShape `blink` 80ms周期 | 低 |
| ├ 耳ぴくぴく | BlendShape `ear_stand` 150-300ms | 低 |
| ├ リップシンク | BlendShape `aa` 30fpsフレーム制御 | 中 |
| └ 感情表現 | 任意BlendShape制御 | 低 |
| **背景画像** | `<img>` cover表示 | 低 |
| **TODOパネル** | HTML/CSS（テキスト、チェックボックス、パルスアニメーション） | 中 |
| **トピックパネル** | HTML/CSS（テキスト、ドットアニメーション） | 中 |
| **字幕パネル** | HTML/CSS（フェードイン/アウト、日英テキスト） | 中 |
| **ウィンドウキャプチャ表示** | `<img>` JPEG表示（複数枠、z-index制御） | 低 |
| **レイアウト編集UI** | ドラッグ＆リサイズ、スナップガイド | 高 |
| **音声再生** | `<audio>` TTS/BGM + AudioContext PCMキャプチャ | 中 |

### 各要素のネイティブ実装方法

#### VRMアバター（最大の課題）

VRM = glTFベースの3Dヒューマノイドモデル形式。ネイティブで扱うには以下が必要:

**方法A: ゲームエンジン活用**

| エンジン | VRM対応 | ヘッドレスレンダリング | 評価 |
|---------|---------|---------------------|------|
| **Unity + UniVRM** | ◎ 公式対応 | ○ `-batchmode -nographics`でレンダリング→RenderTexture→ReadPixels | **最も現実的** |
| **Godot + godot-vrm** | ○ コミュニティ対応 | × `--headless`でレンダリング無効化。オフスクリーン提案段階 | 不可 |
| **Unreal Engine** | △ VRM4Uプラグイン | ○ レンダリング可能だが巨大 | 過剰 |

**方法B: ネイティブレンダリング（自力実装）**

必要なライブラリの組み合わせ:

| レイヤー | C++ | C# / .NET |
|---------|-----|-----------|
| glTFローダー | [tinygltf](https://github.com/syoyo/tinygltf) | [SharpGLTF](https://github.com/vpenades/SharpGLTF) |
| VRM拡張パーサー | [VRM.h](https://github.com/nickvdp/VRM.h) | 自作（JSONパース） |
| 3Dレンダラー | [Filament](https://github.com/google/filament) / [bgfx](https://github.com/bkaradzic/bgfx) | [Veldrid](https://github.com/veldrid/veldrid) / SharpDX |
| MToonシェーダー | HLSL自作（[仕様書](https://github.com/vrm-c/vrm-specification/tree/master/specification/VRMC_materials_mtoon-1.0)参照） | 同左 |
| ボーンアニメーション | スケルタルアニメーション自作 | 同左 |
| BlendShape/MorphTarget | GPU MorphTarget自作 | 同左 |

**MToonシェーダーの再実装**: three-vrm、UniVRM、godot-vrmにGLSL/HLSL参照実装がある。トゥーンシェーディング+リムライト+アウトライン+テクスチャブレンドの実装が必要。

**工数見積もり（方法B）**: glTFロード+VRMパース+MToonシェーダー+ボーンアニメーション+BlendShape = **2-4ヶ月**（3Dグラフィックスエンジニア）

**方法C: libobs + obs-browser（OBSのレンダリングパイプライン活用）**

[libobs](https://github.com/obsproject/obs-studio) をライブラリとして使う:
- [obs-headless](https://github.com/a-rose/obs-headless) がGUIなしでの利用を実証
- シーン合成、エンコーダー管理、RTMP出力が組み込み
- ブラウザソースは内蔵CEFで描画（obs-browser）
- **ただしGPL-2.0ライセンス**、構成が複雑

#### 2Dオーバーレイ（パネル・字幕）

| 技術 | 概要 | 評価 |
|------|------|------|
| **Direct2D + DirectWrite** | Windows標準。D3D11とDXGI経由で直接合成可能 | ◎ テキスト描画品質が高い |
| **SkiaSharp** | Google SkiaのC#バインディング。クロスプラットフォーム | ○ 柔軟だが追加依存 |
| **ImGui** | 即時モードGUI。ゲーム/ツール向け | △ スタイリングが限定的 |

**Direct2D + DirectWriteの場合:**
1. D3D11でVRMを3Dレンダリング → レンダーターゲットテクスチャ
2. そのテクスチャのDXGIサーフェスを取得
3. D2Dレンダーターゲットを作成して2Dオーバーレイ（テキスト、パネル背景、ボーダー）を描画
4. 合成結果をステージングテクスチャにコピー → CPU readback → FFmpegへ

**再実装が必要なCSS機能:**
- グラデーション背景（`linear-gradient`）→ D2D `LinearGradientBrush`
- 角丸ボーダー → D2D `RoundedRectangle`
- `backdrop-filter: blur()` → D2Dエフェクト `GaussianBlur`（GPU）
- テキストシャドウ → D2Dで2回描画（ぼかし+本体）
- アニメーション（パルス、フェード）→ タイマーベースの補間
- vw/vh単位 → レンダリング解像度に対する比率計算

#### 音声

| 方式 | 概要 |
|------|------|
| **NAudio (.NET)** | WAV/MP3デコード、ミキシング、XAudio2バックエンド。現行のNode.js音声コードと同等の機能 |
| **XAudio2 (C++)** | DirectXオーディオAPI。低レイテンシ、ミキシング機能内蔵 |
| **WASAPI直接** | 最低レベル。アプリケーションループバックキャプチャでFFmpegに送信 |

音声パイプライン（WebViewあり版との違い）:
- WebView版: WebView2が`<audio>`で再生 → WASAPIループバックでキャプチャ
- ネイティブ版: NAudio/XAudio2で直接デコード・ミキシング → PCMをFFmpegにパイプ（**よりシンプル**）

### アーキテクチャ図

```
┌─────────────────────────────────────────────────────────┐
│  DirectX 11 レンダーパイプライン                          │
│                                                         │
│  ┌─────────────────┐  ┌────────────────────────────┐    │
│  │ VRM Renderer     │  │ Direct2D Overlay Renderer  │    │
│  │ (glTF+MToon)     │  │ (テキスト・パネル・字幕)     │    │
│  │                  │  │                            │    │
│  │ ボーン制御        │  │ TODOパネル                  │    │
│  │ BlendShape       │  │ トピックパネル               │    │
│  │ アイドルアニメ     │  │ 字幕（フェードアニメ）       │    │
│  └────────┬─────────┘  └──────────┬─────────────────┘    │
│           │ D3D11 Texture         │ D2D on DXGI Surface  │
│           └──────────┬────────────┘                      │
│                      │ 合成済みテクスチャ                  │
│  ┌───────────────────▼────────────────────────────────┐  │
│  │  背景画像 + VRM + オーバーレイ + キャプチャ画像       │  │
│  │  → ステージングテクスチャ → CPU readback             │  │
│  └───────────────────┬────────────────────────────────┘  │
└──────────────────────│──────────────────────────────────┘
                       │ BGRA raw frames
┌──────────────────────▼──────────────────────────────────┐
│  FFmpeg (子プロセス)                                     │
│  映像: stdin rawvideo → H.264                           │
│  音声: 名前付きパイプ PCM → AAC                          │
│  出力: FLV → RTMP → Twitch                              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  NAudio / XAudio2 音声エンジン                           │
│  TTS WAVデコード + BGM MP3/OGGデコード                    │
│  → PCMミキシング → FFmpegへパイプ                         │
│  （WebView不要、WASAPI不要）                              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Windows.Graphics.Capture                               │
│  他アプリのウィンドウ → D3D11テクスチャ → 合成に組み込み   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  HTTP/WebSocketサーバー                                  │
│  WSL2 FastAPIとの通信、制御API                           │
└─────────────────────────────────────────────────────────┘
```

### メリット

1. **ブラウザエンジン完全排除**: Chromium/Edge不要。バイナリサイズ数十MB、メモリ30-50MB
2. **音声パイプライン最適**: WebViewのオーディオ出力を回り道してキャプチャする必要なし。PCMを直接生成してFFmpegに渡せる
3. **フレームレート完全制御**: VSync制約なし。任意のfpsでレンダリング→FFmpegパイプ可能
4. **レンダリング品質**: DirectX直接制御でアンチエイリアス、シェーダー等を完全カスタマイズ
5. **レイアウト変更の柔軟性**: CSS制約なし。パネル配置・アニメーション・エフェクトを自由に実装

### リスク・課題

| 課題 | 深刻度 | 詳細 |
|------|:---:|------|
| **VRM/MToonシェーダー再実装** | **極高** | Three.js three-vrmが担っていたglTFロード+VRM拡張+MToonシェーダー+ボーンアニメーション+BlendShapeを全てネイティブで再実装。3Dグラフィックスの深い知識が必要 |
| **CSS → Direct2D変換** | **高** | グラデーション、角丸、blur、テキストシャドウ、アニメーションをD2Dプリミティブで再実装。CSSほどの表現力を出すには手間がかかる |
| **レイアウト編集UI** | **高** | broadcast.htmlのドラッグ＆リサイズ・スナップガイド・コンテキストメニューをネイティブUIで再実装 |
| **broadcast.htmlとの二重メンテ** | **中** | 移行期間中、broadcast.html（WSL2プレビュー用）とネイティブレンダラーの両方をメンテする必要 |
| **開発期間** | **高** | VRM+オーバーレイ+音声+キャプチャ+UI = **3-6ヶ月**（方法B）、Unity活用でも**1-2ヶ月** |

### 現実的な選択肢の比較

| 方式 | VRM難易度 | 2D難易度 | 開発期間 | バイナリ | メモリ |
|------|:---:|:---:|:---:|:---:|:---:|
| **A: Unity + UniVRM ヘッドレス** | ◎ 対応済み | ○ uGUI/UGUI | 1-2ヶ月 | 大（200MB+） | 中（100-200MB） |
| **B: C# Veldrid + SharpGLTF + D2D** | △ MToon自作 | ○ D2D/SkiaSharp | 3-6ヶ月 | 小（20-40MB） | 小（30-50MB） |
| **C: libobs + obs-browser** | ○ CEFで既存HTML | ○ CEFで既存HTML | 1-2ヶ月 | 大（200MB+） | 大（200MB+） |
| **D: C++ Filament + D2D** | △ MToon自作 | ○ D2D | 4-6ヶ月 | 小（15-30MB） | 小（20-40MB） |

### 判定

**完全ネイティブ（方法B/D）は技術的挑戦としては面白いが、VRM+MToonシェーダーの再実装が極めて重い。**

- **最軽量を求めるなら**: 方法B（C# Veldrid）だが3-6ヶ月かかる
- **VRMを簡単に扱いたいなら**: 方法A（Unity）だがバイナリ/メモリはElectronと同等以上
- **既存資産を活かすなら**: 前セクションのWebView2方式が最もバランスが良い

**ブラウザ排除の最大ボトルネックはVRM/MToonであり、それ以外（2Dオーバーレイ、音声、キャプチャ）はネイティブの方がシンプル。**

## 結論

### 現時点ではElectron継続が最も合理的

**理由:**
1. **オフスクリーンWebGLレンダリング + フレームバッファ取得 + ウィンドウキャプチャ + 音声ミキシング**を単一フレームワークで実現できるのはElectronのみ
2. **Windowsネイティブ（WebView2+WGC+WASAPI）** は技術的に最も魅力的な代替。軽量化効果が大きい（メモリ1/3以下）。ただし全コードをC#等で書き直す必要があり、WebView2の隠しウィンドウ問題（描画停止）が最大のリスク
3. 最有望なPuppeteer方式でも、ウィンドウキャプチャ・システムトレイ・音声ルーティングを別途実装する必要があり、結局Chromiumバイナリサイズは同等
4. CEFは技術的に最も優れたOSRを持つが、C++への移行コストが大きすぎる
5. Tauriは軽量だが、最も重要なオフスクリーンレンダリングが不可能

### 将来的に再検討する条件

| 条件 | 有望な代替 | 影響 |
|------|-----------|------|
| Tauriがオフスクリーンレンダリングを正式サポート（Servo統合） | Tauri | バイナリ/メモリが1/5以下に |
| ウィンドウキャプチャ機能を廃止できる場合 | Puppeteer + システムChrome | 追加バイナリ0、Electron不要 |
| プロジェクトがC++開発リソースを持つ場合 | CEF | 最高パフォーマンスのOSR |

### 短期的な改善策（Electron維持のまま）

Electronを使い続ける前提で、軽量化・柔軟性の改善が可能な施策:

1. **Electron Fuses**: 不要な機能を無効化してバイナリサイズ・攻撃面を削減
2. **electron-builder最適化**: asar圧縮、不要ファイル除外でパッケージサイズ削減
3. **Node.js統合の分離**: 音声ミキシング等をWorkerスレッドに分離してメインプロセスの負荷軽減
4. **CDPプロトコル活用**: Electron内蔵のChromium DevTools Protocolで、Puppeteer的な柔軟制御を実現

## 参考リンク

### Windowsネイティブ
- [WebView2 OSR要望 (#547)](https://github.com/MicrosoftEdge/WebView2Feedback/issues/547)
- [WebView2 隠しウィンドウ問題 (#1077)](https://github.com/MicrosoftEdge/WebView2Feedback/issues/1077)
- [WebView2 → D3D11テクスチャ (pabloko)](https://gist.github.com/pabloko/5b5bfb71ac52d20dfad714c666a0c428)
- [GStreamer webview2srcプラグイン](https://gstreamer.freedesktop.org/documentation/webview2/index.html)
- [Win32CaptureSample (WGCリファレンス)](https://github.com/robmikh/Win32CaptureSample)
- [WebViewToolkit (Unity向け)](https://github.com/cantetfelix/WebViewToolkit)
- [WASAPI ApplicationLoopback公式サンプル](https://github.com/microsoft/windows-classic-samples/tree/main/Samples/ApplicationLoopback)
- [windows-capture (Rust/Python)](https://github.com/NiiightmareXD/windows-capture)

### その他
- [Tauri OSR要望 (tao #289)](https://github.com/tauri-apps/tao/issues/289)
- [puppeteer-capture (beginFrame方式)](https://www.npmjs.com/package/puppeteer-capture)
- [node-puppeteer-rtmp (Twitch配信実証)](https://github.com/MyZeD/node-puppeteer-rtmp)
- [CEF OSR WebGL](https://magpcss.org/ceforum/viewtopic.php?f=10&t=13717)
- [Tauri vs Electron比較 (DoltHub)](https://www.dolthub.com/blog/2025-11-13-electron-vs-tauri/)

## ステータス
- 作成日: 2026-03-14
- 状態: 検討完了 — 現時点ではElectron継続を推奨
