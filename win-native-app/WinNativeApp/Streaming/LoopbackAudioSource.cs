using System.Collections.Concurrent;
using System.IO.Pipes;
using NAudio.CoreAudioApi;
using NAudio.Wave;
using Serilog;

namespace WinNativeApp.Streaming;

/// <summary>
/// 既定再生デバイスの WASAPI Loopback で OS スピーカー出力を取得し、
/// 名前付きパイプへ生 PCM を書き出すソース。録画モード（OutputMode.File）の音声入力として
/// FFmpeg に渡す想定。
///
/// plans/recording-screen-capture-alternative.md Step 1。Step 0 PoC（PocLoopback）で
/// 仮説「見聞きしているものをそのまま録れば AV 同期は構造から消える」を実証済みの設計を
/// 本体側へ移植する。
///
/// 設計メモ（PoC で確定済み）:
/// - 形式は WasapiLoopbackCapture が返すミックス形式そのまま（通常 48kHz f32 stereo）
///   を Format プロパティ経由で公開する。FFmpeg 引数の組み立ては呼び出し側の責務。
/// - 「音声側に -use_wallclock_as_timestamps を付けない」のは FFmpeg 引数組み立て側の話で、
///   このコンポーネントの責務ではない。ここはバイト列をそのままパイプに流すだけ。
/// - WASAPI コールバックは絶対にブロックしない（DataAvailable は queue に積むだけ）。
///   パイプ書き込みはバックグラウンドスレッドが消化する。
/// - 既定デバイス変更（ヘッドホン挿抜など）で RecordingStopped が発火したら reinit する。
/// </summary>
public sealed class LoopbackAudioSource : IDisposable
{
    /// <summary>WASAPI チャンクのキュー上限。約 1 秒分（10ms × 100）を上限にメモリリークを防ぐ。
    /// パイプ側で詰まった場合は古いチャンクから捨てる。FFmpeg 側 _audioQueue (cap=30, 300ms) と
    /// 役割が異なる: こちらはあくまで「OS スピーカー出力の素のキャプチャ」のセーフティネット。</summary>
    private const int MaxQueuedChunks = 100;

    /// <summary>RecordingStopped 後に再初期化するまでの待機時間（デバイス遷移の安定化待ち）。</summary>
    private const int ReinitDelayMs = 500;

    private readonly string _pipeName;
    private readonly object _captureLock = new();

    private NamedPipeServerStream? _pipe;
    private WasapiLoopbackCapture? _capture;
    private Thread? _writer;
    private readonly ConcurrentQueue<byte[]> _queue = new();

    private volatile bool _stopping;
    private volatile bool _reinitInFlight;
    private long _bytesCaptured;
    private long _bytesWritten;
    private long _droppedChunks;
    private bool _disposed;

    public string PipeName => _pipeName;

    /// <summary>WasapiLoopbackCapture が確定したミックス形式。Initialize 後に参照可能。</summary>
    public WaveFormat? Format
    {
        get
        {
            lock (_captureLock) return _capture?.WaveFormat;
        }
    }

    /// <summary>FFmpeg からのパイプ接続済みか。WriterLoop が走っているかどうかも兼ねる。</summary>
    public bool IsConnected => _pipe is { IsConnected: true };

    public long BytesCaptured => Interlocked.Read(ref _bytesCaptured);
    public long BytesWritten => Interlocked.Read(ref _bytesWritten);
    public long DroppedChunks => Interlocked.Read(ref _droppedChunks);
    public bool IsRunning => !_stopping && _capture != null;

    /// <summary>
    /// 名前付きパイプを使う。pipeName を省略するとプロセス ID 付きで一意な名前を生成。
    /// </summary>
    public LoopbackAudioSource(string? pipeName = null)
    {
        _pipeName = pipeName ?? $"winnative_loopback_{Environment.ProcessId}";
    }

