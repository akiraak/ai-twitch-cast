# Claude Code 実況のセリフ間隔が長い問題の調査

## ステータス: 完了（実装: `plans/claude-narration-chain-playback.md`）

## 結論（2026-04-18 調査）

**本命原因**: `_wait_tts_complete` がC#の `IsTtsActive`（FFmpegミキサーキューの在庫）をポーリングしており、**ユーザーが聞くNAudioローカル再生が終わった後もFFmpegキューの消費待ちで2〜3秒余分に待ってしまう**。配信ストリームも real-time でエンコードされるため、キュー消費遅延はそのまま「セリフ間の無音」として現れる。

**採用する対策**: `plans/claude-narration-chain-playback.md`（仮説D：チェーン再生）。Claude Code 実況に限定して、全エントリのWAVを一括で C# へ送信 → C#キューが順次再生 → 各エントリの再生開始を Push で Python に伝達 → 字幕・口パク・感情を発火する構成に変更する。

**狙い**: 理論的にセリフ間の無音を0に近づける。`_wait_tts_complete` のポーリング余剰（中央値2.4秒）・inter-speaker pause 0.3秒・送信レイテンシ 0.23秒 がすべて消える。

### 実測した値（server.log 抜粋、2026-04-13〜14）

| 指標 | 観測範囲 | 中央値 |
|---|---|---|
| `TTS完了待ち: N.N秒追加` の N | 1.4〜6.0秒（外れ値 18.8秒） | 2.4秒 |
| entry#0→entry#1 の実測間隔（01:46:28 → 01:46:36） | 8.0秒（duration≈5.3s）→ 無音ギャップ 2.7秒 | — |
| `C#音声投入完了` | 47〜373ms | 約200ms |

外れ値 18.8秒（23:19:04）は長いTTSでの polling 上限（duration * 0.5）に貼り付いた痕跡で、やはりキュー消費遅延が主因と推定される。

### コードの現状確認（2026-04-18）

- `src/speech_pipeline.py:220-224` — `sleep(duration + 0.1)` → `_wait_tts_complete(max_extra=duration*0.5)` のポーリング実装のまま
- `win-native-app/WinNativeApp/MainForm.cs:886-892` — `OnGetTtsStatus` が `IsTtsActive`（配信中）か `_ttsWaveOut.PlaybackState`（非配信時）を返す従来実装
- `win-native-app/WinNativeApp/MainForm.cs:1387-1400` — TTS用 `PlaybackStopped` ハンドラはまだ Push 通知を出さない（授業プレイヤー `LessonPlayer` 側は `PlaybackStopped` ベースの完了待ちを既に実装済み → 参考になる）
- `win-native-app/WinNativeApp/Server/HttpServer.cs:469, 663-666, 791` — `tts_status` ハンドラ生存・`BroadcastWsEvent` は既に利用可能
- `scripts/services/capture_client.py:200-204` — `lesson_complete` の Push 受信は既実装。同じ要領で `tts_complete` を追加する前例あり

### 実装着手判断

`plans/tts-wait-excess-delay.md` の Step 1〜5 をそのまま実行する。変更ファイルと影響範囲は同プランに明記済み。TODO.md のリンクを同プランへ付け替える。

---

以下は初期調査メモ（残す）。

## 背景

Claude Code 実況（Hookフック経由の掛け合い発話 & `ClaudeWatcher` の定期実況）は、先に `plans/archive/dialogue-parallel-tts.md` で **全エントリのTTSを並列事前生成**する最適化を済ませた。TTS生成待ちは entry#0 で〜5秒、以降は `await完了 0ms`（事前生成済み）となり、ログ上は理論通り動いている。

それでも視聴体験では **セリフ1とセリフ2の間に数秒の「間」が残る** と報告されている。本プランではその原因を切り分け、具体的な対策候補を整理する。

## 実測ログ（server.log より）

並列TTSが効いているケースでも、`send_tts_to_native_app`（音声投入）のタイムスタンプ基準で次のような状況:

