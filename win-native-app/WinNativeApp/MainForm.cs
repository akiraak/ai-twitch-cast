using System.Globalization;
using Microsoft.Web.WebView2.WinForms;
using Serilog;
using WinNativeApp.Capture;
using WinNativeApp.Server;
using WinNativeApp.Streaming;

namespace WinNativeApp;

public class MainForm : Form
{
    private readonly WebView2 _webView;
    private FrameCapture? _capture;
    private readonly string[] _args;
    private readonly string _url;
    private readonly bool _autoStream;

    // Streaming pipeline
    private FfmpegProcess? _ffmpeg;
    private AudioLoopback? _audio;
    private bool _closing;

    // Window capture (Phase 3)
    private CaptureManager? _captureManager;
    private HttpServer? _httpServer;
    private readonly int _httpPort;

    public MainForm(string[] args)
    {
        _args = args;
        _url = args.FirstOrDefault(a => !a.StartsWith("--")) ?? "https://example.com";
        _autoStream = args.Contains("--stream");
        _httpPort = int.TryParse(
            Environment.GetEnvironmentVariable("WIN_CAPTURE_PORT"), out var p) ? p : 9090;

        Text = "WinNativeApp";
        StartPosition = FormStartPosition.Manual;
        Location = new Point(-32000, -32000);
        Size = new Size(1920, 1080);
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;

        _webView = new WebView2 { Dock = DockStyle.Fill };
        Controls.Add(_webView);

        Load += OnLoad;
        FormClosing += OnFormClosing;
    }


    private async void OnLoad(object? sender, EventArgs e)
    {
        Log.Information("[MainForm] Loaded, initializing WebView2...");

        try
        {
            await _webView.EnsureCoreWebView2Async();
            Log.Information("[MainForm] WebView2 ready, version={Version}",
                _webView.CoreWebView2.Environment.BrowserVersionString);

            _webView.CoreWebView2.NavigationCompleted += OnNavigationCompleted;
            _webView.CoreWebView2.Navigate(_url);
            Log.Information("[MainForm] Navigating to {Url}", _url);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[MainForm] WebView2 init failed");
        }

        // ウィンドウキャプチャ管理 + HTTPサーバー起動
        InitializeCaptureServer();
    }

    private void InitializeCaptureServer()
    {
        _captureManager = new CaptureManager();
        _httpServer = new HttpServer(_httpPort);

        _httpServer.OnListWindows = () => WindowEnumerator.GetWindows();

        _httpServer.OnStartCapture = (sourceId, fps, quality) =>
        {
            var hwnd = ParseHwnd(sourceId);
            var title = WindowEnumerator.GetWindowTitle(hwnd);
            var id = _captureManager.StartCapture(hwnd, title, fps, quality);
            // broadcast.htmlにキャプチャレイヤーを追加（UIスレッドで実行）
            BeginInvoke(() => InjectAddCaptureLayer(id, title));
            return id;
        };

        _httpServer.OnStopCapture = (captureId) =>
        {
            var ok = _captureManager.StopCapture(captureId);
            if (ok)
                BeginInvoke(() => InjectRemoveCaptureLayer(captureId));
            return ok;
        };

        _httpServer.OnListCaptures = () => _captureManager.ListCaptures();
        _httpServer.OnGetSnapshot = (id) => _captureManager.GetSnapshot(id);

        try
        {
            _httpServer.Start();
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[MainForm] HTTP server start failed on port {Port}", _httpPort);
        }
    }

    /// <summary>
    /// WebView2にJSを注入してbroadcast.htmlにキャプチャレイヤーを追加する。
    /// </summary>
    private void InjectAddCaptureLayer(string id, string title)
    {
        if (_webView.CoreWebView2 == null) return;
        var snapshotUrl = $"http://localhost:{_httpPort}/snapshot/{id}";
        var js = $"if(typeof addCaptureLayer==='function')" +
                 $"addCaptureLayer('{EscapeJs(id)}','{EscapeJs(snapshotUrl)}','{EscapeJs(title)}',null)";
        _ = _webView.CoreWebView2.ExecuteScriptAsync(js);
        Log.Debug("[MainForm] Injected addCaptureLayer: {Id}", id);
    }

