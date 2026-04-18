# Claude Code 実況のチェーン再生（全件先送り → クライアント順次再生）

## ステータス: 完了

## 背景

`plans/claude-narration-gap-investigation.md` の調査で、Claude Code 実況（`claude_watcher._play_conversation`）のエントリ間ギャップの主因は、Python 側が「1エントリ送信 → 完了ポーリング → 次送信」の直列パイプラインになっていることと判明した。

本プランでは、**全エントリのWAVを先にC#アプリへ送信し、C#側のキューで順次再生**する構成に切り替える。これはギャップ調査プランの「仮説D（チェーン再生）」に該当し、理論的には再生エントリ間の無音が0になる。

**スコープは Claude Code 実況のみ**（`src/claude_watcher.py` `_play_conversation`）。Twitchコメント掛け合い（`src/comment_reader.py`）・授業・WebUIチャットは本プランの対象外。効果を確認してから段階的に展開する。

## 前提のアーキテクチャ

- C#アプリの `_ttsQueue`（`FfmpegProcess.cs:49`）は複数チャンクをキューイングして `MixTtsInto` が自動的に連続消費する → **FFmpeg配信側はそもそもチェーン再生対応済み**
- NAudioローカル再生（`PlayTtsLocally`）は現状「前の再生をStop → 新しい再生Start」の単発式なので、本プランで**キュー化が必要**
- 字幕・口パク・感情切替は Python サーバーから `/ws/broadcast` で `broadcast.html` に送る。**再生開始タイミングは C# からPython へ Push で伝える必要がある**
- Push通知基盤は既にあり:
  - C# → Python: `HttpServer.BroadcastWsEvent`（`lesson_complete` で使用中）
  - Python受信: `scripts/services/capture_client._read_capture_ws`（`lesson_complete` 用ハンドラ前例あり）

## 方針

```
[現状]
  entry#0 send → wait complete → subtitle/lipsync/emotion → wait duration → poll → next
  entry#1 send → ...（2〜3秒のギャップ）

[変更後]
  [Python]
    全エントリのTTS事前生成（並列、既存）
    全エントリをまとめて tts_audio_batch で C# に送信
    各エントリについて:
      await tts_entry_started(entry_id)   ← C# Push
      字幕・口パク・感情を発火（broadcast.html へ送信）
      (次エントリの started 通知を待つループへ)
    await tts_batch_complete              ← 全エントリ完了Push

  [C#]
    バッチ受信 → 全WAVをキューへ積む
    ローカル再生キューを順次消費（PlaybackStopped → 次）
    配信中: _ffmpeg.WriteTtsData で全PCMをFFmpegキューへ投入（自動チェーン）
    各エントリの再生開始時に tts_entry_started{id} を Push
    全エントリ完了時に tts_batch_complete{} を Push
```

### 設計判断

- **ローカル再生キューの「再生開始時点」をサーバへ通知**する設計。FFmpegキュー側はミリ秒単位で連続消費するが、字幕・口パクの基準はローカル再生（＝WebView2内の broadcast.html と同じタイムライン）にする
- ローカルNAudioとFFmpegで僅かなタイムラインズレ（数十ms）は許容。視聴者が見る映像ストリームは FFmpeg 由来・broadcast.html 由来とも同じC#プロセス内で発行され、Twitch送出時に合成されるので、相対同期は壊れない
- 割り込み（Twitchコメント到来）は `tts_batch_cancel` で C# 側キューをクリアし、進行中の再生は Stop して破棄

## WebSocketプロトコル拡張

### Python → C#

新アクション `tts_audio_batch`:

```json
{
  "action": "tts_audio_batch",
  "requestId": "...",
  "items": [
    {"id": "e0", "data": "<base64 WAV>", "volume": 0.41},
    {"id": "e1", "data": "<base64 WAV>", "volume": 0.41},
    ...
  ]
}
```

応答:
```json
{"requestId": "...", "ok": true, "queued": 4}
```

新アクション `tts_batch_cancel`:
```json
{"action": "tts_batch_cancel", "requestId": "..."}
```
応答: `{ok: true, cleared: N}`

### C# → Python (Push通知)

```json
{"type": "tts_entry_started", "id": "e0"}
{"type": "tts_entry_started", "id": "e1"}
{"type": "tts_batch_complete"}
```

## 実装ステップ

### Step 1: C# — TTS再生キュー化 + バッチ受信

**ファイル**: `win-native-app/WinNativeApp/MainForm.cs`

- クラスフィールド追加:
  - `private readonly Queue<TtsQueueItem> _ttsLocalQueue = new();`
  - `private TtsQueueItem? _ttsLocalCurrent;`
  - `private readonly object _ttsQueueLock = new();`
  - `private record TtsQueueItem(string Id, byte[] WavData, float Volume);`
- `OnTtsAudioBatch(List<TtsBatchItem> items)` コールバック:
  1. 全 item を `_ttsLocalQueue` にロック下で enqueue
  2. 配信中なら `TtsDecoder.DecodeWav` で PCM に変換して `_ffmpeg.WriteTtsData` へ全件投入（FFmpeg側チェーン）
  3. 現在idleなら `DequeueAndPlayNextLocal()` を呼ぶ
