using System.Diagnostics;
using System.IO.Pipes;
using NAudio.Wave;

namespace PocLoopback;

// 2 入力 FFmpeg を起動し、video / audio を別々の名前付きパイプから供給する。
// 両方の入力に -use_wallclock_as_timestamps 1 を付け、AV 同期は OS の wall clock 任せにする。
//
// PoC の仮説: WGC (BGRA) と WASAPI Loopback (f32le) を wall clock で同じ時刻に
// 打刻すれば、自前のミキサーやバイトベース PTS を一切使わずに AV が揃う。
public sealed class FfmpegRunner : IDisposable
{
    private readonly string _ffmpegPath;
    private readonly string _outputPath;
    private readonly int _videoWidth;
    private readonly int _videoHeight;
    private readonly int _videoFps;
    private readonly WaveFormat _audioFormat;

    private readonly string _videoPipeName;
    private readonly string _audioPipeName;
    private NamedPipeServerStream? _videoPipe;
    private NamedPipeServerStream? _audioPipe;
    private Process? _process;
    private volatile bool _stopping;
    private long _videoBytesWritten;
    private long _audioBytesWritten;
    private long _videoFrames;

    public bool IsRunning => _process is { HasExited: false };
    public long VideoFrames => Interlocked.Read(ref _videoFrames);
    public long VideoBytes => Interlocked.Read(ref _videoBytesWritten);
    public long AudioBytes => Interlocked.Read(ref _audioBytesWritten);

    public FfmpegRunner(
        string ffmpegPath,
        string outputPath,
        int videoWidth, int videoHeight, int videoFps,
        WaveFormat audioFormat)
    {
        _ffmpegPath = ffmpegPath;
        _outputPath = outputPath;
        _videoWidth = videoWidth;
        _videoHeight = videoHeight;
        _videoFps = videoFps;
        _audioFormat = audioFormat;
        _videoPipeName = $"poc_loopback_video_{Environment.ProcessId}";
        _audioPipeName = $"poc_loopback_audio_{Environment.ProcessId}";
    }