```
01:46:28  [event][parallel] entry#0 await完了: 5129ms (wav=pre-generated)
01:46:28  [tts] C#音声投入完了: 233ms
            ↓ この間に 8秒 の「間」
01:46:36  [tts] TTS完了待ち: 2.6秒追加        ← _wait_tts_complete の timeout消費
01:46:36  [event][parallel] entry#1 await完了: 0ms (wav=pre-generated)
01:46:36  [tts] C#音声投入完了: 231ms
```

entry#0 の音声長が約 5.3s と仮定すると、サーバー側の待ち時間内訳:

| 項目 | 実測値 | 由来 |
|---|---|---|
| `await asyncio.sleep(duration + 0.1)` | ~5.4s | `src/speech_pipeline.py:221` |
| `_wait_tts_complete(max_extra=duration*0.5)` | ~2.6s | `src/speech_pipeline.py:224` |
| `await asyncio.sleep(0.3)`（inter-speaker pause） | 0.3s | `src/comment_reader.py:613`, `claude_watcher.py:429` |
| `send_tts_to_native_app` 次回送信分 | ~0.23s | 上のログから |
| **合計** | **~8.5s** | |

視聴者が知覚する「前のセリフ終了 → 次のセリフ開始」のギャップは概ね:

```
gap_on_stream ≈ _wait_tts_complete_extra + 0.3 + send_latency ≈ 3.1秒
```

短く見積もっても2〜3秒、長い音声だと最大で `duration*0.5 + 0.3 + 0.23 ≈ 3〜5秒` の「間」が挟まる。体感で「長い」と感じる主因はこの **C# 側 TTS 完了待ちの余剰** と結論付けて差し支えない。

## 現状の送信タイミング（重要な前提）

