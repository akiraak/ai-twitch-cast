# フレームレート最適化プラン

## 背景

C#ネイティブ配信アプリ（Phase 5完了）のTwitch配信テストで、**映像が約4fpsしか出ない**問題が発生。
WGCは60fpsでフレームを生成しているが、FFmpegへのフレーム転送がボトルネックになっている。

## 現状分析

### データフロー

```
WGC (60fps)
  → D3D11 staging texture → CPU readback (MemoryCopy)
  → BGRA byte[] (3.7MB/frame @1280x720)
  → Buffer.BlockCopy (3.7MB コピー)
  → ThreadPool → StandardInput.BaseStream.Write (stdin匿名パイプ)
  → FFmpeg rawvideo入力 → libx264 ultrafast → RTMP
```

### ボトルネック箇所

**FFmpegのstdinパイプ書き込み**がボトルネック。

| 要因 | 詳細 |
|------|------|
| フレームサイズ | 1280×720×4(BGRA) = **3,686,400 bytes ≈ 3.7MB** |
| 必要スループット | 3.7MB × 30fps = **111MB/s** |
| 匿名パイプのバッファ | Windows匿名パイプのデフォルトバッファ = **4KB** |
| 書き込み動作 | `Write(3.7MB)` → 4KBずつカーネルに転送 → FFmpegが読むまでブロック → 約920回のチャンク転送 |
| フレームドロップ | `_writingVideo` フラグで前回書き込み中はスキップ |
| 実効レート | 1フレーム書き込み ≈ 250ms → **約4fps** |

### 各段階の所要時間（推定）

| 段階 | 時間 | 備考 |
|------|------|------|
| GPU→CPU readback | 1-3ms | D3D11 Map/MemoryCopy、事前確保済みステージングテクスチャ |
| Buffer.BlockCopy | 1ms | 3.7MBのメモリコピー |
| パイプ書き込み | **200-300ms** | ★ボトルネック。4KBバッファ × 920チャンク |
| FFmpeg rawvideo読み取り | 含まれる | パイプ書き込みと同期 |
| libx264エンコード | 5-15ms | ultrafast preset、CPU依存 |

**結論:** パイプ書き込みが全体の95%を占めている。

## 改善戦略

3段階のアプローチで、簡単な変更から順に実装する。

### Step 1: 名前付きパイプ（大バッファ）— 最小変更で最大効果

**概要:** 映像入力をstdin匿名パイプから名前付きパイプに変更し、バッファサイズを大幅に拡大する。

**原理:**
- 匿名パイプ: バッファ4KB → 3.7MBの書き込みが920回のチャンクに分割、毎回カーネルとFFmpegの同期待ち
- 名前付きパイプ（8MBバッファ）: 3.7MBが1-2回の書き込みでカーネルバッファにコピー完了、FFmpegは非同期に読み取り

**期待改善: 4fps → 15-25fps**

**変更ファイル:** `Streaming/FfmpegProcess.cs`

**実装内容:**

```csharp
// 変更前: stdin匿名パイプ
"-i pipe:0"
_process.StandardInput.BaseStream.Write(copy, 0, copy.Length);

// 変更後: 名前付きパイプ（8MBバッファ）
private NamedPipeServerStream _videoPipe;
private string _videoPipeName = $"winnative_video_{Environment.ProcessId}";

// パイプ作成（音声パイプと同じパターン）
_videoPipe = new NamedPipeServerStream(
    _videoPipeName, PipeDirection.Out, 1,
    PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
    outBufferSize: 8 * 1024 * 1024,  // 8MBバッファ（2フレーム分以上）
    inBufferSize: 0);

// FFmpegの引数
$@"-i \\.\pipe\{_videoPipeName}"  // stdin:0 → 名前付きパイプに変更

// StandardInputのリダイレクトを無効化（もうstdinは使わない）
RedirectStandardInput = false,

// 書き込み
_videoPipe.Write(copy, 0, copy.Length);
```

