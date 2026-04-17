# 授業音声: PlaybackStopped未発火によるハング修正

## ステータス: 多層防御コード実装済み — 実機で再現できず未検証

## 実機検証メモ（2026-04-16）

実装後の初回検証（18:50:44 開始）では、TTSキャッシュミスがあったため Python 側がセクション3のダイアログ生成中に止まり、`lesson_load` が一度も C# に送られないままユーザーが停止した。**C# のローカル再生パスを通っていないため、PlaybackStopped 未発火が解消したかは未確認**。次回検証の前提として、以下のいずれかを満たす必要がある:

- 実行する授業の全セクション・全ダイアログが TTS 事前生成済みであること
- もしくは TTS 生成完了まで数分待てる前提で再生開始ボタンを押すこと

UX 課題（開始後 `lesson_load` 送信前のユーザー視点での「無反応」）は別タスクとして TODO.md に切り出した。本プランは C# 側の PlaybackStopped 対策に限定する。

## 背景

授業再生で最初のセリフしか読まれない問題が Phase 1（36cb5de）以降ずっと残っている。Phase A〜D の一括送信方式への切り替えでも解消しなかった。

### 現象

C#アプリのログ（`app20260416.log`）から確定している事実:

```
18:05:51.191 [INF] Lesson loaded: id=1 sections=8 totalDialogues=37   ← 一括送信は成功
18:05:51.207 [INF] Playing section 1/8: dialogues=4
18:05:51.211 [DBG] Dialogue 1/4: speaker=teacher content="..."
18:05:51.480 [DBG] Audio playback started (542010 bytes)              ← 約11秒の音声
（32秒間ログなし）
18:06:23.750 [DBG] Action=lesson_stop                                 ← ユーザー停止
18:06:23.818 [INF] Lesson 1 finished: reason=stopped sections_played=0/8
```

11秒の音声再生が終わっても `Dialogue 2/4` ログが出ない → `PlayDialoguesAsync` の `await PlayAudio(...)` が永久に返らない。

### 根本原因（2仮説）

`win-native-app/WinNativeApp/MainForm.cs:1362-1428` の `PlayLessonAudioAsync` のハンドラ順序:

```csharp
waveOut.PlaybackStopped += (_, _) => {
    if (disposed) return;
    disposed = true;
    ...
    try { waveOut.Dispose(); } catch { }   // ← (A) Dispose が先
    try { reader.Dispose(); } catch { }
    try { ms.Dispose(); } catch { }
    tcs.TrySetResult();                    // ← (B) 完了通知が最後
};
```

**仮説1: `waveOut.Dispose()` が再生スレッドでハング（有力）**
- `PlaybackStopped` は NAudio の再生コールバックスレッドで発火する
- そのスレッド内から `waveOut.Dispose()` を呼ぶと、内部でコールバックスレッドのJoinを待ち自己デッドロックするケースが知られている
- Dispose で固まれば後続の `tcs.TrySetResult()` に到達しない → `await` が永久待機

**仮説2: `PlaybackStopped` そのものが発火しない**
- Windows側の音声デバイス状態・バッファ処理の問題で末尾完了通知が来ない可能性

どちらの仮説でも症状は同じ（`await PlayAudio()` が返らない）。ステップ6 のログで切り分けつつ、どちらであっても進行できる対策を入れる。

- 音声は鳴る（`waveOut.Play()` は成功し WAVデータも流れる）
- しかし完了通知が来ないため次のダイアログへ進めない
- これはローカル再生完了検知のC#内部の問題。Python→C#のプロトコル層とは独立

### なぜ今まで気づかなかったか

- コメント応答の TTS（`PlayTtsLocally`）は `await` しない fire-and-forget で使われるため、`PlaybackStopped` が発火しなくても実害がなかった
- 授業再生だけが `await PlayAudio()` で完了待機する設計のため、この問題が顕在化した

## 修正方針

### 多層防御アプローチ（3要素）

