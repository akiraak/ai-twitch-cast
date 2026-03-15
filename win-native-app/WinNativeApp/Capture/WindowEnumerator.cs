using System.Runtime.InteropServices;
using System.Text;

namespace WinNativeApp.Capture;

public record WindowInfo(IntPtr Hwnd, string Title);

/// <summary>
/// Win32 APIでデスクトップのウィンドウ一覧を取得する。
/// </summary>
internal static class WindowEnumerator
{
    private delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);

    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr hwnd);

    [DllImport("user32.dll")]
    private static extern int GetWindowTextLength(IntPtr hwnd);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);

    [DllImport("user32.dll")]
    private static extern IntPtr GetShellWindow();

    [DllImport("user32.dll")]
    private static extern bool IsIconic(IntPtr hwnd);

    /// <summary>
    /// 表示中のウィンドウ一覧を取得する（自プロセス・最小化・タイトルなしは除外）。
    /// </summary>
    public static List<WindowInfo> GetWindows()
    {
        var result = new List<WindowInfo>();
        var shellWindow = GetShellWindow();
        var currentPid = (uint)Environment.ProcessId;

        EnumWindows((hwnd, _) =>
        {
            if (hwnd == shellWindow) return true;
            if (!IsWindowVisible(hwnd)) return true;
            if (IsIconic(hwnd)) return true;

            var titleLen = GetWindowTextLength(hwnd);
            if (titleLen == 0) return true;

            GetWindowThreadProcessId(hwnd, out var pid);
            if (pid == currentPid) return true;

            var sb = new StringBuilder(titleLen + 1);
            GetWindowText(hwnd, sb, sb.Capacity);
            var title = sb.ToString();

            if (!string.IsNullOrWhiteSpace(title))
                result.Add(new WindowInfo(hwnd, title));

            return true;
        }, IntPtr.Zero);

        return result;
    }

    /// <summary>
    /// HWNDからウィンドウタイトルを取得する。
    /// </summary>
    public static string GetWindowTitle(IntPtr hwnd)
    {
        var len = GetWindowTextLength(hwnd);
        if (len == 0) return "(unknown)";
        var sb = new StringBuilder(len + 1);
        GetWindowText(hwnd, sb, sb.Capacity);
        return sb.ToString();
    }
}
