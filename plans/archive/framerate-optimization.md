# フレームレート最適化プラン

## 背景

C#ネイティブ配信アプリのTwitch配信テストで、**映像が約4fpsしか出ない**問題が発生。
Step 1-3の最適化で**18fps（0.922x speed）**まで改善したが、目標の30fpsには未達。

## 完了済み最適化（4fps → 18fps）

| Step | 内容 | 効果 |
|------|------|------|
| Step 1 | 名前付きパイプ（8MBバッファ） | stdin書き込み 250ms → 1ms |
| Step 2 | BGRA→NV12 CPU変換 | パイプ転送量 3.7MB → 1.4MB（63%削減） |
| Step 3 | HWエンコーダ自動検出（h264_nvenc） | CPUエンコード負荷解消 |
| 追加 | `-flush_packets 1`除去 | RTMP毎フレームフラッシュで0.748x speed |
| 追加 | サイレンスバッファ 10ms→100ms | 音声不足でFFmpegが0.1x speedに制限 |
| 追加 | デフォルトFPS 30→20 | GPU readback 55msに合わせた暫定値 |

## 現在のボトルネック

**D3D11 Map()のGPU完了待ち = ~55ms/frame**

```
OnFrameArrived (WGCコールバック、50msごと@20fps)
  └─ ExtractBgra
       ├─ CopyResource(staging, srcTexture)   ← GPUにコピー指示（非同期）
       ├─ Map(staging, Read)                   ← ★ GPU完了まで ~55ms ブロック
       ├─ MemoryCopy row-by-row (720行)        ← ~1ms
       └─ Unmap
  └─ OnFrameReady → FfmpegProcess.WriteVideoFrame
       ├─ BGRA→NV12 変換                       ← ~1ms
       └─ NamedPipe.Write                      ← ~1ms
```

**原因:** `CopyResource()`はGPUに非同期コマンドをキューイングするだけだが、直後の`Map()`がGPUパイプラインの全コマンド完了を待つ（暗黙のFlush）。DWMコンポジションやGPU負荷も影響し、実測55msのブロッキングが発生。

**結果:** 1000ms ÷ 55ms ≈ 18fps が上限。

## 改善戦略: ダブルステージングテクスチャ・パイプライン

### 基本原理

ステージングテクスチャを2枚用意し、**CopyResourceとMapを1フレームずらして実行**する。
Frame N-1のCopyResourceから50ms経過後（次フレーム到着時）にMapすれば、GPU完了待ちはほぼ0msになる。

```
Frame 1: Copy → staging[0]                              （初回はMapなし）
Frame 2: Copy → staging[1], Map staging[0] → 読み出し   （50ms経過後 → Map即座完了）
Frame 3: Copy → staging[0], Map staging[1] → 読み出し
Frame 4: Copy → staging[1], Map staging[0] → 読み出し
  ...
```

**トレードオフ:** 1フレーム（50ms @20fps）の遅延が追加される。Twitch配信では問題にならない。

### 期待改善

- Map(): 55ms → <1ms
- 1フレームあたり合計: ~3ms（Map + MemoryCopy + NV12変換 + パイプ書き込み）
- 達成可能FPS: 30fps以上（33ms budget >> 3ms actual）
- **デフォルトFPSを20→30に変更可能**

## 実装

### 変更ファイル: `Capture/FrameCapture.cs` のみ

### 変更内容

