# 対話モード長文再生時の音声切り詰め

## ステータス: 未着手

## 概要

`_play_dialogues` で長い対話テキストの音声がWAVファイルとしては完全なのに、授業再生時に末尾が切り詰められて聞こえる問題を修正する。音声の分割は行わず、再生パイプラインの同期を改善する。

## 背景

- English 1-1 セクション2で長文の対話テキストを再生した結果、末尾が途切れた
- **WAVファイル自体は完全** — 単体で再生すると最後まで音声が入っている
- **授業再生時に切れる** — `LessonRunner` 経由でC#アプリに送信→FFmpegパイプラインで再生すると末尾が欠落する

## 原因分析

### 再生パイプラインの構造

```
Python speak()
  → send_tts_to_native_app() [WAV → base64 → WebSocket → C#]
  → C# OnTtsAudio
    → PlayTtsLocally()        [NAudio ローカル再生]
    → TtsDecoder.DecodeWav()  [24kHz mono 16bit → 48kHz stereo f32le]
    → ffmpeg.WriteTtsData()   [PCMをミキサーキューに投入]
  → C# 応答返却
Python asyncio.sleep(duration + 0.1)
  → 次の dialogue / セクションへ
```

### 問題: Python と C# の再生タイミングのズレ

Python は WAV の `duration + 0.1` 秒待ってから次に進むが、C# 側の実際の再生完了はこれとは独立:

1. **C#オーディオミキサーのタイマージッター**: 10ms タイマーで動作し `Clamp(elapsedMs, 1, 50)` しているため、高負荷時にTTS消費が実時間より遅れる。長い音声ほど遅延が蓄積し、Python の sleep 終了時点でまだ再生が終わっていない
2. **ローカル再生の強制停止**: `PlayTtsLocally` は新しい TTS 到着時に前の再生を `Stop()` する。NAudio の初期化遅延分だけ再生開始が遅れるため、Python の sleep 後に次の TTS が来ると末尾が切れる
3. **累積ドリフト**: 対話セクションでは複数の dialogue が連続再生される。各 dialogue で数十〜数百ms ずつズレが蓄積し、後半の dialogue ほど実際の再生がPythonより遅れる

### `_play_single_speaker` で問題が目立たない理由

文単位（3〜8秒）に分割されるため、1回あたりのズレが小さく `+0.1` のバッファで吸収できる。

## 方針

**音声は分割しない。** 代わりに、Python 側で C# の TTS 再生完了を確認してから次に進む仕組みを導入する。

### 具体的なアプローチ

1. C# 側に `tts_status` WebSocket アクションを追加（`IsTtsActive` を返す）
2. Python の `speak()` で `asyncio.sleep(duration + 0.1)` の後、`tts_status` をポーリングして再生完了を待つ
3. タイムアウト付き（無限待ちを防止）

```
speak() 内のフロー:
  send_tts_to_native_app(wav)
  asyncio.sleep(duration + 0.1)          ← 従来通り（大半はここで完了）
  _wait_tts_complete(max_extra=duration)  ← 新規: まだ再生中なら追加で待つ
```

## 実装ステップ

### Step 1: C# — `tts_status` WebSocket アクション追加

**ファイル**: `win-native-app/WinNativeApp/Server/HttpServer.cs`

WebSocket アクションのディスパッチに `tts_status` を追加:

```csharp
"tts_status" => HandleWsTtsStatus(),
```

ハンドラ:
```csharp
private object HandleWsTtsStatus()
{
    return OnGetTtsStatus?.Invoke() ?? new { ok = true, active = false };
}
```

**ファイル**: `win-native-app/WinNativeApp/Server/HttpServer.cs` (プロパティ追加)

```csharp
public Func<object>? OnGetTtsStatus { get; set; }
```

**ファイル**: `win-native-app/WinNativeApp/MainForm.cs` (コールバック設定)

```csharp
_httpServer.OnGetTtsStatus = () => new
{
    ok = true,
    active = (_ffmpeg is { IsRunning: true })
        ? _ffmpeg.IsTtsActive
        : (_ttsWaveOut?.PlaybackState == PlaybackState.Playing)
};
```

配信中は FFmpeg ミキサーの `IsTtsActive`、非配信時は NAudio のローカル再生状態を返す。

### Step 2: Python — `speak()` に TTS 完了待ちを追加

**ファイル**: `src/speech_pipeline.py`

`_speak_impl` の `asyncio.sleep(duration + 0.1)` の後に TTS 完了ポーリングを追加:

```python
# 音声の長さ分だけ待機
await asyncio.sleep(duration + 0.1)

# C# 側の再生完了を確認（まだ再生中なら追加で待つ）
await self._wait_tts_complete(max_extra=duration * 0.5)
```

新規メソッド:
```python
async def _wait_tts_complete(self, max_extra: float = 5.0):
    """C# 側の TTS 再生が完了するまでポーリングで待機する

    Args:
        max_extra: 追加で待つ最大秒数（無限待ち防止）
    """
    try:
        from scripts.services.capture_client import ws_request
        elapsed = 0.0
        interval = 0.2
        while elapsed < max_extra:
            result = await ws_request("tts_status", timeout=2.0)
            if not (result and result.get("active")):
                break
            await asyncio.sleep(interval)
            elapsed += interval
        if elapsed > 0.1:
            logger.info("[tts] TTS完了待ち: %.1f秒追加", elapsed)
    except Exception:
        pass  # C# 未接続時は静かにスキップ
```

### Step 3: テスト追加

**ファイル**: `tests/test_speech_pipeline.py`

- `_wait_tts_complete` が `active=True` の間ポーリングし、`active=False` で終了すること
- タイムアウトで打ち切られること
- `ws_request` 失敗時に例外を出さずスキップすること

## 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `win-native-app/WinNativeApp/Server/HttpServer.cs` | `tts_status` アクション追加、`OnGetTtsStatus` プロパティ追加 |
| `win-native-app/WinNativeApp/MainForm.cs` | `OnGetTtsStatus` コールバック設定 |
| `src/speech_pipeline.py` | `_wait_tts_complete()` 追加、`_speak_impl` から呼び出し |
| `tests/test_speech_pipeline.py` | `_wait_tts_complete` のテスト追加 |

## リスク

- **ポーリングのオーバーヘッド**: 200ms 間隔で WebSocket 往復が発生するが、TTS 再生中（秒単位）に比べれば軽微。大半のケースでは `duration + 0.1` の sleep で完了し、ポーリングは走らない
- **C# 未接続時**: `ws_request` が失敗したら静かにスキップし、従来動作（`duration + 0.1` のみ）にフォールバック
- **タイムアウト**: `max_extra = duration * 0.5` で無限待ちを防止。30秒音声なら最大15秒追加待ち
- **コメント応答への影響**: `speak()` は全モードで共通だが、コメント応答は短い文（数秒）なのでポーリングに入るケースはほぼない。影響は授業の長文 dialogue に限定される
