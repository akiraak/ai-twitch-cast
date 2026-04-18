# TTS完了待ちの過剰遅延の改善

## ステータス: 未着手

## 概要

`_wait_tts_complete` のポーリング方式（`max_extra=duration * 0.5`）により、長い音声（20秒）で最大10秒の不要な待ち時間が発生している。推定時間でのsleep＋ポーリングを廃止し、C#からの再生完了Push通知をawaitする方式に変更する。

## 原因分析

### 現在のフロー（問題あり）

```
send_tts_to_native_app(wav)
asyncio.sleep(duration + 0.1)              ← 推定時間で待つ
_wait_tts_complete(max_extra=duration*0.5)  ← ポーリング（最大 duration/2 秒追加）
```

`tts_status` は `_ffmpeg.IsTtsActive`（FFmpegミキサーのキュー状態）を返す。ユーザーが聞くNAudioローカル再生は `duration` 秒前後で完了するが、FFmpegキューの消費は高負荷時に遅れるため、ポーリングが長時間回り続ける。

## 方針

**C#がTTS再生完了時にPush通知** → **Pythonがawait** に変更。推定時間のsleepもポーリングも不要になる。

```
変更後:
  tts_complete_event.clear()
  send_tts_to_native_app(wav)
  字幕表示・口パク開始
  await tts_complete_event (timeout: duration + 3.0)
  口パク停止 → 次へ
```

- 正常時: NAudio再生完了 → C# Push → event発火 → 即座に次へ（余分な待ちゼロ）
- C#未接続時: timeoutフォールバック（duration + 3秒）で従来同等の動作

## 実装ステップ

### Step 1: C# — PlaybackStopped で `tts_complete` Push通知送信

**ファイル**: `win-native-app/WinNativeApp/MainForm.cs`

`PlayTtsLocally` の `PlaybackStopped` ハンドラ内で、自然終了時のみPush通知を送信:

```csharp
waveOut.PlaybackStopped += (_, _) =>
{
    if (disposed) return;
    disposed = true;
    if (_ttsWaveOut == waveOut)
    {
        _ttsWaveOut = null;
        _ttsChannel = null;
        _ttsMeter = null;
        // 自然終了 → Push通知
        _ = _httpServer.BroadcastWsEvent(new { type = "tts_complete" });
    }
    // ... existing cleanup ...
};
```

`_ttsWaveOut == waveOut` の条件により、次のTTSで強制Stop()された場合は通知しない（`PlayTtsLocally` が先に `_ttsWaveOut = null` してからStop()するため）。

配信中も `OnTtsAudio` は常に `PlayTtsLocally` を呼ぶ（MainForm.cs:779）ので、NAudioのPlaybackStoppedが配信/非配信の両モードで完了シグナルになる。

### Step 2: Python — capture_client に tts_complete イベント追加

**ファイル**: `scripts/services/capture_client.py`

```python
# モジュール変数
_tts_complete_event: asyncio.Event | None = None

def get_tts_complete_event() -> asyncio.Event:
    """TTS完了通知用のasyncio.Eventを取得する（遅延初期化）"""
    global _tts_complete_event
    if _tts_complete_event is None:
        _tts_complete_event = asyncio.Event()
    return _tts_complete_event
```

`_read_capture_ws` のPush通知処理に `tts_complete` を追加（`lesson_complete` ハンドラの直後、capture_client.py:200-204 の並び）:

```python
if data.get("type") == "tts_complete":
    get_tts_complete_event().set()
    continue
```

### Step 3: Python — speech_pipeline の待機ロジックをイベントベースに変更

**ファイル**: `src/speech_pipeline.py`

`_speak_impl` の待機部分を変更:

```python
# 変更前
await asyncio.sleep(duration + 0.1)
await self._wait_tts_complete(max_extra=duration * 0.5)

# 変更後
await self._wait_tts_complete(timeout=duration + 3.0)
```

`_wait_tts_complete` をイベントベースに書き換え:

