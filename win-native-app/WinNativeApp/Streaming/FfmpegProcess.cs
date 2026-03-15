using System.Diagnostics;
using System.IO.Pipes;
using NAudio.Wave;
using Serilog;

namespace WinNativeApp.Streaming;

public sealed class FfmpegProcess : IDisposable
{
    private Process? _process;
    private readonly StreamConfig _config;
    private readonly string _audioPipeName;
    private readonly string _ffmpegAudioFormat;
    private NamedPipeServerStream? _audioPipe;
    private long _frameCount;
    private long _dropCount;
    private DateTime _startTime;
    private volatile bool _stopping;
    private volatile bool _writingVideo;
    private bool _disposed;

    public bool IsRunning => _process is { HasExited: false };
    public long FrameCount => Interlocked.Read(ref _frameCount);
    public long DropCount => Interlocked.Read(ref _dropCount);
    public TimeSpan Uptime => IsRunning ? DateTime.UtcNow - _startTime : TimeSpan.Zero;

    public FfmpegProcess(StreamConfig config, WaveFormat audioFormat)
    {
        _config = config;
        _audioPipeName = $"winnative_audio_{Environment.ProcessId}";
        _ffmpegAudioFormat = BuildAudioFormatArgs(audioFormat);
    }

    public async Task StartAsync(CancellationToken ct = default)
    {
        if (IsRunning) throw new InvalidOperationException("FFmpeg already running");

        var ffmpeg = FindFfmpeg();
        Log.Information("[FFmpeg] Path: {Path}", ffmpeg);

        // Create audio named pipe (must exist before FFmpeg starts)
        _audioPipe = new NamedPipeServerStream(
            _audioPipeName, PipeDirection.Out, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
            outBufferSize: 1024 * 1024, inBufferSize: 0);

        var rtmpTarget = $"{_config.RtmpUrl}/{_config.StreamKey}";

        var args = string.Join(" ",
            "-y -nostdin",
            // Video input (stdin)
            "-thread_queue_size 64",
            "-f rawvideo -pixel_format bgra",
            $"-video_size {_config.Width}x{_config.Height}",
            $"-framerate {_config.Framerate}",
            "-i pipe:0",
            // Audio input (named pipe)
            "-thread_queue_size 512",
            _ffmpegAudioFormat,
            $@"-i \\.\pipe\{_audioPipeName}",
            // Video encode
            $"-c:v libx264 -preset {_config.Preset} -tune zerolatency",
            $"-b:v {_config.VideoBitrate}",
            $"-maxrate {_config.VideoBitrate}",
            $"-bufsize {ParseBitrateKbps(_config.VideoBitrate) / 2}k",
            "-pix_fmt yuv420p",
            $"-g {_config.Framerate * 2}",
            "-flags +low_delay",
            // Audio encode
            $"-c:a aac -b:a {_config.AudioBitrate} -ar 44100",
            // Output
            "-flush_packets 1",
            $"-f flv \"{rtmpTarget}\""
        );

        Log.Information("[FFmpeg] Command: ffmpeg {Args}", args);

        _process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = ffmpeg,
                Arguments = args,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardInput = true,
                RedirectStandardError = true,
            },
            EnableRaisingEvents = true,
        };

        _process.Exited += (_, _) =>
            Log.Warning("[FFmpeg] Process exited, code={Code}", _process?.ExitCode);

        _process.Start();
        _startTime = DateTime.UtcNow;
        _frameCount = 0;
        _dropCount = 0;
        _stopping = false;

        // Log stderr to file
        _ = LogStderrAsync();

        // Send initial black frame so FFmpeg can probe video input
        var blackFrame = new byte[_config.Width * _config.Height * 4];
        try
        {
            await _process.StandardInput.BaseStream.WriteAsync(blackFrame, ct);
            await _process.StandardInput.BaseStream.FlushAsync(ct);
            Log.Debug("[FFmpeg] Initial black frame sent");
        }
        catch (IOException ex)
        {
            Log.Warning("[FFmpeg] Initial frame error: {Msg}", ex.Message);
        }

        // Wait for FFmpeg to connect to audio pipe
        Log.Information("[FFmpeg] Waiting for audio pipe connection...");
        await _audioPipe.WaitForConnectionAsync(ct);
        Log.Information("[FFmpeg] Audio pipe connected");

        // 初期サイレンスを送信（FFmpegが音声入力を待ってブロックしないように）
        // 1秒分のサイレンス（f32le, 48kHz, stereo = 48000 * 2 * 4 = 384000 bytes）
        var silenceBytes = new byte[384000];
        try
        {
            _audioPipe.Write(silenceBytes, 0, silenceBytes.Length);
            _audioPipe.Flush();
            Log.Information("[FFmpeg] Initial silence sent ({Bytes} bytes)", silenceBytes.Length);
        }
        catch (IOException ex)
        {
            Log.Warning("[FFmpeg] Initial silence error: {Msg}", ex.Message);
        }

        // ヘルスチェック: 5秒後にFFmpegの状態を確認
        _ = Task.Run(async () =>
        {
            await Task.Delay(5000);
            if (_process == null) return;
            if (_process.HasExited)
                Log.Error("[FFmpeg] Process exited after 5s! ExitCode={Code}", _process.ExitCode);
            else
                Log.Information("[FFmpeg] Health check: running, frames={F} drops={D}",
                    FrameCount, DropCount);
        });
    }

    public void WriteVideoFrame(byte[] bgraData)
    {
        if (!IsRunning || _stopping) return;

        var expectedSize = _config.Width * _config.Height * 4;
        if (bgraData.Length != expectedSize)
        {
            Interlocked.Increment(ref _dropCount);
            return;
        }

        // 前の書き込みがまだ完了していなければフレームをスキップ（WGCコールバックをブロックしない）
        if (_writingVideo)
        {
            Interlocked.Increment(ref _dropCount);
            return;
        }

        // データをコピーしてバックグラウンドで書き込み
        var copy = new byte[bgraData.Length];
        Buffer.BlockCopy(bgraData, 0, copy, 0, bgraData.Length);

        _writingVideo = true;
        ThreadPool.QueueUserWorkItem(_ =>
        {
            try
            {
                _process!.StandardInput.BaseStream.Write(copy, 0, copy.Length);
                Interlocked.Increment(ref _frameCount);
            }
            catch (IOException)
            {
                Interlocked.Increment(ref _dropCount);
            }
            finally
            {
                _writingVideo = false;
            }
        });
    }

    public void WriteAudioData(byte[] data, int offset, int count)
    {
        if (_audioPipe is not { IsConnected: true } || _stopping) return;

        try
        {
            _audioPipe.Write(data, offset, count);
        }
        catch (IOException ex)
        {
            Log.Debug("[FFmpeg] Audio pipe error: {Msg}", ex.Message);
        }
    }

    public async Task StopAsync()
    {
        if (_process == null) return;
        _stopping = true;

        Log.Information("[FFmpeg] Stopping (frames={F}, drops={D})...",
            FrameCount, DropCount);

        try
        {
            // Close stdin → EOF → FFmpeg flushes and exits
            try { _process.StandardInput?.Close(); }
            catch { /* already closed */ }

            // Wait up to 5 seconds for graceful exit
            using var cts = new CancellationTokenSource(5000);
            try
            {
                await _process.WaitForExitAsync(cts.Token);
            }
            catch (OperationCanceledException)
            {
                Log.Warning("[FFmpeg] Kill after 5s timeout");
                _process.Kill();
            }
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[FFmpeg] Stop error");
        }

        _audioPipe?.Dispose();
        _audioPipe = null;
        _process?.Dispose();
        _process = null;

        Log.Information("[FFmpeg] Stopped");
    }

    private async Task LogStderrAsync()
    {
        try
        {
            var logPath = Path.Combine(AppContext.BaseDirectory, "logs", "ffmpeg.log");
            Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);
            await using var writer = new StreamWriter(logPath, append: false);
            while (_process is { HasExited: false })
            {
                var line = await _process.StandardError.ReadLineAsync();
                if (line != null)
                {
                    await writer.WriteLineAsync(line);
                    await writer.FlushAsync();
                }
            }
        }
        catch { /* process ended */ }
    }

    private string FindFfmpeg()
    {
        if (!string.IsNullOrEmpty(_config.FfmpegPath) && File.Exists(_config.FfmpegPath))
            return _config.FfmpegPath;

        var candidates = new[]
        {
            Path.Combine(AppContext.BaseDirectory, "resources", "ffmpeg", "ffmpeg.exe"),
            Path.Combine(AppContext.BaseDirectory, "ffmpeg.exe"),
        };

        foreach (var p in candidates)
            if (File.Exists(p)) return p;

        return "ffmpeg.exe"; // rely on PATH
    }

    private static string BuildAudioFormatArgs(WaveFormat wf)
    {
        bool isFloat = wf.Encoding == WaveFormatEncoding.IeeeFloat;

        // WaveFormatExtensible: check SubFormat for actual encoding
        if (wf.Encoding == WaveFormatEncoding.Extensible && wf is WaveFormatExtensible ext)
        {
            // IEEE Float GUID: 00000003-0000-0010-8000-00AA00389B71
            isFloat = ext.SubFormat == new Guid("00000003-0000-0010-8000-00aa00389b71");
        }

        var fmt = isFloat ? "f32le" : $"s{wf.BitsPerSample}le";
        return $"-f {fmt} -ar {wf.SampleRate} -ac {wf.Channels}";
    }

    private static int ParseBitrateKbps(string bitrate)
    {
        var s = bitrate.TrimEnd('k', 'K', 'm', 'M');
        if (int.TryParse(s, out var v))
            return bitrate.EndsWith("m", StringComparison.OrdinalIgnoreCase) ? v * 1000 : v;
        return 2500;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        StopAsync().GetAwaiter().GetResult();
    }
}
