using System.Diagnostics;
using System.IO.Pipes;
using NAudio.Wave;
using Serilog;

namespace WinNativeApp.Streaming;

public sealed class FfmpegProcess : IDisposable
{
    private Process? _process;
    private readonly StreamConfig _config;
    private readonly string _videoPipeName;
    private readonly string _audioPipeName;
    private readonly string _ffmpegAudioFormat;
    private NamedPipeServerStream? _videoPipe;
    private NamedPipeServerStream? _audioPipe;
    private long _frameCount;
    private long _dropCount;
    private DateTime _startTime;
    private volatile bool _stopping;
    private volatile bool _writingVideo;
    private bool _disposed;

    // ダブルバッファ: BGRA入力コピー用
    private byte[]? _videoBufA;
    private byte[]? _videoBufB;
    private int _videoBufIdx;

    // NV12変換用バッファ（BGRA 3.7MB → NV12 1.4MB @1280x720）
    private byte[]? _nv12Buf;

    public bool IsRunning => _process is { HasExited: false };
    public long FrameCount => Interlocked.Read(ref _frameCount);
    public long DropCount => Interlocked.Read(ref _dropCount);
    public TimeSpan Uptime => IsRunning ? DateTime.UtcNow - _startTime : TimeSpan.Zero;

    public FfmpegProcess(StreamConfig config, WaveFormat audioFormat)
    {
        _config = config;
        _videoPipeName = $"winnative_video_{Environment.ProcessId}";
        _audioPipeName = $"winnative_audio_{Environment.ProcessId}";
        _ffmpegAudioFormat = BuildAudioFormatArgs(audioFormat);
    }

