using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using NAudio.Wave;
using Serilog;

namespace WinNativeApp.Streaming;

public sealed class FfmpegProcess : IDisposable
{
    // Windows Multimedia Timer API: タイマー分解能を1msに設定（デフォルト15.6ms）
    [DllImport("winmm.dll", ExactSpelling = true)]
    private static extern uint timeBeginPeriod(uint uMilliseconds);
    [DllImport("winmm.dll", ExactSpelling = true)]
    private static extern uint timeEndPeriod(uint uMilliseconds);

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

    // AV同期診断用: ffmpeg起動時刻を0とする相対tick（ms）。File モード時のみ有効
    private long _diagStartTick;
    private long _diagFirstRealVideoTick = -1;
    private long _diagFirstTtsEnqueueTick = -1;
    private long _diagFirstTtsMixTick = -1;
    private long _diagAudioGenStartTick = -1;

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
    // キュー上限: 約100ms分（10ms × 10チャンク）。
    // 100チャンク（1秒）だと generator → AudioWriterLoop 間で恒常飽和し音声PTSが1秒遅れる問題があった
    // （plans/recording-av-sync-fix.md B2）。100msに絞ることで TTS が到着後 100ms以内にパイプに届く。
    private const int MaxAudioQueueChunks = 10;

    // TTS直接書き込み用キュー（WASAPI迂回 → リップシンク完全同期）
    private readonly ConcurrentQueue<byte[]> _ttsQueue = new();
    private byte[]? _ttsCurrentChunk;
    private int _ttsCurrentOffset;
    private float _ttsVolume = 1.0f;

    // BGMミキサー用フィールド
    private byte[]? _bgmPcm;
    private int _bgmOffset;
    private float _bgmVolume = 1.0f;
    private volatile bool _bgmPlaying;

    // SEミキサー用フィールド（一回再生、ループなし）
    private readonly ConcurrentQueue<byte[]> _seQueue = new();
    private byte[]? _seCurrentChunk;
    private int _seCurrentOffset;
    private float _seVolume = 1.0f;

    // タイマーベース音声ジェネレータ（WASAPI不要、TTS+BGMをPCM合成→FFmpegパイプ）
    private System.Threading.Timer? _audioGenTimer;
    private long _audioGenLastTick;

    // 音声レベルメーター（ミキシング済みチャンクから計算、瞬時値）
    private volatile float _lastRmsDb = -100f;
    private volatile float _lastPeakDb = -100f;

    // ストリーム健全性追跡（診断・改善用）
    private double _lastSpeed;                 // 最新のFFmpegエンコード速度
    private volatile int _lastFps;             // 最新のFFmpeg出力fps
    private long _summaryTick;                 // 定期サマリーの最終出力時刻
    private long _slowWriteCount;              // パイプ書き込みが100ms超えた回数
    private long _maxWriteMs;                  // パイプ書き込みの最大時間
    private double _speedWarnThreshold = 0.95; // speed警告の閾値（段階的に下げる）
    private long _lastDropSnapshot;            // 前回サマリー時のドロップ数
    private long _lastAudioDropSnapshot;       // 前回サマリー時の音声ドロップ数
    public float LastRmsDb => _lastRmsDb;
    public float LastPeakDb => _lastPeakDb;
    public bool IsBgmActive => _bgmPlaying;
    public bool IsTtsActive => _ttsCurrentChunk != null || !_ttsQueue.IsEmpty;
    public bool IsSeActive => _seCurrentChunk != null || !_seQueue.IsEmpty;

    public bool IsRunning => _process is { HasExited: false };
    public long FrameCount => Interlocked.Read(ref _frameCount);
    public long DropCount => Interlocked.Read(ref _dropCount);
    public long AudioDropCount => Interlocked.Read(ref _audioDropCount);
    public TimeSpan Uptime => IsRunning ? DateTime.UtcNow - _startTime : TimeSpan.Zero;
    public double LastSpeed => _lastSpeed;
    public int LastFps => _lastFps;
    public long SlowWriteCount => Interlocked.Read(ref _slowWriteCount);
    public long MaxWriteMs => Interlocked.Read(ref _maxWriteMs);

