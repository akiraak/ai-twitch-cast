// PocLoopback — 録画 AV 同期の別アプローチ PoC（plans/recording-screen-capture-alternative.md Step 0）
//
// 仮説: 「アプリで再生しているだけ（録画も配信もしていない状態）は、画面と
//        スピーカーの音はズレない」。
//        ならば WGC（画面）＋ WASAPI Loopback（スピーカー出力）を別パイプで
//        FFmpeg に流し、両方に -use_wallclock_as_timestamps 1 を付けて wall clock
//        で打刻すれば、自前ミキサー無し・バイトベース PTS 無しで AV が揃うはず。
//
// 使い方（Windows 側で実行）:
//   1. WinNativeApp を別途起動して、適当な TTS / BGM を再生する状態にしておく
//      （WinNativeApp の WaveOutEvent はそのまま既定スピーカーへ出ている）
//   2. WinNativeApp を一度 dotnet build して resources\ffmpeg\ffmpeg.exe を取得
//      （PoC は WinNativeApp と同じ ffmpeg.exe を使う想定）
//   3. dotnet run --project win-native-app\PocLoopback -- ^
//        --window "WinNativeApp" ^
//        --output debug-ss\poc_loopback.mp4 ^
//        --duration 60
//
// 合格判定（plans/recording-screen-capture-alternative.md Step 0 §合格基準）:
//   1. VLC 目視で口パクと音声のズレが ≦ 33ms（フレーム単位）
//   2. 30 秒間でブツブツ・音切れ 0 回
//   3. 音声 PTS と映像 PTS の差が ±100ms 以内
//      ↓ 計測コマンド例（出力後に手動で叩く）:
//      ffprobe -hide_banner -show_packets -select_streams v -of csv ^
//        debug-ss\poc_loopback.mp4 > video_packets.csv
//      ffprobe -hide_banner -show_packets -select_streams a -of csv ^
//        debug-ss\poc_loopback.mp4 > audio_packets.csv
//      （pts_time 列を時系列で比較。最初の音声 pts_time と映像 pts_time の差を見る）
//   4. 30 分長尺ドリフト累積無し（PoC は 60〜90 秒で十分）

using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using PocLoopback;

const int DefaultDurationSec = 60;
const int DefaultFps = 30;

string? windowTitle = null;
IntPtr explicitHwnd = IntPtr.Zero;
string outputPath = "poc_loopback.mp4";
int durationSec = DefaultDurationSec;
int fps = DefaultFps;
string? ffmpegPath = null;

for (int i = 0; i < args.Length; i++)
{
    switch (args[i])
    {
        case "--window" when i + 1 < args.Length: windowTitle = args[++i]; break;
        case "--hwnd" when i + 1 < args.Length:
            // 0xFFFF... 形式と 10 進数の両方を受ける（WinNativeApp 本体から子プロセスで起動するときに使う）
            var hv = args[++i];
            if (hv.StartsWith("0x", StringComparison.OrdinalIgnoreCase))
                explicitHwnd = new IntPtr(long.Parse(hv[2..], System.Globalization.NumberStyles.HexNumber));
            else
                explicitHwnd = new IntPtr(long.Parse(hv));
            break;
        case "--output" when i + 1 < args.Length: outputPath = args[++i]; break;
        case "--duration" when i + 1 < args.Length: durationSec = int.Parse(args[++i]); break;
        case "--fps" when i + 1 < args.Length: fps = int.Parse(args[++i]); break;
        case "--ffmpeg" when i + 1 < args.Length: ffmpegPath = args[++i]; break;
        case "-h" or "--help":
            PrintUsage();
            return 0;
        default:
            Console.Error.WriteLine($"Unknown arg: {args[i]}");
            PrintUsage();
            return 2;
    }
}

if (explicitHwnd == IntPtr.Zero && string.IsNullOrWhiteSpace(windowTitle))
{
    Console.Error.WriteLine("--window <substring> または --hwnd <HWND> のいずれかが必要です");
    PrintUsage();
    return 2;
}

ffmpegPath = ResolveFfmpeg(ffmpegPath);
if (!File.Exists(ffmpegPath))
{
    Console.Error.WriteLine($"ffmpeg not found: {ffmpegPath}");
    return 2;
}

