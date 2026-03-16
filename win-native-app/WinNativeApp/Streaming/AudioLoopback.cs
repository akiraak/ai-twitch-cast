using NAudio.Wave;
using Serilog;

namespace WinNativeApp.Streaming;

/// <summary>
/// WASAPI loopback capture (system-wide audio output).
/// システムで何も再生されていないとき用にサイレンスフォールバック付き。
/// </summary>
public sealed class AudioLoopback : IDisposable
{
    private WasapiLoopbackCapture? _capture;
    private System.Threading.Timer? _silenceTimer;
    private bool _disposed;

    public WaveFormat? Format => _capture?.WaveFormat;

    public void Initialize()
    {
        _capture = new WasapiLoopbackCapture();
        var wf = _capture.WaveFormat;
        Log.Information("[Audio] Loopback format: {Enc} {Rate}Hz {Ch}ch {Bits}bit",
            wf.Encoding, wf.SampleRate, wf.Channels, wf.BitsPerSample);
    }

    public void Start(Action<byte[], int, int> onData)
    {
        if (_capture == null) throw new InvalidOperationException("Not initialized");

        // サイレンスバッファ（WASAPIがデータを出さない場合のフォールバック）
        // 100ms分: 48000Hz * 2ch * 4bytes/sample * 0.1s = 38400 bytes
        // ※ 10ms分だとFFmpegが音声不足で全体が0.1x speedに制限される
        var wf = _capture.WaveFormat;
        var silenceBytes = wf.SampleRate * wf.Channels * (wf.BitsPerSample / 8) / 10; // 100ms分
        var silenceBuf = new byte[silenceBytes];
        long silenceCount = 0;
        long dataCount = 0;
        long lastLogTick = Environment.TickCount64;
        // 実データ受信時刻（サイレンスと実データの二重書き込みを防止）
        long lastDataTick = 0;
        _silenceTimer = new System.Threading.Timer(_ =>
        {
            // 実データが最近届いている間はサイレンスを送らない（二重書き込み防止）
            var elapsed = Environment.TickCount64 - Interlocked.Read(ref lastDataTick);
            if (elapsed < 200) return; // 200ms以内に実データがあればスキップ
            Interlocked.Increment(ref silenceCount);
            try { onData(silenceBuf, 0, silenceBuf.Length); }
            catch { /* pipe closed */ }
        }, null, 100, 100);

        _capture.DataAvailable += (_, e) =>
        {
            if (e.BytesRecorded > 0)
            {
                Interlocked.Increment(ref dataCount);
                Interlocked.Exchange(ref lastDataTick, Environment.TickCount64);
                try { onData(e.Buffer, 0, e.BytesRecorded); }
                catch (Exception ex) { Log.Debug("[Audio] Write error: {Msg}", ex.Message); }

                // 10秒ごとに統計ログ
                var now = Environment.TickCount64;
                var last = Interlocked.Read(ref lastLogTick);
                if (now - last > 10000 && Interlocked.CompareExchange(ref lastLogTick, now, last) == last)
                {
                    var sc = Interlocked.Exchange(ref silenceCount, 0);
                    var dc = Interlocked.Exchange(ref dataCount, 0);
                    Log.Information("[Audio] Stats (10s): data={Data} silence={Silence} bytes={Bytes}",
                        dc, sc, e.BytesRecorded);
                }
            }
        };

        _capture.RecordingStopped += (_, e) =>
        {
            _silenceTimer?.Dispose();
            if (e.Exception != null)
                Log.Error(e.Exception, "[Audio] Recording stopped with error");
            else
                Log.Information("[Audio] Recording stopped");
        };

        _capture.StartRecording();
        Log.Information("[Audio] Recording started");
    }

    public void Stop()
    {
        // 先にnullにしてからDispose（DataAvailableコールバックとのレース防止）
        var timer = _silenceTimer;
        _silenceTimer = null;
        // waitHandleパターンは使わない（WaitOneタイムアウト後にタイマー内部がハンドルを
        // Signalしようとしてクラッシュするため）。単純なDisposeで十分。
        timer?.Dispose();
        try { _capture?.StopRecording(); }
        catch (Exception ex) { Log.Debug("[Audio] Stop error: {Msg}", ex.Message); }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        Stop();
        // NAudioのWasapiLoopbackCapture.Dispose()は内部COM解放が
        // UIスレッドでハング、他スレッドでネイティブクラッシュする。
        // Dispose()を呼ばず、ファイナライザも抑制してリーク許容。
        // StopRecording()で録音は停止済み。COMリソースはプロセス終了時にOS回収。
        var capture = _capture;
        _capture = null;
        if (capture != null)
            GC.SuppressFinalize(capture);
    }
}
