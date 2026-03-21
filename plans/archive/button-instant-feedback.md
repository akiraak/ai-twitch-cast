# Go Live / Stop ボタンの即時フィードバック

## ステータス: 完了

## 背景・課題

- Windowsネイティブアプリ（C#）のUIパネル（`control-panel.html`）で「Go Live」「Stop」ボタンを押しても、処理完了までの間に視覚的なフィードバックがない
- Go Live: ボタン押下 → C#側で`StartStreamingWithKeyAsync`（FFmpegパイプライン構築）→ 完了後にログ表示。この間ボタンは変化しない
- Stop: ボタン押下 → C#側で`StopStreamingAsync`（audio/ffmpeg停止）→ 完了後にログ表示。この間ボタンは変化しない
- ステータス表示(`updateStatus`)はC#から3秒間隔のタイマー(`OnTrayUpdate`)で送信されるため、ボタン押下直後には更新されない
- 結果として、押したかどうか分からず何度も押してしまう

## 現状のフロー

### Go Live
1. パネルHTML: `goLive()` → `send({action:'goLive'})` でC#に送信
2. C# `HandlePanelGoLive()` → `StartStreamingWithKeyAsync()` 実行（数秒かかる）
3. 完了後 `PanelLog("配信を開始しました", "success")` でログに表示
4. 3秒後のタイマーで `updateStatus` → ボタンのdisabled切替

### Stop
1. パネルHTML: `stopStream()` → `send({action:'stopStream'})` でC#に送信
2. C# `HandlePanelStopStream()` → `StopStreamingAsync()` 実行（audio/ffmpeg停止で数秒）
3. 完了後 `PanelLog("配信を停止しました", "success")` でログに表示
4. 3秒後のタイマーで `updateStatus` → ボタンのdisabled切替

## 方針

**2箇所で即時フィードバック**を入れる:

1. **パネルHTML側（`control-panel.html`）**: ボタン押下直後にテキスト変更 + スピナー + disabled化
2. **C#側（`MainForm.cs`）**: 処理開始時に即座にパネルへ「処理中」通知を送信、完了/失敗後に「結果」通知を送信

## 実装ステップ

### 1. CSS追加 — ローディングスピナー（`control-panel.html`）

```css
.btn.loading {
  pointer-events: none;
  opacity: 0.7;
}
.btn.loading::after {
  content: '';
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-left: 6px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  vertical-align: middle;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
```

### 2. JS修正 — ボタン押下時に即座にローディング状態へ（`control-panel.html`）

```javascript
function goLive() {
  const btn = $('goLiveBtn');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.textContent = '準備中…';
  send({action:'goLive'});
}

function stopStream() {
  const btn = $('stopBtn');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.textContent = '停止中…';
  send({action:'stopStream'});
}
```

### 3. JS修正 — C#からの結果通知でボタンを復帰（`control-panel.html`）

C#から `{type: "streamResult", action: "goLive"|"stop", ok: bool}` を受信してボタンを復帰。

```javascript
// switch (m.type) に追加:
case 'streamResult': handleStreamResult(m); break;

function handleStreamResult(m) {
  if (m.action === 'goLive') {
    const btn = $('goLiveBtn');
    btn.classList.remove('loading');
    btn.textContent = '● Go Live';
    // ok時はupdateStatusで切り替わるのでdisabledのまま。失敗時は有効に戻す
    if (!m.ok) btn.disabled = false;
  } else if (m.action === 'stop') {
    const btn = $('stopBtn');
    btn.classList.remove('loading');
    btn.textContent = '■ Stop';
    if (!m.ok) btn.disabled = false;
  }
}
```

### 4. C#修正 — 処理完了時に即座にステータス通知（`MainForm.cs`）

`HandlePanelGoLive` / `HandlePanelStopStream` で処理完了後に `streamResult` メッセージと即時ステータス更新を送信。

```csharp
private async Task HandlePanelGoLive()
{
    // ... 既存のストリームキーチェック ...
    try
    {
        await StartStreamingWithKeyAsync(key);
        PanelLog("配信を開始しました", "success");
        SendPanelMessage(new { type = "streamResult", action = "goLive", ok = true });
        // 即座にステータス更新（3秒タイマーを待たない）
        OnTrayUpdate(null, EventArgs.Empty);
    }
    catch (Exception ex)
    {
        PanelLog($"配信開始失敗: {ex.Message}", "error");
        SendPanelMessage(new { type = "streamResult", action = "goLive", ok = false });
    }
}

private async Task HandlePanelStopStream()
{
    try
    {
        await StopStreamingAsync();
        PanelLog("配信を停止しました", "success");
        SendPanelMessage(new { type = "streamResult", action = "stop", ok = true });
        OnTrayUpdate(null, EventArgs.Empty);
    }
    catch (Exception ex)
    {
        PanelLog($"配信停止失敗: {ex.Message}", "error");
        SendPanelMessage(new { type = "streamResult", action = "stop", ok = false });
    }
}
```

## 変更ファイル

- `win-native-app/WinNativeApp/control-panel.html` — CSS + JS
- `win-native-app/WinNativeApp/MainForm.cs` — `HandlePanelGoLive` / `HandlePanelStopStream` に結果通知追加

## リスク

- ほぼなし。UIフィードバックの追加のみ
- `loading` クラスの `pointer-events: none` + `disabled` で二重押し防止も兼ねる
- `OnTrayUpdate` を手動呼び出しするが、既存のタイマー呼び出しと同じ処理なので安全
