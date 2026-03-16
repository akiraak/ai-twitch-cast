using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using Serilog;
using WinNativeApp.Capture;

namespace WinNativeApp.Server;

/// <summary>
/// HTTP + WebSocketサーバー。
/// キャプチャ管理・配信制御・WSL2サーバーとの通信を提供する。
/// </summary>
public class HttpServer : IDisposable
{
    private HttpListener? _listener;
    private readonly CancellationTokenSource _cts = new();
    private readonly int _port;
    private Task? _listenTask;

    // WebSocket接続管理
    private readonly List<WebSocket> _controlClients = new();
    private readonly object _wsLock = new();
    private readonly SemaphoreSlim _wsSendLock = new(1, 1);

    // キャプチャコールバック（MainFormが設定）
    public Func<List<WindowInfo>>? OnListWindows { get; set; }
    public Func<string, int, int, string>? OnStartCapture { get; set; }  // (sourceId, fps, quality) → captureId
    public Func<string, bool>? OnStopCapture { get; set; }
    public Func<List<CaptureInfo>>? OnListCaptures { get; set; }
    public Func<string, byte[]?>? OnGetSnapshot { get; set; }

    // 配信制御コールバック（MainFormが設定）
    public Func<string, string?, Task<object>>? OnStartStream { get; set; }  // (streamKey, serverUrl) → result
    public Func<Task<object>>? OnStopStream { get; set; }
    public Func<object>? OnGetStreamStatus { get; set; }
    public Func<Task<string?>>? OnScreenshot { get; set; }  // → base64 PNG
    public Action? OnQuit { get; set; }

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

