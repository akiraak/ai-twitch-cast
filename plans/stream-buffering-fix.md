# 配信バッファリング（くるくる）問題の分析と改善

## ステータス: Phase 1-3 実装済み

## 背景

Twitch配信中にバッファリングインジケータ（くるくる）が視聴者に表示される問題。配信パイプライン全体（WebView2レンダリング → WGCキャプチャ → BGRA→NV12変換 → FFmpegエンコード → RTMP送信 → Twitch CDN）のどこかでデータ供給が途切れると発生する。

### 現在の配信パイプライン

```
broadcast.html (WebView2)
  → WGC (Windows Graphics Capture)
    → BGRA→NV12変換 (ThreadPool)
      → 名前付きパイプ (8MBバッファ)
        → FFmpeg (エンコード+RTMP送信)
          → Twitch Ingest Server
            → 視聴者
```

```
音声生成 (10msタイマー)
  → BGM + SE + TTS ミキシング
    → 名前付きパイプ (64KBバッファ)
      → FFmpeg (AACエンコード)
```

## 原因分析

### 原因1: VBVバッファサイズが小さすぎる（最有力）

**現在の設定** (`FfmpegProcess.cs:138-140`):
```
-b:v 2500k
-maxrate 2500k
-bufsize 1250k    ← bitrate/2 = わずか0.5秒分
```

**問題**: CBRモードで `bufsize = bitrate/2` は非常にタイト。ネットワークが一瞬でも揺らぐとFFmpegがフレームを出力できなくなり、Twitchがバッファリング表示する。

**Twitch推奨値**: bufsize = bitrate × 2（4〜5秒分）。現在は推奨の **1/4** しかない。

**影響度**: ★★★★★（最も影響大）

### 原因2: キーフレーム間隔が長い

**現在の設定** (`FfmpegProcess.cs:142`):
```
-g 60    ← fps*2 = 2秒に1回のキーフレーム
```

**問題**: キーフレーム間隔が2秒だと、Twitchが新規視聴者に配信を表示するまで最大2秒かかる。また、バッファリングからの復帰にも時間がかかる。Twitchは `-g 2` (2秒) を推奨しているので設定自体は合っているが、ネットワーク不安定時には短い方が復帰が早い。

**影響度**: ★★☆☆☆（通常時は問題ないが復帰速度に影響）

### 原因3: フレームドロップの連鎖

**現在の挙動** (`FfmpegProcess.cs:261-264`):
```csharp
if (_writingVideo)           // 前のフレームがまだ書き込み中
{
    Interlocked.Increment(ref _dropCount);
    return;                  // フレーム破棄
}
```

**問題**: BGRA→NV12変換（`ColorConverter.BgraToNv12`）が33ms以上かかると次のフレームがドロップ。連続ドロップするとFFmpegへのフレーム供給が途切れ、出力ストリームに穴が開く。

**関連**: NV12変換はCPU処理。CPU負荷が高い時（AI応答生成中、TTS生成中など）に影響を受けやすい。

**影響度**: ★★★☆☆

### 原因4: 名前付きパイプの書き込みブロック

**現在の挙動** (`FfmpegProcess.cs:288`):
```csharp
_videoPipe!.Write(nv12, 0, nv12WriteSize);  // タイムアウトなし、ブロック可
```

**問題**: FFmpegがエンコードに時間がかかるとパイプバッファ（8MB ≈ 5-6フレーム分）が埋まり、`Write()`がブロック。ThreadPoolタスクが詰まるとフレームドロップが加速する。

**影響度**: ★★★☆☆

### 原因5: 音声タイマーのジッター

**現在の設定** (`FfmpegProcess.cs:416`):
```csharp
_audioGenTimer = new Timer(AudioGenCallback, null, 10, 10);  // 10msインターバル
```

**問題**: Windows標準タイマーの分解能は約15.6ms。10ms指定でも実際は15〜16msで発火。音声生成量にジッターが生じ、FFmpegへの音声供給が不安定になる。音声が途切れるとTwitchプレーヤーがバッファリング表示することがある。

**影響度**: ★★☆☆☆

### 原因6: エンコーダの選択

**現在の設定** (`StreamConfig.cs:10,15`):
```csharp
public string Preset { get; set; } = "ultrafast";
public string Encoder { get; set; } = "auto";
```

**問題**: auto検出でHWエンコーダが見つからないと `libx264` にフォールバック。libx264はCPUエンコードなので:
- 1280x720@30fpsでもCPU負荷が高い
- 他のCPU処理（NV12変換、AI推論待ちのスレッド）と競合
- `ultrafast` プリセットでも speed < 1.0x になり得る