    public async Task StartAsync(CancellationToken ct = default)
    {
        if (IsRunning) throw new InvalidOperationException("FFmpeg already running");

        var ffmpeg = FindFfmpeg();
        Log.Information("[FFmpeg] Path: {Path}", ffmpeg);

        // 映像用名前付きパイプ（8MBバッファ — 2フレーム分以上）
        _videoPipe = new NamedPipeServerStream(
            _videoPipeName, PipeDirection.Out, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
            outBufferSize: 8 * 1024 * 1024, inBufferSize: 0);

        // 音声用名前付きパイプ（1MBバッファ）
        _audioPipe = new NamedPipeServerStream(
            _audioPipeName, PipeDirection.Out, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
            outBufferSize: 1024 * 1024, inBufferSize: 0);

        // ダブルバッファ事前確保（BGRA入力コピー用）
        var bgraFrameSize = _config.Width * _config.Height * 4;
        _videoBufA = new byte[bgraFrameSize];
        _videoBufB = new byte[bgraFrameSize];
        _videoBufIdx = 0;

        // NV12変換バッファ（BGRA 3.7MB → NV12 1.4MB @1280x720、パイプ転送量63%削減）
        var nv12Size = ColorConverter.Nv12Size(_config.Width, _config.Height);
        _nv12Buf = new byte[nv12Size];

        var rtmpTarget = $"{_config.RtmpUrl}/{_config.StreamKey}";

        // エンコーダ選択（auto=HW自動検出→libx264フォールバック）
        var encoder = ResolveEncoder(_config.Encoder, FindFfmpeg());
        var encoderArgs = BuildEncoderArgs(encoder, _config);
        Log.Information("[FFmpeg] Encoder: {Encoder}", encoder);

        var args = string.Join(" ",
            "-y -nostdin",
            // Video input (named pipe — 8MBバッファ + NV12でデータ量63%削減)
            "-thread_queue_size 64",
            "-f rawvideo -pixel_format nv12",
            $"-video_size {_config.Width}x{_config.Height}",
            $"-framerate {_config.Framerate}",
            $@"-i \\.\pipe\{_videoPipeName}",
            // Audio input (named pipe)
            "-thread_queue_size 512",
            _ffmpegAudioFormat,
            $@"-i \\.\pipe\{_audioPipeName}",
            // Video encode (encoder-specific)
            encoderArgs,
            $"-b:v {_config.VideoBitrate}",
            $"-maxrate {_config.VideoBitrate}",
            $"-bufsize {ParseBitrateKbps(_config.VideoBitrate) / 2}k",
            "-pix_fmt yuv420p",
            $"-g {_config.Framerate * 2}",
            "-flags +low_delay",
            // Audio encode
            $"-c:a aac -b:a {_config.AudioBitrate} -ar 44100",
            // Output
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
                RedirectStandardInput = false, // stdinは使わない（映像は名前付きパイプ経由）
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

        // FFmpegは-iの順にパイプを開く。映像パイプ→音声パイプの順で接続待ち
        Log.Information("[FFmpeg] Waiting for video pipe connection...");
        await _videoPipe.WaitForConnectionAsync(ct);
        Log.Information("[FFmpeg] Video pipe connected (8MB buffer)");

        // 初期黒フレームを送信（NV12: Yは全て16=黒、UVは全て128=無彩色）
        var blackFrame = new byte[nv12Size];
        // NV12の黒: Y平面=16（TV range black）、UV平面=128（無彩色）
        Array.Fill(blackFrame, (byte)16, 0, _config.Width * _config.Height);
        Array.Fill(blackFrame, (byte)128, _config.Width * _config.Height, nv12Size - _config.Width * _config.Height);
        try
        {
            _videoPipe.Write(blackFrame, 0, blackFrame.Length);
            _videoPipe.Flush();
            Log.Debug("[FFmpeg] Initial black frame sent (NV12, {Size} bytes)", nv12Size);
        }
        catch (IOException ex)
        {
            Log.Warning("[FFmpeg] Initial frame error: {Msg}", ex.Message);
        }

        // 音声パイプ接続待ち
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
        if (_videoPipe is not { IsConnected: true } || _stopping) return;

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

        // ダブルバッファで交互に使用（GCプレッシャー回避）
        var buf = (Interlocked.Increment(ref _videoBufIdx) & 1) == 0 ? _videoBufA! : _videoBufB!;
        Buffer.BlockCopy(bgraData, 0, buf, 0, bgraData.Length);

        var w = _config.Width;
        var h = _config.Height;
        var nv12 = _nv12Buf!;
        var nv12WriteSize = ColorConverter.Nv12Size(w, h);

        _writingVideo = true;
        ThreadPool.QueueUserWorkItem(_ =>
        {
            try
            {
                var sw = Stopwatch.StartNew();

                // BGRA → NV12 変換（3.7MB → 1.4MB @1280x720）
                ColorConverter.BgraToNv12(buf, nv12, w, h);
                var convertMs = sw.ElapsedMilliseconds;

                // NV12をパイプに書き込み
                _videoPipe!.Write(nv12, 0, nv12WriteSize);
                sw.Stop();
                Interlocked.Increment(ref _frameCount);

                // 30フレームごとに変換+書き込み時間をログ
                var fc = Interlocked.Read(ref _frameCount);
                if (fc <= 5 || fc % 30 == 0)
                    Log.Debug("[FFmpeg] NV12 convert={ConvMs}ms write={TotalMs}ms, frames={F} drops={D}",
                        convertMs, sw.ElapsedMilliseconds, fc, DropCount);
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
            // 映像・音声パイプを閉じる → FFmpegがEOFを検知して終了
            try { _videoPipe?.Dispose(); }
            catch { /* already closed */ }
            _videoPipe = null;

            try { _audioPipe?.Dispose(); }
            catch { /* already closed */ }
            _audioPipe = null;

            // Wait up to 5 seconds for graceful exit
            using var cts = new CancellationTokenSource(5000);
            try
            {
                await _process.WaitForExitAsync(cts.Token);
            }
            catch (OperationCanceledException)
            {
                Log.Warning("[FFmpeg] Kill after 5s timeout");
                try { _process.Kill(); } catch { }
                try { _process.WaitForExit(3000); } catch { }
            }
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[FFmpeg] Stop error");
        }

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
            while (_process is { HasExited: false } && !_stopping)
            {
                var line = await _process.StandardError.ReadLineAsync();
                if (line == null) break; // EOF
                await writer.WriteLineAsync(line);
                await writer.FlushAsync();
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

    /// <summary>
    /// "auto"の場合、FFmpegでHWエンコーダの利用可否をprobeして選択する。
    /// NVENC → AMF → QSV → libx264 の優先順。
    /// </summary>
    private static string ResolveEncoder(string encoder, string ffmpegPath)
    {
        if (encoder != "auto") return encoder;

        // HWエンコーダを優先順に試行
        string[] candidates = ["h264_nvenc", "h264_amf", "h264_qsv"];
        foreach (var enc in candidates)
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = ffmpegPath,
                    Arguments = $"-f lavfi -i nullsrc=s=256x256:d=0.1 -c:v {enc} -f null -",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                using var p = Process.Start(psi);
                p!.WaitForExit(5000);
                if (p.ExitCode == 0)
                {
                    Log.Information("[FFmpeg] HW encoder detected: {Enc}", enc);
                    return enc;
                }
            }
            catch
            {
                // ignore probe failures
            }
        }

        Log.Information("[FFmpeg] No HW encoder found, using libx264");
        return "libx264";
    }

    /// <summary>
    /// エンコーダに応じたFFmpeg引数を構築する。
    /// </summary>
    private static string BuildEncoderArgs(string encoder, StreamConfig config)
    {
        return encoder switch
        {
            "h264_nvenc" => $"-c:v h264_nvenc -preset p1 -tune ll -rc cbr",
            "h264_amf" => $"-c:v h264_amf -quality speed -rc cbr",
            "h264_qsv" => $"-c:v h264_qsv -preset veryfast",
            _ => $"-c:v libx264 -preset {config.Preset} -tune zerolatency",
        };
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
