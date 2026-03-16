# プロセス終了しない問題の修正プラン

## 背景

閉じるボタンを押してもWinNativeApp.exeプロセスが残り続けることがある。`./stream.sh --stop`（`taskkill /F`）では消える。

## 根本原因分析

### 原因1: HttpServer.ListenLoop が終了しない（最重要）

`HttpServer.Dispose()` で `_cts.Cancel()` → `_listener.Stop()` しているが、`_listenTask` の完了を待っていない。`GetContextAsync()` がブロックされたままになる場合があり、そのバックグラウンドTaskが生き続けてプロセス終了を阻害する。

**場所**: `Server/HttpServer.cs` L77-102, L621-636

### 原因2: OnFormClosing の async void + Close() 再帰

`OnFormClosing` が `async void` で、`e.Cancel = true` → `await StopStreamingAsync()` → `Close()` という流れ。2回目の `Close()` で再度 `OnFormClosing` が呼ばれるが、`_closing = true` の分岐で `CleanupResources()` を呼んだ後、`e.Cancel` がデフォルト `false` のままなのでフォームは閉じる。ここ自体は正しいが、`StopStreamingAsync()` が例外を投げた場合や `await` がデッドロックした場合にプロセスが残る。

**場所**: `MainForm.cs` L958-1003

### 原因3: FfmpegProcess.LogStderrAsync がブロック

`ReadLineAsync()` がFFmpegプロセス終了後もブロックし続ける可能性。CancellationToken無し。

**場所**: `Streaming/FfmpegProcess.cs` L304-322

### 原因4: FfmpegProcess.StopAsync の Kill() 後に WaitForExit なし

`Kill()` 呼び出し後、実際にプロセスが終了するのを待たずに `Dispose()` している。

**場所**: `Streaming/FfmpegProcess.cs` L262-302

### 原因5: 最終手段の Environment.Exit がない

全てのクリーンアップが失敗した場合に、プロセスを強制終了する手段がない。

## 修正方針

**安全に終了させることを最優先。** タイムアウト付きで各リソースを順次停止し、最終的に `Environment.Exit()` でプロセスを確実に終了させる。

## 実装ステップ

### Step 1: HttpServer.Dispose に _listenTask 待機を追加

```csharp
public void Dispose()
{
    _cts.Cancel();
    // WebSocket接続をクローズ
    lock (_wsLock)
    {
        foreach (var ws in _controlClients)
        {
            try { ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "Server shutdown", CancellationToken.None).Wait(1000); }
            catch { }
        }
        _controlClients.Clear();
    }
    try { _listener?.Stop(); } catch { }
    try { _listener?.Close(); } catch { }
    // ListenLoop タスクの完了を待つ（最大2秒）
    try { _listenTask?.Wait(2000); } catch { }
}
```

### Step 2: FfmpegProcess.StopAsync を堅牢化

Kill() 後に WaitForExit を追加:

```csharp
catch (OperationCanceledException)
{
    Log.Warning("[FFmpeg] Kill after 5s timeout");
    try { _process.Kill(); } catch { }
    try { _process.WaitForExit(3000); } catch { }
}
```

### Step 3: FfmpegProcess.LogStderrAsync にガード追加

プロセス終了後すぐにループを抜けるように:

```csharp
private async Task LogStderrAsync()
{
    try
    {
        var logPath = Path.Combine(AppContext.BaseDirectory, "logs", "ffmpeg.log");
        Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);
        await using var writer = new StreamWriter(logPath, append: false);
        while (_process is { HasExited: false } && !_stopping)
        {
            var line = await _process.StandardError.ReadLineAsync();
            if (line == null) break;  // EOF
            await writer.WriteLineAsync(line);
            await writer.FlushAsync();
        }
    }
    catch { /* process ended */ }
}
```

### Step 4: MainForm.OnFormClosing にタイムアウト付きクリーンアップ + Environment.Exit

```csharp
private async void OnFormClosing(object? sender, FormClosingEventArgs e)
{
    if (_closing)
    {
        CleanupResources();
        return;
    }

    // 配信中に閉じるボタン → トレイに最小化（誤終了防止）
    if (_ffmpeg is { IsRunning: true } && e.CloseReason == CloseReason.UserClosing && !_forceClose)
    {
        e.Cancel = true;
        WindowState = FormWindowState.Minimized;
        Hide();
        _trayIcon?.ShowBalloonTip(2000, "AI Twitch Cast", "配信中のためトレイに最小化しました", ToolTipIcon.Info);
        Log.Information("[MainForm] Minimized to tray (streaming active)");
        return;
    }

    e.Cancel = true;
    _closing = true;
    Hide();
    try { _webView.CoreWebView2.IsMuted = true; } catch { }

    // タイムアウト付きクリーンアップ（最大10秒）
    var cleanupTask = Task.Run(async () =>
    {
        if (_ffmpeg != null)
        {
            try { await StopStreamingAsync(); }
            catch (Exception ex)
            {
                Log.Error(ex, "[MainForm] Error stopping stream during close");
                try { _ffmpeg?.Dispose(); } catch { }
                _ffmpeg = null;
                _audio?.Dispose();
                _audio = null;
            }
        }
    });

    if (!cleanupTask.Wait(10000))
    {
        Log.Warning("[MainForm] Cleanup timed out after 10s, forcing exit");
    }

    CleanupResources();
    Log.CloseAndFlush();
    Environment.Exit(0);
}
```

### Step 5: AudioLoopback.Stop にタイマーDispose待機

```csharp
public void Stop()
{
    using var waitHandle = new ManualResetEvent(false);
    _silenceTimer?.Dispose(waitHandle);
    waitHandle.WaitOne(1000);
    _silenceTimer = null;
    try { _capture?.StopRecording(); }
    catch (Exception ex) { Log.Debug("[Audio] Stop error: {Msg}", ex.Message); }
}
```

## リスク

- `Environment.Exit(0)` は最終手段として安全。`Log.CloseAndFlush()` でログは保存される
- HttpServerの `_listenTask.Wait(2000)` がデッドロックする可能性は低い（CancelTokenで`GetContextAsync`が終了するため）
- FFmpegの `Kill()` + `WaitForExit(3000)` は十分な時間

## ステータス: 完了