1. **主役: ハンドラ順序変更 + Dispose の別スレッド化** — 仮説1（Dispose内デッドロック）を解消する本質的な修正
2. **保険: duration ベースのフォールバックタイムアウト** — 仮説2 やその他の未知原因でも進行を保証
3. **診断: 発火タイミングの両面ログ** — どちらの仮説が正しいかを次回実行で切り分け

### 設計

`DialogueData.Duration`（Python `_wav_to_bundle_entry` が `wave.open(...).getnframes() / getframerate()` で算出済み）を `PlayAudio` に渡し、`Task.Delay(duration + 1.5s)` をレースさせて `tcs` を確実に完了させる。`disposed` は複数スレッドから触るため `Interlocked` で原子化し、フォールバックは `Stop()` 時にキャンセルできるよう `CancellationToken` を受け取る。

```csharp
// LessonPlayer.cs
public Func<byte[], float, double, CancellationToken, Task>? PlayAudio { get; set; }
//                                 ^^^^^^ duration   ^^^^^^^^^^^^^^^^ 停止時にフォールバックも止める

// PlayDialoguesAsync 内:
await PlayAudio(dlg.WavData, 1.0f, dlg.Duration, ct);

// MainForm.cs PlayLessonAudioAsync:
private Task PlayLessonAudioAsync(byte[] wavData, float volume, double duration, CancellationToken ct)
{
    var tcs = new TaskCompletionSource();
    int completed = 0;  // 0=未完了, 1=完了処理開始済み（Interlocked で原子操作）
    var playStart = DateTime.UtcNow;
    ...
    waveOut.PlaybackStopped += (_, _) => {
        if (Interlocked.CompareExchange(ref completed, 1, 0) != 0) return;
        var elapsed = (DateTime.UtcNow - playStart).TotalSeconds;
        Log.Debug("[Lesson] PlaybackStopped fired after {Elapsed:F2}s (duration={D:F2}s)", elapsed, duration);
        tcs.TrySetResult();  // ← (1) まず完了通知して await を解放
        Task.Run(() => {      // ← (2) クリーンアップは別スレッドで（Dispose内デッドロック回避）
            if (_lessonWaveOut == waveOut) {
                _lessonWaveOut = null;
                _lessonChannel = null;
                _lessonMeter = null;
            }
            try { waveOut.Dispose(); } catch { }
            try { reader.Dispose(); } catch { }
            try { ms.Dispose(); } catch { }
        });
    };
    waveOut.Play();

    // フォールバック: duration + 1.5秒 経過で強制的に tcs 完了（ct でキャンセル可能）
    _ = Task.Run(async () => {
        try {
            await Task.Delay(TimeSpan.FromSeconds(duration + 1.5), ct);
        } catch (OperationCanceledException) { return; }
        if (Interlocked.CompareExchange(ref completed, 1, 0) != 0) return;
        var elapsed = (DateTime.UtcNow - playStart).TotalSeconds;
        Log.Warning("[Lesson] PlaybackStopped未発火のためタイムアウトで次へ (elapsed={E:F2}s, duration={D:F2}s, state={S})",
            elapsed, duration, waveOut.PlaybackState);
        tcs.TrySetResult();
        // このケースでは Dispose はしない — 音声まだ鳴っている可能性があるので次の PlayLessonAudioAsync 冒頭の oldWaveOut.Stop/Dispose に任せる
    });

    return tcs.Task;
}
```

### 各要素の意図

**(1) ハンドラ順序変更 — `tcs.TrySetResult()` を Dispose より先に**
- 仮説1（`Dispose` 内デッドロック）が正しい場合、これ単独で修正になる
- `Dispose` がハングしても `await` は既に解放済みなので次のダイアログに進める

**(2) Dispose を `Task.Run` で別スレッドに逃がす**
- 仮説1 の自己デッドロックを根本的に回避
- 新しい `PlayLessonAudioAsync` 冒頭で `oldWaveOut.Stop/Dispose` が呼ばれるパスと競合しないよう、`_lessonWaveOut` の張替えは Task.Run 内でまとめて行う

**(3) duration フォールバック — 保険**
- 仮説2 やその他の未知原因でも授業が確実に進行する
- 正常系にペナルティなし: `PlaybackStopped` が先に発火すれば `completed==1` でフォールバック側は早期 return