```python
async def _wait_tts_complete(self, timeout: float = 5.0):
    """C# 側の TTS 再生完了Push通知を待つ

    Args:
        timeout: 最大待ち秒数（C#未接続時のフォールバック）
    """
    try:
        from scripts.services.capture_client import get_tts_complete_event
        evt = get_tts_complete_event()
        await asyncio.wait_for(evt.wait(), timeout=timeout)
        logger.info("[tts] C#再生完了通知を受信")
    except asyncio.TimeoutError:
        logger.debug("[tts] 再生完了通知タイムアウト (%.1f秒)", timeout)
    except Exception:
        pass  # C# 未接続時は静かにスキップ
```

イベントのclearは `send_tts_to_native_app` の直前に呼ぶ:

```python
# _speak_impl 内、send_tts_to_native_app の直前
from scripts.services.capture_client import get_tts_complete_event
get_tts_complete_event().clear()
await self.send_tts_to_native_app(wav_path)
```

### Step 4: テスト更新

**ファイル**: `tests/test_speech_pipeline.py`

既存 `TestWaitTtsComplete` の5テスト（`test_polls_until_inactive` / `test_immediately_inactive` / `test_timeout_stops_polling` / `test_ws_failure_silently_skips` / `test_none_result_treated_as_inactive`）はポーリング前提なので全削除し、以下3本に置き換える:

- `test_returns_when_event_set` — イベントがawait中に `set()` されたら即座にreturnすること
- `test_returns_if_event_already_set` — 開始時点で既に `set()` 済みなら即座にreturnすること
- `test_timeout_fallback` — `timeout` 秒経過で `TimeoutError` を握りつぶしてreturnすること

インポート失敗（C#未接続相当）時の無音スキップは、`_wait_tts_complete` 内の `except Exception: pass` ブロックで担保されるため、個別テストは不要（`test_timeout_fallback` と `test_returns_when_event_set` がカバー）。

### Step 5: 旧コード削除

- `HttpServer.cs:469` の WebSocket dispatch `"tts_status" => HandleWsTtsStatus()` → 削除
- `HttpServer.cs:663-666` の `HandleWsTtsStatus` メソッド → 削除
- `HttpServer.cs:53` の `OnGetTtsStatus` プロパティ → 削除
- `MainForm.cs:833-839` の `OnGetTtsStatus` コールバック設定 → 削除

## 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `win-native-app/WinNativeApp/MainForm.cs` | `PlaybackStopped` で `tts_complete` Push通知、`OnGetTtsStatus` 削除 |
| `win-native-app/WinNativeApp/Server/HttpServer.cs` | `tts_status` アクション・`OnGetTtsStatus` 削除 |
| `scripts/services/capture_client.py` | `tts_complete` イベント受信 + `get_tts_complete_event()` 追加 |
| `src/speech_pipeline.py` | `_wait_tts_complete` をイベントベースに書き換え、`asyncio.sleep` 削除 |
| `tests/test_speech_pipeline.py` | テストをイベントベースに更新 |

## リスク

- **C#未接続時**: イベントが届かずtimeout（duration + 3秒）で進む。従来のsleep(duration + 0.1)より最大3秒遅いが、C#未接続=音声なしなので実害なし
- **PlaybackStopped発火タイミング**: NAudioの内部バッファ分だけ実際の聴取終了より早く発火する可能性がある（数十ms程度）。体感上は問題ない
- **配信中のFFmpegキュー挙動変化**: 現行は `IsTtsActive`（FFmpegキュー）が空になるまで待つため、配信ストリーム上でも前TTSと次TTSが重ならない。NAudio完了ベースに変えると、高負荷でキューが遅れている間に次TTSが投入され、FFmpegキューに積み上がる。ただし次TTSは生成に約1秒かかる（TTS合成 + リップシンク解析）ため、その間にキューが捌けるケースが大半で実害は小さい。ポーリング方式に戻すほどの回帰ではないと判断
