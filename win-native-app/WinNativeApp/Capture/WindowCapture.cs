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

/// <summary>
/// 任意のウィンドウ(HWND)をWGCでキャプチャし、JPEGフレームを保持する。
/// CreateFreeThreadedでフレームコールバックはスレッドプールで実行される（UIスレッド非依存）。
/// </summary>
public sealed class WindowCapture : IDisposable
{
    private ID3D11Device? _d3dDevice;
    private ID3D11DeviceContext? _d3dContext;
    private IDirect3DDevice? _winrtDevice;
    private Direct3D11CaptureFramePool? _framePool;
    private GraphicsCaptureSession? _session;
    private int _frameCount;
    private readonly object _lock = new();
    private bool _disposed;

    // 最新JPEGフレーム（volatile: スレッドプール書き込み、HTTPスレッド読み取り）
    private volatile byte[]? _latestJpeg;
    private readonly int _jpegQuality;

    // FPSスロットル
    public int TargetFps { get; set; }
    private readonly Stopwatch _fpsWatch = Stopwatch.StartNew();
    private long _lastFrameTimeMs;

    // ステージングリソース（フレーム間で再利用）
    private ID3D11Texture2D? _stagingTexture;
    private byte[]? _frameBuffer;
    private int _cachedWidth, _cachedHeight;

    // JPEGエンコーダ（キャッシュ）
    private static readonly ImageCodecInfo JpegCodec =
        ImageCodecInfo.GetImageEncoders().First(c => c.FormatID == ImageFormat.Jpeg.Guid);

    // 識別情報
    public string Id { get; }
    public string WindowTitle { get; }
    public IntPtr Hwnd { get; }
    public int FrameCount => _frameCount;

    public WindowCapture(string id, IntPtr hwnd, string windowTitle, int fps = 15, int jpegQuality = 70)
    {
        Id = id;
        Hwnd = hwnd;
        WindowTitle = windowTitle;
        TargetFps = fps;
        _jpegQuality = jpegQuality;
    }

    public void Start()
    {
        D3D11.D3D11CreateDevice(
            null, DriverType.Hardware, DeviceCreationFlags.BgraSupport,
            [FeatureLevel.Level_11_1, FeatureLevel.Level_11_0],
            out _d3dDevice!, out _d3dContext!).CheckError();

        using var dxgiDevice = _d3dDevice.QueryInterface<IDXGIDevice>();
        _winrtDevice = Direct3DInterop.CreateDirect3DDevice(dxgiDevice.NativePointer);

        var item = Direct3DInterop.CreateCaptureItemForWindow(Hwnd);
        Log.Information("[WindowCapture:{Id}] Started: {W}x{H} '{Title}'",
            Id, item.Size.Width, item.Size.Height, WindowTitle);

        // CreateFreeThreaded: コールバックがスレッドプールで発火（UIスレッド不要）
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
    }

    private void OnFrameArrived(Direct3D11CaptureFramePool sender, object args)
    {
        using var frame = sender.TryGetNextFrame();
        if (frame == null) return;

        _frameCount++;

        // FPSスロットル
        if (TargetFps > 0)
        {
            var now = _fpsWatch.ElapsedMilliseconds;
            var minInterval = 1000.0 / TargetFps;
            if (now - _lastFrameTimeMs < minInterval)
                return;
            _lastFrameTimeMs = now;
        }

        ExtractAndEncode(frame);
    }

    private unsafe void ExtractAndEncode(Direct3D11CaptureFrame frame)
    {
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

                // BGRA → JPEG
                _latestJpeg = BgraToJpeg(_frameBuffer!, w, h);
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[WindowCapture:{Id}] Frame {N} failed", Id, _frameCount);
            }
        }
    }

    private unsafe byte[] BgraToJpeg(byte[] bgra, int width, int height)
    {
        // System.Drawing: Format32bppArgb はメモリ上 BGRA 配列（D3D11 BGRAと一致）
        using var bmp = new Bitmap(width, height, PixelFormat.Format32bppArgb);
        var bits = bmp.LockBits(
            new Rectangle(0, 0, width, height),
            ImageLockMode.WriteOnly,
            PixelFormat.Format32bppArgb);

        fixed (byte* src = bgra)
        {
            Buffer.MemoryCopy(src, (void*)bits.Scan0, bits.Stride * height, width * height * 4);
        }
        bmp.UnlockBits(bits);

        using var ms = new MemoryStream();
        var encoderParams = new EncoderParameters(1);
        encoderParams.Param[0] = new EncoderParameter(
            System.Drawing.Imaging.Encoder.Quality, _jpegQuality);
        bmp.Save(ms, JpegCodec, encoderParams);
        return ms.ToArray();
    }

    /// <summary>
    /// 最新のJPEGフレームを取得する（スレッドセーフ）。
    /// </summary>
    public byte[]? GetLatestFrame() => _latestJpeg;

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
        Log.Debug("[WindowCapture:{Id}] Staging: {W}x{H}", Id, w, h);
    }

    public void Stop()
    {
        _session?.Dispose();
        _session = null;
        _framePool?.Dispose();
        _framePool = null;
        Log.Information("[WindowCapture:{Id}] Stopped (frames={N})", Id, _frameCount);
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
