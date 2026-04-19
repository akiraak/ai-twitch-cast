# 録画停止時の NullReferenceException クラッシュ修正

## ステータス: 完了

## 要旨

録画終了（`stopRecord`）直後に C# 配信アプリが `NullReferenceException` で落ちる事象。
`FfmpegProcess.WriteVideoFrame` が ThreadPool にキューしたラムダが、`FfmpegProcess.StopAsync`
による `_videoPipe = null` と競合し、ラムダ内 `_videoPipe!.Write(...)` で NRE → `AppDomain.UnhandledException`
に到達してプロセス終了。結果、録画済み MP4 のアップロードが開始されず、ファイルが
ローカル（`C:\Users\akira\AppData\Local\AITwitchCast\recordings\`）に取り残される。

## 再現ログ（`app20260419.log` 14:20:37）

```
14:20:37.448 [Panel] Action: stopRecord
14:20:37.449 [Rec] ffmpeg.StopAsync()...
14:20:37.450 [FFmpeg] === 配信終了レポート (00:00:45) === フレーム: 1256 ドロップ: 107 ...
14:20:37.453 [FFmpeg] Audio writer thread exiting (queue=30)      ← パイプdispose後
14:20:37.460 [FTL] [CRASH] UnhandledException (terminating=true)
System.NullReferenceException: Object reference not set to an instance of an object.
   at WinNativeApp.Streaming.FfmpegProcess.<>c__DisplayClass78_0.<WriteVideoFrame>b__0(Object _)
       in Streaming\FfmpegProcess.cs:line 341