```csharp
// === フィールド追加 ===

// ダブルステージングテクスチャ
private ID3D11Texture2D?[] _stagingTextures = new ID3D11Texture2D?[2];
private int _stagingIdx;          // 次にCopyResourceする先のインデックス（0 or 1）
private bool _hasPendingFrame;    // 前フレームのCopyResourceが完了待ちか
private int _pendingWidth, _pendingHeight;

// 既存フィールドの削除:
// - _stagingTexture → _stagingTextures[2] に置き換え
// - _cachedWidth, _cachedHeight はそのまま（テクスチャ再作成判定用）


// === ExtractBgra → パイプライン化 ===

private unsafe void ExtractBgra(Direct3D11CaptureFrame frame, out int width, out int height)
{
    width = 0;
    height = 0;

    lock (_lock)
    {
        try
        {
            var textureGuid = typeof(ID3D11Texture2D).GUID;
            var texturePtr = Direct3DInterop.GetDXGISurfaceFromWinRT(
                frame.Surface, textureGuid);

            using var srcTex = new ID3D11Texture2D(texturePtr);
            var desc = srcTex.Description;
            int w = (int)desc.Width;
            int h = (int)desc.Height;

            EnsureStaging(w, h, desc.Format);

            // ① 前フレームのMapを先に実行（前回のCopyResourceから50ms経過 → 即座完了）
            if (_hasPendingFrame)
            {
                int readIdx = _stagingIdx ^ 1;  // 前フレームが書き込んだテクスチャ
                var mapped = _d3dContext!.Map(_stagingTextures[readIdx]!, 0, MapMode.Read);
                try
                {
                    int rw = _pendingWidth, rh = _pendingHeight;
                    // RowPitch == Width*4 なら一括コピー、違えば行ごと
                    if (mapped.RowPitch == rw * 4)
                    {
                        fixed (byte* dst = _frameBuffer!)
                        {
                            Buffer.MemoryCopy(
                                (void*)mapped.DataPointer, dst,
                                rw * rh * 4, rw * rh * 4);
                        }
                    }
                    else
                    {
                        for (int y = 0; y < rh; y++)
                        {
                            var src = (byte*)(mapped.DataPointer + y * mapped.RowPitch);
                            fixed (byte* dst = &_frameBuffer![y * rw * 4])
                            {
                                Buffer.MemoryCopy(src, dst, rw * 4, rw * 4);
                            }
                        }
                    }
                    width = rw;
                    height = rh;
                }
                finally
                {
                    _d3dContext.Unmap(_stagingTextures[readIdx]!, 0);
                }
            }

            // ② 今フレームのCopyResourceをキューイング（非同期、すぐ戻る）
            _d3dContext!.CopyResource(_stagingTextures[_stagingIdx]!, srcTex);
            _pendingWidth = w;
            _pendingHeight = h;
            _hasPendingFrame = true;
            _stagingIdx ^= 1;  // 次フレームは別のテクスチャに書き込む
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[Capture] ExtractBgra failed at frame {N}", _frameCount);
        }
    }
}


// === EnsureStaging → 2枚分作成 ===

private void EnsureStaging(int w, int h, Format fmt)
{
    if (_cachedWidth == w && _cachedHeight == h && _stagingTextures[0] != null)
        return;

    for (int i = 0; i < 2; i++)
    {
        _stagingTextures[i]?.Dispose();
        _stagingTextures[i] = _d3dDevice!.CreateTexture2D(new Texture2DDescription
        {
            Width = (uint)w,
            Height = (uint)h,
            MipLevels = 1,
            ArraySize = 1,
            Format = fmt,
            SampleDescription = new SampleDescription(1, 0),
            Usage = ResourceUsage.Staging,
            BindFlags = BindFlags.None,
            CPUAccessFlags = CpuAccessFlags.Read,
        });
    }

    _frameBuffer = new byte[w * h * 4];
    _cachedWidth = w;
    _cachedHeight = h;
    _hasPendingFrame = false;
    _stagingIdx = 0;
    Log.Debug("[Capture] Double staging allocated: {W}x{H}", w, h);
}


// === Dispose → 2枚分解放 ===

public void Dispose()
{
    if (_disposed) return;
    _disposed = true;
    Stop();
    foreach (var tex in _stagingTextures)
        tex?.Dispose();
    _winrtDevice?.Dispose();
    _d3dContext?.Dispose();
    _d3dDevice?.Dispose();
}
```

### 変更ファイル: `Streaming/StreamConfig.cs`