    public FfmpegProcess(StreamConfig config, WaveFormat? audioFormat = null)
    {
        _config = config;
        _videoPipeName = $"winnative_video_{Environment.ProcessId}";
        _audioPipeName = $"winnative_audio_{Environment.ProcessId}";
        _ffmpegAudioFormat = audioFormat != null
            ? BuildAudioFormatArgs(audioFormat)
            : "-f f32le -ar 48000 -ac 2";
    }

    public async Task StartAsync(CancellationToken ct = default)
    {
        if (IsRunning) throw new InvalidOperationException("FFmpeg already running");

        // タイマー分解能を1msに設定（音声ジェネレータの10msタイマー精度向上）
        timeBeginPeriod(1);

        var ffmpeg = FindFfmpeg();
        Log.Information("[FFmpeg] Path: {Path}", ffmpeg);

        // 映像用名前付きパイプ（8MBバッファ — 2フレーム分以上）
        _videoPipe = new NamedPipeServerStream(
            _videoPipeName, PipeDirection.Out, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
            outBufferSize: 8 * 1024 * 1024, inBufferSize: 0);

        // 音声用名前付きパイプ（256KBバッファ — タイマージッター吸収）
        _audioPipe = new NamedPipeServerStream(
            _audioPipeName, PipeDirection.Out, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
            outBufferSize: 256 * 1024, inBufferSize: 0);

        // ダブルバッファ事前確保（BGRA入力コピー用）
        var bgraFrameSize = _config.Width * _config.Height * 4;
        _videoBufA = new byte[bgraFrameSize];
        _videoBufB = new byte[bgraFrameSize];
        _videoBufIdx = 0;

        // NV12変換バッファ（BGRA 3.7MB → NV12 1.4MB @1280x720、パイプ転送量63%削減）
        var nv12Size = ColorConverter.Nv12Size(_config.Width, _config.Height);
        _nv12Buf = new byte[nv12Size];

        // エンコーダ選択（auto=HW自動検出→libx264フォールバック）
        var encoder = ResolveEncoder(_config.Encoder, FindFfmpeg());
        var encoderArgs = BuildEncoderArgs(encoder, _config);
        Log.Information("[FFmpeg] Mode: {Mode}, Encoder: {Encoder}, AudioOffset: {Offset}s",
            _config.Mode, encoder, _config.AudioOffset);

        // 出力モード別の最終引数と低遅延系フラグの有無を決定
        string outputArgs;
        string lowLatencyArgs;
        if (_config.Mode == OutputMode.File)
        {
            var outputPath = _config.OutputPath
                ?? throw new InvalidOperationException("OutputPath is required for File mode");
            var dir = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            // +frag_keyframe はクラッシュ耐性、+faststart はmoov先頭配置（アップロード後のseek最適化）
            outputArgs = $"-f mp4 -movflags +faststart+frag_keyframe \"{outputPath}\"";
            // 録画は画質優先のため低遅延フラグを使わない
            lowLatencyArgs = "";
            Log.Information("[FFmpeg] Recording to file: {Path}", outputPath);
        }
        else
        {
            var rtmpTarget = $"{_config.RtmpUrl}/{_config.StreamKey}";
            outputArgs = $"-f flv -flvflags no_duration_filesize \"{rtmpTarget}\"";
            lowLatencyArgs = "-flags +low_delay -fflags +nobuffer -flush_packets 1";
        }

        // 録画モードのみ映像入力に -use_wallclock_as_timestamps 1 を付与する。
        // frame_index × (1/fps) 基準のPTSだと WGC キャプチャの実到着レートと乖離して線形ドリフトする
        // （50秒で +533ms 程度）。実時刻で打刻することでドロップ時は時間圧縮ではなく
        // 直前フレームの停止として表現され、MP4再生時のAV同期が維持される。
        // 配信(RTMP)は Twitch 側で吸収されるため従来通り frame_index 基準のまま。
        // plans/recording-av-sync-verification.md / plans/recording-av-sync-fix.md
        var wallclockOpt = _config.Mode == OutputMode.File
            ? "-use_wallclock_as_timestamps 1"
            : "";

        var args = string.Join(" ",
            "-y -nostdin",
            // Video input (named pipe — 8MBバッファ + NV12でデータ量63%削減)
            "-thread_queue_size 64",
            wallclockOpt,
            "-f rawvideo -pixel_format nv12",
            $"-video_size {_config.Width}x{_config.Height}",
            $"-framerate {_config.Framerate}",
            $@"-i \\.\pipe\{_videoPipeName}",
            // Audio input (named pipe)
            "-thread_queue_size 1024",
            _ffmpegAudioFormat,
            // AudioOffset: 音声入力PTSをオフセット（負=早める、正=遅らせる）
            // wallclock映像との乖離を吸収。0 なら無効化（引数省略）
            _config.AudioOffset != 0
                ? $"-itsoffset {_config.AudioOffset.ToString("F3", System.Globalization.CultureInfo.InvariantCulture)}"
                : "",
            $@"-i \\.\pipe\{_audioPipeName}",
            // Video encode (encoder-specific)
            encoderArgs,
            $"-b:v {_config.VideoBitrate}",
            $"-maxrate {_config.VideoBitrate}",
            $"-bufsize {ParseBitrateKbps(_config.VideoBitrate) * 2}k",
            "-pix_fmt yuv420p",
            $"-g {_config.Framerate * 2}",
            lowLatencyArgs,
            // Audio encode
            $"-c:a aac -b:a {_config.AudioBitrate} -ar 44100",
            // Output (RTMP or File)
            outputArgs
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
        _diagStartTick = Environment.TickCount64;
        _diagFirstRealVideoTick = -1;
        _diagFirstTtsEnqueueTick = -1;
        _diagFirstTtsMixTick = -1;
        _diagAudioGenStartTick = -1;
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
            Log.Information("[AVSync] t={T}ms: black frame written", Environment.TickCount64 - _diagStartTick);
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
            Log.Information("[AVSync] t={T}ms: audio primed silence written ({Bytes}B)",
                Environment.TickCount64 - _diagStartTick, totalSilenceBytes);
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
                // StopAsync と競合した場合、pipe が dispose/null 化されているので早期 return
                // （ローカル変数 pipe に取り出すことで以降のチェック〜Write 間の null 化レースを排除）
                var pipe = _videoPipe;
                if (_stopping || pipe is null) return;

                var sw = Stopwatch.StartNew();

                // BGRA → NV12 変換（3.7MB → 1.4MB @1280x720）
                ColorConverter.BgraToNv12(buf, nv12, w, h);
                var convertMs = sw.ElapsedMilliseconds;

                // NV12をパイプに書き込み
                pipe.Write(nv12, 0, nv12WriteSize);
                sw.Stop();
                Interlocked.Increment(ref _frameCount);
                var writeMs = sw.ElapsedMilliseconds;

                var relVideo = Environment.TickCount64 - _diagStartTick;
                if (Interlocked.CompareExchange(ref _diagFirstRealVideoTick, relVideo, -1) == -1)
                    Log.Information("[AVSync] t={T}ms: first real video frame written", relVideo);

                // パイプ書き込み遅延の追跡（FFmpegがRTMP送信に追いつけないと100ms超）
                if (writeMs > 100)
                {
                    Interlocked.Increment(ref _slowWriteCount);
                    var prevMax = Interlocked.Read(ref _maxWriteMs);
                    if (writeMs > prevMax)
                        Interlocked.Exchange(ref _maxWriteMs, writeMs);
                    Log.Warning("[FFmpeg] Video pipe write slow: {WriteMs}ms (network/encode backpressure)", writeMs);
                }

                // NV12変換が遅い場合は警告（フレーム間隔の75%超）
                var frameIntervalMs = 1000 / _config.Framerate;
                if (convertMs > frameIntervalMs * 3 / 4)
                    Log.Warning("[FFmpeg] NV12 conversion slow: {Ms}ms (threshold {Thresh}ms)",
                        convertMs, frameIntervalMs * 3 / 4);

                // 30フレームごとに変換+書き込み時間をログ
                var fc = Interlocked.Read(ref _frameCount);
                if (fc <= 5 || fc % 30 == 0)
                    Log.Debug("[FFmpeg] NV12 convert={ConvMs}ms write={TotalMs}ms, frames={F} drops={D}",
                        convertMs, writeMs, fc, DropCount);
            }
            catch (Exception ex) when (ex is IOException
                                    or ObjectDisposedException
                                    or NullReferenceException)
            {
                Interlocked.Increment(ref _dropCount);
                // 停止中は想定内のレース（StopAsync と競合）。停止外で起きていたら痕跡を残す
                if (!_stopping)
                    Log.Debug("[FFmpeg] Video write race caught: {Type}", ex.GetType().Name);
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
    /// TTS PCMデータをミキサーキューに追加する。
    /// サーバーから受信したTTS WAVをTtsDecoderで変換後のf32le 48kHz stereo PCM。
    /// AudioWriterLoopがWASAPI（BGM）データとサンプル単位で加算合成する。
    /// </summary>
    public void WriteTtsData(byte[] f32lePcm)
    {
        if (_audioPipe is not { IsConnected: true } || _stopping) return;
        _ttsQueue.Enqueue(f32lePcm);
        Log.Information("[FFmpeg] TTS PCM enqueued: {Size} bytes ({Dur:F1}s)",
            f32lePcm.Length, f32lePcm.Length / (48000.0 * 2 * 4));
        var rel = Environment.TickCount64 - _diagStartTick;
        if (Interlocked.CompareExchange(ref _diagFirstTtsEnqueueTick, rel, -1) == -1)
            Log.Information("[AVSync] t={T}ms: first TTS enqueued ({Size}B, {Dur:F2}s) audioQueue={Q}",
                rel, f32lePcm.Length, f32lePcm.Length / (48000.0 * 2 * 4), _audioQueue.Count);
    }

    /// <summary>TTS音量を変更する（再生中のミキシングにリアルタイム反映）。</summary>
    public void SetTtsVolume(float volume)
    {
        _ttsVolume = volume;
        Log.Debug("[FFmpeg] TTS volume set: {Vol:F2}", volume);
    }

    /// <summary>
    /// SE PCMデータをミキサーキューに追加する（一回再生、ループなし）。
    /// </summary>
    public void WriteSeData(byte[] f32lePcm, float volume)
    {
        if (_audioPipe is not { IsConnected: true } || _stopping) return;
        _seVolume = volume;
        _seQueue.Enqueue(f32lePcm);
        Log.Information("[FFmpeg] SE PCM enqueued: {Size} bytes ({Dur:F1}s), vol={Vol:F2}",
            f32lePcm.Length, f32lePcm.Length / (48000.0 * 2 * 4), volume);
    }

    /// <summary>SE音量を変更する。</summary>
    public void SetSeVolume(float volume)
    {
        _seVolume = volume;
        Log.Debug("[FFmpeg] SE volume set: {Vol:F2}", volume);
    }

    /// <summary>
    /// タイマーベースの音声ジェネレータを開始する。
    /// 壁時計時間を追跡し、実際の経過時間分の音声を生成する。
    /// Windowsタイマー解像度（15.6ms）に依存せずリアルタイムレートを維持。
    /// </summary>
    public void StartAudioGenerator()
    {
        // 48kHz stereo f32le = 384 bytes per ms
        const int bytesPerMs = 48000 * 2 * 4 / 1000;
        _audioGenLastTick = Environment.TickCount64;
        _diagAudioGenStartTick = _audioGenLastTick - _diagStartTick;
        Log.Information("[AVSync] t={T}ms: audio generator started", _diagAudioGenStartTick);
        _audioGenTimer = new System.Threading.Timer(_ =>
        {
            if (_stopping || _audioPipe is not { IsConnected: true }) return;
            try
            {
                var now = Environment.TickCount64;
                var elapsedMs = (int)(now - _audioGenLastTick);
                _audioGenLastTick = now;

                // 経過時間をクランプ（1〜50ms、異常値防止）
                elapsedMs = Math.Clamp(elapsedMs, 1, 50);

                // 経過時間に応じたチャンクサイズ（f32leサンプル境界に揃える）
                var chunkSize = (elapsedMs * bytesPerMs / 4) * 4;

                var chunk = new byte[chunkSize]; // all zeros = silence
                MixBgmInto(chunk);
                MixSeInto(chunk);
                MixTtsInto(chunk);
                _audioQueue.Enqueue(chunk);

                // RMS/peakメーター計算（f32leサンプルから）
                MeasureLevel(chunk, now);

                // キュー上限超過時は古いチャンクを破棄
                while (_audioQueue.Count > MaxAudioQueueChunks)
                {
                    if (_audioQueue.TryDequeue(out byte[] _))
                        Interlocked.Increment(ref _audioDropCount);
                }
            }
            catch (Exception ex)
            {
                Log.Debug("[FFmpeg] AudioGen error: {Msg}", ex.Message);
            }
        }, null, 0, 10);
        Log.Information("[FFmpeg] Audio generator started (time-tracked, {BytesPerMs} bytes/ms)", bytesPerMs);
    }

    /// <summary>
    /// BGM PCMデータを設定する（48kHz stereo f32le）。ループ再生される。
    /// </summary>
    public void SetBgm(byte[]? pcmData, float volume)
    {
        _bgmPcm = pcmData;
        _bgmOffset = 0;
        _bgmVolume = volume;
        _bgmPlaying = pcmData != null && pcmData.Length > 0;
        Log.Information("[FFmpeg] BGM set: {Size} bytes, vol={Vol:F2}", pcmData?.Length ?? 0, volume);
    }

    /// <summary>BGMの音量を変更する。</summary>
    public void SetBgmVolume(float volume)
    {
        _bgmVolume = volume;
        Log.Debug("[FFmpeg] BGM volume set: {Vol:F2}", volume);
    }

    /// <summary>BGM再生を停止する。</summary>
    public void StopBgm()
    {
        _bgmPlaying = false;
        _bgmPcm = null;
        _bgmOffset = 0;
        Log.Information("[FFmpeg] BGM stopped");
    }

    /// <summary>
    /// チャンクにBGM PCMを加算合成する（in-place）。
    /// _bgmPcmの末尾に達したらオフセット0に戻ってループ再生する。
    /// </summary>
    private void MixBgmInto(byte[] chunk)
    {
        if (!_bgmPlaying) return;
        var pcm = _bgmPcm;
        if (pcm == null || pcm.Length < 4) return;

        var vol = _bgmVolume;
        for (int i = 0; i + 3 < chunk.Length; i += 4)
        {
            // ループ: 末尾に達したら先頭に戻る
            if (_bgmOffset + 3 >= pcm.Length)
                _bgmOffset = 0;

            float bgmSample = BitConverter.ToSingle(pcm, _bgmOffset) * vol;
            float current = BitConverter.ToSingle(chunk, i);
            float mixed = Math.Clamp(current + bgmSample, -1.0f, 1.0f);
            BitConverter.TryWriteBytes(chunk.AsSpan(i), mixed);
            _bgmOffset += 4;
        }
    }

    /// <summary>
    /// チャンクにTTS PCMを加算合成する（in-place）。
    /// TTSキューからデータを消費し、なくなったら何もしない。
    /// </summary>
    private void MixTtsInto(byte[] chunk)
    {
        int pos = 0;
        while (pos + 3 < chunk.Length)
        {
            if (_ttsCurrentChunk == null || _ttsCurrentOffset >= _ttsCurrentChunk.Length)
            {
                if (!_ttsQueue.TryDequeue(out _ttsCurrentChunk))
                    break;
                _ttsCurrentOffset = 0;
                var rel = Environment.TickCount64 - _diagStartTick;
                var dur = _ttsCurrentChunk.Length / (48000.0 * 2 * 4);
                Log.Information("[AVSync] t={T}ms: TTS chunk pulled ({Bytes}B, {Dur:F2}s, audioQ={Q})",
                    rel, _ttsCurrentChunk.Length, dur, _audioQueue.Count);
                if (Interlocked.CompareExchange(ref _diagFirstTtsMixTick, rel, -1) == -1)
                    Log.Information("[AVSync] t={T}ms: first TTS mix start (enqueued→mix lag={Lag}ms)",
                        rel, _diagFirstTtsEnqueueTick >= 0 ? rel - _diagFirstTtsEnqueueTick : -1);
            }

            int available = _ttsCurrentChunk.Length - _ttsCurrentOffset;
            int remaining = chunk.Length - pos;
            int toMix = Math.Min(available, remaining);
            toMix = (toMix / 4) * 4;

            if (toMix <= 0) break;

            var vol = _ttsVolume;
            for (int i = 0; i < toMix; i += 4)
            {
                float bgm = BitConverter.ToSingle(chunk, pos + i);
                float tts = BitConverter.ToSingle(_ttsCurrentChunk, _ttsCurrentOffset + i) * vol;
                float mixed = Math.Clamp(bgm + tts, -1.0f, 1.0f);
                BitConverter.TryWriteBytes(chunk.AsSpan(pos + i), mixed);
            }

            _ttsCurrentOffset += toMix;
            pos += toMix;
        }
    }

    /// <summary>
    /// チャンクにSE PCMを加算合成する（in-place）。TTSと同じパターンだがループなし。
    /// </summary>
    private void MixSeInto(byte[] chunk)
    {
        int pos = 0;
        while (pos + 3 < chunk.Length)
        {
            if (_seCurrentChunk == null || _seCurrentOffset >= _seCurrentChunk.Length)
            {
                if (!_seQueue.TryDequeue(out _seCurrentChunk))
                    break;
                _seCurrentOffset = 0;
            }

            int available = _seCurrentChunk.Length - _seCurrentOffset;
            int remaining = chunk.Length - pos;
            int toMix = Math.Min(available, remaining);
            toMix = (toMix / 4) * 4;

            if (toMix <= 0) break;

            var vol = _seVolume;
            for (int i = 0; i < toMix; i += 4)
            {
                float existing = BitConverter.ToSingle(chunk, pos + i);
                float se = BitConverter.ToSingle(_seCurrentChunk, _seCurrentOffset + i) * vol;
                float mixed = Math.Clamp(existing + se, -1.0f, 1.0f);
                BitConverter.TryWriteBytes(chunk.AsSpan(pos + i), mixed);
            }

            _seCurrentOffset += toMix;
            pos += toMix;
        }
    }

    /// <summary>ミキシング済みf32leチャンクからRMS/瞬時peakを計算する。</summary>
    private void MeasureLevel(byte[] chunk, long nowTick)
    {
        float sumSq = 0;
        float maxAbs = 0;
        int numSamples = chunk.Length / 4;
        if (numSamples == 0) return;

        for (int i = 0; i + 3 < chunk.Length; i += 4)
        {
            float s = BitConverter.ToSingle(chunk, i);
            sumSq += s * s;
            float abs = Math.Abs(s);
            if (abs > maxAbs) maxAbs = abs;
        }

        _lastRmsDb = MathF.Sqrt(sumSq / numSamples) is var rms and > 0 ? 20f * MathF.Log10(rms) : -100f;
        _lastPeakDb = maxAbs > 0 ? 20f * MathF.Log10(maxAbs) : -100f;
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
                // タイマーベースジェネレータが既にBGM+TTSをミキシング済み
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

        Log.Information("[AVSync] === summary === firstVideo={V}ms audioGenStart={G}ms firstTtsEnq={E}ms firstTtsMix={M}ms",
            _diagFirstRealVideoTick, _diagAudioGenStartTick, _diagFirstTtsEnqueueTick, _diagFirstTtsMixTick);

        var totalFrames = FrameCount;
        var totalDrops = DropCount;
        var totalAudioDrops = AudioDropCount;
        var dropRate = totalFrames > 0 ? (double)totalDrops / (totalFrames + totalDrops) * 100 : 0;
        var slowWrites = Interlocked.Read(ref _slowWriteCount);
        var maxWrite = Interlocked.Read(ref _maxWriteMs);
        var uptime = Uptime;

        Log.Information("[FFmpeg] === 配信終了レポート ({Uptime:hh\\:mm\\:ss}) === " +
            "フレーム: {Frames} ドロップ: {Drops} ({DropRate:F1}%) | " +
            "音声ドロップ: {AudioDrops} | 最終speed: {Speed:F3}x fps: {Fps} | " +
            "パイプ遅延: slow={SlowWrites}回 max={MaxWrite}ms",
            uptime, totalFrames, totalDrops, dropRate,
            totalAudioDrops, _lastSpeed, _lastFps,
            slowWrites, maxWrite);

        try
        {
            // 音声ジェネレータタイマーを停止
            try { _audioGenTimer?.Dispose(); }
            catch { /* already disposed */ }
            _audioGenTimer = null;

            // BGM・SEも停止
            _bgmPlaying = false;
            _bgmPcm = null;
            _seCurrentChunk = null;
            while (_seQueue.TryDequeue(out _)) { }

            // パイプ dispose 前に、ThreadPool にキュー済みの映像書き込みラムダの終了を待つ
            // （Fix A のラムダ先頭チェックだけでは、チェック〜Write 間に窓が残るため）
            var spinStart = Environment.TickCount64;
            while (_writingVideo && Environment.TickCount64 - spinStart < 200)
                Thread.Sleep(5);
            if (_writingVideo)
                Log.Warning("[FFmpeg] Video writer did not finish within 200ms; forcing close");

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

        // タイマー分解能を元に戻す
        timeEndPeriod(1);

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
            _summaryTick = startTick;
            _speedWarnThreshold = 0.95;
            var speedRegex = new System.Text.RegularExpressions.Regex(@"speed=\s*([\d.]+)x");
            var fpsRegex = new System.Text.RegularExpressions.Regex(@"fps=\s*(\d+)");

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
                    Log.Information("[AVSync] t={T}ms: ffmpeg encoding started (first frame=)",
                        Environment.TickCount64 - _diagStartTick);
                }

                // speed & fps追跡
                var speedMatch = speedRegex.Match(line);
                if (speedMatch.Success &&
                    double.TryParse(speedMatch.Groups[1].Value, System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out var speed))
                {
                    _lastSpeed = speed;

                    // 段階的speed警告（同じ閾値では1回だけ、0.05刻み: 0.95→0.90→0.85→0.80）
                    if (speed < _speedWarnThreshold)
                    {
                        var bitrateKbps = ParseBitrateKbps(_config.VideoBitrate);
                        var recommendedBitrate = (int)(bitrateKbps * speed * 0.9); // 10%マージン
                        Log.Warning("[FFmpeg] Speed dropped below {Threshold:F2}x: speed={Speed}x fps={Fps} " +
                            "— ネットワーク帯域不足の可能性。推奨ビットレート: {Rec}k (現在: {Cur}k)",
                            _speedWarnThreshold, speed, _lastFps, recommendedBitrate, bitrateKbps);
                        // 次の閾値に下げる（0.05刻み）
                        _speedWarnThreshold = Math.Round(_speedWarnThreshold - 0.05, 2);
                    }
                }

                var fpsMatch = fpsRegex.Match(line);
                if (fpsMatch.Success && int.TryParse(fpsMatch.Groups[1].Value, out var fps))
                    _lastFps = fps;

                // 60秒ごとの定期サマリー（配信全体の健全性を一目で確認）
                var now = Environment.TickCount64;
                if (now - _summaryTick > 60_000)
                {
                    _summaryTick = now;
                    var totalFrames = FrameCount;
                    var totalDrops = DropCount;
                    var totalAudioDrops = AudioDropCount;
                    var dropRate = totalFrames > 0 ? (double)totalDrops / (totalFrames + totalDrops) * 100 : 0;
                    var recentDrops = totalDrops - _lastDropSnapshot;
                    var recentAudioDrops = totalAudioDrops - _lastAudioDropSnapshot;
                    _lastDropSnapshot = totalDrops;
                    _lastAudioDropSnapshot = totalAudioDrops;
                    var slowWrites = Interlocked.Read(ref _slowWriteCount);
                    var maxWrite = Interlocked.Read(ref _maxWriteMs);
                    var uptime = Uptime;

                    Log.Information("[FFmpeg] === 配信サマリー ({Uptime:hh\\:mm\\:ss}) === " +
                        "speed={Speed:F3}x fps={Fps}/{Target} | " +
                        "フレーム: {Frames} ドロップ: {Drops} ({DropRate:F1}%, 直近+{Recent}) | " +
                        "音声ドロップ: {AudioDrops} (直近+{RecentAudio}) | " +
                        "パイプ遅延: slow={SlowWrites}回 max={MaxWrite}ms | " +
                        "キュー: audio={AudioQueue}",
                        uptime, _lastSpeed, _lastFps, _config.Framerate,
                        totalFrames, totalDrops, dropRate, recentDrops,
                        totalAudioDrops, recentAudioDrops,
                        slowWrites, maxWrite,
                        _audioQueue.Count);
                }

                // 起動後60秒間はSerilogにも出力（音声途切れ診断用）
                if (now - startTick < 60_000)
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

        Log.Information("[FFmpeg] Auto-detecting HW encoder (path={Path})...", ffmpegPath);

        // FFmpegが見つからない場合はprobeスキップ
        if (!File.Exists(ffmpegPath))
        {
            Log.Warning("[FFmpeg] FFmpeg not found at {Path}, skipping HW probe", ffmpegPath);
            return "libx264";
        }

        // まず -encoders リストからHWエンコーダの有無を確認
        string encoderList = "";
        try
        {
            var listPsi = new ProcessStartInfo
            {
                FileName = ffmpegPath,
                Arguments = "-hide_banner -encoders",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using var listProc = Process.Start(listPsi);
            encoderList = listProc!.StandardOutput.ReadToEnd();
            listProc.WaitForExit(5000);
        }
        catch (Exception ex)
        {
            Log.Warning("[FFmpeg] Failed to list encoders: {Msg}", ex.Message);
        }

        // HWエンコーダを優先順に試行
        string[] candidates = ["h264_nvenc", "h264_amf", "h264_qsv"];
        foreach (var enc in candidates)
        {
            // -encoders リストに含まれていなければスキップ
            if (!string.IsNullOrEmpty(encoderList) && !encoderList.Contains(enc))
            {
                Log.Debug("[FFmpeg] {Enc} not in encoder list, skipping", enc);
                continue;
            }

            try
            {
                // color=black でシンプルなテストフレームを生成（nullsrcより互換性が高い）
                var psi = new ProcessStartInfo
                {
                    FileName = ffmpegPath,
                    Arguments = $"-y -f lavfi -i color=black:s=256x256:d=0.1 -frames:v 1 -c:v {enc} -f null NUL",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                using var p = Process.Start(psi);
                var stderr = p!.StandardError.ReadToEnd();
                p.WaitForExit(10000);
                if (p.ExitCode == 0)
                {
                    Log.Information("[FFmpeg] HW encoder detected: {Enc}", enc);
                    return enc;
                }
                var errTail = stderr.Length > 300 ? stderr[^300..] : stderr;
                Log.Information("[FFmpeg] Probe {Enc} failed (exit={Code}): {Err}", enc, p.ExitCode, errTail);
            }
            catch (Exception ex)
            {
                Log.Warning("[FFmpeg] Probe {Enc} exception: {Msg}", enc, ex.Message);
            }
        }

        Log.Warning("[FFmpeg] No HW encoder found, falling back to libx264 (will be slow at high resolutions)");
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
