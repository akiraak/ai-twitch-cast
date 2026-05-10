using System.Runtime.InteropServices;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX;
using Windows.Graphics.DirectX.Direct3D11;
using WinRT;

namespace PocLoopback;

// PoC 用の最小 WGC キャプチャ。WinNativeApp/Capture/FrameCapture.cs を簡素化。
// 本実装と違いシングルバッファ・クロップ無し。BGRA をそのまま Action に渡す。
public sealed class ScreenCapture : IDisposable
{
    public Action<byte[], int, int>? OnFrame { get; set; }

    private ID3D11Device? _device;
    private ID3D11DeviceContext? _context;
    private IDirect3DDevice? _winrtDevice;
    private Direct3D11CaptureFramePool? _framePool;
    private GraphicsCaptureSession? _session;
    private ID3D11Texture2D? _staging;
    private byte[]? _frameBuffer;
    private int _stagingW, _stagingH;
    private readonly object _lock = new();
    private long _frameCount;

    public long FrameCount => Interlocked.Read(ref _frameCount);

    public void Start(IntPtr hwnd)
    {
        D3D11.D3D11CreateDevice(
            null, DriverType.Hardware, DeviceCreationFlags.BgraSupport,
            [FeatureLevel.Level_11_1, FeatureLevel.Level_11_0],
            out _device!, out _context!).CheckError();

        using var dxgi = _device.QueryInterface<IDXGIDevice>();
        _winrtDevice = CreateWinRTDevice(dxgi.NativePointer);

        var item = CreateCaptureItemForWindow(hwnd)
            ?? throw new InvalidOperationException($"Failed to create capture item for HWND=0x{hwnd:X}");

        Console.WriteLine($"[Capture] Item size: {item.Size.Width}x{item.Size.Height}");

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
        Interlocked.Increment(ref _frameCount);

        var cb = OnFrame;
        if (cb == null) return;

        ExtractBgra(frame, out var w, out var h);
        if (w == 0 || h == 0) return;

        try { cb(_frameBuffer!, w, h); }
        catch (NullReferenceException) { /* disposed during stop */ }
    }

    private unsafe void ExtractBgra(Direct3D11CaptureFrame frame, out int width, out int height)
    {
        width = 0; height = 0;
        lock (_lock)
        {
            try
            {
                var iid = typeof(ID3D11Texture2D).GUID;
                var nativePtr = GetNativePointer(frame.Surface, iid);
                using var srcTex = new ID3D11Texture2D(nativePtr);
                var desc = srcTex.Description;
                int w = (int)desc.Width;
                int h = (int)desc.Height;

                EnsureStaging(w, h, desc.Format);
                _context!.CopyResource(_staging!, srcTex);

                var mapped = _context.Map(_staging!, 0, MapMode.Read);
                try
                {
                    if (_frameBuffer == null || _frameBuffer.Length != w * h * 4)
                        _frameBuffer = new byte[w * h * 4];

                    if (mapped.RowPitch == w * 4)
                    {
                        fixed (byte* dst = _frameBuffer)
                        {
                            Buffer.MemoryCopy((void*)mapped.DataPointer, dst, w * h * 4, w * h * 4);
                        }
                    }
                    else
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
                    width = w; height = h;
                }
                finally
                {
                    _context.Unmap(_staging!, 0);
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"[Capture] ExtractBgra failed: {ex.Message}");
            }
        }
    }

    private void EnsureStaging(int w, int h, Format fmt)
    {
        if (_stagingW == w && _stagingH == h && _staging != null) return;
        _staging?.Dispose();
        _staging = _device!.CreateTexture2D(new Texture2DDescription
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
        _stagingW = w; _stagingH = h;
    }

    public void Stop()
    {
        _session?.Dispose(); _session = null;
        _framePool?.Dispose(); _framePool = null;
    }

    public void Dispose()
    {
        Stop();
        _staging?.Dispose();
        _winrtDevice?.Dispose();
        _context?.Dispose();
        _device?.Dispose();
    }

    // ----- WinRT/D3D interop -----

    [DllImport("d3d11.dll", EntryPoint = "CreateDirect3D11DeviceFromDXGIDevice",
        SetLastError = true, PreserveSig = false)]
    private static extern void CreateDirect3D11DeviceFromDXGIDevice(
        IntPtr dxgiDevice, out IntPtr graphicsDevice);

    private static IDirect3DDevice CreateWinRTDevice(IntPtr dxgiDevicePtr)
    {
        CreateDirect3D11DeviceFromDXGIDevice(dxgiDevicePtr, out var devPtr);
        try { return MarshalInterface<IDirect3DDevice>.FromAbi(devPtr); }
        finally { Marshal.Release(devPtr); }
    }

    private static GraphicsCaptureItem? CreateCaptureItemForWindow(IntPtr hwnd)
    {
        var windowId = new Windows.UI.WindowId { Value = (ulong)hwnd.ToInt64() };
        return GraphicsCaptureItem.TryCreateFromWindowId(windowId);
    }

    [ComImport]
    [Guid("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IDirect3DDxgiInterfaceAccess
    {
        IntPtr GetInterface([In] ref Guid iid);
    }

    private static IntPtr GetNativePointer(IDirect3DSurface surface, Guid targetIid)
    {
        var winrtObj = (IWinRTObject)surface;
        var nativePtr = winrtObj.NativeObject.ThisPtr;
        var accessGuid = new Guid("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1");
        Marshal.ThrowExceptionForHR(Marshal.QueryInterface(nativePtr, ref accessGuid, out var accessPtr));
        try
        {
            var access = (IDirect3DDxgiInterfaceAccess)Marshal.GetObjectForIUnknown(accessPtr);
            return access.GetInterface(ref targetIid);
        }
        finally { Marshal.Release(accessPtr); }
    }
}
