using NAudio.Wave;

namespace WinNativeApp.Streaming;

/// <summary>
/// IWaveProviderをラップし、通過するIEEE float音声サンプルのRMS/peakを測定する。
/// WaveChannel32（f32le出力）の後段に挿入して使用する。
/// </summary>
public class MeteringWaveProvider : IWaveProvider
{
    private readonly IWaveProvider _source;
    private volatile float _rmsDb = -100f;
    private volatile float _peakDb = -100f;

    public WaveFormat WaveFormat => _source.WaveFormat;
    public float RmsDb => _rmsDb;
    /// <summary>直近Read()の瞬時ピーク（ホールドなし）</summary>
    public float PeakDb => _peakDb;

    public MeteringWaveProvider(IWaveProvider source)
    {
        _source = source;
    }

    public int Read(byte[] buffer, int offset, int count)
    {
        int read = _source.Read(buffer, offset, count);
        if (read <= 0) return read;

        // IEEE float 32-bit (4 bytes per sample) のみ測定
        if (_source.WaveFormat.BitsPerSample != 32) return read;

        float sumSq = 0;
        float maxAbs = 0;
        int numSamples = read / 4;

        for (int i = offset; i + 3 < offset + read; i += 4)
        {
            float s = BitConverter.ToSingle(buffer, i);
            sumSq += s * s;
            float abs = Math.Abs(s);
            if (abs > maxAbs) maxAbs = abs;
        }

        float rms = MathF.Sqrt(sumSq / numSamples);
        _rmsDb = rms > 0 ? 20f * MathF.Log10(rms) : -100f;

        _peakDb = maxAbs > 0 ? 20f * MathF.Log10(maxAbs) : -100f;

        return read;
    }
}