    /// <summary>
    /// パイプを生成し、WASAPI Loopback の WaveFormat を確定する（StartRecording はまだ呼ばない）。
    /// 戻り値は確定したミックス形式（FFmpeg 引数の組み立てに使用）。
    ///
    /// StartRecording を ConnectAsync まで遅らせている理由: ffmpeg プロセス起動 +
    /// 名前付きパイプ接続待ちには 2〜3 秒かかるため、ここで StartRecording してしまうと
    /// その間 WASAPI が捕捉したオーディオが queue に溜まり、接続直後にバーストで
    /// pipe に流れ込む。ffmpeg はこれを audio PTS=0..N秒 として記録するので、
    /// 結果として「音声が映像より 3 秒先行する」状態になる
    /// （Step 4-1 60s 計測で end offset +2876ms / lip-sync 大幅ズレを確認）。
    ///
    /// 対策: Initialize は capture オブジェクト生成と Format 取得まで、
    /// StartRecording は ConnectAsync で pipe 接続後に呼ぶことで、
    /// audio 1 サンプル目 ≈ video 最初の実フレームの wallclock となり、AV 同期が成立する。
    /// </summary>
    public WaveFormat Initialize()
    {
        if (_disposed) throw new ObjectDisposedException(nameof(LoopbackAudioSource));
        if (_capture != null) throw new InvalidOperationException("LoopbackAudioSource already initialized");

        // 1MB バッファは FfmpegProcess._audioPipe と同基準（plans/recording-av-sync-fix.md C+A 計測）
        _pipe = new NamedPipeServerStream(
            _pipeName, PipeDirection.Out, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
            outBufferSize: 1024 * 1024, inBufferSize: 0);

        InitCapture();

        var f = _capture?.WaveFormat
            ?? throw new InvalidOperationException("WasapiLoopbackCapture WaveFormat is null after Initialize");
        return f;
    }

    /// <summary>
    /// FFmpeg からのパイプ接続を待ち、接続後に WASAPI StartRecording と書き込みスレッドを起動する。
    /// pipe 接続前に StartRecording しないことで、3 秒近いプリバッファ
    /// （= 音声先行 lip-sync ズレ）を発生させない。
    /// </summary>
    public async Task ConnectAsync(CancellationToken ct = default)
    {
        if (_pipe == null) throw new InvalidOperationException("Call Initialize() before ConnectAsync()");
        if (_writer != null) throw new InvalidOperationException("ConnectAsync already called");

        Log.Information("[Loopback] Waiting for ffmpeg pipe connection (pipe={Pipe})...", _pipeName);
        await _pipe.WaitForConnectionAsync(ct);
        Log.Information("[Loopback] Pipe connected");

        // pipe 接続後に StartRecording を呼ぶ → audio サンプル 0 が ffmpeg 受信タイミングと揃う
        StartCapture();

        _writer = new Thread(WriterLoop)
        {
            IsBackground = true,
            Name = "LoopbackPipeWriter",
        };
        _writer.Start();
    }

    /// <summary>
    /// Initialize + ConnectAsync をまとめて行う後方互換 API。
    /// 接続待ちで長時間ブロックするため、FFmpeg を別途並行起動するケースでは
    /// Initialize / ConnectAsync を分けて呼ぶこと。
    /// </summary>
    public async Task StartAsync(CancellationToken ct = default)
    {
        Initialize();
        await ConnectAsync(ct);
    }

    /// <summary>
    /// WasapiLoopbackCapture を生成しハンドラを取り付ける。StartRecording はまだ呼ばない。
    /// 実際の録音開始は <see cref="StartCapture"/> で行う（pipe 接続後）。
    /// </summary>
    private void InitCapture()
    {
        lock (_captureLock)
        {
            if (_stopping) return;

            var cap = new WasapiLoopbackCapture();
            var f = cap.WaveFormat;
            Log.Information("[Loopback] Capture format: {Encoding} {Rate}Hz {Bits}bit ch={Ch}",
                f.Encoding, f.SampleRate, f.BitsPerSample, f.Channels);

            cap.DataAvailable += OnDataAvailable;
            cap.RecordingStopped += OnRecordingStopped;
            _capture = cap;
        }
    }

    /// <summary>
    /// WASAPI Loopback の StartRecording を呼ぶ。InitCapture 済みであることが前提。
    /// pipe 接続後に呼ぶことで、capture と pipe の起動タイミングを揃える。
    /// </summary>
    private void StartCapture()
    {
        lock (_captureLock)
        {
            if (_stopping) return;
            if (_capture == null)
                throw new InvalidOperationException("Call InitCapture() before StartCapture()");
            _capture.StartRecording();
            Log.Information("[Loopback] StartRecording");
        }
    }

