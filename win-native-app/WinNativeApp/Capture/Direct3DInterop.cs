using System.Runtime.InteropServices;
using WinRT;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX.Direct3D11;

namespace WinNativeApp.Capture;

/// <summary>
/// D3D11 / WinRT / WGC COM interop helpers.
/// </summary>
internal static class Direct3DInterop
{
    // ----- IDirect3DDevice from DXGI device -----

    [DllImport("d3d11.dll", EntryPoint = "CreateDirect3D11DeviceFromDXGIDevice",
        SetLastError = true, PreserveSig = false)]
    private static extern void CreateDirect3D11DeviceFromDXGIDevice(
        IntPtr dxgiDevice, out IntPtr graphicsDevice);

    public static IDirect3DDevice CreateDirect3DDevice(IntPtr dxgiDevicePtr)
    {
        CreateDirect3D11DeviceFromDXGIDevice(dxgiDevicePtr, out var devicePtr);
        try
        {
            return MarshalInterface<IDirect3DDevice>.FromAbi(devicePtr);
        }
        finally
        {
            Marshal.Release(devicePtr);
        }
    }

    // ----- GraphicsCaptureItem from HWND (Windows 11 API) -----

    public static GraphicsCaptureItem CreateCaptureItemForWindow(IntPtr hwnd)
    {
        var windowId = new Windows.UI.WindowId { Value = (ulong)hwnd.ToInt64() };
        var item = GraphicsCaptureItem.TryCreateFromWindowId(windowId);
        if (item == null)
            throw new InvalidOperationException(
                $"Failed to create GraphicsCaptureItem for HWND=0x{hwnd:X}");
        return item;
    }

    // ----- Native texture from WinRT IDirect3DSurface -----

    [ComImport]
    [Guid("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IDirect3DDxgiInterfaceAccess
    {
        IntPtr GetInterface([In] ref Guid iid);
    }

    private static readonly Guid IDirect3DDxgiInterfaceAccessIid =
        new("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1");

    public static IntPtr GetDXGISurfaceFromWinRT(IDirect3DSurface surface, Guid targetIid)
    {
        // Get native COM pointer from CsWinRT projected object
        var winrtObj = (IWinRTObject)surface;
        var nativePtr = winrtObj.NativeObject.ThisPtr;

        // QI for IDirect3DDxgiInterfaceAccess
        var accessGuid = IDirect3DDxgiInterfaceAccessIid;
        Marshal.ThrowExceptionForHR(
            Marshal.QueryInterface(nativePtr, ref accessGuid, out var accessPtr));

        try
        {
            // Call GetInterface via standard COM interop
            var access = (IDirect3DDxgiInterfaceAccess)Marshal.GetObjectForIUnknown(accessPtr);
            return access.GetInterface(ref targetIid);
        }
        finally
        {
            Marshal.Release(accessPtr);
        }
    }
}