**変更量:** FfmpegProcess.cs のみ、約30行の変更

**注意点:**
- `RedirectStandardInput`を無効化するため、`-nostdin`フラグはそのまま維持
- FFmpegの起動後、名前付きパイプの接続待ちが必要（音声パイプと同じパターン）
- 音声パイプより先に映像パイプを接続する（FFmpegの入力順序に合わせる）

---

### Step 2: BGRA→NV12 CPU変換 — データ量を63%削減

**概要:** FFmpegに渡す前に、CPU上でBGRA（4バイト/ピクセル）をNV12（1.5バイト/ピクセル）に変換する。

**原理:**
- BGRA: 1280×720×4 = 3,686,400 bytes (3.7MB)
- NV12: 1280×720×1.5 = 1,382,400 bytes (1.4MB)
- データ量が**63%削減** → パイプスループットの余裕が大幅に増加

**期待改善: Step 1と組み合わせて → 25-30fps**

**変更ファイル:**
- `Streaming/FfmpegProcess.cs` — FFmpeg引数変更 + NV12バッファ書き込み
- `Capture/FrameCapture.cs` または新規 `Streaming/ColorConverter.cs` — BGRA→NV12変換

**実装内容:**

```csharp
// 新規: ColorConverter.cs（またはFfmpegProcess内にstaticメソッド）
public static class ColorConverter
{
    /// <summary>
    /// BGRA → NV12 変換。
    /// NV12レイアウト: Y平面 (W×H) + UV平面 (W×H/2、UVインターリーブ)
    /// </summary>
    public static void BgraToNv12(byte[] bgra, byte[] nv12, int width, int height)
    {
        int ySize = width * height;
        int uvOffset = ySize;

        for (int y = 0; y < height; y++)
        {
            for (int x = 0; x < width; x++)
            {
                int bgraIdx = (y * width + x) * 4;
                byte b = bgra[bgraIdx];
                byte g = bgra[bgraIdx + 1];
                byte r = bgra[bgraIdx + 2];
                // BGRA→YUV BT.601
                byte yVal = (byte)Math.Clamp((( 66 * r + 129 * g +  25 * b + 128) >> 8) + 16, 0, 255);
                nv12[y * width + x] = yVal;

                // UV: 2x2ブロックの左上ピクセルのみ（サブサンプリング）
                if ((y & 1) == 0 && (x & 1) == 0)
                {
                    byte u = (byte)Math.Clamp(((-38 * r -  74 * g + 112 * b + 128) >> 8) + 128, 0, 255);
                    byte v = (byte)Math.Clamp(((112 * r -  94 * g -  18 * b + 128) >> 8) + 128, 0, 255);
                    int uvIdx = uvOffset + (y / 2) * width + (x & ~1);
                    nv12[uvIdx]     = u;
                    nv12[uvIdx + 1] = v;
                }
            }
        }
    }
}

// FFmpegの引数変更
"-f rawvideo -pixel_format nv12"  // bgra → nv12 に変更
"-pix_fmt yuv420p"  // これは出力フォーマットなので維持（NV12は既にyuv420p互換）
```

**パフォーマンス考慮:**
- 純C#のループでも1280×720なら5-10ms程度（921,600ピクセル）
- `Unsafe` + SIMD (`System.Runtime.Intrinsics`) で1-3msに最適化可能
- NV12変換はThreadPoolの書き込みスレッド内で実行（WGCコールバックをブロックしない）

**注意点:**
- NV12はFFmpegの`rawvideo`デマルチプレクサが直接対応（`-pixel_format nv12`）
- BT.601係数を使用（SDコンテンツ向け。HDならBT.709に変更）
- FFmpeg側で`-pix_fmt yuv420p`を指定しているが、NV12→yuv420pはFFmpeg内部でほぼゼロコストの変換

---

### Step 3: NVENCハードウェアエンコード — GPUでH.264エンコードまで完結（オプション）

**概要:** NVIDIA GPUのNVENCエンコーダを使用し、フレームをGPU上でH.264にエンコードしてからFFmpegに渡す。