**Q. 掛け合いの全セリフは、クライアント(C#)に送信し終わってから再生を開始しているか？**

**A. NO。TTS生成は並列だが、C#への送信・再生は完全な直列パイプライン。**

```
[TTS生成]      entry#0 ┓
               entry#1 ┣━━ 並列起動（既に実装済み）
               entry#2 ┛

[C#へ送信]     entry#0 送信 → 再生完了を待つ(duration + _wait_tts_complete)
                                   → entry#1 送信 → 再生完了を待つ
                                                         → entry#2 送信 → ...
```

実装箇所:
- `src/comment_reader.py:601-630` (`speak_event`)・`src/claude_watcher.py:407-465` (`_play_conversation`) とも、ループ内で `await self._speech.speak(..., wav_path=wav, ...)` を呼ぶ
- `SpeechPipeline._speak_impl` (`src/speech_pipeline.py:192-224`) は:
  1. `send_tts_to_native_app(wav_path)` で **1エントリだけ** C# に送信
  2. `await asyncio.sleep(duration + 0.1)` で再生分待つ
  3. `await self._wait_tts_complete(max_extra=duration*0.5)` で完了確認
  4. ここまで終わって初めてループが次のentryに進み、次の送信が始まる

一方 C# 側は:

- `_ttsQueue = ConcurrentQueue<byte[]>`（`FfmpegProcess.cs:49`）に **複数チャンクを積める**
- `MixTtsInto`（`FfmpegProcess.cs:520-551`）は `_ttsCurrentChunk` を消費しきったら即 `_ttsQueue.TryDequeue` するので、**キューに2つ以上入っていれば物理的に隙間ゼロでチェーン再生される**
- つまり C# 側は「複数セリフを先行して積まれる」ことを前提に設計されているのに、サーバー側がそれを使っていない

### 含意

これは「仮説D（チェーン再生）」と同じ方向の発見で、**改善余地としてはむしろ本命**。字幕・口パク・感情切替の同期という副次課題があるが、解消すればエントリ間ギャップを **理論的に0秒** まで詰められる。

逆に、「全セリフ送り終えてから再生開始」のような**バッファリング開始遅延**は発生していない（entry#0 は受信直後に再生される）。問題は「次エントリが来るまでに既存エントリが再生し切ってしまい、空き時間ができる」こと。

## 仮説

### 仮説A: `IsTtsActive` の報告が実際の再生終端から数秒遅れる（本命）

C# `FfmpegProcess.IsTtsActive` は:

```csharp
public bool IsTtsActive => _ttsCurrentChunk != null || !_ttsQueue.IsEmpty;
```

- `_audioGenTimer` は 10ms 間隔で発火し `elapsedMs = Clamp(1, 50)` に応じた量のPCMを `_ttsQueue` からドレインする
- 理論上は実時間と同速度でドレインされるが、以下で遅延する可能性:
  - タイマージッタ（GCやOSスケジューラで 10ms → 数十msになる）
  - `_audioQueue > MaxAudioQueueChunks` 時のバックプレッシャ（ただしTTS drainは影響しない作り）
  - `ConcurrentQueue.TryDequeue(out _ttsCurrentChunk)` 失敗時は null がセットされるため「古いチャンクが残り続ける」バグは無さそう（再確認必要）

実測の 2.6s 余剰は `max_extra = duration * 0.5` の上限一杯、つまり「ポーリングのタイムアウトまで `active: true` を観測している」可能性が高い。**真に再生が終わっているのに `active: true` と返っている** のか、**実際にC#内で再生が遅れている** のかを切り分ける必要がある。

### 仮説B: `duration + 0.1` の待機が既に過剰（副次的）

`wave.open().getnframes() / getframerate()` は入力WAV（24kHz mono）のサンプル数ベース。C#は 48kHz stereo f32le にリサンプルする（2倍サンプル数、同じ時間長）。理論上は過不足なし。ただし `_audioGenTimer` の発火遅延が蓄積するとPython側の sleep がC#の実再生より早く切り上がることもありうる。

### 仮説C: `asyncio.sleep(0.3)` の inter-speaker pause が冗長

掛け合い実装時に「人間らしい間」として入れた 0.3秒だが、すでに `_wait_tts_complete` で 2.6秒待たされているので重複して長くなっている。

### 仮説D: C#の `_ttsQueue` にそもそもチェーンできる

`MixTtsInto` は `_ttsCurrentChunk` を消費し切ったら即 `_ttsQueue.TryDequeue` する構造なので、**複数のTTSチャンクをキューに積めば隙間なく再生される**。つまり現状のアーキテクチャなら「entry#0 の再生を待たずに entry#1〜N を全部 C# に送ってしまえば無音ギャップはゼロ」になる可能性がある。

## 調査ステップ

### Step 1: ギャップの構成要素を定量化

- `server.log` から直近10件の掛け合い発話を抽出し、entry#n ごとに:
  - `C#音声投入完了` のタイムスタンプ
  - `TTS完了待ち: N.N秒追加` の N
  - entry#(n-1) 終了から entry#n 開始までの実測ギャップ
  を表にする
- C#側 `Serilog` の TTS関連ログ（`TtsDecoder` の duration 出力・ `_audioGenTimer` のジッタ）も合わせて確認

### Step 2a: 送信タイミングの検証（簡易実験）

最小コストで効果を確認するには、上述「現状の送信タイミング」のボトルネックを崩す実験が有効:

- `speak_event()` / `_play_conversation()` を改変し、**ループ前に全エントリを `send_tts_to_native_app` で C# に投入してから** 順次 `notify_overlay` / `lipsync` / 感情切替を発火する暫定版を作る
- 音声が詰まって鳴り続けるが、視聴体験としてエントリ間のギャップがどこまで縮まるかを定性的に確認
- 字幕・口パクの同期ズレは別途対処する前提（この段階では計測専用）

### Step 2b: `IsTtsActive` の精度を検証

C# に一時的にログを追加:

- `MixTtsInto` で `_ttsCurrentChunk` を消費しきった瞬間にタイムスタンプを出す
- `HandleWsTtsStatus` が呼ばれた瞬間と `active` の値もログ
- Python側 `_wait_tts_complete` のポーリングで受けた `active` と合わせて時系列比較

目的: 「実際の再生終端」 と 「`active: false` になる時刻」 のラグを測定。**ラグがゼロなら仮説A棄却**（本当に再生が遅れている → 仮説Bに進む）、**ラグが2秒前後ならフラグ報告の遅延**（Cの修正で治る）。

### Step 3: 改善策の候補出し

調査結果に応じて以下のいずれか／組合せを採用する:

#### A. `_wait_tts_complete` の `max_extra` を縮める

- 現在 `duration * 0.5`（最大 2.5s） → 固定 0.3〜0.5s 程度
- 長い音声で再生が遅延した場合は切り詰まるリスクがあるが、ポーリングではなく **C# からの "tts_done" プッシュ通知** に切り替えると完全に解決

#### B. `asyncio.sleep(0.3)` を 0 か 0.1s に縮める

- `_wait_tts_complete` ですでに充分な間が発生しているため重複解消

#### C. 次エントリを先行投入（チェーン再生）

- `speak()` 内で `send_tts_to_native_app` → `sleep(duration)` → 字幕発火までを分離し、**次エントリのWAVをC#に先行して送って `_ttsQueue` に積んでおく**
- C# は `_ttsQueue` を自動でチェーン消費するので、entry間のギャップは物理的にゼロになる
- 難しさ: 字幕・口パク・emotion切替の同期タイミングをどうC#側から取るか
  - C#側に `tts_chunk_started` / `tts_chunk_ended` イベントを追加し、サーバーへWebSocketプッシュ
  - サーバーはそれを受けて字幕・口パクを発火

#### D. C#側 `_audioGenTimer` のジッタ改善

- もし実測で真にドレインが遅れているなら、10ms Timer を高精度タイマー（`MultimediaTimer` 等）に置換

### Step 4: 影響範囲の整理

本問題は Claude Code 実況だけでなく **掛け合いモード全般（Twitchコメント応答・授業の対話セクション・コミット報告）** に影響する。修正は以下の4箇所に波及する:

| コール元 | ファイル |
|---|---|
| Hook掛け合い | `src/comment_reader.py` `speak_event()` |
| 分割セグメント | `src/comment_reader.py` `_speak_segment()` |
| ClaudeWatcher | `src/claude_watcher.py` `_play_conversation()` |
| WebUIチャット | `src/comment_reader.py` `respond_webui()` |

### Step 5: 実装 → 検証

- 採用案の実装
- `server.log` で同じ指標（`C#音声投入完了` 間隔）を測り、改善前後で比較
- `python3 -m pytest tests/ -q` でリグレッションチェック
- サーバー起動＋実配信で視聴体験を確認

### Step 6: ドキュメント更新

- `docs/speech-generation-flow.md` の掛け合いセクションに「チェーン再生」の仕様を追記
- `MEMORY.md` / `.claude/projects/.../memory/tts-audio.md` 更新

## リスク・注意点

1. **チェーン再生（C案）はC#↔サーバの状態同期が必要** — `tts_chunk_ended` 通知を追加する設計変更が入る。スコープが膨らむ場合はまずA/B案（タイマ調整）で様子を見る
2. **短いmax_extraで切り詰める** と、稀にC#再生が本当に遅れたとき音声が重なる。`duration` を少し長めに見積もる安全策とセットで
3. **Twitch配信側の遅延** は本プランで改善できない（ingest bufferが別途2〜3秒あるが、視聴者が知覚するのは **セリフ間の相対的な間隔** なので関係しない）
4. **字幕・口パクの同期** — C#先行投入（C案）に進む場合、Pythonで `notify_overlay` + `lipsync` を発火するタイミングを C# からの通知ベースに変える必要がある。既存の `speaking_end` イベントの扱いも要見直し

## 対象ファイル（実装時）

| ファイル | 想定変更 |
|---|---|
| `src/speech_pipeline.py` | `_wait_tts_complete` の `max_extra` 調整、または削除してイベント駆動化 |
| `src/comment_reader.py` | inter-speaker pause 調整、チェーン再生時のspeak呼び出し順序変更 |
| `src/claude_watcher.py` | 同上 |
| `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs` | 必要に応じて `_ttsCurrentChunk` 消費終了イベントの発火 |
| `win-native-app/WinNativeApp/Server/HttpServer.cs` | `tts_done` プッシュ通知の送信 |
| `scripts/services/capture_client.py` | `tts_done` 受信ハンドラ |
| `docs/speech-generation-flow.md` | フロー図と仕様更新 |

## 完了条件

- 掛け合い 2〜4 エントリの再生で、視聴者体感のエントリ間ギャップが **1秒以下** まで縮まる
- `server.log` の `C#音声投入完了` 間隔が `duration + (0.5秒以内)` に収まる
- TTS再生が切り詰められる回帰がない
- `python3 -m pytest tests/ -q` パス
