using Serilog;

namespace WinNativeApp.Streaming;

/// <summary>
/// TTS WAVバイナリをFFmpeg用PCM（48kHz stereo f32le）に変換する。
/// 入力: 24kHz mono 16bit WAV（Gemini TTS出力）
/// 出力: 48kHz stereo f32le PCM byte[]（WASAPIフォーマットと一致）
/// </summary>
public static class TtsDecoder
{
    /// <summary>
    /// WAVバイナリをデコード・リサンプルし、音量適用済みのf32le PCMを返す。
    /// </summary>
    /// <param name="wavData">WAVファイルのバイト配列</param>
    /// <param name="volume">適用する音量（0.0〜4.0、perceptualGain適用済みの値）</param>
    /// <returns>48kHz stereo f32le PCMバイト配列</returns>
    public static byte[] DecodeWav(byte[] wavData, float volume = 1.0f)
    {
        if (wavData.Length < 44)
            throw new ArgumentException("WAV data too short");

        // "RIFF" check
        if (wavData[0] != 'R' || wavData[1] != 'I' || wavData[2] != 'F' || wavData[3] != 'F')
            throw new ArgumentException("Not a WAV file");

        // WAVヘッダーからフォーマット情報取得
        int channels = BitConverter.ToInt16(wavData, 22);
        int sampleRate = BitConverter.ToInt32(wavData, 24);
        int bitsPerSample = BitConverter.ToInt16(wavData, 34);

        // "data"チャンクを検索（fmtチャンクサイズが可変のため固定オフセットは不可）
        int dataOffset = -1;
        int dataSize = 0;
        for (int i = 12; i < wavData.Length - 8; i++)
        {
            if (wavData[i] == 'd' && wavData[i + 1] == 'a' && wavData[i + 2] == 't' && wavData[i + 3] == 'a')
            {
                dataSize = BitConverter.ToInt32(wavData, i + 4);
                dataOffset = i + 8;
                break;
            }
        }

        if (dataOffset < 0)
            throw new ArgumentException("No data chunk found in WAV");

        // データサイズをファイル実サイズでクランプ
        dataSize = Math.Min(dataSize, wavData.Length - dataOffset);

        Log.Debug("[TtsDecoder] WAV: {Ch}ch {Rate}Hz {Bits}bit, data={Size} bytes",
            channels, sampleRate, bitsPerSample, dataSize);

        int bytesPerSample = bitsPerSample / 8;
        int numSamples = dataSize / (bytesPerSample * channels);

        // リサンプル比率: 24kHz→48kHz = 2x
        const int OutputRate = 48000;
        int resampleRatio = OutputRate / sampleRate;
        if (sampleRate * resampleRatio != OutputRate)
        {
            resampleRatio = Math.Max(1, (int)Math.Round((double)OutputRate / sampleRate));
            Log.Warning("[TtsDecoder] Non-integer resample: {In}→{Out}Hz, ratio={Ratio}x",
                sampleRate, OutputRate, resampleRatio);
        }

        // 出力: 48kHz stereo f32le
        int outputSamples = numSamples * resampleRatio;
        int outputBytes = outputSamples * 2 * 4; // stereo × f32le(4bytes)
        var output = new byte[outputBytes];

        int srcPos = dataOffset;
        int dstPos = 0;

        for (int i = 0; i < numSamples && srcPos + bytesPerSample * channels <= wavData.Length; i++)
        {
            // 入力サンプル読み取り（monoの場合は1サンプル、stereoの場合は左チャンネル）
            float sample;
            if (bitsPerSample == 16)
            {
                short s16 = BitConverter.ToInt16(wavData, srcPos);
                sample = s16 / 32768.0f;
            }
            else if (bitsPerSample == 32)
            {
                sample = BitConverter.ToSingle(wavData, srcPos);
            }
            else
            {
                sample = 0;
            }
            srcPos += bytesPerSample * channels;

            // 音量適用 + クリッピング防止
            sample *= volume;
            sample = Math.Clamp(sample, -1.0f, 1.0f);

            // リサンプル×ステレオ化して書き込み
            for (int r = 0; r < resampleRatio && dstPos + 8 <= output.Length; r++)
            {
                BitConverter.TryWriteBytes(output.AsSpan(dstPos), sample);       // L
                BitConverter.TryWriteBytes(output.AsSpan(dstPos + 4), sample);   // R
                dstPos += 8;
            }
        }

        Log.Information("[TtsDecoder] {InSamples} samples → {OutBytes} bytes ({Dur:F1}s), vol={Vol:F2}",
            numSamples, dstPos, (double)numSamples / sampleRate, volume);

        return output;
    }
}
