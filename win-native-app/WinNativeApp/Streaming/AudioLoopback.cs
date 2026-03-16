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
        _silenceTimer = new System.Threading.Timer(_ =>
        {
            try { onData(silenceBuf, 0, silenceBuf.Length); }
            catch { /* pipe closed */ }
        }, null, 100, 100);

        _capture.DataAvailable += (_, e) =>
        {
            if (e.BytesRecorded > 0)
            {
                _silenceTimer?.Change(100, 100);
                try { onData(e.Buffer, 0, e.BytesRecorded); }
                catch (Exception ex) { Log.Debug("[Audio] Write error: {Msg}", ex.Message); }
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
        if (_silenceTimer != null)
        {
            using var waitHandle = new ManualResetEvent(false);
            _silenceTimer.Dispose(waitHandle);
            waitHandle.WaitOne(1000);
            _silenceTimer = null;
        }
        try { _capture?.StopRecording(); }
        catch (Exception ex) { Log.Debug("[Audio] Stop error: {Msg}", ex.Message); }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        Stop();
        _capture?.Dispose();
    }
}
