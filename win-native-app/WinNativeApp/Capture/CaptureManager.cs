using System.Collections.Concurrent;
using Serilog;

namespace WinNativeApp.Capture;

public record CaptureInfo(string Id, string Name, int FrameCount);

/// <summary>
/// 複数のウィンドウキャプチャセッションを管理する。
/// ConcurrentDictionaryでスレッドセーフ（HTTP/UIスレッドから同時アクセス可能）。
/// </summary>
public class CaptureManager : IDisposable
{
    private readonly ConcurrentDictionary<string, WindowCapture> _captures = new();
    private int _nextId;
    private bool _disposed;

    /// <summary>
    /// ウィンドウキャプチャを開始する。
    /// </summary>
    public string StartCapture(IntPtr hwnd, string title, int fps = 15, int quality = 70)
    {
        var id = $"cap_{Interlocked.Increment(ref _nextId) - 1}";
        var capture = new WindowCapture(id, hwnd, title, fps, quality);
        capture.Start();
        _captures[id] = capture;
        Log.Information("[CaptureManager] Started {Id}: '{Title}'", id, title);
        return id;
    }

    /// <summary>
    /// キャプチャを停止・削除する。
    /// </summary>
    public bool StopCapture(string id)
    {
        if (!_captures.TryRemove(id, out var capture))
            return false;

        capture.Dispose();
        Log.Information("[CaptureManager] Stopped {Id}", id);
        return true;
    }

    /// <summary>
    /// アクティブなキャプチャ一覧を取得する。
    /// </summary>
    public List<CaptureInfo> ListCaptures()
    {
        return _captures.Values
            .Select(c => new CaptureInfo(c.Id, c.WindowTitle, c.FrameCount))
            .ToList();
    }

    /// <summary>
    /// 指定キャプチャの最新JPEGフレームを取得する。
    /// </summary>
    public byte[]? GetSnapshot(string id)
    {
        return _captures.TryGetValue(id, out var capture) ? capture.GetLatestFrame() : null;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        foreach (var capture in _captures.Values)
            capture.Dispose();
        _captures.Clear();
    }
}
