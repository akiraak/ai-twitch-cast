using System.Drawing;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
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

    // Win32: クライアント領域オフセット計算用
    [DllImport("user32.dll")]
    private static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
    [DllImport("user32.dll")]
    private static extern bool ClientToScreen(IntPtr hwnd, ref POINT point);
    [StructLayout(LayoutKind.Sequential)]
    private struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    private struct POINT { public int X, Y; }

    // Phase 7: 配信領域サイズ（UIパネルを除いたbroadcast.html部分）
    private const int BroadcastWidth = 1280;
    private const int BroadcastHeight = 720;
    private const int UiPanelWidth = 400;

    private readonly WebView2 _webView;
    private readonly WebView2 _panelView;  // Phase 7: UIパネル（HTML/CSS）
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

    // サーバーAPI用共有HttpClient（初期音量取得用）
    private static readonly HttpClient _sharedHttp = new() { Timeout = TimeSpan.FromSeconds(10) };

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
        // Phase 7: 配信領域 + UIパネル
        ClientSize = new Size(BroadcastWidth + UiPanelWidth, BroadcastHeight);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        ShowInTaskbar = true;

        // タイトルバーをダークモードに設定
        var darkMode = 1;
        DwmSetWindowAttribute(Handle, DWMWA_USE_IMMERSIVE_DARK_MODE, ref darkMode, sizeof(int));

        // Phase 7: WebView2は左側に固定配置（Dock.Fillではなく明示的サイズ）
        _webView = new WebView2
        {
            Location = new Point(0, 0),
            Size = new Size(BroadcastWidth, BroadcastHeight),
            Anchor = AnchorStyles.Top | AnchorStyles.Left,
        };
        Controls.Add(_webView);

        // Phase 7: UIパネル（WebView2 + HTML/CSS）を右側に配置
        _panelView = new WebView2
        {
            Location = new Point(BroadcastWidth, 0),
            Size = new Size(UiPanelWidth, BroadcastHeight),
            Anchor = AnchorStyles.Top | AnchorStyles.Left,
        };
        Controls.Add(_panelView);

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
        var uptime = streaming ? _ffmpeg!.Uptime : TimeSpan.Zero;
        var frames = _ffmpeg?.FrameCount ?? 0;
        var drops = _ffmpeg?.DropCount ?? 0;

        if (streaming)
        {
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

        // Phase 7: UIパネルに状態送信
        SendPanelMessage(new
        {
            type = "status",
            streaming,
            uptime = uptime.ToString(@"hh\:mm\:ss"),
            frames,
            drops
        });
        SendPanelCaptures();
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


    // =====================================================
    // UIパネル (Phase 7: WebView2 + HTML/CSS)
    // =====================================================

    /// <summary>パネルWebView2にJSONメッセージを送信する</summary>
    private void SendPanelMessage(object data)
    {
        if (_panelView.CoreWebView2 == null) return;
        try
        {
            _panelView.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(data));
        }
        catch { /* panel not ready */ }
    }

    /// <summary>パネルのログエリアにメッセージを表示する</summary>
    private void PanelLog(string text, string level = "")
    {
        SendPanelMessage(new { type = "log", text, level });
    }

    /// <summary>パネルにキャプチャ一覧を送信する</summary>
    private void SendPanelCaptures()
    {
        var captures = _captureManager?.ListCaptures() ?? [];
        SendPanelMessage(new
        {
            type = "captures",
            captures = captures.Select(c => new { id = c.Id, name = c.Name }).ToArray()
        });
    }

    /// <summary>パネルからのメッセージを処理する</summary>
    private async void OnPanelMessage(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        try
        {
            Log.Debug("[Panel] Received message: {Json}", e.WebMessageAsJson);
            var msg = JsonSerializer.Deserialize<JsonElement>(e.WebMessageAsJson);
            var action = msg.GetProperty("action").GetString() ?? "";
            Log.Information("[Panel] Action: {Action}", action);

            switch (action)
            {
                case "init":
                    // 初期状態を送信
                    PanelLog("接続完了", "success");
                    var windows = WindowEnumerator.GetWindows();
                    SendPanelMessage(new
                    {
                        type = "windows",
                        windows = windows.Select(w => new { title = w.Title, hwnd = $"0x{w.Hwnd.ToInt64():X}" }).ToArray()
                    });
                    SendPanelCaptures();
                    // サーバーから現在の音量を取得してパネルに反映
                    _ = Task.Run(async () =>
                    {
                        try
                        {
                            var serverUrl = _url.Contains("/broadcast")
                                ? _url[.._url.IndexOf("/broadcast", StringComparison.Ordinal)]
                                : "http://localhost:8080";
                            var json = await _sharedHttp.GetStringAsync($"{serverUrl}/api/broadcast/volume");
                            var vol = JsonSerializer.Deserialize<JsonElement>(json);
                            BeginInvoke(() => SendPanelMessage(new
                            {
                                type = "volume",
                                master = (int)(vol.GetProperty("master").GetDouble() * 100),
                                tts = (int)(vol.GetProperty("tts").GetDouble() * 100),
                                bgm = (int)(vol.GetProperty("bgm").GetDouble() * 100),
                            }));
                        }
                        catch (Exception ex)
                        {
                            Log.Debug("[MainForm] Volume fetch failed: {Error}", ex.Message);
                        }
                    });
                    break;

                case "goLive":
                    await HandlePanelGoLive();
                    break;

                case "stopStream":
                    await HandlePanelStopStream();
                    break;

                case "refreshWindows":
                    var wins = WindowEnumerator.GetWindows();
                    SendPanelMessage(new
                    {
                        type = "windows",
                        windows = wins.Select(w => new { title = w.Title, hwnd = $"0x{w.Hwnd.ToInt64():X}" }).ToArray()
                    });
                    PanelLog($"ウィンドウ一覧更新: {wins.Count}件", "info");
                    break;

                case "startCapture":
                    HandlePanelStartCapture(msg);
                    break;

                case "stopCapture":
                    HandlePanelStopCapture(msg);
                    break;

                case "volume":
                    HandlePanelVolume(msg);
                    break;
            }
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[Panel] OnPanelMessage error for: {Json}", e.WebMessageAsJson);
        }
    }

    private async Task HandlePanelGoLive()
    {
        var config = StreamConfig.FromArgs(_args);
        var key = _activeStreamKey ?? config.StreamKey;
        if (string.IsNullOrEmpty(key))
        {
            PanelLog("ストリームキーが未設定です", "error");
            return;
        }
        try
        {
            await StartStreamingWithKeyAsync(key);
            PanelLog("配信を開始しました", "success");
        }
        catch (Exception ex)
        {
            PanelLog($"配信開始失敗: {ex.Message}", "error");
        }
    }

    private async Task HandlePanelStopStream()
    {
        Log.Information("[Panel] HandlePanelStopStream called, _ffmpeg={HasFfmpeg}, IsRunning={Running}",
            _ffmpeg != null, _ffmpeg?.IsRunning);
        try
        {
            await StopStreamingAsync();
            PanelLog("配信を停止しました", "success");
            Log.Information("[Panel] HandlePanelStopStream completed successfully");
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[Panel] HandlePanelStopStream failed");
            PanelLog($"配信停止失敗: {ex.Message}", "error");
        }
    }

    private void HandlePanelStartCapture(JsonElement msg)
    {
        if (_captureManager == null) return;
        var hwndStr = msg.GetProperty("hwnd").GetString() ?? "";
        var title = msg.GetProperty("title").GetString() ?? "";
        try
        {
            var hwnd = ParseHwnd(hwndStr);
            var id = _captureManager.StartCapture(hwnd, title, 15, 70);
            InjectAddCaptureLayer(id, title);
            SendPanelCaptures();
            PanelLog($"キャプチャ開始: {title}", "success");
        }
        catch (Exception ex)
        {
            PanelLog($"キャプチャ開始失敗: {ex.Message}", "error");
        }
    }

    private void HandlePanelStopCapture(JsonElement msg)
    {
        if (_captureManager == null) return;
        var id = msg.GetProperty("id").GetString() ?? "";
        var ok = _captureManager.StopCapture(id);
        if (ok)
        {
            InjectRemoveCaptureLayer(id);
            SendPanelCaptures();
            PanelLog($"キャプチャ停止: {id}", "info");
        }
    }

    private void HandlePanelVolume(JsonElement msg)
    {
        var volumeType = msg.GetProperty("volumeType").GetString() ?? "";
        var value = msg.GetProperty("value").GetInt32();
        var vol = value / 100.0;
        var volStr = vol.ToString("F2", CultureInfo.InvariantCulture);

        if (_webView.CoreWebView2 == null) return;

        // broadcast.htmlの音量を即座に変更 + WebSocket経由でサーバーに保存（デバウンス200ms）
        var js = $@"
            if (typeof volumes !== 'undefined') {{
                volumes.{EscapeJs(volumeType)} = {volStr};
                if (typeof applyVolume === 'function') applyVolume();
            }}
            clearTimeout(window._volSaveTimer);
            window._volSaveTimer = setTimeout(function() {{
                if (window._ws && window._ws.readyState === 1) {{
                    window._ws.send(JSON.stringify({{
                        type: 'save_volume',
                        source: '{EscapeJs(volumeType)}',
                        volume: {volStr}
                    }}));
                }}
            }}, 200);";
        _ = _webView.CoreWebView2.ExecuteScriptAsync(js);
    }

    private async void OnLoad(object? sender, EventArgs e)
    {
        Log.Information("[MainForm] Loaded, initializing WebView2...");

        try
        {
            // broadcast.html用WebView2（autoplay音声許可 + バックグラウンドスロットリング無効化）
            var env = await CoreWebView2Environment.CreateAsync(null, null,
                new CoreWebView2EnvironmentOptions(
                    "--autoplay-policy=no-user-gesture-required " +
                    "--disable-background-timer-throttling " +
                    "--disable-renderer-backgrounding " +
                    "--disable-backgrounding-occluded-windows"));
            await _webView.EnsureCoreWebView2Async(env);
            Log.Information("[MainForm] WebView2 ready, version={Version}",
                _webView.CoreWebView2.Environment.BrowserVersionString);

            _webView.CoreWebView2.NavigationCompleted += OnNavigationCompleted;
            // JSコンソールをC#ログに転送（WebView2 postMessage経由）
            _webView.CoreWebView2.WebMessageReceived += (_, args) =>
            {
                try
                {
                    var msg = JsonSerializer.Deserialize<JsonElement>(args.WebMessageAsJson);
                    if (msg.TryGetProperty("_console", out var text))
                        Log.Debug("[WebView2:JS] {Message}", text.GetString());
                    // broadcast.htmlからの音量変更通知 → パネルに転送
                    if (msg.TryGetProperty("_volumeSync", out var volSync))
                    {
                        SendPanelMessage(new
                        {
                            type = "volume",
                            master = (int)(volSync.GetProperty("master").GetDouble() * 100),
                            tts = (int)(volSync.GetProperty("tts").GetDouble() * 100),
                            bgm = (int)(volSync.GetProperty("bgm").GetDouble() * 100),
                        });
                    }
                    // broadcast.htmlからの音量レベル → パネルに転送
                    if (msg.TryGetProperty("_audioLevel", out var audioLevel))
                    {
                        SendPanelMessage(new
                        {
                            type = "audioLevel",
                            db = audioLevel.GetProperty("db").GetDouble(),
                            peak = audioLevel.GetProperty("peak").GetDouble(),
                            bgm = audioLevel.GetProperty("bgm").GetBoolean(),
                            tts = audioLevel.GetProperty("tts").GetBoolean(),
                        });
                    }
                }
                catch { }
            };
            await _webView.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(@"
                (function(){
                    const orig = console.log;
                    console.log = function(){
                        orig.apply(console, arguments);
                        try { window.chrome.webview.postMessage({_console: Array.from(arguments).join(' ')}); } catch(e){}
                    };
                    const origErr = console.error;
                    console.error = function(){
                        origErr.apply(console, arguments);
                        try { window.chrome.webview.postMessage({_console: 'ERROR: ' + Array.from(arguments).join(' ')}); } catch(e){}
                    };
                })();
            ");
            _webView.CoreWebView2.Navigate(_url);
            Log.Information("[MainForm] Navigating to {Url}", _url);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[MainForm] WebView2 init failed");
        }

        // ウィンドウキャプチャ管理 + HTTPサーバー起動
        InitializeCaptureServer();

        // Phase 7: パネルWebView2初期化（HTTPサーバー起動後）
        try
        {
            await _panelView.EnsureCoreWebView2Async(_webView.CoreWebView2.Environment);
            _panelView.CoreWebView2.WebMessageReceived += OnPanelMessage;
            // C#アプリのHTTPサーバーからパネルHTMLを取得
            _panelView.CoreWebView2.Navigate($"http://localhost:{_httpPort}/panel");
            Log.Information("[MainForm] Panel WebView2 initialized");
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[MainForm] Panel WebView2 init failed");
        }
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

        // 3.5. FFmpegがパイプの読み取りを開始するまで待機（音声途切れ防止）
        await Task.Delay(500);

        // 4. Connect audio loopback → FFmpeg audio pipe
        _audio.Start((data, offset, count) => _ffmpeg.WriteAudioData(data, offset, count));

        // 5. Connect frame capture → FFmpeg video stdin
        _capture.TargetFps = config.Framerate;
        _capture.OnFrameReady = (data, w, h) => _ffmpeg.WriteVideoFrame(data);

        _streamStartTime = DateTime.UtcNow;
        Text = "AI Twitch Cast - 配信中";
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
                 $"addCaptureLayer('{EscapeJs(id)}','{EscapeJs(snapshotUrl)}','{EscapeJs(title)}'," +
                 $"{{x:5,y:10,width:40,height:45,zIndex:2}})";
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

        // 音声診断ログ
        _ = _webView.CoreWebView2.ExecuteScriptAsync(@"
            setTimeout(() => {
                const bgm = document.getElementById('bgm-audio');
                const tts = document.getElementById('tts-audio');
                console.log('[AudioDiag] bgm.paused=' + bgm?.paused + ' src=' + (bgm?.src||'') + ' volume=' + bgm?.volume + ' muted=' + bgm?.muted + ' readyState=' + bgm?.readyState);
                console.log('[AudioDiag] tts.paused=' + tts?.paused + ' src=' + (tts?.src||'') + ' volume=' + tts?.volume);
                if (typeof _meterCtx !== 'undefined' && _meterCtx) {
                    console.log('[AudioDiag] AudioContext state=' + _meterCtx.state + ' sampleRate=' + _meterCtx.sampleRate);
                } else {
                    console.log('[AudioDiag] AudioContext not created');
                }
            }, 3000);
        ");

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

            // Phase 7: WGCはウィンドウ全体（タイトルバー+枠含む）をキャプチャするため、
            // クライアント領域のオフセットを計算してクロップに反映する
            GetWindowRect(Handle, out var windowRect);
            var clientOrigin = new POINT { X = 0, Y = 0 };
            ClientToScreen(Handle, ref clientOrigin);
            int offsetX = clientOrigin.X - windowRect.Left;
            int offsetY = clientOrigin.Y - windowRect.Top;

            capture.CropRect = new Rectangle(offsetX, offsetY, BroadcastWidth, BroadcastHeight);
            Log.Information("[MainForm] CropRect set to ({X},{Y},{W},{H}) (client offset: {OX},{OY})",
                offsetX, offsetY, BroadcastWidth, BroadcastHeight, offsetX, offsetY);
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
        // ★ 最初にキャプチャコールバックを切断（_ffmpeg=null後にコールバックが飛ぶとNRE→クラッシュ）
        if (_capture != null)
        {
            _capture.OnFrameReady = null;
            _capture.TargetFps = 0;
        }
        Log.Information("[Stop] Capture disconnected");

        // ローカル変数に退避してフィールドを即座にクリア
        // → UI更新（OnTrayUpdate）と×ボタン（OnFormClosing）が即座に正しく動作する
        var ffmpeg = _ffmpeg;
        var audio = _audio;
        _ffmpeg = null;
        _audio = null;
        _activeStreamKey = null;
        Text = "AI Twitch Cast - 待機中";
        Log.Information("[Stop] State cleared. Starting cleanup...");

        // クリーンアップ（ローカル変数で実行、フィールドは既にnull）
        Log.Information("[Stop] audio.Stop()...");
        try { audio?.Stop(); }
        catch (Exception ex) { Log.Error(ex, "[Stop] audio.Stop() failed"); }
        Log.Information("[Stop] audio.Stop() done");

        Log.Information("[Stop] audio.Dispose()...");
        try { audio?.Dispose(); }
        catch (Exception ex) { Log.Error(ex, "[Stop] audio.Dispose() failed"); }
        Log.Information("[Stop] audio.Dispose() done");

        if (ffmpeg != null)
        {
            Log.Information("[Stop] ffmpeg.StopAsync()...");
            try { await ffmpeg.StopAsync(); }
            catch (Exception ex) { Log.Error(ex, "[Stop] ffmpeg.StopAsync() failed"); }
            Log.Information("[Stop] ffmpeg.StopAsync() done");

            Log.Information("[Stop] ffmpeg.Dispose()...");
            try { ffmpeg.Dispose(); }
            catch (Exception ex) { Log.Error(ex, "[Stop] ffmpeg.Dispose() failed"); }
            Log.Information("[Stop] ffmpeg.Dispose() done");
        }

        Log.Information("[Stop] Streaming stopped");
    }

    private void OnFormClosing(object? sender, FormClosingEventArgs e)
    {
        Log.Information("[MainForm] OnFormClosing: reason={Reason} closing={Closing} forceClose={Force}",
            e.CloseReason, _closing, _forceClose);

        if (_closing)
        {
            // Second pass — skip (Environment.Exit handles actual exit)
            Log.Information("[MainForm] OnFormClosing: second pass, skipping");
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

        // ★ 即座にウィンドウを隠す（クリーンアップ中の「間」を解消）
        e.Cancel = true;
        _closing = true;
        Hide();
        try { _webView.CoreWebView2.IsMuted = true; } catch { }

        // 安全タイマー: クリーンアップが何秒かかっても5秒後に強制終了
        _ = Task.Run(async () =>
        {
            await Task.Delay(5000);
            Log.Warning("[MainForm] Safety timeout: forcing exit after 5s");
            Log.CloseAndFlush();
            Environment.Exit(1);
        });

        Log.Information("[MainForm] Closing: starting cleanup (ffmpeg={HasFfmpeg})...",
            _ffmpeg != null);

        // タイムアウト付きストリーミング停止（最大3秒）
        if (_ffmpeg != null)
        {
            var stopTask = Task.Run(async () =>
            {
                try
                {
                    Log.Information("[MainForm] Closing: StopStreamingAsync...");
                    await StopStreamingAsync();
                    Log.Information("[MainForm] Closing: StopStreamingAsync done");
                }
                catch (Exception ex)
                {
                    Log.Error(ex, "[MainForm] Error stopping stream during close");
                    try { _ffmpeg?.Dispose(); } catch { }
                    _ffmpeg = null;
                    _audio?.Dispose();
                    _audio = null;
                }
            });
            stopTask.Wait(3000);
        }

        Log.Information("[MainForm] Closing: CleanupResources...");
        CleanupResources();
        Log.Information("[MainForm] Exit");
        Log.CloseAndFlush();
        Environment.Exit(0);
    }

    private void CleanupResources()
    {
        Log.Information("[Cleanup] trayUpdateTimer...");
        _trayUpdateTimer?.Stop();
        _trayUpdateTimer?.Dispose();
        if (_trayIcon != null)
        {
            Log.Information("[Cleanup] trayIcon...");
            _trayIcon.Visible = false;
            _trayIcon.Dispose();
        }
        // 配信パイプラインが残っていたら強制クリーンアップ
        if (_ffmpeg != null)
        {
            Log.Information("[Cleanup] ffmpeg.Dispose...");
            try { _ffmpeg.Dispose(); } catch { }
            _ffmpeg = null;
        }
        Log.Information("[Cleanup] audio...");
        _audio?.Stop();
        _audio?.Dispose();
        _audio = null;
        Log.Information("[Cleanup] capture...");
        _capture?.Stop();
        _capture?.Dispose();
        Log.Information("[Cleanup] captureManager...");
        _captureManager?.Dispose();
        Log.Information("[Cleanup] httpServer...");
        _httpServer?.Dispose();
        Log.Information("[Cleanup] done");
    }
}
