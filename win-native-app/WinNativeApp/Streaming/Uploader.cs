using Serilog;

namespace WinNativeApp.Streaming;

/// <summary>
/// 録画ファイルをPythonサーバへストリーミングアップロードするユーティリティ。
/// 進捗は <see cref="BytesSent"/> / <see cref="BytesTotal"/> でポーリング取得できる。
/// 成功時はローカル側に .uploaded マーカーを作る（7日gc の判定用）。
/// </summary>
public sealed class Uploader
{
    private static readonly HttpClient _http = new() { Timeout = TimeSpan.FromHours(2) };

    public string FilePath { get; }
    public string ServerBaseUrl { get; }
    public long BytesTotal { get; }
    public long BytesSent => Interlocked.Read(ref _bytesSent);
    public bool IsRunning => _running;
    public string? LastError { get; private set; }
    public DateTime? CompletedAt { get; private set; }

    private long _bytesSent;
    private volatile bool _running;

    public Uploader(string filePath, string serverBaseUrl)
    {
        FilePath = filePath;
        ServerBaseUrl = serverBaseUrl.TrimEnd('/');
        BytesTotal = new FileInfo(filePath).Length;
    }

    /// <summary>
    /// アップロードを実行する。成功時は <c>.uploaded</c> マーカーファイルを作る。
    /// 失敗時は <see cref="LastError"/> に理由が入る。
    /// </summary>
    public async Task<bool> UploadAsync(CancellationToken ct = default)
    {
        if (_running) throw new InvalidOperationException("Upload already running");
        _running = true;
        LastError = null;
        Interlocked.Exchange(ref _bytesSent, 0);

        try
        {
            var filename = Path.GetFileName(FilePath);
            var url = $"{ServerBaseUrl}/api/recordings/upload";

            Log.Information("[Upload] Start: {Path} ({Size} bytes) → {Url}",
                FilePath, BytesTotal, url);

            await using var fs = new FileStream(FilePath, FileMode.Open, FileAccess.Read,
                FileShare.Read, bufferSize: 1024 * 1024, useAsync: true);
            using var progressStream = new ProgressReadStream(fs, n => Interlocked.Add(ref _bytesSent, n));
            using var content = new StreamContent(progressStream, bufferSize: 1024 * 1024)
            {
                Headers = { ContentLength = BytesTotal },
            };
            content.Headers.ContentType =
                new System.Net.Http.Headers.MediaTypeHeaderValue("application/octet-stream");

            using var request = new HttpRequestMessage(HttpMethod.Post, url) { Content = content };
            request.Headers.Add("X-Filename", filename);

            using var response = await _http.SendAsync(
                request, HttpCompletionOption.ResponseHeadersRead, ct);
            var body = await response.Content.ReadAsStringAsync(ct);

            if (!response.IsSuccessStatusCode)
            {
                LastError = $"HTTP {(int)response.StatusCode}: {body}";
                Log.Error("[Upload] Failed: {Err}", LastError);
                return false;
            }

            // 成功 → .uploaded マーカーを作る（7日gc の判定用）
            try
            {
                await File.WriteAllTextAsync(FilePath + ".uploaded",
                    DateTime.UtcNow.ToString("o"), ct);
            }
            catch (Exception ex)
            {
                Log.Warning("[Upload] Failed to write .uploaded marker: {Msg}", ex.Message);
            }

            CompletedAt = DateTime.UtcNow;
            Log.Information("[Upload] Success: {File} ({Bytes} bytes)", filename, BytesTotal);
            return true;
        }
        catch (Exception ex)
        {
            LastError = ex.Message;
            Log.Error(ex, "[Upload] Exception");
            return false;
        }
        finally
        {
            _running = false;
        }
    }

    /// <summary>
    /// ローカル一時領域を走査し、.uploaded マーカー付きで mtime が retentionDays 日以上前の
    /// MP4ファイル本体＋マーカーを削除する。マーカーがないファイル（未アップロード扱い）は削除しない。
    /// </summary>
    public static int GarbageCollect(string recordingsDir, int retentionDays)
    {
        if (!Directory.Exists(recordingsDir)) return 0;
        var cutoff = DateTime.UtcNow.AddDays(-retentionDays);
        int removed = 0;
        foreach (var markerPath in Directory.EnumerateFiles(recordingsDir, "*.mp4.uploaded"))
        {
            try
            {
                var mp4Path = markerPath[..^".uploaded".Length];
                var info = File.Exists(mp4Path) ? new FileInfo(mp4Path) : null;
                if (info != null && info.LastWriteTimeUtc < cutoff)
                {
                    File.Delete(mp4Path);
                    File.Delete(markerPath);
                    removed++;
                    Log.Information("[Upload/GC] Removed old recording: {Path}", mp4Path);
                }
                else if (info == null)
                {
                    // マーカーだけ残っている → 掃除
                    File.Delete(markerPath);
                }
            }
            catch (Exception ex)
            {
                Log.Warning("[Upload/GC] Failed for {Path}: {Msg}", markerPath, ex.Message);
            }
        }
        return removed;
    }
}

/// <summary>
/// 読み取りバイト数をコールバックに通知するReadStreamラッパー。
/// アップロード進捗表示のため BytesSent を累積する用途。
/// </summary>
internal sealed class ProgressReadStream : Stream
{
    private readonly Stream _inner;
    private readonly Action<int> _onRead;

    public ProgressReadStream(Stream inner, Action<int> onRead)
    {
        _inner = inner;
        _onRead = onRead;
    }

    public override bool CanRead => _inner.CanRead;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => _inner.Length;
    public override long Position
    {
        get => _inner.Position;
        set => throw new NotSupportedException();
    }

    public override int Read(byte[] buffer, int offset, int count)
    {
        int n = _inner.Read(buffer, offset, count);
        if (n > 0) _onRead(n);
        return n;
    }

    public override async Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken ct)
    {
        int n = await _inner.ReadAsync(buffer.AsMemory(offset, count), ct);
        if (n > 0) _onRead(n);
        return n;
    }

    public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
    {
        int n = await _inner.ReadAsync(buffer, ct);
        if (n > 0) _onRead(n);
        return n;
    }

    public override void Flush() => _inner.Flush();
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

    protected override void Dispose(bool disposing)
    {
        if (disposing) _inner.Dispose();
        base.Dispose(disposing);
    }
}