**(4) `Interlocked.CompareExchange` による原子化**
- `completed` フラグは PlaybackStopped コールバックスレッドと Task.Delay 継続スレッドから同時アクセスされる
- 単純 `bool` ではメモリ可視性・競合の保証がないため `int` + CAS で明示的に1回だけ完了させる

**(5) フォールバックに `CancellationToken` を渡す**
- `Stop()` 時にフォールバック Task.Delay もキャンセルされ、無駄な警告ログや後続への干渉を防ぐ
- `LessonPlayer._cts.Token` を `PlayAudio` 経由で渡す

**(6) 発火タイミングログ**
- PlaybackStopped 発火時刻・フォールバック発火時刻・その時点の `waveOut.PlaybackState` を両方記録
- 警告が出続ければ仮説2 寄り、出なければ仮説1 を修正したことで解消したと判断できる

### マージン 1.5秒 の根拠

- NAudio の WaveOutEvent はバッファ末尾の再生完了を検知するのに数百ms〜1秒のラグがある
- 授業のセリフ間300msギャップに対して、1.5秒の超過は許容範囲
- 音声が途切れるリスクを避ける側に倒す（もし将来タイトに詰めたければ `PlaybackState == Playing` の追加ポーリングで延長する拡張が可能）

## 実装ステップ

1. [x] `LessonPlayer.cs` の `PlayAudio` シグネチャを `Func<byte[], float, double, CancellationToken, Task>?` に変更
2. [x] `PlayDialoguesAsync` の呼び出しを `await PlayAudio(dlg.WavData, 1.0f, dlg.Duration, ct)` に変更
3. [x] `MainForm.cs` の `PlayLessonAudioAsync` に `double duration, CancellationToken ct` 引数追加
4. [x] `PlaybackStopped` ハンドラで `Interlocked.CompareExchange` による原子的完了判定 + `tcs.TrySetResult()` を先に、`Dispose` 一式は `Task.Run` で後に
5. [x] フォールバック `Task.Run(async () => { Task.Delay(duration + 1.5, ct); ... })` を追加（`ContinueWith` は使わない）
6. [x] PlaybackStopped・フォールバック両方で発火時刻と `PlaybackState` をログに出す
7. [ ] ビルド＆動作確認: `./stream.sh` → 授業再生 → 全8セクション・37ダイアログが順次再生されること **（前提: 全TTSが事前生成済み）**
8. [ ] ログ確認: `PlaybackStopped未発火のためタイムアウトで次へ` の警告頻度を確認
    - 出ない → 仮説1 が原因、ハンドラ順序修正で解消
    - 毎回出る → 仮説2 が原因、NAudio の代替（例: `WaveOut`/`DirectSoundOut`）検討が次フェーズ
    - 時々出る → デバイス状態依存、現状のフォールバックで実用上問題なし

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| duration より実際の音声が長い | セリフが途中で切れる | マージン1.5秒。Python側は `wave` モジュールで正確算出しているので基本的に不一致なし |
| PlaybackStopped が後から発火して二重に tcs 完了 | 影響なし | `Interlocked.CompareExchange` で1回だけ処理、`TrySetResult` も冪等 |
| フォールバック発火時にまだ音声再生中 → 次のダイアログと被る | 音が重なる一瞬 | 次の `PlayLessonAudioAsync` 冒頭の `oldWaveOut.Stop/Dispose` で強制停止されるため、実害は数10ms程度 |
| フォールバックが常に走る（仮説2 が真） | ログに警告が出続ける | 警告ログの頻度を見て次フェーズでNAudio代替を検討。機能としては正常動作 |
| `Stop()` 時にフォールバックが孤立 | 停止後に無駄なログ・tcs更新 | `CancellationToken` でキャンセル |

## 完了条件

- 授業（English 1-1 v8 など）を開始すると全セクション・全ダイアログが最後まで再生される
- `lesson_complete` Push通知が C# から返る
- Python側の `_wait_lesson_complete` が正常に完了してDB永続化がクリアされる
