namespace WinNativeApp.Streaming;

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
            }
        }

        // 環境変数フォールバック
        config.StreamKey ??= Environment.GetEnvironmentVariable("STREAM_KEY")
                          ?? Environment.GetEnvironmentVariable("TWITCH_STREAM_KEY");

        if (config.FfmpegPath == null)
            config.FfmpegPath = Environment.GetEnvironmentVariable("FFMPEG_PATH");

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