**原理:**
- GPUテクスチャ → NVENC → H.264 NAL units (10-50KB/frame)
- パイプ転送量: 3.7MB → 10-50KB（**99%削減**）
- CPU libx264エンコードも不要になり、CPU負荷も大幅低下

**期待改善: → 30fps（確実）**

**方式A: FFmpeg側のNVENCを使う（推奨・変更最小）**

```
// FFmpegの引数変更のみ
"-c:v h264_nvenc -preset p1 -tune ll"  // libx264 → h264_nvenc
// p1 = 最速プリセット、ll = low latency tune
```

- BGRAのままパイプに流してFFmpeg内でNVENCエンコード
- Step 1（名前付きパイプ）は前提として必要（rawvideoの転送は必要）
- Step 2（NV12変換）と組み合わせるとさらに効果的
- NVIDIA GPU搭載マシンでのみ動作

**方式B: D3D11テクスチャを直接NVENCに渡す（最速・変更大）**

```csharp
// GPU上でテクスチャ → NVENCエンコード → compressed NAL → パイプ
// CPU readbackが完全に不要になる
// ただしNVENC C# SDKの導入が必要（NvEncSharp等）
```

- CPU readback自体を省略（ゼロコピー）
- パイプ帯域は事実上問題にならない（圧縮済み）
- 実装コストが大きく、NVIDIA専用

**方式C: AMD AMF / Intel QSV（GPU非依存対応）**

```
// AMD GPU
"-c:v h264_amf -quality speed"

// Intel iGPU (QSV)
"-c:v h264_qsv -preset veryfast"
```

- FFmpegの引数変更のみで対応可能
- GPUベンダーの自動検出ロジックが必要

**注意点:**
- NVIDIA以外のGPU対応が必要な場合は方式A+Cの組み合わせ（自動検出）
- Twitch推奨のキーフレーム間隔（2秒）を維持すること
- NVENCの同時セッション数制限に注意（コンシューマGPUは通常5セッション）

---

## 実装順序と判断基準

```
Step 1: 名前付きパイプ
  │
  ├─ 25fps以上出る → 完了（Step 2/3はスキップ可）
  │
  └─ 15-20fps程度 → Step 2へ
       │
       ├─ 28fps以上出る → 完了
       │
       └─ まだ不足 → Step 3へ（NVENC）
```

| Step | 期待fps | 実装コスト | 変更ファイル数 | 変更行数 |
|------|:-------:|:----------:|:--------------:|:--------:|
| Step 1 | 15-25 | **低** | 1 | ~30 |
| Step 2 | 25-30 | **中** | 2 | ~80 |
| Step 3A | 30 | **低** | 1 | ~5 |
| Step 3B | 30+ | **高** | 3+ | ~200 |

## 補足: その他の最適化（Step 1-3の効果が十分なら不要）

### GPU上でBGRA→NV12変換（D3D11 Compute Shader）

FrameCapture内のGPUテクスチャに対してCompute Shaderを実行し、GPU上でBGRA→NV12に変換してからCPU readbackする。
CPU readbackのデータ量自体が1.4MBに削減される。

- 実装: HLSL Compute Shader + D3D11 CreateComputeShader
- 効果: CPU readback時間とメモリコピー時間が63%削減
- Step 2のCPU変換と排他（どちらか一方）

### ダブルバッファリング

WriteVideoFrameで毎回`new byte[]`するのではなく、2つのバッファを交互に使用。
GCプレッシャー削減とメモリアロケーション時間短縮。

```csharp
// 現状: 毎フレーム3.7MBのアロケーション
var copy = new byte[bgraData.Length];

// 改善: 事前確保した2バッファを交互に使用
private byte[] _bufA, _bufB;
private int _bufIdx;
var buf = (_bufIdx++ & 1) == 0 ? _bufA : _bufB;
Buffer.BlockCopy(bgraData, 0, buf, 0, bgraData.Length);
```

### FrameCapture側のreadback最適化

