using System.Globalization;
using System.Runtime.InteropServices;
using Microsoft.Web.WebView2.WinForms;
using Serilog;
using WinNativeApp.Capture;
using WinNativeApp.Server;
using WinNativeApp.Streaming;

namespace WinNativeApp;

public class MainForm : Form
{
    // DWM Dark Mode API
    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
    private const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;

    private readonly WebView2 _webView;
    private FrameCapture? _capture;
    private readonly string[] _args;
    private readonly string _url;
    private readonly bool _autoStream;

    // Streaming pipeline
    private FfmpegProcess? _ffmpeg;
    private AudioLoopback? _audio;
    private bool _closing;
    private bool _forceClose;
    private DateTime _streamStartTime;
    private string? _activeStreamKey;

    // Window capture (Phase 3)
    private CaptureManager? _captureManager;
    private HttpServer? _httpServer;
    private readonly int _httpPort;

    // System tray (Phase 5)
    private NotifyIcon? _trayIcon;
    private ToolStripMenuItem? _trayStatusItem;
    private ToolStripMenuItem? _trayStreamItem;
    private System.Windows.Forms.Timer? _trayUpdateTimer;

    public MainForm(string[] args)
    {
        _args = args;
        _url = args.FirstOrDefault(a => !a.StartsWith("--")) ?? "https://example.com";
        _autoStream = args.Contains("--stream");
        _httpPort = int.TryParse(
            Environment.GetEnvironmentVariable("WIN_CAPTURE_PORT"), out var p) ? p : 9090;

        Text = "AI Twitch Cast - 起動中";
        StartPosition = FormStartPosition.CenterScreen;
        Size = new Size(1280, 720);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        ShowInTaskbar = true;

        // タイトルバーをダークモードに設定
        var darkMode = 1;
        DwmSetWindowAttribute(Handle, DWMWA_USE_IMMERSIVE_DARK_MODE, ref darkMode, sizeof(int));

        _webView = new WebView2 { Dock = DockStyle.Fill };
        Controls.Add(_webView);

        InitializeTrayIcon();

        Load += OnLoad;
        FormClosing += OnFormClosing;
    }

    // =====================================================
    // システムトレイアイコン
    // =====================================================