**確認方法**: FFmpegログで `[FFmpeg] Encoder:` を確認。`libx264` なら要対策。

**影響度**: ★★★★☆（libx264使用時のみ）

### 原因7: broadcast.html初期化の遅延

**現在の挙動** (`static/js/broadcast/init.js`):
```javascript
// 10以上のAPIコールを逐次実行
await fetch('/api/background/list');
await fetch('/api/overlay');
await fetch('/api/volume');
// ...さらに7-8個のfetch
```

**問題**: init.jsで10以上のfetch呼び出しが逐次実行される。サーバーが重い時に初期化が遅れ、WebView2のキャプチャ開始後もページが完全にレンダリングされていない状態が続く。

**影響度**: ★☆☆☆☆（起動時のみ、配信中のくるくるとは別問題の可能性）

## 改善策

### Phase 1: FFmpeg設定の最適化（即効性◎、リスク低）

配信アプリの再ビルドだけで対応可能。コードの変更は最小限。

#### 1-1. VBVバッファサイズを拡大

```csharp
// FfmpegProcess.cs:140 — 現在
$"-bufsize {ParseBitrateKbps(_config.VideoBitrate) / 2}k",

// 改善案: bitrate × 2（Twitch推奨値）
$"-bufsize {ParseBitrateKbps(_config.VideoBitrate) * 2}k",
```

| 設定 | 現在 | 改善後 | Twitch推奨 |
|------|------|--------|-----------|
| bufsize | 1250k (0.5秒) | 5000k (2秒) | bitrate×2 |

**効果**: ネットワークの一時的な揺らぎを吸収。最も即効性がある変更。

#### 1-2. ビットレートの見直し

```
現在: 2500k (720p@30fpsには十分だが余裕が少ない)
推奨: 3000k〜4000k (Twitchの720p推奨は3000k)
```

CLIオプション `--bitrate 3500k` で変更可能（コード変更不要）。

#### 1-3. FFmpegの追加フラグ

```
-fflags +nobuffer        # 入力バッファリングを最小化
-flush_packets 1         # パケット即時フラッシュ
```

### Phase 2: フレーム供給の安定化（効果高、変更中程度）

#### 2-1. NV12変換時間の監視・警告

```csharp
// FfmpegProcess.cs:281-296 — 既存のログを閾値で警告レベルに
var convertMs = sw.ElapsedMilliseconds;
if (convertMs > 25) // フレーム間隔の75%超えたら警告
    Log.Warning("[FFmpeg] NV12 conversion slow: {Ms}ms (threshold 25ms)", convertMs);
```

#### 2-2. パイプ書き込みのタイムアウト

```csharp
// 現在: タイムアウトなし（ブロック）
_videoPipe!.Write(nv12, 0, nv12WriteSize);

// 改善: CancellationTokenで50ms制限
using var cts = new CancellationTokenSource(50);
try {
    await _videoPipe!.WriteAsync(nv12.AsMemory(0, nv12WriteSize), cts.Token);
} catch (OperationCanceledException) {
    Interlocked.Increment(ref _dropCount);
    Log.Warning("[FFmpeg] Video pipe write timeout (50ms)");
}
```

#### 2-3. FFmpeg speed監視

```csharp
// LogStderrAsync内でspeed=値をパース
// speed < 0.95 が5秒以上続いたら警告ログ
var match = Regex.Match(line, @"speed=\s*([\d.]+)x");
if (match.Success && double.Parse(match.Groups[1].Value) < 0.95)
    Log.Warning("[FFmpeg] Encoding falling behind: speed={Speed}x", match.Groups[1].Value);
```

### Phase 3: 音声パイプラインの安定化（効果中、変更中程度）

#### 3-1. 高分解能タイマーの使用

```csharp
// Windows Multimedia Timer API で1ms精度を確保
[DllImport("winmm.dll")]
private static extern uint timeBeginPeriod(uint period);

// アプリ起動時
timeBeginPeriod(1);  // タイマー分解能を1msに設定
```

#### 3-2. 音声パイプバッファの拡大

```csharp
// 現在: 64KB (166ms) → 改善: 256KB (666ms)
_audioPipe = new NamedPipeServerStream(_audioPipeName, PipeDirection.Out, 1,
    PipeTransmissionMode.Byte, PipeOptions.None, 0, 256 * 1024);
```

### Phase 4: ネットワーク耐性の向上（効果中、変更大）

#### 4-1. Twitch Ingestサーバーの最適化