    // primer: PTS 0 として書き出す 1 フレーム分の BGRA バイト列。null/サイズ不一致なら黒フレームを使う。
    // FFmpeg は rawvideo の最初の 1 フレームを読まないと音声パイプを open しない。primer に「最初の実フレーム」
    // を渡せば、WGC frame_arrived が静止コンテンツで遅れても先頭の黒区間が出ない（plans/recording-quality-improvements.md Step 1）
    public async Task StartAsync(CancellationToken ct = default, byte[]? primer = null)
    {
        if (IsRunning) throw new InvalidOperationException("FFmpeg already running");

        var dir = Path.GetDirectoryName(_outputPath);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

        _videoPipe = new NamedPipeServerStream(
            _videoPipeName, PipeDirection.Out, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
            outBufferSize: 8 * 1024 * 1024, inBufferSize: 0);

        _audioPipe = new NamedPipeServerStream(
            _audioPipeName, PipeDirection.Out, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
            outBufferSize: 1024 * 1024, inBufferSize: 0);

        var audioArgs = BuildAudioFormatArgs(_audioFormat);

        // yuv420p は偶数次元必須。入力が奇数なら 1px 切り落とす。
        // PocLoopback はクライアント側で crop 済みの偶数次元（1280×720 等）が来ることがあるので
        // その場合は filter を省いてパイプラインを軽くする
        bool dimsAreEven = (_videoWidth & 1) == 0 && (_videoHeight & 1) == 0;
        string videoFilterArg = dimsAreEven
            ? ""
            : "-vf \"crop=trunc(iw/2)*2:trunc(ih/2)*2\"";

        var args = string.Join(" ",
            "-y -nostdin -hide_banner",
            // Video input
            "-thread_queue_size 64",
            "-use_wallclock_as_timestamps 1",
            "-f rawvideo -pixel_format bgra",
            $"-video_size {_videoWidth}x{_videoHeight}",
            $"-framerate {_videoFps}",
            $@"-i \\.\pipe\{_videoPipeName}",
            // Audio input（生 PCM はサンプル数ベース PTS の方が AAC エンコーダと相性が良い。
            //  wallclock を付けると silence プライムや読みバーストで PTS が歪んで
            //  Non-monotonic DTS / Queue input is backward in time が連発する。
            //  AV 同期は映像側 wallclock + 連続的に流れる loopback 音声で揃う想定。
            //  WinNativeApp/Streaming/FfmpegProcess.cs も同じ設計で映像にだけ付けている）。
            //
            // -analyzeduration 0 -probesize 32: format / sample rate / channels は audioArgs で
            // 明示しているので ffmpeg の自動推定は不要。デフォルトの 5 秒 / 5MB 待機を 0 にしないと、
            // ffmpeg が audio stream init を完了するまで encoder pipeline が起動せず、その間
            // video pipe buffer 8MB（≒ 2 frames）が満杯になって PocLoopback の同期 _videoPipe.Write が
            // ブロック → WGC frame_arrived の callback も連鎖ブロック → 録画冒頭が drop だらけに
            // (recorder.log 16:34:19 で video frames=20 at t=5s = 4 fps しか書けない事象として実証済み)
            "-thread_queue_size 1024 -analyzeduration 0 -probesize 32",
            audioArgs,
            $@"-i \\.\pipe\{_audioPipeName}",
            // Encode
            videoFilterArg,
            // -fps_mode cfr: 入力 frame の PTS 間隔が広い（broadcast.html 静止で WGC frame_arrived が
            // 数 fps しか来ない）場合に ffmpeg 側で duplicate frame を生成して 30 fps 一定に保つ。
            // これがないと MP4 が「frame=2 まま停滞 → 28 秒後にやっと audio stream init」のような
            // デッドロックを起こす（recorder.log 16:24:11 で実証済み）
            $"-fps_mode cfr -r {_videoFps}",
            "-c:v libx264 -preset veryfast -pix_fmt yuv420p",
            $"-g {_videoFps * 2}",
            "-c:a aac -b:a 192k -ar 48000",
            // Output: +faststart は moov 先頭配置（アップロード後のシーク最適化）。
            // +frag_keyframe は付けない — fragmented MP4 になり、moov の nb_frames が
            // フラグメント 1 個分（60）しか書かれず VLC 等が「先頭の 1 秒だけループ再生」
            // する症状を起こす（WinNativeApp/Streaming/FfmpegProcess.cs:209-216 で実証済み）。
            // クラッシュ耐性は失うが、StopAsync による正常停止で trailer 書き込み →
            // faststart relocation が走り moov が正しく配置される
            "-movflags +faststart",
            $"\"{_outputPath}\""
        );

        Console.WriteLine($"[FFmpeg] Path: {_ffmpegPath}");
        Console.WriteLine($"[FFmpeg] Args: {args}");

        _process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = _ffmpegPath,
                Arguments = args,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardError = true,
            },
            EnableRaisingEvents = true,
        };
        _process.Exited += (_, _) =>
            Console.WriteLine($"[FFmpeg] Exited code={_process?.ExitCode}");

        _process.Start();
        _ = MirrorStderrAsync();

        Console.WriteLine("[FFmpeg] Waiting for video pipe connection...");
        await _videoPipe.WaitForConnectionAsync(ct);
        Console.WriteLine("[FFmpeg] Video pipe connected");

        // 初期フレームを送る（FFmpeg は最低 1 フレーム読まないと次の入力を開かない）。
        // primer が渡されていればそれを使う（最初の実フレーム → PTS 0 から実画面が映る）。
        // 渡されていない or サイズ不一致なら黒フレームに fallback（後方互換）
        int expected = _videoWidth * _videoHeight * 4;
        byte[] primerFrame;
        string primerSource;
        if (primer != null && primer.Length == expected)
        {
            primerFrame = primer;
            primerSource = "real-frame";
        }
        else
        {
            if (primer != null)
                Console.Error.WriteLine($"[FFmpeg] Primer size mismatch: {primer.Length} != {expected}, falling back to black frame");
            primerFrame = new byte[expected];
            primerSource = "black";
        }
        try
        {
            _videoPipe.Write(primerFrame, 0, expected);
            _videoPipe.Flush();
            Console.WriteLine($"[FFmpeg] Initial primer frame sent ({expected} bytes, source={primerSource})");
        }
        catch (IOException ex)
        {
            Console.Error.WriteLine($"[FFmpeg] Initial primer frame error: {ex.Message}");
        }

        Console.WriteLine("[FFmpeg] Waiting for audio pipe connection...");
        await _audioPipe.WaitForConnectionAsync(ct);
        Console.WriteLine("[FFmpeg] Audio pipe connected");

        // 音声側 silence プライムは敢えて送らない。
        // サンプル数ベース PTS なので silence 14400 サンプル × 100ms 後に
        // 実音が来ると PTS は連続するが、wallclock を使っていないため読みバースト
        // による PTS 歪みは起きない。AAC エンコーダは入力が来てから動き始める。
    }

    public void WriteVideoFrame(byte[] bgra, int width, int height)
    {
        if (_videoPipe is not { IsConnected: true } || _stopping) return;
        var expected = width * height * 4;
        if (bgra.Length < expected) return;
        try
        {
            _videoPipe.Write(bgra, 0, expected);
            Interlocked.Add(ref _videoBytesWritten, expected);
            Interlocked.Increment(ref _videoFrames);
        }
        catch (IOException) when (_stopping) { }
        catch (ObjectDisposedException) when (_stopping) { }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[FFmpeg] Video write failed: {ex.Message}");
        }
    }

    public void WriteAudio(byte[] data, int count)
    {
        if (_audioPipe is not { IsConnected: true } || _stopping) return;
        try
        {
            _audioPipe.Write(data, 0, count);
            Interlocked.Add(ref _audioBytesWritten, count);
        }
        catch (IOException) when (_stopping) { }
        catch (ObjectDisposedException) when (_stopping) { }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[FFmpeg] Audio write failed: {ex.Message}");
        }
    }

    public async Task StopAsync()
    {
        if (_process == null) return;
        _stopping = true;

        try { _videoPipe?.Dispose(); } catch { }
        _videoPipe = null;
        try { _audioPipe?.Dispose(); } catch { }
        _audioPipe = null;

        try
        {
            using var cts = new CancellationTokenSource(5000);
            await _process.WaitForExitAsync(cts.Token);
        }
        catch (OperationCanceledException)
        {
            Console.Error.WriteLine("[FFmpeg] Kill after 5s timeout");
            try { _process.Kill(); } catch { }
            try { _process.WaitForExit(3000); } catch { }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[FFmpeg] Stop error: {ex.Message}");
        }

        _process?.Dispose();
        _process = null;
    }

    private async Task MirrorStderrAsync()
    {
        try
        {
            while (_process is { HasExited: false } && !_stopping)
            {
                var line = await _process.StandardError.ReadLineAsync();
                if (line == null) break;
                Console.WriteLine($"[ffmpeg] {line}");
            }
        }
        catch { }
    }

    private static string BuildAudioFormatArgs(WaveFormat wf)
    {
        bool isFloat = wf.Encoding == WaveFormatEncoding.IeeeFloat;
        if (wf.Encoding == WaveFormatEncoding.Extensible && wf is WaveFormatExtensible ext)
        {
            // KSDATAFORMAT_SUBTYPE_IEEE_FLOAT
            isFloat = ext.SubFormat == new Guid("00000003-0000-0010-8000-00aa00389b71");
        }

        string fmt;
        if (isFloat)
            fmt = "f32le";
        else
            fmt = $"s{wf.BitsPerSample}le";

        return $"-f {fmt} -ar {wf.SampleRate} -ac {wf.Channels}";
    }

    public void Dispose()
    {
        StopAsync().GetAwaiter().GetResult();
    }
}