- `DequeueAndPlayNextLocal()`:
  1. `_ttsLocalQueue.TryDequeue` して `_ttsLocalCurrent` にセット
  2. `PlayTtsLocally(wavData, volume)` で再生開始
  3. `_httpServer.BroadcastWsEvent(new {type = "tts_entry_started", id})`
- `PlayTtsLocally` の `PlaybackStopped` ハンドラ内で、自然終了（Stop ではなく再生完了）時に `DequeueAndPlayNextLocal()` を呼ぶか、キューが空なら `tts_batch_complete` を Push
  - 既存の `PlaybackStopped` は「前の再生を上書き停止した際の dispose」も兼ねているため、**自然終了かStopかを区別するフラグ**が必要（例: `_ttsStoppedByUser`）
- バッチキャンセル (`OnTtsBatchCancel`) 受信時: キューをクリア、`_ttsStoppedByUser = true` にセットして `_ttsWaveOut?.Stop()`

### Step 2: C# — HttpServer にアクション追加

**ファイル**: `win-native-app/WinNativeApp/Server/HttpServer.cs`

- `HandleWsMessage` 分岐に `"tts_audio_batch" => await HandleWsTtsAudioBatch(msg)` / `"tts_batch_cancel" => HandleWsTtsBatchCancel()` を追加
- `OnTtsAudioBatch` / `OnTtsBatchCancel` デリゲートを定義
- 各ハンドラで base64 decode → MainForm 側に委譲

### Step 3: Python — Push受信 + エントリ別イベント管理

**ファイル**: `scripts/services/capture_client.py`

```python
_tts_entry_events: dict[str, asyncio.Event] = {}
_tts_batch_complete_event: asyncio.Event | None = None

def get_tts_entry_event(entry_id: str) -> asyncio.Event:
    if entry_id not in _tts_entry_events:
        _tts_entry_events[entry_id] = asyncio.Event()
    return _tts_entry_events[entry_id]

def clear_tts_entry_events():
    _tts_entry_events.clear()
    global _tts_batch_complete_event
    _tts_batch_complete_event = asyncio.Event()
    return _tts_batch_complete_event
```

`_read_capture_ws` の Push 分岐に追加:

```python
if data.get("type") == "tts_entry_started":
    eid = data.get("id")
    if eid:
        get_tts_entry_event(eid).set()
    continue
if data.get("type") == "tts_batch_complete":
    if _tts_batch_complete_event:
        _tts_batch_complete_event.set()
    continue
```

バッチ送信関数:

```python
async def send_tts_batch(items: list[dict]) -> dict:
    return await ws_request("tts_audio_batch", items=items, timeout=15.0)

async def cancel_tts_batch() -> dict:
    return await ws_request("tts_batch_cancel", timeout=5.0)
```

### Step 4: SpeechPipeline に `speak_batch` を追加

**ファイル**: `src/speech_pipeline.py`

```python
async def speak_batch(self, entries: list[dict]) -> None:
    """複数エントリを一括送信してチェーン再生する

    Args:
        entries: [{
            "text": str,          # 発話テキスト（ログ用）
            "wav_path": Path,     # 事前生成済みWAV
            "subtitle": dict,     # {author, trigger_text, result}
            "emotion": str,
            "avatar_id": str,
            "character_config": dict,
        }, ...]
    """
```

処理内容:
1. 各エントリの `lipsync_frames` / `duration` / base64 WAV を事前解析（並列 `asyncio.to_thread`）
2. 各エントリに UUID を採番、`capture_client.clear_tts_entry_events()` で Event を初期化
3. `send_tts_batch([{id, data, volume}])` で一括送信
4. 各エントリについて:
   - `await get_tts_entry_event(id).wait()` で再生開始を検知
   - `apply_emotion` / `notify_overlay` / lipsync WS 送信
   - 次エントリの started を待つ（＝現在エントリの duration 分自動的に待つ）
5. 最後に `await _tts_batch_complete_event.wait()` （タイムアウト: sum(durations) + 5秒）
6. 各エントリの `lipsync_stop` を broadcast へ送信
7. テンポラリWAVを削除

タイムアウト値は安全側に sum(durations) + 5秒とする（長すぎるバッチで永久stuckを防ぐ）。

`_speak_impl` と `_wait_tts_complete` は本プランの範囲外。既存コードはそのまま。

### Step 5: ClaudeWatcher を `speak_batch` ベースに変更

**ファイル**: `src/claude_watcher.py` `_play_conversation`

現行: ループで `self._speech.speak(...)` を1件ずつ呼び出し

変更後:
1. TTS事前生成の並列起動は既存通り
2. 全 task を `await` してWAVを揃える（失敗したエントリはスキップ or フォールバック空打ち）
3. `entries` 配列を組み立てて `self._speech.speak_batch(entries)` を1回呼ぶ
4. コメント割り込み（`self._comment_reader.queue_size > 0`）を検知したら `capture_client.cancel_tts_batch()` を呼んで中断、`speak_batch` は CancelledError/TimeoutError で抜けるように設計
5. DB保存（`_save_avatar_comment`）は各エントリ再生終了後ではなく、バッチ送信前にまとめて行う（再生順は保証されるので問題なし）

