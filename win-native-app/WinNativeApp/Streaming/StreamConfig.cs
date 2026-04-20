namespace WinNativeApp.Streaming;

public enum OutputMode
{
    Rtmp,
    File,
}

/// <summary>
/// パイプライン状態。配信・録画・アップロードを排他管理する。
/// Uploading中は録画中のファイルをサーバへ送出中で、次の録画・配信は両方ブロックされる。
/// </summary>
public enum PipelineState
{
    Standby,
    Streaming,
    Recording,
    Uploading,
}

public class StreamConfig
{
    public int Width { get; set; } = 1280;
    public int Height { get; set; } = 720;
    public int Framerate { get; set; } = 30;
    public string VideoBitrate { get; set; } = "2500k";
    public string AudioBitrate { get; set; } = "128k";
    public string Preset { get; set; } = "ultrafast";
    /// <summary>
    /// 映像エンコーダ。"auto"=HWエンコーダ自動検出→フォールバックlibx264、
    /// "libx264"=CPU、"h264_nvenc"=NVIDIA、"h264_amf"=AMD、"h264_qsv"=Intel
    /// </summary>
    public string Encoder { get; set; } = "auto";
    public string? StreamKey { get; set; }
    public string RtmpUrl { get; set; } = "rtmp://live-tyo.twitch.tv/app";
    public string? FfmpegPath { get; set; }

    public OutputMode Mode { get; set; } = OutputMode.Rtmp;
    public string? OutputPath { get; set; }

    /// <summary>
    /// 音声タイムスタンプのオフセット（秒）。音声パイプライン遅延を補正する。
    /// 負の値=音声を早める。環境のオーディオドライバやエンコーダに依存するため調整可能。
    /// デフォルト: 0（B2 で _audioQueue 上限を 100ms に絞ったため、-itsoffset は一旦無効化して
    /// 単独効果を測定する。残差があれば --audio-offset で微調整。plans/recording-av-sync-fix.md）
    /// </summary>
    public double AudioOffset { get; set; } = 0;

    /// <summary>
    /// CLI args優先、環境変数フォールバック。
    /// </summary>
    public static StreamConfig FromArgs(string[] args)
    {
        var config = new StreamConfig();

        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--stream-key" when i + 1 < args.Length:
                    config.StreamKey = args[++i];
                    break;
                case "--resolution" when i + 1 < args.Length:
                    ParseResolution(args[++i], config);
                    break;
                case "--fps" when i + 1 < args.Length:
                    if (int.TryParse(args[++i], out var fps))
                        config.Framerate = fps;
                    break;
                case "--bitrate" when i + 1 < args.Length:
                    config.VideoBitrate = args[++i];
                    break;
                case "--ffmpeg-path" when i + 1 < args.Length:
                    config.FfmpegPath = args[++i];
                    break;
                case "--rtmp-url" when i + 1 < args.Length:
                    config.RtmpUrl = args[++i];
                    break;
                case "--encoder" when i + 1 < args.Length:
                    config.Encoder = args[++i];
                    break;
                case "--audio-offset" when i + 1 < args.Length:
                    if (double.TryParse(args[++i], System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out var offset))
                        config.AudioOffset = offset;
                    break;
            }
        }

        // 環境変数フォールバック
        config.StreamKey ??= Environment.GetEnvironmentVariable("STREAM_KEY")
                          ?? Environment.GetEnvironmentVariable("TWITCH_STREAM_KEY");

        if (config.FfmpegPath == null)
            config.FfmpegPath = Environment.GetEnvironmentVariable("FFMPEG_PATH");

        var audioOffsetEnv = Environment.GetEnvironmentVariable("AUDIO_OFFSET");
        if (audioOffsetEnv != null && double.TryParse(audioOffsetEnv,
            System.Globalization.NumberStyles.Float,
            System.Globalization.CultureInfo.InvariantCulture, out var envOffset))
            config.AudioOffset = envOffset;

        return config;
    }

    private static void ParseResolution(string value, StreamConfig config)
    {
        if (value.Contains('x'))
        {
            var parts = value.Split('x');
            if (int.TryParse(parts[0], out var w) && int.TryParse(parts[1], out var h))
            {
                config.Width = w;
                config.Height = h;
            }
        }
    }
}
