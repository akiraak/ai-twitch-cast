# PlayTtsLocally バッチチェーン再生ハングの修正

## ステータス: 未着手

## 要旨

Claude Code 実況のチェーン再生（`speak_batch`）で **entry#0 を再生後、entry#1 以降が発火しないハング** が発生している。原因は `PlayTtsLocally` の `WaveChannel32` が `PadWithZeroes = true`（NAudio デフォルト）で、WAV 終端後に無音ゼロを無限に返し続け、`WaveOutEvent.PlaybackStopped` が自然発火しないこと。`PlaybackStopped` が発火しないため `DequeueAndPlayNextLocal(finishedCurrent: true)` が呼ばれず、`_ttsLocalCurrent` が永久に残留 → 後続バッチも `wasIdle=false` で弾かれる。

`PlayLessonAudioAsync`（MainForm.cs:1633）にはコミット `e4846b7` で同現象への多層防御（duration+1.5s フォールバック）が入っているが、`PlayTtsLocally` には未移植。

## 背景（2026-04-18 実測）

### Python 側（`server.log` 13:51:43〜）
```
[batch] C#へバッチ送信完了: queued=4
[batch] entry#0 字幕・口パク発火: id=ff10c00b0001
[batch] entry#1 started Push未着（タイムアウト）
[batch] バッチ完了Push未着（タイムアウト 27.0s）
```

### C# 側（`app20260418.log` 13:41:17〜）
```
13:41:16.957 Batch queued: count=4 wasIdle=true
13:41:16.960 Batch entry started: id=c08ee1...
13:41:17.208 Local playback started (179130 bytes)  ← entry#0 の音声（3.7秒）
... 以降 2分間 TTS 系ログなし ...
13:43:18.630 Batch queued: count=4 wasIdle=false    ← 決定打
```

`wasIdle=false` = `_ttsLocalCurrent` が entry#0 のまま残留 → `OnTtsAudioBatch` が `DequeueAndPlayNextLocal()` を呼ばず、後続バッチもすべて詰まる。

## 修正方針

以下3つをまとめて実装する（単独では合わせ技で再発する可能性があるため）。

### Fix A（本命・最小）: `PadWithZeroes = false`

`win-native-app/WinNativeApp/MainForm.cs:1473` の `WaveChannel32` 初期化にプロパティを追加:

```csharp
// 旧
var channel = new WaveChannel32(reader) { Volume = Math.Clamp(volume, 0f, 1f) };
// 新
var channel = new WaveChannel32(reader) {
    Volume = Math.Clamp(volume, 0f, 1f),
    PadWithZeroes = false,
};
```

これで WAV 終端で `Read()` が 0 を返し、`WaveOutEvent` が `PlaybackStopped` を自然発火する。

### Fix B（多層防御）: duration ベース フォールバック

`PlayLessonAudioAsync`（MainForm.cs:1601-1646）と同じ構造で `PlayTtsLocally` にフォールバックタイマーを追加:

```csharp
// PlaybackStopped と競合しないよう Interlocked.CompareExchange で原子化
int completed = 0;
// WAV の duration を計算（bytes / (sampleRate × blockAlign)）
// waveOut.Play() 後:
_ = Task.Run(async () => {
    try { await Task.Delay(TimeSpan.FromSeconds(duration + 1.5)); } catch { return; }
    if (Interlocked.CompareExchange(ref completed, 1, 0) != 0) return;
    // 強制的に PlaybackStopped 相当の後始末を実行
    // → DequeueAndPlayNextLocal(finishedCurrent: true) を BeginInvoke
});
```

- `PlaybackStopped` の `disposed` フラグも `Interlocked.CompareExchange` に合わせる
- キャンセルトークン（`CancellationTokenSource`）で WaveOut 新規作成時や Stop 時に自動キャンセル

### Fix C（副次）: `OnTtsAudio` 単発が `_ttsLocalCurrent` をクリア

`MainForm.cs:833-866` の `OnTtsAudio`（単発）でバッチ中断時、現状は `_ttsLocalQueue.Clear()` と `_ttsBatchActive = false` のみで `_ttsLocalCurrent` はそのまま:

```csharp
lock (_ttsQueueLock) {
    if (_ttsLocalQueue.Count > 0 || _ttsBatchActive) {
        _ttsLocalQueue.Clear();
        hadBatch = _ttsBatchActive;
        _ttsBatchActive = false;
        _ttsLocalCurrent = null;  // ← 追加
    }
}
```

これがないと「バッチ再生中に単発が割り込む → 単発が自然終了しない（他の理由で中断） → `_ttsLocalCurrent` 残存」の合わせ技で Fix A/B を通り抜けて同じハングが起きる。

## 対象ファイル

| ファイル | 想定変更 |
|---|---|
| `win-native-app/WinNativeApp/MainForm.cs` | `PlayTtsLocally` に `PadWithZeroes=false` / duration フォールバック追加、`OnTtsAudio` に `_ttsLocalCurrent = null` 追加 |
| `tests/test_native_app_patterns.py` | C#ソース静的チェックを追加（`PadWithZeroes = false` の存在、フォールバックタイマーの存在、`OnTtsAudio` の `_ttsLocalCurrent` クリア） |
| `docs/speech-generation-flow.md` | 「Claude Code実況のチェーン再生」セクションに PadWithZeroes 回避と duration フォールバックの要件を追記 |
| `DONE.md` / `TODO.md` | 完了時に移動 |

## リスク

1. **Fix A で `PlaybackStopped` が早すぎるタイミングで発火**
   - WAV 末尾の無音サンプルが切られて「プツッ」とクリッピングノイズが出る可能性
   - 対策: `NumberOfBuffers=3, DesiredLatency=100` のバッファが既に 300ms 余裕あるので大丈夫なはず。実配信で音切れが出る場合は末尾に 100ms の無音を付加するなど後処理検討
2. **Fix B と Fix A の重複発火**
   - `Interlocked.CompareExchange` で原子化しているため重複実行は防げる
   - ただし `completed=1` のあとに古い `PlaybackStopped` が走ると二重 Dispose になる可能性 → `disposed` フラグで別管理
3. **Fix C の後方互換**
   - `_ttsLocalCurrent = null` を追加しても、単発 TTS は別に現在再生中の waveOut を Stop してから新 WaveOut を Play するので、単発自身の動作には影響しない

## 検証

1. `./stream.sh` → `curl -X POST http://localhost:$WEB_PORT/api/avatar/speak -d '{"event_type":"作業報告","detail":"掛け合いテスト"}'`
2. `server.log` で `[batch] entry#0..#3 字幕・口パク発火` が 4 件すべて出ることを確認
3. `server.log` で `[batch] バッチ完了Push未着` が出なくなることを確認
4. C# ログで `Batch entry started` が 4 件、`Local playback started` が 4 件、`Batch complete → Push` が 1 件出ることを確認
5. 連続 10 回以上テストして毎回 4 件全部発話されることを確認
6. バッチ再生中に別の単発 TTS（例: 教師モードプレビュー）を割り込ませても、以降のバッチが正常に再生開始することを確認（Fix C の検証）
7. `python3 -m pytest tests/ -q` オールグリーン

## 完了条件

- Claude Code 実況の掛け合い（2〜4 エントリ）が全件発話される
- `server.log` に `[batch] entry#N started Push未着` が出ない
- C# 側 `Batch entry started` 件数が送信件数と一致する
- 単発 → バッチ or バッチ → 単発 → バッチの割り込みパターンでもハングしない
- `python3 -m pytest tests/ -q` オールグリーン