                // WebSocketアップグレード判定
                if (context.Request.IsWebSocketRequest)
                {
                    _ = Task.Run(() => HandleWebSocketUpgrade(context, ct));
                }
                else
                {
                    _ = Task.Run(() => HandleRequest(context));
                }
            }
            catch (HttpListenerException) when (ct.IsCancellationRequested) { break; }
            catch (ObjectDisposedException) { break; }
            catch (Exception ex)
            {
                Log.Error(ex, "[HttpServer] Listen error");
            }
        }
    }

    // =====================================================
    // HTTP リクエスト処理
    // =====================================================

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
            // キャプチャ系
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
            else if (path.StartsWith("/stream/") && path != "/stream/start" && path != "/stream/stop" && path != "/stream/status" && method == "GET")
                HandleSnapshot("/snapshot/" + path["/stream/".Length..], res);  // /stream/{id} → /snapshot/{id} 互換
            // 配信制御系
            else if (path == "/stream/start" && method == "POST")
                await HandleStreamStart(req, res);
            else if (path == "/stream/stop" && method == "POST")
                await HandleStreamStop(res);
            else if (path == "/stream/status" && method == "GET")
                await HandleStreamStatus(res);
            else if (path == "/quit" && method == "POST")
                await HandleQuit(res);
            // Phase 7: UIパネルHTML配信
            else if (path == "/panel" && method == "GET")
                await HandlePanel(res);
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
        var streaming = false;
        if (OnGetStreamStatus != null)
        {
            var status = OnGetStreamStatus();
            if (status is IDictionary<string, object> dict)
                streaming = dict.TryGetValue("streaming", out var s) && s is true;
        }
        await WriteJson(res, new
        {
            ok = true,
            captures = captures.Count,
            streaming,
            broadcast_window = true,  // WebView2は常に起動している
            version = "AITwitchCast/1.0"
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

    private async Task HandleStreamStart(HttpListenerRequest req, HttpListenerResponse res)
    {
        using var reader = new StreamReader(req.InputStream);
        var body = await reader.ReadToEndAsync();
        var json = JsonSerializer.Deserialize<JsonElement>(body);

        var streamKey = json.TryGetProperty("streamKey", out var sk) ? sk.GetString() : null;
        var serverUrl = json.TryGetProperty("serverUrl", out var su) ? su.GetString() : null;

        if (OnStartStream == null)
        {
            res.StatusCode = 500;
            await WriteJson(res, new { ok = false, error = "Streaming not available" });
            return;
        }

        var result = await OnStartStream(streamKey ?? "", serverUrl);
        await WriteJson(res, result);
    }

    private async Task HandleStreamStop(HttpListenerResponse res)
    {
        if (OnStopStream == null)
        {
            await WriteJson(res, new { ok = false, error = "Streaming not available" });
            return;
        }
        var result = await OnStopStream();
        await WriteJson(res, result);
    }

    private async Task HandleStreamStatus(HttpListenerResponse res)
    {
        var result = OnGetStreamStatus?.Invoke() ?? new { streaming = false };
        await WriteJson(res, result);
    }

    private async Task HandleQuit(HttpListenerResponse res)
    {
        await WriteJson(res, new { ok = true });
        OnQuit?.Invoke();
    }

    private async Task HandlePanel(HttpListenerResponse res)
    {
        var htmlPath = Path.Combine(AppContext.BaseDirectory, "control-panel.html");
        if (!File.Exists(htmlPath))
        {
            res.StatusCode = 404;
            await WriteJson(res, new { error = "control-panel.html not found" });
            return;
        }
        res.ContentType = "text/html; charset=utf-8";
        var html = await File.ReadAllTextAsync(htmlPath);
        var bytes = Encoding.UTF8.GetBytes(html);
        res.ContentLength64 = bytes.Length;
        await res.OutputStream.WriteAsync(bytes);
        res.Close();
    }

    // =====================================================
    // WebSocket /ws/control
    // =====================================================

    private async Task HandleWebSocketUpgrade(HttpListenerContext context, CancellationToken ct)
    {
        var path = context.Request.Url?.AbsolutePath ?? "";

        if (path != "/ws/control")
        {
            context.Response.StatusCode = 404;
            context.Response.Close();
            return;
        }

        WebSocketContext wsContext;
        try
        {
            wsContext = await context.AcceptWebSocketAsync(null);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[WebSocket] Accept failed");
            context.Response.StatusCode = 500;
            context.Response.Close();
            return;
        }

        var ws = wsContext.WebSocket;
        lock (_wsLock) { _controlClients.Add(ws); }
        Log.Information("[WebSocket] 制御WebSocket接続");

        try
        {
            await HandleControlWebSocket(ws, ct);
        }
        finally
        {
            lock (_wsLock) { _controlClients.Remove(ws); }
            Log.Information("[WebSocket] 制御WebSocket切断");
            try { ws.Dispose(); } catch { }
        }
    }

    private async Task HandleControlWebSocket(WebSocket ws, CancellationToken ct)
    {
        var buffer = new byte[4096];

        while (ws.State == WebSocketState.Open && !ct.IsCancellationRequested)
        {
            WebSocketReceiveResult result;
            using var ms = new MemoryStream();

            try
            {
                do
                {
                    result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "", CancellationToken.None);
                        return;
                    }
                    ms.Write(buffer, 0, result.Count);
                } while (!result.EndOfMessage);
            }
            catch (WebSocketException) { return; }
            catch (OperationCanceledException) { return; }

            if (result.MessageType != WebSocketMessageType.Text) continue;

            var msgText = Encoding.UTF8.GetString(ms.ToArray());
            _ = Task.Run(() => ProcessControlMessage(ws, msgText));
        }
    }

    private async Task ProcessControlMessage(WebSocket ws, string msgText)
    {
        string? requestId = null;
        try
        {
            var msg = JsonSerializer.Deserialize<JsonElement>(msgText);
            requestId = msg.TryGetProperty("requestId", out var rid) ? rid.GetString() : null;
            var action = msg.TryGetProperty("action", out var act) ? act.GetString() ?? "" : "";

            Log.Debug("[WebSocket] Action={Action} RequestId={RequestId}", action, requestId);

            object result = action switch
            {
                "status" => HandleWsStatus(),
                "windows" => HandleWsWindows(),
                "start_capture" => HandleWsStartCapture(msg),
                "stop_capture" => HandleWsStopCapture(msg),
                "captures" => HandleWsCaptures(),
                "start_stream" => await HandleWsStartStream(msg),
                "stop_stream" => await HandleWsStopStream(),
                "stream_status" => HandleWsStreamStatus(),
                "screenshot" => await HandleWsScreenshot(),
                "broadcast_open" => new { ok = true },       // WebView2は常にオープン
                "broadcast_close" => new { ok = true },       // C#では閉じない
                "broadcast_status" => new { open = true },
                "preview_open" => new { ok = true },          // C#にはプレビューウィンドウなし
                "preview_close" => new { ok = true },
                "preview_status" => new { open = false },
                "quit" => HandleWsQuit(),
                _ => new { ok = false, error = $"unknown action: {action}" }
            };

            await SendWsResponse(ws, requestId, result);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "[WebSocket] Error processing action");
            try
            {
                await SendWsResponse(ws, requestId, new { ok = false, error = ex.Message });
            }
            catch { }
        }
    }

    private object HandleWsStatus()
    {
        var captures = OnListCaptures?.Invoke() ?? [];
        var streaming = false;
        if (OnGetStreamStatus != null)
        {
            var status = OnGetStreamStatus();
            if (status is IDictionary<string, object> dict)
                streaming = dict.TryGetValue("streaming", out var s) && s is true;
        }
        return new
        {
            ok = true,
            captures = captures.Count,
            streaming,
            broadcast_window = true,
            version = "AITwitchCast/1.0"
        };
    }

    private object HandleWsWindows()
    {
        var windows = OnListWindows?.Invoke() ?? [];
        return windows.Select(w => new
        {
            id = $"0x{w.Hwnd.ToInt64():X}",
            name = w.Title
        }).ToArray();
    }

    private object HandleWsStartCapture(JsonElement msg)
    {
        var sourceId = msg.TryGetProperty("sourceId", out var sid) ? sid.GetString() ?? "" : "";
        var fps = msg.TryGetProperty("fps", out var f) ? f.GetInt32() : 15;
        var quality = msg.TryGetProperty("quality", out var q) ? (int)(q.GetDouble() * 100) : 70;

        if (OnStartCapture == null)
            return new { ok = false, error = "Capture not available" };

        var id = OnStartCapture(sourceId, fps, quality);
        return new
        {
            ok = true,
            id,
            stream_url = $"http://localhost:{_port}/snapshot/{id}"
        };
    }

    private object HandleWsStopCapture(JsonElement msg)
    {
        var id = msg.TryGetProperty("id", out var idEl) ? idEl.GetString() ?? "" : "";
        var ok = OnStopCapture?.Invoke(id) ?? false;
        return new { ok };
    }

    private object HandleWsCaptures()
    {
        var captures = OnListCaptures?.Invoke() ?? [];
        return captures.Select(c => new
        {
            id = c.Id,
            name = c.Name,
            frames = c.FrameCount,
            has_frame = c.FrameCount > 0
        }).ToArray();
    }

    private async Task<object> HandleWsStartStream(JsonElement msg)
    {
        if (OnStartStream == null)
            return new { ok = false, error = "Streaming not available" };

        var streamKey = msg.TryGetProperty("streamKey", out var sk) ? sk.GetString() : null;
        var serverUrl = msg.TryGetProperty("serverUrl", out var su) ? su.GetString() : null;

        return await OnStartStream(streamKey ?? "", serverUrl);
    }

    private async Task<object> HandleWsStopStream()
    {
        if (OnStopStream == null)
            return new { ok = false, error = "Streaming not available" };
        return await OnStopStream();
    }

    private object HandleWsStreamStatus()
    {
        return OnGetStreamStatus?.Invoke() ?? new { streaming = false };
    }

    private async Task<object> HandleWsScreenshot()
    {
        if (OnScreenshot == null)
            return new { ok = false, error = "Screenshot not available" };

        var png64 = await OnScreenshot();
        if (png64 == null)
            return new { ok = false, error = "Screenshot failed" };

        return new { ok = true, png_base64 = png64, format = "png", source = "broadcast" };
    }

    private object HandleWsQuit()
    {
        // 少し遅延してからアプリ終了（レスポンスを返す時間を確保）
        Task.Delay(500).ContinueWith(_ => OnQuit?.Invoke());
        return new { ok = true };
    }

    private async Task SendWsResponse(WebSocket ws, string? requestId, object result)
    {
        if (ws.State != WebSocketState.Open) return;

        // Electronと同じフォーマット: 配列は {data: [...]}、オブジェクトはそのまま展開
        var response = new Dictionary<string, object?>();
        if (requestId != null)
            response["requestId"] = requestId;

        if (result is Array || result is System.Collections.IEnumerable && result is not string && result is not IDictionary<string, object>)
        {
            response["data"] = result;
        }
        else
        {
            // anonymous objectのプロパティをフラットにマージ
            var jsonStr = JsonSerializer.Serialize(result);
            var props = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(jsonStr);
            if (props != null)
            {
                foreach (var kv in props)
                    response[kv.Key] = kv.Value;
            }
        }

        var json = JsonSerializer.Serialize(response);
        var bytes = Encoding.UTF8.GetBytes(json);
        await _wsSendLock.WaitAsync();
        try
        {
            if (ws.State == WebSocketState.Open)
                await ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, CancellationToken.None);
        }
        finally
        {
            _wsSendLock.Release();
        }
    }

    // =====================================================
    // ヘルパー
    // =====================================================

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
        Log.Information("[HttpServer] Dispose: cancelling...");
        _cts.Cancel();
        // WebSocket接続をクローズ
        Log.Information("[HttpServer] Dispose: closing {Count} WebSocket(s)...", _controlClients.Count);
        lock (_wsLock)
        {
            foreach (var ws in _controlClients)
            {
                try
                {
                    using var wsCts = new CancellationTokenSource(1000);
                    ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "Server shutdown", wsCts.Token).Wait(1500);
                }
                catch { }
                // CloseAsyncがハングする場合に備えてAbortで強制切断
                try { ws.Abort(); } catch { }
            }
            _controlClients.Clear();
        }
        Log.Information("[HttpServer] Dispose: stopping listener...");
        try { _listener?.Stop(); } catch { }
        try { _listener?.Close(); } catch { }
        // ListenLoopタスクの完了を待つ（最大2秒）
        Log.Information("[HttpServer] Dispose: waiting for listenTask...");
        try { _listenTask?.Wait(2000); } catch { }
        Log.Information("[HttpServer] Dispose: done");
    }
}
