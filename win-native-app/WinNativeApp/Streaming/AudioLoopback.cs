using NAudio.Wave;
using Serilog;

namespace WinNativeApp.Streaming;

/// <summary>
/// WASAPI loopback capture (system-wide audio output).
/// TODO: Upgrade to process-specific Application Loopback (Win11 API) for WebView2-only capture.
/// </summary>
public sealed class AudioLoopback : IDisposable
{
    private WasapiLoopbackCapture? _capture;
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

        _capture.DataAvailable += (_, e) =>
        {
            if (e.BytesRecorded > 0)
            {
                try { onData(e.Buffer, 0, e.BytesRecorded); }
                catch (Exception ex) { Log.Debug("[Audio] Write error: {Msg}", ex.Message); }
            }
        };

        _capture.RecordingStopped += (_, e) =>
        {
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