IntPtr hwnd;
if (explicitHwnd != IntPtr.Zero)
{
    hwnd = explicitHwnd;
    Console.WriteLine($"[Main] Target HWND=0x{hwnd:X} (from --hwnd)");
}
else
{
    hwnd = FindWindowByTitle(windowTitle!);
    if (hwnd == IntPtr.Zero)
    {
        Console.Error.WriteLine($"Window not found (substring='{windowTitle}'). Visible windows:");
        foreach (var t in EnumerateVisibleTitles()) Console.Error.WriteLine($"  - {t}");
        return 3;
    }
    Console.WriteLine($"[Main] Target HWND=0x{hwnd:X} (substring='{windowTitle}')");
}

using var screen = new ScreenCapture();
using var loopback = new LoopbackCapture();
FfmpegRunner? ffmpeg = null;

// Ctrl+C: グレースフル終了
using var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) =>
{
    e.Cancel = true;
    Console.WriteLine("[Main] Ctrl+C received, stopping...");
    cts.Cancel();
};

// stdin に "stop" 一行 (または EOF) が来たらグレースフル終了。
// WinNativeApp 本体から子プロセス起動して制御するための入口
// （plans/recording-screen-capture-alternative.md Step 4: 同プロセス WGC で
// broadcast.html の更新が掴めない症状の回避策として別プロセス化）。
_ = Task.Run(() =>
{
    try
    {
        while (!cts.IsCancellationRequested)
        {
            var line = Console.In.ReadLine();
            if (line == null)
            {
                Console.WriteLine("[Main] stdin EOF, stopping...");
                cts.Cancel();
                return;
            }
            if (line.Trim().Equals("stop", StringComparison.OrdinalIgnoreCase))
            {
                Console.WriteLine("[Main] stdin 'stop' received, stopping...");
                cts.Cancel();
                return;
            }
        }
    }
    catch (Exception ex)
    {
        Console.Error.WriteLine($"[Main] stdin reader error: {ex.Message}");
    }
});

// 1) 画面キャプチャ開始（最初のフレームでサイズ確定 → FFmpeg 起動）
var firstFrame = new TaskCompletionSource<(int w, int h)>(
    TaskCreationOptions.RunContinuationsAsynchronously);
screen.OnFrame = (_, w, h) => firstFrame.TrySetResult((w, h));
screen.Start(hwnd);
Console.WriteLine("[Main] Screen capture started, waiting for first frame...");

(int w, int h) size;
try
{
    size = await firstFrame.Task.WaitAsync(TimeSpan.FromSeconds(5), cts.Token);
}
catch (TimeoutException)
{
    Console.Error.WriteLine("[Main] Timed out waiting for first frame from WGC");
    return 4;
}
Console.WriteLine($"[Main] First frame size: {size.w}x{size.h}");

// 2) Loopback 開始（OnAudio はまだ未設定 → 廃棄される）→ Format 確定
loopback.Start();
var audioFormat = loopback.Format
    ?? throw new InvalidOperationException("LoopbackCapture.Format is null after Start");

// 3) FFmpeg 起動
ffmpeg = new FfmpegRunner(ffmpegPath, outputPath, size.w, size.h, fps, audioFormat);
await ffmpeg.StartAsync(cts.Token);

// 4) コールバック差し替え → 録画パイプへ流し始める
screen.OnFrame = (bgra, w, h) => ffmpeg.WriteVideoFrame(bgra, w, h);
loopback.OnAudio = (data, count) => ffmpeg.WriteAudio(data, count);
Console.WriteLine($"[Main] Recording to {outputPath} for {durationSec}s ...");

// 5) 指定秒待機 + 簡易進捗
var sw = Stopwatch.StartNew();
try
{
    while (sw.Elapsed.TotalSeconds < durationSec && !cts.IsCancellationRequested)
    {
        await Task.Delay(TimeSpan.FromSeconds(5), cts.Token);
        Console.WriteLine($"[Main] t={sw.Elapsed.TotalSeconds:F1}s | " +
            $"video frames={ffmpeg.VideoFrames} bytes={ffmpeg.VideoBytes} | " +
            $"audio bytes={ffmpeg.AudioBytes} ({loopback.BytesCaptured} captured)");
    }
}
catch (OperationCanceledException) { }

