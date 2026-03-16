using System.Collections.Concurrent;
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
    private volatile bool _encodingStarted; // FFmpegエンコード開始検知フラグ
    private bool _disposed;

    // ダブルバッファ: BGRA入力コピー用
    private byte[]? _videoBufA;
    private byte[]? _videoBufB;
    private int _videoBufIdx;

    // NV12変換用バッファ（BGRA 3.7MB → NV12 1.4MB @1280x720）
    private byte[]? _nv12Buf;

    // 音声バッファキュー（WASAPIコールバックをブロックしない非同期書き込み）
    private readonly ConcurrentQueue<byte[]> _audioQueue = new();
    private Thread? _audioWriter;
    private long _audioDropCount;
    // キュー上限: 約1秒分（エンコード開始時にフラッシュするため、起動後は低水位を維持）
    private const int MaxAudioQueueChunks = 100;

    public bool IsRunning => _process is { HasExited: false };
    public long FrameCount => Interlocked.Read(ref _frameCount);
    public long DropCount => Interlocked.Read(ref _dropCount);
    public long AudioDropCount => Interlocked.Read(ref _audioDropCount);
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

        // 音声用名前付きパイプ（64KBバッファ — 映像パイプとの遅延差を最小化）
        _audioPipe = new NamedPipeServerStream(
            _audioPipeName, PipeDirection.Out, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
            outBufferSize: 64 * 1024, inBufferSize: 0);

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
        Log.Information("[FFmpeg] Encoder: {Encoder}, AudioOffset: {Offset}s", encoder, _config.AudioOffset);

        var args = string.Join(" ",
            "-y -nostdin",
            // Video input (named pipe — 8MBバッファ + NV12でデータ量63%削減)
            "-thread_queue_size 64",
            "-f rawvideo -pixel_format nv12",
            $"-video_size {_config.Width}x{_config.Height}",
            $"-framerate {_config.Framerate}",
            $@"-i \\.\pipe\{_videoPipeName}",
            // Audio input (named pipe)
            "-thread_queue_size 1024",
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
            $"-f flv -flvflags no_duration_filesize \"{rtmpTarget}\""
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
        _audioDropCount = 0;
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

        // 初期サイレンスを送信（FFmpegのAAC encoder + resamplerのプライミング用）
        // 300ms分を100msチャンクで送信（最小限のプライミング、パイプバッファを満杯にしない）
        // f32le, 48kHz, stereo: 100ms = 48000 * 2 * 4 / 10 = 38400 bytes
        var silenceChunk = new byte[38400];
        var totalSilenceBytes = 0;
        try
        {
            for (var i = 0; i < 3; i++) // 3 × 100ms = 300ms
            {
                _audioPipe.Write(silenceChunk, 0, silenceChunk.Length);
                totalSilenceBytes += silenceChunk.Length;
            }
            _audioPipe.Flush();
            Log.Information("[FFmpeg] Initial silence sent ({Bytes} bytes, {Sec:F1}s)",
                totalSilenceBytes, totalSilenceBytes / 384000.0);
        }
        catch (IOException ex)
        {
            Log.Warning("[FFmpeg] Initial silence error (sent {Bytes} bytes): {Msg}",
                totalSilenceBytes, ex.Message);
        }

        // 音声バッファキュー書き込みスレッド開始
        _audioWriter = new Thread(AudioWriterLoop)
        {
            IsBackground = true,
            Name = "AudioPipeWriter",
        };
        _audioWriter.Start();
        Log.Information("[FFmpeg] Audio writer thread started");

        // ヘルスチェック: 5秒後にFFmpegの状態を確認
        _ = Task.Run(async () =>
        {
            await Task.Delay(5000);
            if (_process == null) return;
            if (_process.HasExited)
                Log.Error("[FFmpeg] Process exited after 5s! ExitCode={Code}", _process.ExitCode);
            else
                Log.Information("[FFmpeg] Health check: running, frames={F} drops={D} audioDrops={AD}",
                    FrameCount, DropCount, AudioDropCount);
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

    /// <summary>
    /// 音声データをキューに追加（WASAPIコールバックから呼ばれる、絶対にブロックしない）。
    /// バックグラウンドスレッドがキューからパイプに書き込む。
    /// FFmpeg起動直後はパイプ書き込みが遅い（RTMP接続確立中）ため、
    /// 直接書き込むとWASAPIコールバックがブロックされて音声途切れが発生する。
    /// </summary>
    public void WriteAudioData(byte[] data, int offset, int count)
    {
        if (_audioPipe is not { IsConnected: true } || _stopping) return;

        // WASAPIバッファは再利用されるのでコピーが必要
        var copy = new byte[count];
        Buffer.BlockCopy(data, offset, copy, 0, count);
        _audioQueue.Enqueue(copy);

        // キュー上限超過時は古いチャンクを破棄（FFmpegが追いつけない分）
        while (_audioQueue.Count > MaxAudioQueueChunks)
        {
            if (_audioQueue.TryDequeue(out _))
                Interlocked.Increment(ref _audioDropCount);
        }
    }

    /// <summary>
    /// バックグラウンドスレッド: キューから音声データを読み取りパイプに書き込む。
    /// パイプが満杯のときはこのスレッドだけがブロックされ、WASAPIは影響を受けない。
    /// </summary>
    private void AudioWriterLoop()
    {
        var logTick = Environment.TickCount64;
        long written = 0;
        long dropped = 0;
        var flushed = false; // エンコード開始時のキューフラッシュ済みフラグ

        while (!_stopping)
        {
            var pipe = _audioPipe;
            if (pipe is not { IsConnected: true }) break;

            // FFmpegエンコード開始検知 → 溜まったキューをフラッシュ（起動遅延を除去）
            if (_encodingStarted && !flushed)
            {
                flushed = true;
                var flushedCount = 0;
                while (_audioQueue.TryDequeue(out _))
                    flushedCount++;
                Log.Information("[FFmpeg] Audio queue flushed on encoding start: {Count} chunks discarded", flushedCount);
            }

            if (_audioQueue.TryDequeue(out var chunk))
            {
                try
                {
                    pipe.Write(chunk, 0, chunk.Length);
                    written++;
                }
                catch (Exception) // IOException, OperationCanceledException, ObjectDisposedException
                {
                    break; // パイプ切断 or 停止
                }
            }
            else
            {
                Thread.Sleep(1); // キュー空 → 1ms待機
            }

            // 10秒ごとにキュー状態をログ
            var now = Environment.TickCount64;
            if (now - logTick > 10_000)
            {
                var ad = Interlocked.Read(ref _audioDropCount);
                var newDrops = ad - dropped;
                Log.Information("[FFmpeg] Audio queue: depth={Depth} written={W} drops={D} (+{New})",
                    _audioQueue.Count, written, ad, newDrops);
                dropped = ad;
                written = 0;
                logTick = now;
            }
        }

        Log.Information("[FFmpeg] Audio writer thread exiting (queue={Depth})", _audioQueue.Count);
    }

    public async Task StopAsync()
    {
        if (_process == null) return;
        _stopping = true;

        Log.Information("[FFmpeg] Stopping (frames={F}, drops={D}, audioDrops={AD})...",
            FrameCount, DropCount, AudioDropCount);

        try
        {
            // パイプを先に閉じる → AudioWriterLoopのブロック中Write()を解除
            try { _videoPipe?.Dispose(); }
            catch { /* already closed */ }
            _videoPipe = null;

            try { _audioPipe?.Dispose(); }
            catch { /* already closed */ }
            _audioPipe = null;

            // パイプ閉鎖後に音声書き込みスレッドの終了を待つ
            _audioWriter?.Join(2000);
            _audioWriter = null;

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
            var startTick = Environment.TickCount64;
            while (_process is { HasExited: false } && !_stopping)
            {
                var line = await _process.StandardError.ReadLineAsync();
                if (line == null) break; // EOF
                await writer.WriteLineAsync(line);
                await writer.FlushAsync();

                // エンコード開始検知: "frame=" が出たらフラグセット
                if (!_encodingStarted && line.Contains("frame="))
                {
                    _encodingStarted = true;
                    Log.Information("[FFmpeg] Encoding started detected (audio queue will flush)");
                }

                // 起動後60秒間はSerilogにも出力（音声途切れ診断用）
                if (Environment.TickCount64 - startTick < 60_000)
                    Log.Debug("[FFmpeg:stderr] {Line}", line);
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