```csharp
// FPS デフォルト値を30に戻す
public int Framerate { get; set; } = 30;
```

## 計測ログの追加

Map()の所要時間を計測し、ダブルバッファの効果を確認する。

```csharp
// ExtractBgra内、Map前後にStopwatch
if (_hasPendingFrame)
{
    var sw = Stopwatch.StartNew();
    var mapped = _d3dContext!.Map(...);
    var mapMs = sw.ElapsedMilliseconds;
    // ... データ読み出し ...
    sw.Stop();
    if (_frameCount <= 5 || _frameCount % 30 == 0)
        Log.Debug("[Capture] Map={MapMs}ms total={TotalMs}ms", mapMs, sw.ElapsedMilliseconds);
}
```

## 変更量

| ファイル | 変更内容 | 変更行数 |
|----------|----------|:--------:|
| `Capture/FrameCapture.cs` | ダブルステージングテクスチャ + パイプライン化 + RowPitch最適化 + 計測ログ | ~50行 |
| `Streaming/StreamConfig.cs` | FPS 20→30 | 1行 |

## リスク

| リスク | 深刻度 | 対策 |
|--------|:------:|------|
| 初回フレームが出力されない | 低 | パイプラインの初回はCopyResourceのみでMapしないため、1フレーム遅れで開始。FfmpegProcess側の初期黒フレームが表示されるので視覚的問題なし |
| 解像度変更時のテクスチャ不整合 | 低 | EnsureStagingで両テクスチャを再作成 + `_hasPendingFrame=false`でパイプラインリセット |
| Map()がまだ遅い場合 | 中 | 計測ログで確認。50ms経過後もMapが遅い場合、原因はGPU contention（DWM等）。対策: ID3D11Query(Event)で完了チェック → 未完了ならスキップ |
| 1フレーム遅延 | 低 | 20fps=50ms、30fps=33msの遅延追加。Twitch配信のバッファ（2-5秒）に比べ無視できる |

## 検証方法

1. **Map時間:** ログの `[Capture] Map=Xms` で確認。目標: <5ms
2. **FFmpeg FPS:** `ffmpeg.log` の `frame=` 行でエンコードFPS確認。目標: 30fps
3. **ドロップ数:** `[FFmpeg] ... drops=X` で確認。目標: drops=0に近い
4. **Twitch目視:** 配信画面のスムーズさ確認

## 将来の追加最適化（今回のスコープ外）

30fps達成後、さらなる高みを目指す場合:

- **D3D11 → NVENC直接エンコード（ゼロコピー）:** GPU上でD3D11テクスチャ→NVENCエンコード→圧縮NAL（10-50KB/frame）をパイプに流す。CPU readback完全不要。NvEncSharp等のライブラリが必要。
- **D3D11 Compute ShaderでBGRA→NV12:** GPU上で色変換してからCPU readback。readbackデータ量が3.7MB→1.4MBに。

## ステータス

- 作成日: 2026-03-14
- 状態: 完了
- Step 1-3: 完了（4fps → 18fps）
- Step 4: 完了（18fps → 30fps）— ダブルステージングテクスチャ + FPSスロットル固定間隔化
- 最終結果: 30fps / speed=1.01x / Map=0ms / drops固定 / write=1ms
- 変更ファイル:
  - `Capture/FrameCapture.cs` — ダブルステージングテクスチャ + パイプライン化 + RowPitch最適化 + 固定間隔FPSスロットル
  - `Streaming/FfmpegProcess.cs` — 名前付きパイプ + NV12変換 + HWエンコーダ + ダブルバッファ
  - `Streaming/ColorConverter.cs` — BGRA→NV12変換
  - `Streaming/StreamConfig.cs` — FPS=30 + Encoderプロパティ
  - `Streaming/AudioLoopback.cs` — サイレンスバッファ100ms化
  - `Server/HttpServer.cs` — WebSocket SendAsync排他制御