    private void InitializeTrayIcon()
    {
        _trayStatusItem = new ToolStripMenuItem("状態: 起動中...") { Enabled = false };
        _trayStreamItem = new ToolStripMenuItem("配信開始", null, OnTrayStreamToggle);

        var menu = new ContextMenuStrip();
        menu.Items.Add(_trayStatusItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(_trayStreamItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("終了", null, (_, _) => { _forceClose = true; Close(); });

        _trayIcon = new NotifyIcon
        {
            Icon = CreateTrayIcon(Color.Gray),
            Text = "AI Twitch Cast - 起動中",
            Visible = true,
            ContextMenuStrip = menu,
        };
        _trayIcon.DoubleClick += (_, _) =>
        {
            Show();
            WindowState = FormWindowState.Normal;
            Activate();
        };

        // トレイアイコン定期更新（3秒）
        _trayUpdateTimer = new System.Windows.Forms.Timer { Interval = 3000 };
        _trayUpdateTimer.Tick += OnTrayUpdate;
        _trayUpdateTimer.Start();
    }

    private void OnTrayUpdate(object? sender, EventArgs e)
    {
        var streaming = _ffmpeg is { IsRunning: true };
        var captures = _captureManager?.ListCaptures().Count ?? 0;

        if (streaming)
        {
            var uptime = _ffmpeg!.Uptime;
            var frames = _ffmpeg.FrameCount;
            var uptimeStr = uptime.ToString(@"hh\:mm\:ss");
            _trayIcon!.Icon = CreateTrayIcon(Color.Red);
            _trayIcon.Text = $"配信中 ({uptimeStr}) - {frames} frames";
            _trayStatusItem!.Text = $"配信中: {uptimeStr} / {frames} frames";
            _trayStreamItem!.Text = "配信停止";
            Text = $"AI Twitch Cast - 配信中 {uptimeStr}";
        }
        else
        {
            _trayIcon!.Icon = CreateTrayIcon(Color.LimeGreen);
            _trayIcon.Text = $"AI Twitch Cast - 待機中 (キャプチャ: {captures})";
            _trayStatusItem!.Text = $"待機中 (キャプチャ: {captures})";
            _trayStreamItem!.Text = "配信開始";
            Text = "AI Twitch Cast - 待機中";
        }
    }

    private async void OnTrayStreamToggle(object? sender, EventArgs e)
    {
        if (_ffmpeg is { IsRunning: true })
        {
            await StopStreamingAsync();
            _trayIcon?.ShowBalloonTip(2000, "AI Twitch Cast", "配信を停止しました", ToolTipIcon.Info);
        }
        else
        {
            var config = StreamConfig.FromArgs(_args);
            if (string.IsNullOrEmpty(config.StreamKey) && string.IsNullOrEmpty(_activeStreamKey))
            {
                _trayIcon?.ShowBalloonTip(3000, "AI Twitch Cast", "ストリームキーが設定されていません", ToolTipIcon.Warning);
                return;
            }
            try
            {
                await StartStreamingWithKeyAsync(_activeStreamKey ?? config.StreamKey ?? "");
                _trayIcon?.ShowBalloonTip(2000, "AI Twitch Cast", "配信を開始しました", ToolTipIcon.Info);
            }
            catch (Exception ex)
            {
                _trayIcon?.ShowBalloonTip(3000, "AI Twitch Cast", $"配信開始失敗: {ex.Message}", ToolTipIcon.Error);
            }
        }
    }

    private static Icon CreateTrayIcon(Color color)
    {
        var bmp = new Bitmap(16, 16);
        using var g = Graphics.FromImage(bmp);
        g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        using var brush = new SolidBrush(color);
        g.FillEllipse(brush, 2, 2, 12, 12);
        using var pen = new Pen(Color.White, 1);
        g.DrawEllipse(pen, 2, 2, 12, 12);
        return Icon.FromHandle(bmp.GetHicon());
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

        // キャプチャコールバック
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

        // 配信制御コールバック
        _httpServer.OnStartStream = async (streamKey, serverUrl) =>
        {
            return await HandleStartStreamRequest(streamKey, serverUrl);
        };

        _httpServer.OnStopStream = async () =>
        {
            return await HandleStopStreamRequest();
        };

        _httpServer.OnGetStreamStatus = () => GetStreamStatusDict();

        _httpServer.OnScreenshot = async () =>
        {
            return await TakeScreenshotAsync();
        };

        _httpServer.OnQuit = () =>
        {
            BeginInvoke(() => { _forceClose = true; Close(); });
        };

        try
        {
            _httpServer.Start();
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[MainForm] HTTP server start failed on port {Port}", _httpPort);
        }
    }

    // =====================================================
    // 配信制御（WebSocket/HTTP共通）
    // =====================================================

    private async Task<object> HandleStartStreamRequest(string streamKey, string? serverUrl)
    {
        // WebView2操作はUIスレッドが必要 → InvokeでUIスレッドに移動
        var tcs = new TaskCompletionSource<object>();
        BeginInvoke(async () =>
        {
            try
            {
                var result = await HandleStartStreamOnUIThread(streamKey, serverUrl);
                tcs.TrySetResult(result);
            }
            catch (Exception ex)
            {
                tcs.TrySetResult(new Dictionary<string, object> { ["ok"] = false, ["error"] = ex.Message });
            }
        });
        return await tcs.Task;
    }

    private async Task<object> HandleStartStreamOnUIThread(string streamKey, string? serverUrl)
    {
        if (_ffmpeg != null)
            return new Dictionary<string, object> { ["ok"] = false, ["error"] = "既に配信中です" };

        if (string.IsNullOrEmpty(streamKey))
        {
            // 引数・環境変数からフォールバック
            streamKey = StreamConfig.FromArgs(_args).StreamKey ?? "";
            if (string.IsNullOrEmpty(streamKey))
                return new Dictionary<string, object> { ["ok"] = false, ["error"] = "streamKey が必要です" };
        }

        _activeStreamKey = streamKey;

        try
        {
            // serverUrl指定があればbroadcast.htmlを再ナビゲーション
            if (!string.IsNullOrEmpty(serverUrl) && _webView.CoreWebView2 != null)
            {
                var currentUrl = _webView.CoreWebView2.Source;
                if (!currentUrl.StartsWith(serverUrl, StringComparison.OrdinalIgnoreCase))
                {
                    Log.Information("[MainForm] Navigating to serverUrl: {Url}", serverUrl);
                    // serverUrlからbroadcast URLを構築（tokenは現在のURLから引き継ぎ）
                    var token = "";
                    if (currentUrl.Contains("token="))
                    {
                        var idx = currentUrl.IndexOf("token=", StringComparison.Ordinal);
                        token = currentUrl[(idx + 6)..];
                        if (token.Contains('&'))
                            token = token[..token.IndexOf('&')];
                    }
                    var newUrl = $"{serverUrl.TrimEnd('/')}/broadcast?token={token}";
                    _webView.CoreWebView2.Navigate(newUrl);
                    await Task.Delay(2000); // ページ読み込み待ち
                }
            }

            await StartStreamingWithKeyAsync(streamKey);
            return new Dictionary<string, object> { ["ok"] = true };
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[MainForm] start_stream failed");
            return new Dictionary<string, object> { ["ok"] = false, ["error"] = ex.Message };
        }
    }

    private async Task<object> HandleStopStreamRequest()
    {
        var tcs = new TaskCompletionSource<object>();
        BeginInvoke(async () =>
        {
            try
            {
                if (_ffmpeg == null)
                {
                    tcs.TrySetResult(new Dictionary<string, object> { ["ok"] = false, ["error"] = "配信中ではありません" });
                    return;
                }

                var uptime = _ffmpeg.Uptime;
                var frames = _ffmpeg.FrameCount;
                var drops = _ffmpeg.DropCount;

                await StopStreamingAsync();

                tcs.TrySetResult(new Dictionary<string, object>
                {
                    ["ok"] = true,
                    ["uptime_seconds"] = (int)uptime.TotalSeconds,
                    ["frames_sent"] = frames,
                    ["frames_dropped"] = drops,
                });
            }
            catch (Exception ex)
            {
                tcs.TrySetResult(new Dictionary<string, object> { ["ok"] = false, ["error"] = ex.Message });
            }
        });
        return await tcs.Task;
    }

    private object GetStreamStatusDict()
    {
        var streaming = _ffmpeg is { IsRunning: true };
        var config = StreamConfig.FromArgs(_args);

        var ffmpegPath = "";
        try
        {
            var candidates = new[]
            {
                config.FfmpegPath ?? "",
                Path.Combine(AppContext.BaseDirectory, "resources", "ffmpeg", "ffmpeg.exe"),
                Path.Combine(AppContext.BaseDirectory, "ffmpeg.exe"),
                "ffmpeg.exe"
            };
            ffmpegPath = candidates.FirstOrDefault(p => !string.IsNullOrEmpty(p) && File.Exists(p)) ?? "ffmpeg.exe";
        }
        catch { ffmpegPath = "ffmpeg.exe"; }

        return new Dictionary<string, object>
        {
            ["streaming"] = streaming,
            ["broadcast_window_open"] = true,
            ["uptime_seconds"] = streaming ? (object)(int)_ffmpeg!.Uptime.TotalSeconds : null!,
            ["frames_sent"] = _ffmpeg?.FrameCount ?? 0,
            ["frames_dropped"] = _ffmpeg?.DropCount ?? 0,
            ["config"] = new Dictionary<string, object>
            {
                ["resolution"] = $"{config.Width}x{config.Height}",
                ["framerate"] = config.Framerate,
                ["videoBitrate"] = config.VideoBitrate,
                ["audioBitrate"] = config.AudioBitrate,
                ["preset"] = config.Preset,
            },
            ["ffmpeg_path"] = ffmpegPath,
            ["ffmpeg_exists"] = File.Exists(ffmpegPath),
            ["audio_stream_connected"] = _audio != null,
            ["audio_receiving_pcm"] = _audio != null && streaming,
            ["mixer_active"] = false,
            ["bgm_playing"] = false,
            ["tts_playing"] = false,
        };
    }

    private Task<string?> TakeScreenshotAsync()
    {
        var tcs = new TaskCompletionSource<string?>();
        // CoreWebView2へのアクセスはすべてUIスレッドで実行する必要がある
        BeginInvoke(async () =>
        {
            try
            {
                if (_webView.CoreWebView2 == null)
                {
                    tcs.SetResult(null);
                    return;
                }
                using var ms = new MemoryStream();
                await _webView.CoreWebView2.CapturePreviewAsync(
                    Microsoft.Web.WebView2.Core.CoreWebView2CapturePreviewImageFormat.Png, ms);
                tcs.SetResult(Convert.ToBase64String(ms.ToArray()));
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[MainForm] Screenshot failed");
                tcs.TrySetResult(null);
            }
        });
        return tcs.Task;
    }

    // =====================================================
    // 配信パイプライン
    // =====================================================

    private async Task StartStreamingWithKeyAsync(string streamKey)
    {
        if (_capture == null)
        {
            Log.Error("[MainForm] Cannot stream: no capture running");
            throw new InvalidOperationException("No capture running");
        }

        var config = StreamConfig.FromArgs(_args);
        config.StreamKey = streamKey;

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

        _streamStartTime = DateTime.UtcNow;
        Log.Information("[MainForm] Streaming pipeline active");
    }

    // =====================================================
    // キャプチャレイヤーJS injection
    // =====================================================

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

    // =====================================================
    // ナビゲーション・キャプチャ
    // =====================================================

    private async void OnNavigationCompleted(object? sender,
        Microsoft.Web.WebView2.Core.CoreWebView2NavigationCompletedEventArgs e)
    {
        Log.Information("[MainForm] Navigation completed, success={Success}", e.IsSuccess);

        if (!e.IsSuccess) return;

        Text = "AI Twitch Cast - 待機中";

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

            await StartStreamingWithKeyAsync(config.StreamKey);
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

        _activeStreamKey = null;
        Log.Information("[MainForm] Streaming stopped");
    }

    private async void OnFormClosing(object? sender, FormClosingEventArgs e)
    {
        if (_closing)
        {
            // Second pass after async cleanup
            CleanupResources();
            return;
        }

        // 配信中に閉じるボタン → トレイに最小化（誤終了防止）
        if (_ffmpeg is { IsRunning: true } && e.CloseReason == CloseReason.UserClosing && !_forceClose)
        {
            e.Cancel = true;
            WindowState = FormWindowState.Minimized;
            Hide();
            _trayIcon?.ShowBalloonTip(2000, "AI Twitch Cast", "配信中のためトレイに最小化しました", ToolTipIcon.Info);
            Log.Information("[MainForm] Minimized to tray (streaming active)");
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

        CleanupResources();
    }

    private void CleanupResources()
    {
        _trayUpdateTimer?.Stop();
        _trayUpdateTimer?.Dispose();
        if (_trayIcon != null)
        {
            _trayIcon.Visible = false;
            _trayIcon.Dispose();
        }
        _capture?.Stop();
        _capture?.Dispose();
        _captureManager?.Dispose();
        _httpServer?.Dispose();
        Log.Information("[MainForm] Closed");
    }
}
