using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using Serilog;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX;
using Windows.Graphics.DirectX.Direct3D11;

namespace WinNativeApp.Capture;

public sealed class FrameCapture : IDisposable
{
    private ID3D11Device? _d3dDevice;
    private ID3D11DeviceContext? _d3dContext;
    private IDirect3DDevice? _winrtDevice;
    private Direct3D11CaptureFramePool? _framePool;
    private GraphicsCaptureSession? _session;
    private int _frameCount;
    private readonly object _lock = new();
    private bool _disposed;

    // Streaming: raw BGRA frame callback (byte[] bgra, int width, int height)
    public Action<byte[], int, int>? OnFrameReady { get; set; }

    // Target frame rate (0 = no throttle, process every WGC frame)
    public int TargetFps { get; set; }

    /// <summary>
    /// クロップ矩形（キャプチャフレーム座標系）。設定時はこの領域のみ出力する。
    /// Phase 7: UIパネル追加時に配信領域のみを切り出すために使用。
    /// </summary>
    public Rectangle? CropRect { get; set; }

    private readonly Stopwatch _fpsWatch = Stopwatch.StartNew();
    private long _lastFrameTimeMs;

    // ダブルステージングテクスチャ（パイプライン化でGPU readback待ち解消）
    private readonly ID3D11Texture2D?[] _stagingTextures = new ID3D11Texture2D?[2];
    private int _stagingIdx;           // 次にCopyResourceする先のインデックス（0 or 1）
    private bool _hasPendingFrame;     // 前フレームのCopyResourceが完了待ちか
    private int _pendingWidth, _pendingHeight;

    private byte[]? _frameBuffer;
    private int _cachedWidth, _cachedHeight;    // ステージングテクスチャサイズ
    private int _outputWidth, _outputHeight;    // 出力バッファサイズ（クロップ適用後）

    public int FrameCount => _frameCount;

    public void StartCapture(IntPtr hwnd)
    {
        D3D11.D3D11CreateDevice(
            null, DriverType.Hardware, DeviceCreationFlags.BgraSupport,
            [FeatureLevel.Level_11_1, FeatureLevel.Level_11_0],
            out _d3dDevice!, out _d3dContext!).CheckError();

        Log.Information("[Capture] D3D11 device created");

        using var dxgiDevice = _d3dDevice.QueryInterface<IDXGIDevice>();
        _winrtDevice = Direct3DInterop.CreateDirect3DDevice(dxgiDevice.NativePointer);

        var item = Direct3DInterop.CreateCaptureItemForWindow(hwnd);
        Log.Information("[Capture] Item: {W}x{H}", item.Size.Width, item.Size.Height);

        // CreateFreeThreaded: コールバックがスレッドプールで発火（UIスレッド非依存）
        _framePool = Direct3D11CaptureFramePool.CreateFreeThreaded(
            _winrtDevice,
            DirectXPixelFormat.B8G8R8A8UIntNormalized,
            2,
            item.Size);

        _framePool.FrameArrived += OnFrameArrived;

        _session = _framePool.CreateCaptureSession(item);
        _session.IsBorderRequired = false;
        _session.IsCursorCaptureEnabled = false;
        _session.StartCapture();

        Log.Information("[Capture] Session started");
    }

    private void OnFrameArrived(Direct3D11CaptureFramePool sender, object args)
    {
        using var frame = sender.TryGetNextFrame();
        if (frame == null) return;

        _frameCount++;

        // 最初の数フレームと以降100フレームごとにログ
        if (_frameCount <= 3 || _frameCount % 100 == 0)
            Log.Debug("[Capture] Frame {N} arrived", _frameCount);

        // FPS throttle（固定間隔ベース: ジッター耐性のため _lastFrameTimeMs += interval）
        if (TargetFps > 0)
        {
            var now = _fpsWatch.ElapsedMilliseconds;
            var minInterval = 1000L / TargetFps;  // 30fps → 33ms
            if (now - _lastFrameTimeMs < minInterval)
                return;
            // 固定間隔で進める（now基準だとジッターが蓄積して22fpsに低下する）
            // ただし大幅に遅れた場合はnowにリセット（フレームバースト防止）
            _lastFrameTimeMs += minInterval;
            if (now - _lastFrameTimeMs > minInterval * 2)
                _lastFrameTimeMs = now;
        }

        if (OnFrameReady == null) return;

        // Extract BGRA bytes from GPU texture (double-buffered pipeline)
        ExtractBgra(frame, out var w, out var h);
        if (w == 0 || h == 0) return;

        OnFrameReady.Invoke(_frameBuffer!, w, h);
    }

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