```

過去の録画停止（12:53:16 / 12:59:59 / 13:02:49 / 14:19:06）はすべて `ffmpeg stopped` →
`[Upload] Start` → `[Upload] Success` の順で正常完了しており、今回はタイミング次第で
露見するレースコンディションだと分かる。

## 原因（レース）

`FfmpegProcess.cs:305-380` の `WriteVideoFrame`:

1. `if (_videoPipe is not { IsConnected: true } || _stopping) return;` でガード（line 307）
2. `_writingVideo = true` してから ThreadPool に書き込みラムダをキュー（line 333）
3. ラムダ内で `_videoPipe!.Write(nv12, 0, nv12WriteSize)` を実行（line 344）

一方 `StopAsync`（line 700-772）:

- `_stopping = true`（line 703）
- `_videoPipe?.Dispose()` → `_videoPipe = null`（line 735-737）
- `_audioWriter?.Join(2000)` は行うが、**ThreadPool にキュー済みの映像書き込みラムダは待たない**

ガード通過〜ラムダ実行の間に StopAsync が割り込むと、ラムダ起動時には `_videoPipe` が null。
`_videoPipe!.Write(...)` が NRE を投げ、ラムダの `catch (IOException)` にはかからず
AppDomain 未処理例外 → プロセス終了。

線の数（Release/PDBでは±1ズレ得るが）: 実コードで NRE を投げ得るのは line 344 の
`_videoPipe!.Write(...)` と line 340 の `ColorConverter.BgraToNv12(buf, nv12, w, h)`
（ただし `buf`/`nv12` はラムダキュー前にローカル変数にスナップショット済みなので null にはならない）
→ 実質 **line 344 が真の発生点**、スタックの line 341 は Release JIT の近接行報告。

## 修正方針（3層、まとめて実装）

### Fix A（本命）: ラムダ先頭で stopping / null チェック

`FfmpegProcess.cs:335` 付近、`try` の直後に早期 return を追加:

```csharp
ThreadPool.QueueUserWorkItem(_ =>
{
    try
    {
        // 停止要求があればスキップ（StopAsync と競合しても無害）
        if (_stopping || _videoPipe is null) return;

        var sw = Stopwatch.StartNew();
        ColorConverter.BgraToNv12(buf, nv12, w, h);
        ...
        _videoPipe.Write(nv12, 0, nv12WriteSize);  // ! を外す（null は上でチェック済み）
```

### Fix B（多層防御）: catch を広げて飲み込む

現状の `catch (IOException)` は race で起きる `NullReferenceException` /
`ObjectDisposedException` を補足できない。以下のように広げる:

```csharp
catch (Exception ex) when (ex is IOException
                        or ObjectDisposedException
                        or NullReferenceException)
{
    Interlocked.Increment(ref _dropCount);
    // 停止中は想定内のレース、停止外なら記録
    if (!_stopping)
        Log.Debug("[FFmpeg] Video write race caught: {Type}", ex.GetType().Name);
}
```

### Fix C（副次）: StopAsync でキュー済みラムダの完了を待つ

`FfmpegProcess.cs:734` の `_videoPipe?.Dispose()` の**直前**に、`_writingVideo` が
false になるのを短時間待つループを挟む:

```csharp
// パイプ閉鎖前にキュー済みの映像書き込みラムダの終了を待つ（最大 200ms）
var spinStart = Environment.TickCount64;
while (_writingVideo && Environment.TickCount64 - spinStart < 200)
    Thread.Sleep(5);
if (_writingVideo)
    Log.Warning("[FFmpeg] Video writer did not finish within 200ms; forcing close");

try { _videoPipe?.Dispose(); }
```

Fix A だけでは「ラムダ先頭のチェック〜`Write` の間」に新たな窓が残るので、
pipe を dispose する前に ThreadPool 側を収束させておくほうが安全。

## 対象ファイル

| ファイル | 想定変更 |
|---|---|
| `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs` | `WriteVideoFrame` のラムダ先頭に stopping/null チェック（Fix A）、catch を `IOException / ObjectDisposedException / NullReferenceException` に拡張（Fix B）、`StopAsync` で pipe dispose 前に `_writingVideo` 収束をスピンウェイト（Fix C） |
| `tests/test_native_app_patterns.py` | C# ソース静的チェックを追加: `WriteVideoFrame` ラムダ内の早期 return、catch 節の ObjectDisposed/NullReference 取り込み、`StopAsync` の `_writingVideo` ウェイト |
| `DONE.md` / `TODO.md` | 完了時に移動 |

## リスク

| リスク | 影響度 | 対策 |
|---|---|---|
| Fix C のスピンウェイトで停止が最大 200ms 遅延 | 低 | 従来の StopAsync は 100〜200ms 要しており、誤差範囲。`--record` 専用でもない（配信停止時も通る）が、停止ボタンの体感差は出ない |
| Fix B で本当の `NullReferenceException`（バグ）を握り潰す | 中 | `_stopping=false` のときだけ Debug ログを出す条件付きで痕跡は残る。実害があれば後日発見可能 |
| 音声側（`WriteAudioData` / `AudioWriterLoop`）に同じ race がある可能性 | 中 | 音声側は既に `_audioWriter?.Join(2000)` で待機 + ループ内の try/catch で広く握り潰しているため実質対処済み。今回の修正は映像ラムダのみに限定 |

## 検証

1. `./server.sh` + `./stream.sh` で起動 → 録画開始 → 60秒録画 → `stopRecord`
2. C# ログに `CRASH` が出ず、`[Rec] ffmpeg stopped` → `[Upload] Start` → `[Upload] Success` まで流れることを確認
3. 上記を 10 回連続で実施し 1 回も落ちないことを確認（旧実装では数回〜十数回に 1 回程度発生する race のはず）
4. 録画停止直後に意図的に高負荷（例: 別ウィンドウキャプチャ切替）を与えて race を誘発しても crash しないことを確認
5. `python3 -m pytest tests/ -q -m "not slow"` オールグリーン

## 運用上の救出手段（修正前でも使える）

- クラッシュ時も MP4 は `C:\Users\akira\AppData\Local\AITwitchCast\recordings\` に残る
- 再起動後、管理画面から `retryUpload` で再送可能（`app20260419.log:4407` 参照）
