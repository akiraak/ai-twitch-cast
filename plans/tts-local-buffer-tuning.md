# C#ローカルTTS再生のバッファ縮小でセリフ間ギャップを詰める

## ステータス: 未着手

## 背景

`plans/claude-narration-chain-playback.md` のチェーン再生実装により、Claude Code 実況のエントリ間ギャップは Python 側の直列ポーリング起因分は解消済み。サーバー側は全TTSを並列生成→`speak_batch` で C# に一括送信→`tts_entry_started` Push 駆動で字幕/口パク/感情を発火する構成になっている。

一方でユーザーの体感としては、セリフとセリフの間にまだ短くない「間」が残っている。ソースを読むと、残るボトルネックは **C#ローカル再生（NAudio `WaveOutEvent`）の再生エンジン再起動コスト** に集中している。

### 残っている「間」の発生源（確認済み）

| 箇所 | 発生源 | 推定遅延 |
|---|---|---|
| `MainForm.cs:1475` | `new WaveOutEvent()`（`DesiredLatency` 既定=300ms）— バッファが埋まってから再生開始 | 〜300ms |
| `MainForm.cs:1484` | `PlaybackStopped` は内部バッファが完全に空になってから発火 → `DequeueAndPlayNextLocal` への遷移遅延 | 〜300ms |
| `MainForm.cs:1471-1476` | 毎エントリで `WaveFileReader` + `WaveChannel32` + `MeteringWaveProvider` + `WaveOutEvent` を新規生成・初期化 | 数十ms |

合算で **数百ms〜600ms** のエントリ間無音が残る。

## 方針

`PlayTtsLocally` の `WaveOutEvent` に `DesiredLatency` と `NumberOfBuffers` を明示指定してバッファを縮める。デフォルトの `DesiredLatency=300, NumberOfBuffers=3`（合計 900ms のPCMを内部保持）から段階的に縮小する。

### ステップ

1. **段階1（安全域）**: `DesiredLatency=100, NumberOfBuffers=3`
   - 再生開始/終了の両端で約200msずつ短縮を狙う
   - 音切れが出ないことを配信 + ローカルの両方で確認
2. **段階2（積極）**: 段階1で問題なければ `NumberOfBuffers=2` に削る
   - さらに100〜200ms短縮
3. **段階3（要実装）**: 依然として不足なら以下を検討
   - `WaveOutEvent` を使い回し、`BufferedWaveProvider` で差し替える（初期化コスト0）
   - `PlaybackStopped` を待たず、現在再生中WAVの残時間が閾値以下になったら次エントリの `Init()` を先行実行（プリロール）
   - TTS 生成時に WAV 末尾の無音をトリム（`src/tts.py`）

## 対象ファイル

| ファイル | 想定変更 |
|---|---|
| `win-native-app/WinNativeApp/MainForm.cs` | `PlayTtsLocally` 内の `new WaveOutEvent()` に `DesiredLatency` / `NumberOfBuffers` を設定 |

※ `PlayLessonAudioAsync`（授業用）は対象外。授業は既に `LessonPlayer` で独自のチェーン実装があり、挙動を揃える場合は別タスクとする。

## リスク

1. **音切れ・プツッとしたノイズ**（最大リスク）
   - バッファ縮小でGCポーズ・スレッドスケジューリング遅延時にアンダーランが起きる
   - 本アプリは同時にFFmpegエンコード・WebView2・WGCキャプチャ・WS通信を走らせておりCPUスパイクの可能性がある
2. **短いWAVでの `PlaybackStopped` 不安定**
   - 極端にバッファを小さくすると NAudio の再生終了判定がずれる報告がある
   - チェーン再生は `PlaybackStopped` に依存しているため、不安定化すると次エントリ未発火/二重発火の可能性
3. **配信視聴者への影響は基本なし**
   - NAudioローカル再生は開発者のスピーカー用。Twitch配信音声は FFmpeg経路（`TtsDecoder`）で別送
   - ただし配信用ミキサーにもローカル経路のタイミング基準が間接的に使われていないか、実装時に再確認

## 検証

- `stream.sh` で配信アプリ起動 → Claude Code実況が連続発話するシナリオで:
  - エントリ間のギャップが体感で短縮されているか
  - プツッとしたノイズ・音切れがないか
  - `tts_entry_started` / `tts_batch_complete` Push が正常発火しているか（`jslog.txt` / `server.log`）
- 授業再生は対象外だが、同じプロセス内で動くため副作用がないかざっと確認
- `python3 -m pytest tests/ -q` でリグレッションチェック（C#側変更なのでPythonテストは影響ないはず）

## 完了条件

- Claude Code 実況のエントリ間ギャップが 200ms 以下に収まる（体感および server.log の `tts_entry_started` タイムスタンプ間隔）
- 5分以上の連続実況でノイズ・音切れが発生しない
- 配信・ローカル両方で音質劣化がない
