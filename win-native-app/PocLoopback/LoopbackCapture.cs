using NAudio.CoreAudioApi;
using NAudio.Wave;

namespace PocLoopback;

// 既定再生デバイスの WASAPI Loopback を NAudio で取得し、生バイト列を Action に渡す。
// 形式は既定デバイスのミックス形式（通常 48kHz f32 stereo）をそのまま使う。
public sealed class LoopbackCapture : IDisposable
{
    private WasapiLoopbackCapture? _cap;
    private long _bytesCaptured;

    public WaveFormat? Format => _cap?.WaveFormat;
    public long BytesCaptured => Interlocked.Read(ref _bytesCaptured);

    // (data, count) — count バイトだけが有効。data は再利用されるバッファなのでコピー前提。
    public Action<byte[], int>? OnAudio { get; set; }

    public void Start()
    {
        _cap = new WasapiLoopbackCapture();
        var f = _cap.WaveFormat;
        Console.WriteLine($"[Loopback] Format: {f.Encoding} {f.SampleRate}Hz {f.BitsPerSample}bit ch={f.Channels}");

        _cap.DataAvailable += (_, e) =>
        {
            if (e.BytesRecorded <= 0) return;
            Interlocked.Add(ref _bytesCaptured, e.BytesRecorded);
            try { OnAudio?.Invoke(e.Buffer, e.BytesRecorded); }
            catch (Exception ex) { Console.Error.WriteLine($"[Loopback] OnAudio error: {ex.Message}"); }
        };
        _cap.RecordingStopped += (_, e) =>
        {
            if (e.Exception != null)
                Console.Error.WriteLine($"[Loopback] RecordingStopped exception: {e.Exception.Message}");
            else
                Console.WriteLine("[Loopback] RecordingStopped");
        };

        _cap.StartRecording();
        Console.WriteLine("[Loopback] StartRecording");
    }

    public void Stop()
    {
        try { _cap?.StopRecording(); } catch { }
    }

    public void Dispose()
    {
        Stop();
        _cap?.Dispose();
        _cap = null;
    }
}