FrameCapture.ExtractBgra()で行ごとにMemoryCopyしている部分を、RowPitch == Width*4の場合は一括コピーに変更。

```csharp
// 現状: 行ごとにコピー（720回のMemoryCopy）
for (int y = 0; y < h; y++)
    Buffer.MemoryCopy(src + y * rowPitch, dst + y * w * 4, w * 4, w * 4);

// 改善: RowPitch == Width*4 なら一括コピー
if (mapped.RowPitch == w * 4)
    Buffer.MemoryCopy(mapped.DataPointer, dst, totalSize, totalSize);
else
    // padding がある場合のみ行ごとコピー
    for (int y = 0; y < h; y++) ...
```

## リスク

| リスク | 深刻度 | 対策 |
|--------|:------:|------|
| 名前付きパイプの接続順序 | 中 | FFmpegの入力順序（`-i`の順）でパイプを接続。映像→音声の順で`WaitForConnectionAsync` |
| NV12変換の色差 | 低 | BT.601係数で十分。必要ならBT.709に切り替え |
| NVENCの可用性 | 中 | NVIDIA GPU非搭載時は`libx264`にフォールバック。FFmpegの`-hwaccel auto`で自動検出 |
| 名前付きパイプのバッファ上限 | 低 | Windowsの名前付きパイプは最大数GBのバッファ可能。8MBで十分 |
| FFmpegのrawvideo NV12対応 | 低 | FFmpegは`-pixel_format nv12`をネイティブサポート |

## 検証方法

1. **FPS計測:** FfmpegProcess内の`_frameCount`と`_dropCount`を定期ログ出力
2. **書き込み時間計測:** WriteVideoFrame内にStopwatchを追加、フレームあたりの書き込み時間をログ
3. **FFmpegログ:** `ffmpeg.log`の`frame=`行でエンコードFPSを確認
4. **Twitch確認:** 配信画面のスムーズさを目視確認

```csharp
// 計測ログ追加例
var sw = Stopwatch.StartNew();
_videoPipe.Write(copy, 0, copy.Length);
sw.Stop();
if (_frameCount % 30 == 0)
    Log.Debug("[FFmpeg] Write {Ms}ms, frames={F} drops={D}",
        sw.ElapsedMilliseconds, FrameCount, DropCount);
```

## ステータス

- 作成日: 2026-03-14
- 状態: Step 1-3 テスト完了、追加最適化が必要
- Step 1 完了: 名前付きパイプ（8MBバッファ）— パイプ書き込み250ms→1ms
- Step 2 完了: BGRA→NV12 CPU変換（ColorConverter.cs）— NV12 convert=1ms
- Step 3 完了: HWエンコーダ自動検出 — h264_nvenc使用確認
- 追加修正1: `-flush_packets 1`除去 — RTMP毎フレームフラッシュが0.748x speedの原因だった
- 追加修正2: サイレンスフォールバック修正（10ms→100ms）— 音声不足でFFmpegが0.1x speedに制限されていた根本原因
- 追加修正3: デフォルトFPSを30→20に変更 — GPU readbackが55ms/frameのため暫定
- テスト結果:
  - 4fps (0.11x) → 18fps (0.922x) に大幅改善
  - NV12 convert=1ms, write=1ms, drops=12（ほぼゼロ）
  - ボトルネックはFrameCapture.ExtractBgraのD3D11 Map()（GPU完了待ち~55ms）
- 次のアクション: FrameCaptureダブルバッファ・ステージングテクスチャで30fps化
- 変更ファイル:
  - `Streaming/FfmpegProcess.cs` — 名前付きパイプ + NV12変換 + HWエンコーダ + ダブルバッファ + 計測ログ
  - `Streaming/ColorConverter.cs` — BGRA→NV12変換（新規）
  - `Streaming/StreamConfig.cs` — `Encoder`プロパティ + `--encoder`引数 + FPS=20
  - `Streaming/AudioLoopback.cs` — サイレンスバッファ100ms化
