using System.Drawing;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using NAudio.Wave;
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
    private bool _closing;
    private bool _forceClose;
    private DateTime _streamStartTime;
    private string? _activeStreamKey;

    // BGM state
    private WaveOutEvent? _bgmWaveOut;
    private WaveChannel32? _bgmChannel;
    private MeteringWaveProvider? _bgmMeter;
    private MediaFoundationReader? _bgmReader;
    private string? _currentBgmUrl;
    private string? _currentBgmCachePath;
    private string _serverBaseUrl = "http://localhost:8080";

    // TTS再生中のサンプルレベル音量制御 + メータリング
    private WaveOutEvent? _ttsWaveOut;
    private WaveChannel32? _ttsChannel;
    private MeteringWaveProvider? _ttsMeter;

    // SE state
    private WaveChannel32? _seChannel;
    private MeteringWaveProvider? _seMeter;
    private static readonly string SeCacheDir = Path.Combine(Path.GetTempPath(), "ai-twitch-cast-se");

    // 音量トラッキング（0.0〜2.0 for master, 0.0〜1.0 for others）
    private float _volumeMaster = 0.8f;
    private float _volumeTts = 0.8f;
    private float _volumeBgm = 1.0f;
    private float _volumeTrack = 1.0f;  // 曲別ボリューム（bgm_playで受信）
    private float _volumeSe = 0.8f;

    // 音量メータータイマー（50ms間隔で音声レベルをパネルに送信）
    private System.Windows.Forms.Timer? _meterTimer;

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
                    SendPanelMessage(new { type = "serverUrl", url = _serverBaseUrl });
                    var windows = WindowEnumerator.GetWindows();
                    SendPanelMessage(new
                    {
                        type = "windows",
                        windows = windows.Select(w => new { title = w.Title, hwnd = $"0x{w.Hwnd.ToInt64():X}" }).ToArray()
                    });
                    SendPanelCaptures();
                    // 音量・syncDelayはbroadcast.htmlからの_volumeSync/_syncDelay通知で反映
                    // （broadcast.htmlがinit()でサーバーfetchし、postMessageでMainForm経由でパネルに転送）
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

                case "syncDelay":
                    HandlePanelSyncDelay(msg);
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
            SendPanelMessage(new { type = "streamResult", action = "goLive", ok = false });
            return;
        }
        try
        {
            await StartStreamingWithKeyAsync(key);
            PanelLog("配信を開始しました", "success");
            SendPanelMessage(new { type = "streamResult", action = "goLive", ok = true });
            OnTrayUpdate(null, EventArgs.Empty);
        }
        catch (Exception ex)
        {
            PanelLog($"配信開始失敗: {ex.Message}", "error");
            SendPanelMessage(new { type = "streamResult", action = "goLive", ok = false });
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
            SendPanelMessage(new { type = "streamResult", action = "stop", ok = true });
            OnTrayUpdate(null, EventArgs.Empty);
            Log.Information("[Panel] HandlePanelStopStream completed successfully");
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[Panel] HandlePanelStopStream failed");
            PanelLog($"配信停止失敗: {ex.Message}", "error");
            SendPanelMessage(new { type = "streamResult", action = "stop", ok = false });
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
            // Pythonサーバーにキャプチャ追加を通知
            _ = _httpServer?.BroadcastWsEvent(new { type = "capture_changed", action = "add", id, name = title });
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
            _ = _httpServer?.BroadcastWsEvent(new { type = "capture_changed", action = "remove", id });
        }
    }

    private void HandlePanelVolume(JsonElement msg)
    {
        var volumeType = msg.GetProperty("volumeType").GetString() ?? "";
        var value = msg.GetProperty("value").GetInt32();
        var vol = value / 100.0;
        var volStr = vol.ToString("F2", CultureInfo.InvariantCulture);

        // C#音声パイプラインに即時反映
        UpdateVolume(volumeType, (float)vol);

        if (_webView.CoreWebView2 == null) return;

        // track音量はbroadcast.htmlのvolumes変数には含めず、サーバーDBに曲別音量として保存
        if (volumeType == "track")
        {
            var bgmFile = _currentBgmUrl != null ? Uri.UnescapeDataString(Path.GetFileName(_currentBgmUrl)) : null;
            if (bgmFile != null)
            {
                var escapedFile = EscapeJs(bgmFile);
                var js = $@"
                    clearTimeout(window._trackVolSaveTimer);
                    window._trackVolSaveTimer = setTimeout(function() {{
                        if (window._ws && window._ws.readyState === 1) {{
                            window._ws.send(JSON.stringify({{
                                type: 'save_track_volume',
                                file: '{escapedFile}',
                                volume: {volStr}
                            }}));
                        }}
                    }}, 200);";
                _ = _webView.CoreWebView2.ExecuteScriptAsync(js);
            }
            return;
        }

        // broadcast.htmlのJS変数を更新 + WebSocket経由でサーバーDBに保存（デバウンス200ms）
        var jsVol = $@"
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
        _ = _webView.CoreWebView2.ExecuteScriptAsync(jsVol);
    }

    private void HandlePanelSyncDelay(JsonElement msg)
    {
        var value = msg.GetProperty("value").GetInt32();
        if (_webView.CoreWebView2 == null) return;

        // broadcast.htmlの遅延値を更新 + DB保存
        var js = $@"
            _lipsyncDelay = {value};
            console.log('[Sync] delay updated:', {value});
            clearTimeout(window._delaySaveTimer);
            window._delaySaveTimer = setTimeout(function() {{
                if (window._ws && window._ws.readyState === 1) {{
                    window._ws.send(JSON.stringify({{
                        type: 'save_volume',
                        source: 'overlay.sync.lipsyncDelay',
                        volume: {value}
                    }}));
                }}
            }}, 200);";
        _ = _webView.CoreWebView2.ExecuteScriptAsync(js);
    }

    /// <summary>音量値を更新し、C#音声パイプラインに反映する。</summary>
    private void UpdateVolume(string type, float vol)
    {
        if (type == "master") _volumeMaster = vol;
        else if (type == "tts") _volumeTts = vol;
        else if (type == "bgm") _volumeBgm = vol;
        else if (type == "track") _volumeTrack = vol;
        else if (type == "se") _volumeSe = vol;

        // master or bgm or track変更時: BGMローカル再生 + FFmpegミキサーに反映
        if (type == "master" || type == "bgm" || type == "track")
            ApplyBgmVolume();

        // master or tts変更時: 再生中TTSの音量をリアルタイム更新
        if (type == "master" || type == "tts")
            ApplyTtsVolume();

        // master or se変更時: 再生中SEの音量をリアルタイム更新
        if (type == "master" || type == "se")
            ApplySeVolume();
    }

    /// <summary>TTS実効音量を計算し、ローカル再生とFFmpegミキサーに適用する。</summary>
    private void ApplyTtsVolume()
    {
        var effectiveVol = EffectiveTtsVolume();
        var ch = _ttsChannel;
        if (ch != null)
            ch.Volume = Math.Clamp(effectiveVol, 0f, 1f);
        _ffmpeg?.SetTtsVolume(effectiveVol);
    }

    /// <summary>TTS実効音量: perceptual gain（二乗カーブ）— Python側と同じ計算式</summary>
    private float EffectiveTtsVolume()
    {
        return Math.Min(1.0f, _volumeTts * _volumeTts) * (_volumeMaster * _volumeMaster);
    }

    /// <summary>BGM実効音量を計算し、ローカル再生とFFmpegに適用する。</summary>
    private void ApplyBgmVolume()
    {
        var effectiveVol = EffectiveBgmVolume();
        if (_bgmChannel != null)
            _bgmChannel.Volume = Math.Clamp(effectiveVol, 0f, 1f);
        _ffmpeg?.SetBgmVolume(effectiveVol);
        Log.Debug("[BGM] Volume applied: master={M:F2} bgm={B:F2} track={T:F2} effective={E:F3}",
            _volumeMaster, _volumeBgm, _volumeTrack, effectiveVol);
    }

    /// <summary>BGM実効音量: perceptual gain（二乗カーブ） — TTS計算式と同じ + 曲別ボリューム</summary>
    private float EffectiveBgmVolume()
    {
        return Math.Min(1.0f, _volumeBgm * _volumeBgm) * (_volumeMaster * _volumeMaster) * _volumeTrack;
    }

    /// <summary>SE実効音量を計算し、ローカル再生に適用する。</summary>
    private void ApplySeVolume()
    {
        var effectiveVol = EffectiveSeVolume();
        var ch = _seChannel;
        if (ch != null)
            ch.Volume = Math.Clamp(effectiveVol, 0f, 1f);
        _ffmpeg?.SetSeVolume(effectiveVol);
    }

    /// <summary>SE実効音量: perceptual gain（二乗カーブ）</summary>
    private float EffectiveSeVolume()
    {
        return Math.Min(1.0f, _volumeSe * _volumeSe) * (_volumeMaster * _volumeMaster);
    }

    private async void OnLoad(object? sender, EventArgs e)
    {
        Log.Information("[MainForm] Loaded, initializing WebView2...");

        // サーバーベースURLを抽出
        if (_url.Contains("/broadcast"))
            _serverBaseUrl = _url[.._url.IndexOf("/broadcast", StringComparison.Ordinal)];
        else if (_url.StartsWith("http"))
            _serverBaseUrl = _url.TrimEnd('/');

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
            // デフォルトコンテキストメニューを無効化（broadcast.htmlのカスタムメニューのみ使用）
            _webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            // JSコンソールをC#ログに転送（WebView2 postMessage経由）
            _webView.CoreWebView2.WebMessageReceived += (_, args) =>
            {
                try
                {
                    var msg = JsonSerializer.Deserialize<JsonElement>(args.WebMessageAsJson);
                    if (msg.TryGetProperty("_console", out var text))
                        Log.Debug("[WebView2:JS] {Message}", text.GetString());
                    // broadcast.htmlからの音量変更通知 → パネルに転送 + C#音声に反映
                    if (msg.TryGetProperty("_volumeSync", out var volSync))
                    {
                        var m = (float)volSync.GetProperty("master").GetDouble();
                        var t = (float)volSync.GetProperty("tts").GetDouble();
                        var b = (float)volSync.GetProperty("bgm").GetDouble();
                        var se = volSync.TryGetProperty("se", out var seVal) ? (float)seVal.GetDouble() : _volumeSe;
                        UpdateVolume("master", m);
                        UpdateVolume("tts", t);
                        UpdateVolume("bgm", b);
                        UpdateVolume("se", se);
                        var syncDelay = volSync.TryGetProperty("lipsyncDelay", out var ld) ? (int)ld.GetDouble() : -1;
                        var panelMsg = new Dictionary<string, object>
                        {
                            ["type"] = "volume",
                            ["master"] = (int)(m * 100),
                            ["tts"] = (int)(t * 100),
                            ["bgm"] = (int)(b * 100),
                            ["se"] = (int)(se * 100),
                        };
                        if (syncDelay >= 0) panelMsg["syncDelay"] = syncDelay;
                        SendPanelMessage(panelMsg);
                    }
                    // broadcast.htmlからのsyncDelay通知 → パネルに転送
                    if (msg.TryGetProperty("_syncDelay", out var syncDelayEl))
                    {
                        var delay = (int)syncDelayEl.GetDouble();
                        SendPanelMessage(new { type = "volume", syncDelay = delay });
                        Log.Debug("[Sync] Delay from broadcast.html: {Delay}ms", delay);
                    }
                    // broadcast.htmlからのコメント通知 → パネルに転送
                    if (msg.TryGetProperty("_comment", out var commentData))
                    {
                        SendPanelMessage(new
                        {
                            type = "comment",
                            author = commentData.GetProperty("author").GetString(),
                            message = commentData.GetProperty("trigger_text").GetString(),
                            speech = commentData.GetProperty("speech").GetString(),
                            translation = commentData.TryGetProperty("translation", out var tr) ? tr.GetString() : "",
                            emotion = commentData.TryGetProperty("emotion", out var emo) ? emo.GetString() : "neutral",
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
            _panelView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
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

        // TTS音声: 常にローカル再生 + 配信中はFFmpegパイプにも送信
        _httpServer.OnTtsAudio = (wavData, volume) =>
        {
            try
            {
                // ローカル再生: WaveChannel32で音量制御（再生中の音量変更対応）
                PlayTtsLocally(wavData, EffectiveTtsVolume());
                // 配信中: PCMリサンプル → FFmpegミキサー（音量はMixTtsIntoでリアルタイム適用）
                if (_ffmpeg is { IsRunning: true })
                {
                    var pcm = TtsDecoder.DecodeWav(wavData, 1.0f);
                    _ffmpeg.WriteTtsData(pcm);
                }
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[MainForm] TTS audio failed");
            }
        };

        // BGM制御コールバック（Task.Runから呼ばれるためBeginInvokeでUIスレッドに移動）
        _httpServer.OnBgmPlay = (url, trackVolume) =>
        {
            BeginInvoke(() =>
            {
                _volumeTrack = Math.Clamp(trackVolume, 0f, 1f);
                SendPanelMessage(new { type = "track_volume", volume = (int)(_volumeTrack * 100) });
                PlayBgm(url);
            });
        };

        _httpServer.OnBgmStop = () =>
        {
            BeginInvoke(() =>
            {
                StopBgmPlayback();
                _ffmpeg?.StopBgm();
                SendPanelMessage(new { type = "bgm_status", state = "stopped" });
                Log.Information("[BGM] Stopped");
            });
        };

        _httpServer.OnBgmVolume = (source, volume) =>
        {
            BeginInvoke(() =>
            {
                var clamped = Math.Clamp(volume, 0f, 1f);
                UpdateVolume(source, clamped);
                if (source == "track")
                    SendPanelMessage(new { type = "track_volume", volume = (int)(clamped * 100) });
            });
        };

        // SE制御コールバック
        _httpServer.OnSePlay = (url, volume) =>
        {
            BeginInvoke(() => PlaySe(url, volume));
        };

        try
        {
            _httpServer.Start();
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[MainForm] HTTP server start failed on port {Port}", _httpPort);
        }

        // 音量メータータイマー開始（50ms間隔 = 20Hz更新）
        _meterTimer = new System.Windows.Forms.Timer { Interval = 50 };
        _meterTimer.Tick += (_, _) => UpdateAudioMeter();
        _meterTimer.Start();
    }

    /// <summary>音声レベルを測定し、パネルに送信する。</summary>
    private void UpdateAudioMeter()
    {
        float db, peak;
        bool bgmActive, ttsActive;

        if (_ffmpeg is { IsRunning: true })
        {
            // 配信中: FFmpegミキサーの実測値
            db = _ffmpeg.LastRmsDb;
            peak = _ffmpeg.LastPeakDb;
            bgmActive = _ffmpeg.IsBgmActive;
            ttsActive = _ffmpeg.IsTtsActive;
        }
        else
        {
            // 非配信: MeteringWaveProviderの実測値を合成
            bgmActive = _bgmMeter != null && _bgmWaveOut?.PlaybackState == PlaybackState.Playing;
            ttsActive = _ttsMeter != null;
            var bgmDb = bgmActive ? _bgmMeter!.RmsDb : -100f;
            var ttsDb = ttsActive ? _ttsMeter!.RmsDb : -100f;
            var bgmPeak = bgmActive ? _bgmMeter!.PeakDb : -100f;
            var ttsPeak = ttsActive ? _ttsMeter!.PeakDb : -100f;
            // 2ソースのdBを線形加算（パワー合算）
            double bgmPow = Math.Pow(10, bgmDb / 10.0);
            double ttsPow = Math.Pow(10, ttsDb / 10.0);
            db = (float)(10.0 * Math.Log10(bgmPow + ttsPow));
            peak = Math.Max(bgmPeak, ttsPeak);
        }

        var dbVal = double.IsFinite(db) ? Math.Max(-60.0, (double)db) : -60.0;
        var peakVal = double.IsFinite(peak) ? Math.Max(-60.0, (double)peak) : -60.0;

        // 初回のみログ出力（デバッグ用）
        if (_meterLogCount < 5 || (bgmActive && _meterLogCount % 100 == 0))
        {
            Log.Debug("[Meter] db={Db:F1} peak={Peak:F1} bgm={Bgm} tts={Tts} streaming={S}",
                dbVal, peakVal, bgmActive, ttsActive, _ffmpeg is { IsRunning: true });
        }
        _meterLogCount++;

        SendPanelMessage(new
        {
            type = "audioLevel",
            db = dbVal,
            peak = peakVal,
            bgm = bgmActive,
            tts = ttsActive,
        });
    }
    private int _meterLogCount;

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
            ["audio_mode"] = "direct_pipe",
            ["bgm_playing"] = _bgmReader != null,
            ["bgm_url"] = _currentBgmUrl ?? "",
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

        // WASAPI不要 — 全音声はC#が直接パイプに書き込む
        _ffmpeg = new FfmpegProcess(config);

        await _ffmpeg.StartAsync();
        await Task.Delay(500);

        // タイマーベース音声ジェネレータ開始（サイレンス + TTS + BGMミキシング）
        _ffmpeg.StartAudioGenerator();
        _ffmpeg.SetTtsVolume(EffectiveTtsVolume());

        // フレームキャプチャ → FFmpegビデオパイプ接続
        _capture.TargetFps = config.Framerate;
        _capture.OnFrameReady = (data, w, h) => _ffmpeg.WriteVideoFrame(data);

        // BGMが再生中なら、PCMにデコードしてFFmpegミキサーに渡す
        if (_currentBgmCachePath != null)
        {
            var bgmPath = _currentBgmCachePath;
            var ffmpeg = _ffmpeg;
            Task.Run(() =>
            {
                try
                {
                    var pcm = DecodeBgmToPcm(bgmPath);
                    ffmpeg?.SetBgm(pcm, EffectiveBgmVolume());
                    Log.Information("[BGM] PCM decoded for streaming (on start): {Size} bytes", pcm.Length);
                }
                catch (Exception ex)
                {
                    Log.Error(ex, "[BGM] PCM decode failed on streaming start");
                }
            });
        }

        _streamStartTime = DateTime.UtcNow;
        Text = "AI Twitch Cast - 配信中";
        Log.Information("[MainForm] Streaming pipeline active (direct audio, no WASAPI)");
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

    /// <summary>
    /// TTS WAVをローカルスピーカーで再生する（NAudio WaveOutEvent + WaveChannel32）。
    /// WaveChannel32でサンプルレベル音量制御（再生中の音量変更対応）。
    /// </summary>
    private void PlayTtsLocally(byte[] wavData, float volume)
    {
        // 前回の再生を停止・破棄
        var oldWaveOut = _ttsWaveOut;
        _ttsWaveOut = null;
        _ttsChannel = null;
        _ttsMeter = null;
        oldWaveOut?.Stop();
        oldWaveOut?.Dispose();

        try
        {
            var ms = new MemoryStream(wavData);
            var reader = new WaveFileReader(ms);
            var channel = new WaveChannel32(reader) { Volume = Math.Clamp(volume, 0f, 1f) };
            var meter = new MeteringWaveProvider(channel);
            var waveOut = new WaveOutEvent();
            waveOut.Init(meter);
            waveOut.Volume = 1.0f; // デバイスレベルは常にmax（音量制御はWaveChannel32で行う）

            // フィールドに保持してGC回収を防止
            _ttsWaveOut = waveOut;
            _ttsChannel = channel;
            _ttsMeter = meter;

            waveOut.PlaybackStopped += (_, _) =>
            {
                if (_ttsWaveOut == waveOut)
                {
                    _ttsWaveOut = null;
                    _ttsChannel = null;
                    _ttsMeter = null;
                }
                waveOut.Dispose();
                reader.Dispose();
                ms.Dispose();
            };

            waveOut.Play();
            Log.Debug("[TTS] Local playback started ({Size} bytes, vol={Vol:F2})", wavData.Length, volume);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[TTS] Local playback failed");
        }
    }

    /// <summary>BGMをローカル再生する。ダウンロード→再生開始。</summary>
    // BGMキャッシュディレクトリ（初回ダウンロード後はローカルから即再生）
    private static readonly string BgmCacheDir = Path.Combine(Path.GetTempPath(), "ai-twitch-cast-bgm");

    private void PlayBgm(string url)
    {
        StopBgmPlayback();
        _currentBgmUrl = url;

        var fullUrl = url.StartsWith("http") ? url : _serverBaseUrl + url;
        Log.Information("[BGM] Play: {Url}", fullUrl);

        // ファイル名を抽出（表示用）
        var fileName = Uri.UnescapeDataString(Path.GetFileNameWithoutExtension(new Uri(fullUrl).AbsolutePath));

        Task.Run(async () =>
        {
            try
            {
                // キャッシュチェック（URLハッシュ + 拡張子）
                Directory.CreateDirectory(BgmCacheDir);
                var urlHash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(
                    System.Text.Encoding.UTF8.GetBytes(fullUrl)))[..16];
                var ext = Path.GetExtension(new Uri(fullUrl).AbsolutePath);
                if (string.IsNullOrEmpty(ext)) ext = ".mp3";
                var cachePath = Path.Combine(BgmCacheDir, $"{urlHash}{ext}");

                if (File.Exists(cachePath))
                {
                    Log.Information("[BGM] Cache hit: {Path}", cachePath);
                }
                else
                {
                    Log.Information("[BGM] Downloading {Url}...", fullUrl);
                    BeginInvoke(() => SendPanelMessage(new { type = "bgm_status", state = "downloading", name = fileName, size = 0L }));

                    using var httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(120) };
                    var data = await httpClient.GetByteArrayAsync(fullUrl);
                    await File.WriteAllBytesAsync(cachePath, data);
                    Log.Information("[BGM] Downloaded: {Size} bytes → {Path}", data.Length, cachePath);
                }

                BeginInvoke(() =>
                {
                    StartBgmPlayback(cachePath);
                    SendPanelMessage(new { type = "bgm_status", state = "playing", name = fileName });
                });
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[BGM] Failed: {Url}", fullUrl);
                BeginInvoke(() => SendPanelMessage(new { type = "bgm_status", state = "error", error = ex.Message }));
            }
        });
    }

    /// <summary>BGMファイルの再生を開始する（UIスレッド）。</summary>
    private void StartBgmPlayback(string localPath)
    {
        try
        {
            _currentBgmCachePath = localPath;
            _bgmReader = new MediaFoundationReader(localPath);
            // WaveChannel32でサンプルレベル音量（waveOut.Volumeはデバイスレベルで他WaveOutに干渉するため不使用）
            _bgmChannel = new WaveChannel32(_bgmReader) { Volume = Math.Clamp(EffectiveBgmVolume(), 0f, 1f) };
            _bgmMeter = new MeteringWaveProvider(_bgmChannel);
            _bgmWaveOut = new WaveOutEvent();
            _bgmWaveOut.Init(_bgmMeter);
            _bgmWaveOut.Volume = 1.0f; // デバイスレベルは常にmax（音量制御はWaveChannel32で行う）
            _bgmWaveOut.Play();
            Log.Information("[BGM] Playback started: {Format}, vol={Vol:F3}, file={Path}",
                _bgmReader.WaveFormat, _bgmChannel.Volume, localPath);

            // 再生終了時にループ
            _bgmWaveOut.PlaybackStopped += (s, e) =>
            {
                if (_bgmReader != null)
                {
                    try { _bgmReader.Position = 0; _bgmWaveOut?.Play(); }
                    catch { }
                }
            };

            // 配信中: PCMにデコードしてFFmpegミキサーに渡す
            if (_ffmpeg is { IsRunning: true })
            {
                var ffmpeg = _ffmpeg;
                Task.Run(() =>
                {
                    try
                    {
                        var pcm = DecodeBgmToPcm(localPath);
                        ffmpeg?.SetBgm(pcm, EffectiveBgmVolume());
                        Log.Information("[BGM] PCM decoded for streaming: {Size} bytes", pcm.Length);
                    }
                    catch (Exception ex)
                    {
                        Log.Error(ex, "[BGM] PCM decode failed");
                    }
                });
            }
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[BGM] Playback start failed: {Path}", localPath);
        }
    }

    /// <summary>BGMのローカル再生を停止する。</summary>
    private void StopBgmPlayback()
    {
        var reader = _bgmReader;
        var waveOut = _bgmWaveOut;
        _bgmReader = null;
        _bgmChannel = null;
        _bgmMeter = null;
        _bgmWaveOut = null;
        _currentBgmUrl = null;
        _currentBgmCachePath = null;
        try { waveOut?.Stop(); } catch { }
        try { waveOut?.Dispose(); } catch { }
        try { reader?.Dispose(); } catch { }
    }

    /// <summary>SE（効果音）を再生する。BGMと違いループなし（一回再生）。</summary>
    private void PlaySe(string url, float volume)
    {
        // 再生中のSEがあれば停止
        StopSePlayback();

        var fullUrl = url.StartsWith("http") ? url : _serverBaseUrl + url;
        Log.Information("[SE] Play: {Url}, vol={Vol:F2}", fullUrl, volume);

        Task.Run(async () =>
        {
            try
            {
                // キャッシュチェック
                Directory.CreateDirectory(SeCacheDir);
                var urlHash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(
                    System.Text.Encoding.UTF8.GetBytes(fullUrl)))[..16];
                var ext = Path.GetExtension(new Uri(fullUrl).AbsolutePath);
                if (string.IsNullOrEmpty(ext)) ext = ".wav";
                var cachePath = Path.Combine(SeCacheDir, $"{urlHash}{ext}");

                if (!File.Exists(cachePath))
                {
                    Log.Information("[SE] Downloading {Url}...", fullUrl);
                    using var httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
                    var data = await httpClient.GetByteArrayAsync(fullUrl);
                    await File.WriteAllBytesAsync(cachePath, data);
                    Log.Information("[SE] Downloaded: {Size} bytes", data.Length);
                }

                BeginInvoke(() =>
                {
                    try
                    {
                        var reader = new MediaFoundationReader(cachePath);
                        var channel = new WaveChannel32(reader) { Volume = Math.Clamp(volume, 0f, 1f) };
                        var meter = new MeteringWaveProvider(channel);
                        _seChannel = channel;
                        _seMeter = meter;
                        var waveOut = new WaveOutEvent();
                        waveOut.Init(meter);
                        waveOut.Volume = 1.0f;
                        waveOut.Play();
                        Log.Information("[SE] Playback started, vol={Vol:F2}", volume);

                        waveOut.PlaybackStopped += (_, _) =>
                        {
                            if (_seChannel == channel) { _seChannel = null; _seMeter = null; }
                            waveOut.Dispose();
                            reader.Dispose();
                        };

                        // 配信中: PCMにデコードしてFFmpegミキサーに渡す
                        if (_ffmpeg is { IsRunning: true })
                        {
                            var ffmpeg = _ffmpeg;
                            Task.Run(() =>
                            {
                                try
                                {
                                    var pcm = DecodeBgmToPcm(cachePath); // 同じデコーダを流用
                                    ffmpeg?.WriteSeData(pcm, volume);
                                    Log.Information("[SE] PCM for streaming: {Size} bytes", pcm.Length);
                                }
                                catch (Exception ex)
                                {
                                    Log.Error(ex, "[SE] PCM decode failed");
                                }
                            });
                        }
                    }
                    catch (Exception ex)
                    {
                        Log.Error(ex, "[SE] Playback start failed");
                    }
                });
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[SE] Failed: {Url}", fullUrl);
            }
        });
    }

    /// <summary>SE再生を停止する。</summary>
    private void StopSePlayback()
    {
        _seChannel = null;
        _seMeter = null;
    }

    /// <summary>
    /// BGM音声ファイルを48kHz stereo f32le PCMバイト配列にデコードする（FFmpegミキサー用）。
    /// </summary>
    private static byte[] DecodeBgmToPcm(string url)
    {
        using var reader = new MediaFoundationReader(url);
        var targetFormat = WaveFormat.CreateIeeeFloatWaveFormat(48000, 2);
        using var resampler = new MediaFoundationResampler(reader, targetFormat);
        resampler.ResamplerQuality = 60;
        using var ms = new MemoryStream();
        var buffer = new byte[8192];
        int read;
        while ((read = resampler.Read(buffer, 0, buffer.Length)) > 0)
            ms.Write(buffer, 0, read);
        return ms.ToArray();
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
        _ffmpeg = null;
        _activeStreamKey = null;
        Text = "AI Twitch Cast - 待機中";
        Log.Information("[Stop] State cleared. Starting cleanup...");

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
        _meterTimer?.Stop();
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
        Log.Information("[Cleanup] bgm...");
        StopBgmPlayback();
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