    /// <summary>
    /// WebView2にJSを注入してbroadcast.htmlからキャプチャレイヤーを削除する。
    /// </summary>
    private void InjectRemoveCaptureLayer(string id)
    {
        if (_webView.CoreWebView2 == null) return;
        var js = $"if(typeof removeCaptureLayer==='function')removeCaptureLayer('{EscapeJs(id)}')";
        _ = _webView.CoreWebView2.ExecuteScriptAsync(js);
        Log.Debug("[MainForm] Injected removeCaptureLayer: {Id}", id);
    }

    private static string EscapeJs(string s) =>
        s.Replace("\\", "\\\\").Replace("'", "\\'").Replace("\n", "\\n");

    private static IntPtr ParseHwnd(string sourceId)
    {
        var s = sourceId.StartsWith("0x", StringComparison.OrdinalIgnoreCase)
            ? sourceId[2..] : sourceId;
        return new IntPtr(long.Parse(s, NumberStyles.HexNumber));
    }

    private async void OnNavigationCompleted(object? sender,
        Microsoft.Web.WebView2.Core.CoreWebView2NavigationCompletedEventArgs e)
    {
        Log.Information("[MainForm] Navigation completed, success={Success}", e.IsSuccess);

        if (!e.IsSuccess) return;

        // Wait for rendering to settle
        await Task.Delay(2000);
        StartCapture();

        if (_autoStream)
        {
            // Let capture warm up before streaming
            await Task.Delay(1000);
            await StartStreamingAsync();
        }
    }

    private void StartCapture()
    {
        try
        {
            var capture = new FrameCapture();
            capture.StartCapture(Handle);
            _capture = capture;
            Log.Information("[MainForm] Capture started for HWND=0x{Hwnd:X}", Handle);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[MainForm] Failed to start capture");
            _capture = null;
        }
    }

    public async Task StartStreamingAsync()
    {
        if (_capture == null)
        {
            Log.Error("[MainForm] Cannot stream: no capture running");
            return;
        }

        try
        {
            var config = StreamConfig.FromArgs(_args);
            if (string.IsNullOrEmpty(config.StreamKey))
            {
                Log.Error("[MainForm] --stream-key が未指定です");
                return;
            }

            Log.Information("[MainForm] Starting streaming pipeline...");
            Log.Information("[MainForm] Resolution={W}x{H} FPS={F} Bitrate={B}",
                config.Width, config.Height, config.Framerate, config.VideoBitrate);

            // 1. Initialize audio loopback → get format for FFmpeg
            _audio = new AudioLoopback();
            _audio.Initialize();

            // 2. Create FFmpeg process with config + actual audio format
            _ffmpeg = new FfmpegProcess(config, _audio.Format!);

            // 3. Start FFmpeg (creates named pipe, starts process, waits for pipe connection)
            await _ffmpeg.StartAsync();

            // 4. Connect audio loopback → FFmpeg audio pipe
            _audio.Start((data, offset, count) => _ffmpeg.WriteAudioData(data, offset, count));

            // 5. Connect frame capture → FFmpeg video stdin
            _capture.TargetFps = config.Framerate;
            _capture.OnFrameReady = (data, w, h) => _ffmpeg.WriteVideoFrame(data);

            Log.Information("[MainForm] Streaming pipeline active");
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[MainForm] Failed to start streaming");
            await StopStreamingAsync();
        }
    }

    public async Task StopStreamingAsync()
    {
        // Disconnect capture callback first to stop writing to closing pipes
        if (_capture != null)
        {
            _capture.OnFrameReady = null;
            _capture.TargetFps = 0;
        }

        _audio?.Stop();
        _audio?.Dispose();
        _audio = null;

        if (_ffmpeg != null)
        {
            await _ffmpeg.StopAsync();
            _ffmpeg.Dispose();
            _ffmpeg = null;
        }

        Log.Information("[MainForm] Streaming stopped");
    }

    private async void OnFormClosing(object? sender, FormClosingEventArgs e)
    {
        if (_closing)
        {
            // Second pass after async cleanup
            _capture?.Stop();
            _capture?.Dispose();
            _captureManager?.Dispose();
            _httpServer?.Dispose();
            Log.Information("[MainForm] Closed");
            return;
        }

        if (_ffmpeg != null)
        {
            // Need async cleanup → cancel close, do cleanup, re-close
            e.Cancel = true;
            _closing = true;
            await StopStreamingAsync();
            Close();
            return;
        }

        _capture?.Stop();
        _capture?.Dispose();
        _captureManager?.Dispose();
        _httpServer?.Dispose();
        Log.Information("[MainForm] Closed");
    }
}
