using System.Net;
using System.Text;
using System.Text.Json;
using Serilog;
using WinNativeApp.Capture;

namespace WinNativeApp.Server;

/// <summary>
/// キャプチャ管理用HTTPサーバー。
/// ウィンドウ一覧・キャプチャ開始/停止・スナップショット取得のAPIを提供する。
/// </summary>
public class HttpServer : IDisposable
{
    private HttpListener? _listener;
    private readonly CancellationTokenSource _cts = new();
    private readonly int _port;
    private Task? _listenTask;

    // コールバック（MainFormが設定）
    public Func<List<WindowInfo>>? OnListWindows { get; set; }
    public Func<string, int, int, string>? OnStartCapture { get; set; }  // (sourceId, fps, quality) → captureId
    public Func<string, bool>? OnStopCapture { get; set; }
    public Func<List<CaptureInfo>>? OnListCaptures { get; set; }
    public Func<string, byte[]?>? OnGetSnapshot { get; set; }

    public int Port => _port;

    public HttpServer(int port = 9090)
    {
        _port = port;
    }

    public void Start()
    {
        _listener = CreateListener();
        _listenTask = Task.Run(() => ListenLoop(_cts.Token));
    }

    private HttpListener CreateListener()
    {
        // 全インターフェース接続を試行（admin権限 or URL予約が必要）
        try
        {
            var listener = new HttpListener();
            listener.Prefixes.Add($"http://*:{_port}/");
            listener.Start();
            Log.Information("[HttpServer] Listening on *:{Port}", _port);
            return listener;
        }
        catch (HttpListenerException)
        {
            Log.Debug("[HttpServer] Cannot bind to *, falling back to localhost");
        }

        // localhost のみ（admin不要）
        var fallback = new HttpListener();
        fallback.Prefixes.Add($"http://localhost:{_port}/");
        fallback.Start();
        Log.Warning("[HttpServer] Listening on localhost:{Port} only (admin needed for external access)", _port);
        return fallback;
    }

    private async Task ListenLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var context = await _listener!.GetContextAsync();
                _ = Task.Run(() => HandleRequest(context));
            }
            catch (HttpListenerException) when (ct.IsCancellationRequested) { break; }
            catch (ObjectDisposedException) { break; }
            catch (Exception ex)
            {
                Log.Error(ex, "[HttpServer] Listen error");
            }
        }
    }

    private async Task HandleRequest(HttpListenerContext context)
    {
        var req = context.Request;
        var res = context.Response;
        var path = req.Url?.AbsolutePath ?? "/";
        var method = req.HttpMethod;

        // CORS
        res.AddHeader("Access-Control-Allow-Origin", "*");
        res.AddHeader("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
        res.AddHeader("Access-Control-Allow-Headers", "Content-Type");

        if (method == "OPTIONS")
        {
            res.StatusCode = 204;
            res.Close();
            return;
        }

        try
        {
            if (path == "/status" && method == "GET")
                await HandleStatus(res);
            else if (path == "/windows" && method == "GET")
                await HandleListWindows(res);
            else if (path == "/capture" && method == "POST")
                await HandleStartCapture(req, res);
            else if (path.StartsWith("/capture/") && method == "DELETE")
                await HandleStopCapture(path, res);
            else if (path == "/captures" && method == "GET")
                await HandleListCaptures(res);
            else if (path.StartsWith("/snapshot/") && method == "GET")
                HandleSnapshot(path, res);
            else
            {
                res.StatusCode = 404;
                await WriteJson(res, new { error = "Not found" });
            }
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[HttpServer] {Method} {Path}", method, path);
            try
            {
                res.StatusCode = 500;
                await WriteJson(res, new { error = ex.Message });
            }
            catch { /* response already sent */ }
        }
    }

    private async Task HandleStatus(HttpListenerResponse res)
    {
        var captures = OnListCaptures?.Invoke() ?? [];
        await WriteJson(res, new
        {
            ok = true,
            captures = captures.Count,
            version = "WinNativeApp/1.0"
        });
    }

    private async Task HandleListWindows(HttpListenerResponse res)
    {
        var windows = OnListWindows?.Invoke() ?? [];
        var list = windows.Select(w => new
        {
            id = $"0x{w.Hwnd.ToInt64():X}",
            name = w.Title
        });
        await WriteJson(res, list);
    }

    private async Task HandleStartCapture(HttpListenerRequest req, HttpListenerResponse res)
    {
        using var reader = new StreamReader(req.InputStream);
        var body = await reader.ReadToEndAsync();
        var json = JsonSerializer.Deserialize<JsonElement>(body);

        var sourceId = json.GetProperty("sourceId").GetString() ?? "";
        var fps = json.TryGetProperty("fps", out var fpsEl) ? fpsEl.GetInt32() : 15;
        var quality = json.TryGetProperty("quality", out var qEl)
            ? (int)(qEl.GetDouble() * 100) : 70;

        if (OnStartCapture == null)
        {
            res.StatusCode = 500;
            await WriteJson(res, new { error = "Capture not available" });
            return;
        }

        try
        {
            var id = OnStartCapture(sourceId, fps, quality);
            await WriteJson(res, new
            {
                ok = true,
                id,
                stream_url = $"http://localhost:{_port}/snapshot/{id}"
            });
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[HttpServer] StartCapture failed: sourceId={SourceId}", sourceId);
            res.StatusCode = 400;
            await WriteJson(res, new { error = ex.Message });
        }
    }

    private async Task HandleStopCapture(string path, HttpListenerResponse res)
    {
        var id = path["/capture/".Length..];
        var ok = OnStopCapture?.Invoke(id) ?? false;
        if (!ok)
        {
            res.StatusCode = 404;
            await WriteJson(res, new { error = "Capture not found" });
            return;
        }
        await WriteJson(res, new { ok = true });
    }

    private async Task HandleListCaptures(HttpListenerResponse res)
    {
        var captures = OnListCaptures?.Invoke() ?? [];
        var list = captures.Select(c => new { id = c.Id, name = c.Name, frames = c.FrameCount });
        await WriteJson(res, list);
    }

    private void HandleSnapshot(string path, HttpListenerResponse res)
    {
        var id = path["/snapshot/".Length..];
        var jpeg = OnGetSnapshot?.Invoke(id);
        if (jpeg == null)
        {
            res.StatusCode = 404;
            res.Close();
            return;
        }

        res.ContentType = "image/jpeg";
        res.ContentLength64 = jpeg.Length;
        res.OutputStream.Write(jpeg, 0, jpeg.Length);
        res.Close();
    }

    private static async Task WriteJson(HttpListenerResponse res, object data)
    {
        res.ContentType = "application/json";
        var json = JsonSerializer.Serialize(data);
        var bytes = Encoding.UTF8.GetBytes(json);
        res.ContentLength64 = bytes.Length;
        await res.OutputStream.WriteAsync(bytes);
        res.Close();
    }

    public void Dispose()
    {
        _cts.Cancel();
        try { _listener?.Stop(); } catch { }
        try { _listener?.Close(); } catch { }
    }
}