                // ① 前フレームのMapを先に実行（前回のCopyResourceから1フレーム経過 → GPU完了済み → 即座完了）
                if (_hasPendingFrame)
                {
                    int readIdx = _stagingIdx ^ 1;  // 前フレームが書き込んだテクスチャ
                    var sw = Stopwatch.StartNew();
                    var mapped = _d3dContext!.Map(_stagingTextures[readIdx]!, 0, MapMode.Read);
                    var mapMs = sw.ElapsedMilliseconds;
                    try
                    {
                        int rw = _pendingWidth, rh = _pendingHeight;

                        // クロップ矩形の計算（設定時は指定領域のみ、未設定時は全体）
                        var crop = CropRect;
                        int outW, outH, srcX, srcY;
                        if (crop.HasValue)
                        {
                            srcX = Math.Clamp(crop.Value.X, 0, rw);
                            srcY = Math.Clamp(crop.Value.Y, 0, rh);
                            outW = Math.Min(crop.Value.Width, rw - srcX);
                            outH = Math.Min(crop.Value.Height, rh - srcY);
                        }
                        else
                        {
                            srcX = 0; srcY = 0; outW = rw; outH = rh;
                        }

                        EnsureOutputBuffer(outW, outH);

                        // クロップなし＋RowPitch一致 → 一括コピー（最速パス）
                        if (srcX == 0 && srcY == 0 && outW == rw && outH == rh && mapped.RowPitch == rw * 4)
                        {
                            fixed (byte* dst = _frameBuffer!)
                            {
                                Buffer.MemoryCopy(
                                    (void*)mapped.DataPointer, dst,
                                    outW * outH * 4, outW * outH * 4);
                            }
                        }
                        else
                        {
                            // 行ごとコピー（クロップ対応 + RowPitch不一致対応）
                            for (int y = 0; y < outH; y++)
                            {
                                var src = (byte*)(mapped.DataPointer + (srcY + y) * mapped.RowPitch + srcX * 4);
                                fixed (byte* dst = &_frameBuffer![y * outW * 4])
                                {
                                    Buffer.MemoryCopy(src, dst, outW * 4, outW * 4);
                                }
                            }
                        }

                        width = outW;
                        height = outH;
                    }
                    finally
                    {
                        _d3dContext.Unmap(_stagingTextures[readIdx]!, 0);
                    }

                    sw.Stop();
                    if (_frameCount <= 5 || _frameCount % 30 == 0)
                        Log.Debug("[Capture] Map={MapMs}ms readback={TotalMs}ms frame={N} out={OutW}x{OutH}",
                            mapMs, sw.ElapsedMilliseconds, _frameCount, width, height);
                }

                // ② 今フレームのCopyResourceをキューイング（非同期GPU操作、すぐ戻る）
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

        _cachedWidth = w;
        _cachedHeight = h;
        _hasPendingFrame = false;
        _stagingIdx = 0;
        _outputWidth = 0;  // 出力バッファ再確保を強制
        _outputHeight = 0;
        Log.Debug("[Capture] Double staging allocated: {W}x{H}", w, h);
    }

    private void EnsureOutputBuffer(int w, int h)
    {
        if (_outputWidth == w && _outputHeight == h && _frameBuffer != null)
            return;

        _frameBuffer = new byte[w * h * 4];
        _outputWidth = w;
        _outputHeight = h;
        Log.Debug("[Capture] Output buffer: {W}x{H} (crop={Crop})", w, h, CropRect.HasValue);
    }

    public void Stop()
    {
        _session?.Dispose();
        _session = null;
        _framePool?.Dispose();
        _framePool = null;
        Log.Information("[Capture] Stopped (frames={N})", _frameCount);
    }

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
}