    private void OnDataAvailable(object? sender, WaveInEventArgs e)
    {
        if (_stopping || e.BytesRecorded <= 0) return;

        Interlocked.Add(ref _bytesCaptured, e.BytesRecorded);

        // WASAPI コールバックの buffer は再利用されるためコピー必須
        var copy = new byte[e.BytesRecorded];
        Buffer.BlockCopy(e.Buffer, 0, copy, 0, e.BytesRecorded);
        _queue.Enqueue(copy);

        // セーフティ: パイプが詰まって writer が消化できなくなった場合の上限
        while (_queue.Count > MaxQueuedChunks)
        {
            if (_queue.TryDequeue(out _))
                Interlocked.Increment(ref _droppedChunks);
        }
    }

    private void OnRecordingStopped(object? sender, StoppedEventArgs e)
    {
        if (_stopping) return; // 意図的な停止は無視

        if (e.Exception != null)
            Log.Warning(e.Exception, "[Loopback] RecordingStopped with exception, will reinit in {Ms}ms", ReinitDelayMs);
        else
            Log.Information("[Loopback] RecordingStopped (default device change?), will reinit in {Ms}ms", ReinitDelayMs);

        // 既定デバイス変更などで止まった場合に新規 capture で復帰
        // 多重発火対策: _reinitInFlight でガード
        if (!_reinitInFlight)
        {
            _reinitInFlight = true;
            _ = Task.Run(async () =>
            {
                try
                {
                    await Task.Delay(ReinitDelayMs);
                    if (_stopping) return;

                    lock (_captureLock)
                    {
                        try { _capture?.Dispose(); } catch { /* already disposed */ }
                        _capture = null;
                    }

                    // reinit は ConnectAsync 後にしか発火しないので、StartCapture まで実行する
                    InitCapture();
                    StartCapture();
                }
                catch (Exception ex)
                {
                    Log.Error(ex, "[Loopback] Reinit failed");
                }
                finally
                {
                    _reinitInFlight = false;
                }
            });
        }
    }

    private void WriterLoop()
    {
        long lastLogTick = Environment.TickCount64;
        long writtenSinceLog = 0;

        while (!_stopping)
        {
            var pipe = _pipe;
            if (pipe is not { IsConnected: true }) break;

            if (_queue.TryDequeue(out var chunk))
            {
                try
                {
                    pipe.Write(chunk, 0, chunk.Length);
                    Interlocked.Add(ref _bytesWritten, chunk.Length);
                    writtenSinceLog += chunk.Length;
                }
                catch (Exception ex) when (ex is IOException or ObjectDisposedException)
                {
                    if (!_stopping)
                        Log.Warning("[Loopback] Pipe write failed: {Type} {Msg}", ex.GetType().Name, ex.Message);
                    break;
                }
            }
            else
            {
                Thread.Sleep(1);
            }

            // 10 秒ごとにキュー状況をログ
            var now = Environment.TickCount64;
            if (now - lastLogTick > 10_000)
            {
                Log.Information("[Loopback] queue depth={Depth} written={W}B (+{New}B) drops={D}",
                    _queue.Count, BytesWritten, writtenSinceLog, DroppedChunks);
                writtenSinceLog = 0;
                lastLogTick = now;
            }
        }

        Log.Information("[Loopback] Writer loop exiting (queue depth={Depth})", _queue.Count);
    }

    /// <summary>キャプチャ・パイプ・書き込みスレッドを順に停止する。</summary>
    public void Stop()
    {
        if (_stopping) return;
        _stopping = true;

        lock (_captureLock)
        {
            try { _capture?.StopRecording(); } catch { /* already stopped */ }
        }

        // パイプを閉じて WriterLoop のブロック中 Write を解除
        try { _pipe?.Dispose(); } catch { /* already closed */ }
        _pipe = null;

        _writer?.Join(2000);
        _writer = null;

        lock (_captureLock)
        {
            try { _capture?.Dispose(); } catch { /* already disposed */ }
            _capture = null;
        }

        Log.Information("[Loopback] Stopped (capturedBytes={C} writtenBytes={W} drops={D} queueRemain={Q})",
            BytesCaptured, BytesWritten, DroppedChunks, _queue.Count);
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        Stop();
    }
}
