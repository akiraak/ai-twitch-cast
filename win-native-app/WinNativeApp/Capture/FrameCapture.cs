using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
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

    private readonly Stopwatch _fpsWatch = Stopwatch.StartNew();
    private long _lastFrameTimeMs;

    // Pre-allocated staging resources (reused across frames)
    private ID3D11Texture2D? _stagingTexture;
    private byte[]? _frameBuffer;
    private int _cachedWidth, _cachedHeight;

    // Debug: save frames as PNG
    public bool SaveFrames { get; set; }
    private readonly string _captureDir;

    public int FrameCount => _frameCount;

    public FrameCapture()
    {
        _captureDir = Path.Combine(AppContext.BaseDirectory, "captures");
    }

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

        _framePool = Direct3D11CaptureFramePool.Create(
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

        // FPS throttle
        if (TargetFps > 0)
        {
            var now = _fpsWatch.ElapsedMilliseconds;
            var minInterval = 1000.0 / TargetFps;
            if (now - _lastFrameTimeMs < minInterval)
                return;
            _lastFrameTimeMs = now;
        }

        bool hasCallback = OnFrameReady != null;
        bool shouldSave = SaveFrames && (_frameCount <= 5 || _frameCount % 30 == 0);

        if (!hasCallback && !shouldSave) return;

        // Extract BGRA bytes from GPU texture
        ExtractBgra(frame, out var w, out var h);
        if (_frameBuffer == null) return;

        if (hasCallback)
            OnFrameReady!.Invoke(_frameBuffer, w, h);

        if (shouldSave)
            SaveBufferAsPng(w, h);
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

                _d3dContext!.CopyResource(_stagingTexture!, srcTex);

                var mapped = _d3dContext.Map(_stagingTexture!, 0, MapMode.Read);
                try
                {
                    for (int y = 0; y < h; y++)
                    {
                        var src = (byte*)(mapped.DataPointer + y * mapped.RowPitch);
                        fixed (byte* dst = &_frameBuffer![y * w * 4])
                        {
                            Buffer.MemoryCopy(src, dst, w * 4, w * 4);
                        }
                    }
                }
                finally
                {
                    _d3dContext.Unmap(_stagingTexture!, 0);
                }

                width = w;
                height = h;
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[Capture] ExtractBgra failed at frame {N}", _frameCount);
            }
        }
    }

    private void EnsureStaging(int w, int h, Format fmt)
    {
        if (_cachedWidth == w && _cachedHeight == h && _stagingTexture != null)
            return;

        _stagingTexture?.Dispose();
        _stagingTexture = _d3dDevice!.CreateTexture2D(new Texture2DDescription
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

        _frameBuffer = new byte[w * h * 4];
        _cachedWidth = w;
        _cachedHeight = h;
        Log.Debug("[Capture] Staging allocated: {W}x{H}", w, h);
    }

    private unsafe void SaveBufferAsPng(int w, int h)
    {
        try
        {
            Directory.CreateDirectory(_captureDir);

            using var bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb);
            var bits = bmp.LockBits(
                new Rectangle(0, 0, w, h),
                ImageLockMode.WriteOnly,
                PixelFormat.Format32bppArgb);

            fixed (byte* src = _frameBuffer!)
            {
                Buffer.MemoryCopy(src, (void*)bits.Scan0, bits.Stride * h, w * h * 4);
            }

            bmp.UnlockBits(bits);

            var path = Path.Combine(_captureDir, $"frame_{_frameCount:D6}.png");
            bmp.Save(path, ImageFormat.Png);
            Log.Information("[Capture] Saved frame {N} ({W}x{H})", _frameCount, w, h);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[Capture] SavePng failed");
        }
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
        _stagingTexture?.Dispose();
        _winrtDevice?.Dispose();
        _d3dContext?.Dispose();
        _d3dDevice?.Dispose();
    }
}