```csharp
// 現在: 固定で東京サーバー
public string RtmpUrl { get; set; } = "rtmp://live-tyo.twitch.tv/app";

// 改善: 自動選択または--rtmp-urlで柔軟に変更可能（既に対応済み）
```

Twitchの [Ingest Endpoints API](https://dev.twitch.tv/docs/video-broadcast/) で最寄りサーバーを確認し、latencyが低いものを選択。

#### 4-2. FFmpegの再接続設定

```
-reconnect 1
-reconnect_streamed 1
-reconnect_delay_max 2
```

RTMPの接続が不安定な場合に自動再接続を試行。

## 推奨実装順序

| 優先度 | 対策 | 工数 | 期待効果 |
|--------|------|------|----------|
| **1** | VBVバッファ拡大 (1-1) | 1行変更 | ★★★★★ |
| **2** | ビットレート見直し (1-2) | CLI引数のみ | ★★★☆☆ |
| **3** | エンコーダ確認 | ログ確認のみ | ★★★★☆ |
| **4** | FFmpeg追加フラグ (1-3) | 2行追加 | ★★★☆☆ |
| **5** | speed監視 (2-3) | 10行追加 | ★★☆☆☆ (診断用) |
| **6** | NV12変換警告 (2-1) | 3行追加 | ★★☆☆☆ (診断用) |
| **7** | パイプ書き込みタイムアウト (2-2) | 10行変更 | ★★★☆☆ |
| **8** | 高分解能タイマー (3-1) | 5行追加 | ★★☆☆☆ |
| **9** | 音声バッファ拡大 (3-2) | 1行変更 | ★★☆☆☆ |

## 診断手順

くるくるが発生した時の調査手順:

### Step 1: FFmpegログ確認
```
# C#アプリのコンソールまたはログファイルで確認
[FFmpeg] Encoder: h264_nvenc       ← HWエンコーダ使用中か？
[FFmpeg] NV12 convert=Xms write=Yms, frames=F drops=D   ← ドロップ数は？
```

### Step 2: エンコード速度確認
FFmpeg stderrに `speed=` 値が出力される:
- `speed >= 1.0x` → エンコードは問題なし、ネットワークが原因
- `speed < 1.0x` → エンコードが追いつけていない

### Step 3: ネットワーク確認
```bash
# Twitch Ingestサーバーへのping/traceroute
ping live-tyo.twitch.tv
# 帯域テスト（配信ビットレート+30%の余裕が必要）
# 2500k配信 → 3250kbps以上の上り帯域が必要
```

### Step 4: CPU/GPU負荷確認
- タスクマネージャーでCPU使用率確認
- libx264使用中にCPU 80%超えていたらHWエンコーダに切り替え

## 関連ファイル

| ファイル | 役割 |
|----------|------|
| `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs` | FFmpegプロセス管理・パイプ・エンコード設定 |
| `win-native-app/WinNativeApp/Streaming/StreamConfig.cs` | 配信パラメータ（解像度・ビットレート・エンコーダ） |
| `win-native-app/WinNativeApp/Capture/FrameCapture.cs` | WGCフレームキャプチャ・FPSスロットル |
| `win-native-app/WinNativeApp/MainForm.cs` | WebView2管理・キャプチャ開始 |
| `static/js/broadcast/init.js` | broadcast.html初期化（逐次API呼び出し） |
| `plans/latency-skip-catchup.md` | 遅延検知・復帰機能（関連プラン） |

## リスク

| リスク | 影響度 | 対策 |
|--------|--------|------|
| bufsize拡大でエンコード遅延増加 | 低 | `+low_delay`フラグと併用、実測で確認 |
| ビットレート上げすぎで帯域不足 | 中 | 上り帯域をspeedtest等で事前確認 |
| HWエンコーダ非対応環境 | 中 | auto検出+libx264フォールバック（既存） |
| タイマー分解能変更の副作用 | 低 | アプリ終了時に`timeEndPeriod(1)`で元に戻す |

## 参考: Twitch推奨配信設定（720p30）

| パラメータ | Twitch推奨 | 現在の設定 |
|-----------|-----------|-----------|
| 解像度 | 1280x720 | 1280x720 ✅ |
| FPS | 30 | 30 ✅ |
| ビットレート | 3000-4500 kbps | 2500 kbps ⚠️ |
| キーフレーム | 2秒 | 2秒 ✅ |
| エンコーダ | x264/NVENC | auto (OK) ✅ |
| VBVバッファ | ビットレート×2 | ビットレート/2 ✕ |