### Step 6: テスト

**ファイル**: `tests/test_speech_pipeline.py`, `tests/test_capture_client.py`, `tests/test_claude_watcher.py`

- `speak_batch`: 2エントリ分のモックWAVと `tts_entry_started` のモックPushで、字幕・lipsync発火順を検証
- `capture_client.get_tts_entry_event`: Event取得・clear・重複取得の振る舞い
- `_play_conversation`: `speak_batch` が1回呼ばれること・割り込み時 `cancel_tts_batch` 呼び出しを検証
- C#側テスト: `tests/test_native_app_patterns.py` で `_ttsLocalQueue` の clear・`_ttsStoppedByUser` フラグ利用の静的チェックを追加

### Step 7: 動作確認 & 計測

1. `./server.sh` 起動、Claude Code の応答を発火させて4エントリ掛け合いを生成
2. `server.log` で `tts_entry_started` 間の間隔 ≒ 各エントリの duration であることを確認
3. 視聴映像でセリフ間の無音を体感確認（目標: 1秒以下、理想: 0秒）
4. 途中でTwitchコメントを流して割り込みキャンセル → 残りエントリが即停止することを確認
5. `python3 -m pytest tests/ -q` パス

### Step 8: ドキュメント

- `docs/speech-generation-flow.md` — Claude Code 実況セクションに「バッチ送信 + C#チェーン再生」のフローを追記
- `.claude/projects/-home-ubuntu-ai-twitch-cast/memory/tts-audio.md` — バッチ再生パスを記録
- `claude-narration-gap-investigation.md` → 完了マーク

## リスク・注意点

| リスク | 対策 |
|---|---|
| `PlayTtsLocally` の `PlaybackStopped` が Stop()時も発火し、誤って次エントリを再生してしまう | `_ttsStoppedByUser` フラグで Stop/自然終了を区別 |
| ローカル再生とFFmpegストリーム再生のタイムラインズレ | 両者とも先入れ先出しで順序は保証される。数十ms のズレは視聴体感に影響しない |
| バッチ途中で割り込みが入ったときに「鳴り続ける」 | `tts_batch_cancel` → キュークリア + Stop + Pushの`tts_batch_complete`発火 |
| `tts_entry_started` の Push が届く前に C# 側で再生が始まってしまうと字幕が遅れる | C# 側で Push 送信 → `waveOut.Play()` の順序にする |
| 視聴者が聞く Twitch 側と broadcast.html の字幕がずれる | Twitch側は常に2〜3秒のバッファ遅延があり、配信アプリ内のWebView2は直接描画。元から同期していないため本変更で状態が悪化することはない |
| `send_tts_batch` の WAV 合計サイズが大きすぎる（4エントリ × ~400KB = 1.6MB のbase64） | 1メッセージで処理。WebSocketは10MB上限なので問題なし。必要なら分割送信の余地あり |

## 対象外（将来の別プラン）

- `comment_reader.speak_event()` / `_speak_segment()` / `respond_webui()` の掛け合い
- 授業の複数セクション再生（`LessonPlayer` は別のキュー機構）
- 単発 `speak()` の完了検知改善（ポーリング → Pushイベント化）

本プランで成功を確認したら、これらへ段階的に展開する別プランを起こす。

## 対象ファイル

| ファイル | 変更内容 |
|---|---|
| `win-native-app/WinNativeApp/MainForm.cs` | `_ttsLocalQueue` 追加、バッチハンドラ、`PlaybackStopped` 二分岐、Push送信 |
| `win-native-app/WinNativeApp/Server/HttpServer.cs` | `tts_audio_batch` / `tts_batch_cancel` アクション追加 |
| `scripts/services/capture_client.py` | Push受信ハンドラ、`send_tts_batch`/`cancel_tts_batch`、entry event 管理 |
| `src/speech_pipeline.py` | `speak_batch` メソッド追加 |
| `src/claude_watcher.py` | `_play_conversation` を `speak_batch` 化 |
| `tests/test_speech_pipeline.py` | `speak_batch` のテスト |
| `tests/test_capture_client.py` | Push受信・entry event のテスト |
| `tests/test_claude_watcher.py` | 置換後の振る舞いを検証 |
| `tests/test_native_app_patterns.py` | キュークリア/Stop分岐の静的チェック |
| `docs/speech-generation-flow.md` | フロー追記 |

## 完了条件

- Claude Code 4エントリ掛け合いで、`tts_entry_started` 間の間隔が各 duration と一致（ギャップ ≦ 300ms）
- 視聴者体感のエントリ間無音が **1秒以下**（目標: ほぼ0秒）
- Twitchコメント割り込みで全エントリが即停止し、`speak_batch` が戻る
- `python3 -m pytest tests/ -q` パス
- リグレッションなし（単発 `speak()` を使う他モードは無影響）
