using Microsoft.Web.WebView2.WinForms;
using Serilog;
using WinNativeApp.Capture;
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

    public MainForm(string[] args)
    {
        _args = args;
        _url = args.FirstOrDefault(a => !a.StartsWith("--")) ?? "https://example.com";
        _autoStream = args.Contains("--stream");

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
        Log.Information("[MainForm] Closed");
    }
}