// 6) 停止（順序: source → ffmpeg）
Console.WriteLine("[Main] Stopping...");
screen.Stop();
loopback.Stop();
await ffmpeg.StopAsync();

Console.WriteLine($"[Main] Done. Output: {outputPath}");
Console.WriteLine($"[Main] === summary === " +
    $"duration={sw.Elapsed.TotalSeconds:F1}s " +
    $"video_frames={ffmpeg.VideoFrames} " +
    $"video_bytes={ffmpeg.VideoBytes} " +
    $"audio_bytes={ffmpeg.AudioBytes} " +
    $"loopback_captured={loopback.BytesCaptured}");
Console.WriteLine("[Main] 合格判定: VLC 目視 + ffprobe -show_packets でPTS差を確認");
return 0;


// ----- helpers -----

static void PrintUsage()
{
    Console.Error.WriteLine(
        """
        PocLoopback — WGC + WASAPI Loopback の AV 同期 PoC
        Usage:
          PocLoopback --window <title-substring> [--output <path.mp4>]
                      [--duration <sec>] [--fps <n>] [--ffmpeg <path>]
        Defaults:
          --output  poc_loopback.mp4
          --duration 60
          --fps 30
          --ffmpeg auto (PATH or ../WinNativeApp/...resources/ffmpeg/ffmpeg.exe)
        """);
}

static string ResolveFfmpeg(string? supplied)
{
    if (!string.IsNullOrEmpty(supplied)) return supplied;

    // 1) PocLoopback の出力ディレクトリ近辺を探索
    var baseDir = AppContext.BaseDirectory;
    var candidates = new[]
    {
        // bin/Debug/net8.0-... → ../../../../WinNativeApp/bin/Debug/net8.0-...
        Path.Combine(baseDir, "..", "..", "..", "..", "WinNativeApp",
            "bin", "Debug", "net8.0-windows10.0.22621.0", "resources", "ffmpeg", "ffmpeg.exe"),
        Path.Combine(baseDir, "..", "..", "..", "..", "WinNativeApp",
            "bin", "Release", "net8.0-windows10.0.22621.0", "resources", "ffmpeg", "ffmpeg.exe"),
        Path.Combine(baseDir, "..", "..", "..", "..", "WinNativeApp",
            "resources", "ffmpeg", "ffmpeg.exe"),
        Path.Combine(baseDir, "ffmpeg.exe"),
    };
    foreach (var c in candidates)
    {
        var full = Path.GetFullPath(c);
        if (File.Exists(full)) return full;
    }
    return "ffmpeg.exe"; // PATH fallback
}

static IntPtr FindWindowByTitle(string substring)
{
    IntPtr found = IntPtr.Zero;
    NativeMethods.EnumWindows((hwnd, _) =>
    {
        if (!NativeMethods.IsWindowVisible(hwnd)) return true;
        var len = NativeMethods.GetWindowTextLength(hwnd);
        if (len == 0) return true;
        var sb = new StringBuilder(len + 1);
        NativeMethods.GetWindowText(hwnd, sb, sb.Capacity);
        var title = sb.ToString();
        if (title.Contains(substring, StringComparison.OrdinalIgnoreCase))
        {
            found = hwnd;
            return false;
        }
        return true;
    }, IntPtr.Zero);
    return found;
}

static IEnumerable<string> EnumerateVisibleTitles()
{
    var list = new List<string>();
    NativeMethods.EnumWindows((hwnd, _) =>
    {
        if (!NativeMethods.IsWindowVisible(hwnd)) return true;
        var len = NativeMethods.GetWindowTextLength(hwnd);
        if (len == 0) return true;
        var sb = new StringBuilder(len + 1);
        NativeMethods.GetWindowText(hwnd, sb, sb.Capacity);
        var title = sb.ToString();
        if (!string.IsNullOrWhiteSpace(title)) list.Add(title);
        return true;
    }, IntPtr.Zero);
    return list;
}

// 型宣言（delegate 含む）はトップレベル文の後ろに置く必要がある（CS8803）
internal static class NativeMethods
{
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
}
