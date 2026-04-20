# 録画モードのAV同期ずれ修正

## ステータス: wallclock対応は実装完了／C→B1→B2 まで実施済み、B2 計測完了→C+A 案へ進む

## 背景

`plans/client-video-recording.md` で実装した録画機能で、生成されるMP4の**音と映像がずれる**問題が報告されていた。
配信（Twitch RTMP）では Twitch 側の同期吸収があるため目立たないが、録画ファイルをローカル再生するとズレが顕在化していた。

原因の切り分けは `plans/recording-av-sync-verification.md` で 3 ビルド（default / wallclock / pacer）を比較して完了済み。
結論: **`-use_wallclock_as_timestamps 1`（wallclock）** を採用。

## 原因（検証済み）

現行の映像入力は `-framerate 30 -f rawvideo` で FFmpeg に渡すため、FFmpeg は**フレームに `frame_index × (1/30s)` の PTS** を付ける（到着時刻ではない）。
一方、音声は C# 側の 10ms タイマー + `Environment.TickCount64` で**実時刻レート**で書いている。

この 2 つが別時計のため、WGC キャプチャの実到着レート（平均 30.32fps など、微妙に 30 からズレる）と PTS（30fps 固定）の差が累積し、**50 秒で +533ms の線形ドリフト**が計測された。

映像入力に `-use_wallclock_as_timestamps 1` を付けると FFmpeg は**読み取り実時刻で PTS を打つ**ので、キャプチャレートが揺れてもドリフトが累積せず、ドロップ時も「時間圧縮」ではなく「直前フレームが停止」として表現される。

音声は既に実時間で動いているため、映像 PTS が実時刻に揃えば音声と自動的に同期する。

## 方針

録画モード（`OutputMode.File`）のとき**常に** `-use_wallclock_as_timestamps 1` を映像入力に付与する。配信モード（RTMP）は従来通り（検証対象外・運用実績あり）。

- **音声**: 従来通りの C# 側タイマーベースジェネレータ（TTS + BGM + SE を合成してパイプに書く）を維持。WASAPI Loopback 方式は採用しない（複雑さが増える割に wallclock 単独で AV 同期は成立する）
- **映像**: `OutputMode.File` のとき `-use_wallclock_as_timestamps 1` を付ける
- **切替フラグなし**: 検証用に導入した `VideoTimingMode` enum / `--video-timing` CLI / `VIDEO_TIMING` 環境変数、および Pacer モードの実装はすべて削除

## 実装内容

| ファイル | 変更 |
|----------|------|
| `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs` | `OutputMode.File` のときに常に `-use_wallclock_as_timestamps 1` を映像入力へ付与。Pacer 実装・`_pacer*` フィールド・`_dupCount` / `DupCount` をすべて削除 |
| `win-native-app/WinNativeApp/Streaming/StreamConfig.cs` | `VideoTimingMode` enum・`VideoTiming` プロパティ・`--video-timing` / `VIDEO_TIMING` パース処理を削除 |
| `stream.sh` | `--video-timing` フラグの Usage / オプション説明を削除。`--av-sync-test` は回帰検証用に残置 |
| `static/av_sync_test.html` | 検証素材として保持（将来の回帰検証に使う） |
| `scripts/verify_av_sync.py` | 計測スクリプトとして保持 |

## 既知のトレードオフ

検証で確認された、wallclock 単独方式に残る軽微な特性:

- **先頭 -700ms の定数オフセット**: FFmpeg 初期化中にパイプへ書いた初期黒フレームが init 完了時刻で刻印され、後続の実フレームと時間的に詰まるため、最初のフラッシュが理想より 700ms 早く見える。2秒目以降は ±1 フレームの量子化のみで追従するため、録画長に依存せず定数。
- 音声も同じ初期遅延を経由するため、**音声との相対位置はゼロで吸収される**見込み（要目視確認）。もしズレる場合は `-itsoffset` で補正する。

## 目視確認で判明した残課題（2026-04-19）

実TTS発話ありの 60〜90 秒録画を VLC で目視確認したところ、**音声が口パクに対して約 2 秒遅れる**問題が判明した。

### C: 診断ログから判明した原因

C# 側の FfmpegProcess.cs に `[AVSync]` 診断ログを追加し、1 本の録画で以下のタイムラインを実測（`t=` は FFmpeg プロセス起動を 0 とする相対 ms）:

```
t=   78ms : FFmpeg起動 → 黒フレーム書き込み・音声パイプに 300ms silence プライム
t=  594ms : audio generator 起動（TickCount64 駆動、10ms tick）
t=  672ms : 最初の実WGC映像フレーム書き込み
t= 6656ms : FFmpeg エンコード開始（stderr "frame=" 初出）
t=25265ms : 最初のTTS到着 → 即 mix 開始（enqueue→mix lag=0ms）
...       : TTS chunk pulled audioQ=100（＝_audioQueue 上限飽和）
```

**根本原因**: generator → AudioWriterLoop 間の `_audioQueue` が恒常的に満杯（`MaxAudioQueueChunks = 100` ＝ 約 1 秒分）。generator は 10ms ごとにチャンクを積むが、FFmpeg のエンコード開始時点（t=6.6s）で 6 秒分の内部 catch-up が必要になり、その間にキューが一気に埋まる。以後は定常的に飽和状態を維持。

結果:
- TTS の PCM は generator で mix された後、キュー末尾に積まれ、パイプに到達するまで **約 1 秒遅延**
- これに「プライム silence 300ms」のオフセットが加わり、**音声 PTS は wallclock より 1.2〜1.5 秒遅い**
- 目視観測「2 秒遅れ」とほぼ整合（0.5〜1 秒の目視誤差を許容）

また、この遅延の計算中に **`StreamConfig.AudioOffset` が FFmpeg 引数に反映されていない死にコード** であることも発見（`FfmpegProcess.cs:144` でログ出力のみ、args 組立に登場しない）。

### B1: AudioOffset を `-itsoffset` として配線（実施済み、副作用あり）

`FfmpegProcess.cs` で音声入力に `-itsoffset {AudioOffset}` を追加し、デフォルト -0.5 のまま再録画。結果:

| 指標 | B1 前（itsoffset 無し）| B1 後（itsoffset -0.5）|
|------|------|------|
| 音声 duration - 映像 duration | +1.62s | +1.01s |
| 実映像 fps | 28.4 | **24.6** |
| 映像ドロップ | 125 (2.8%) | **415 (12.4%)** |
| パイプ遅延 slow 回数 | 2 | **37** |

音声遅延は一部改善したが、**映像 fps と pipe write が明確に悪化**。推測: `-itsoffset -0.5` 指定により muxer が音声到着を待つ分 back-pressure が映像パイプに伝わり、speed=1.04x とギリギリの状態を崩した。

### B2: `MaxAudioQueueChunks` の縮小（実施済み、計測完了）

- `FfmpegProcess.cs`: `MaxAudioQueueChunks` 100（約1秒） → **10（約100ms）** に縮小
- `StreamConfig.cs`: `AudioOffset` デフォルトを **-0.5 → 0** に戻し、B1 の `-itsoffset` を実質無効化

#### 計測結果（2026-04-19 22:11〜22:21、9分45秒・授業再生）

| 指標 | B1 前 | B1 副作用 | **B2** |
|---|---|---|---|
| audio queue depth | 恒常 ~100（飽和）| ~100 | **99% が 0〜1、最大 10**（cap） |
| TTS enq→mix lag | 0ms | 0ms | **16ms** |
| fps | 28 | 26 | **30** |
| ドロップ率 | 2.8% | 12.4% | **1.9%** |
| パイプ遅延 slow | 2 回 | 37 回 | **3 回** |
| MP4 duration 差（音声−映像）| +1.62s | +1.01s | **+0.85s** |
| 音声ドロップ | 11 | 11 | **2055**（≒20s分、3.5%）|

→ B1 副作用は完全解消。音声 PTS の蓄積遅延も解消。**ただし以下の新症状が出た**:

#### B2 で残った症状（VLC 目視・ユーザー報告）
1. **音がぶつぶつ鳴る**: cap=10 到達時に古いチャンク（過去 10ms）から捨てる設計のため、頻繁な小ドロップが「音切れ」として知覚される
2. **0.5 秒の遅延が出るときと合うときが混在**: キュー深さが 0〜10 で揺らぐため、再生時の音声遅延も 0〜100ms で揺らぐ
3. ログ実測: 3.5 ドロップ/秒、深さは 0〜1 で安定だが瞬間的に 10 までスパイク

→ 100→10 に絞りすぎてジッタ吸収余裕がなくなったのが原因。

### C+A: cap=30 + AudioOffset=-0.3（次に実施）

- `FfmpegProcess.cs`: `MaxAudioQueueChunks` 10 → **30**（上限 300ms に緩和）
  - ジッタ吸収余地を確保 → ドロップ激減 → ぶつぶつ解消見込み
  - 最悪遅延 100ms → 300ms（B1 の 1000ms よりは十分マシ）
- `StreamConfig.cs`: `AudioOffset` デフォルトを **0 → -0.3**
  - 平均堆積 ~150ms＋プライム 300ms＋初期遅延 の合計 ~500ms オフセットを補正
  - 「合うとき」「ずれるとき」の中央値をゼロに寄せる
- B1 副作用の本格復活はしない見込み（cap=100 → 10 で副作用解消、cap=30 はその間）

#### 検証手順（C+A 適用後）
1. `./stream.sh --stop && ./stream.sh` で再ビルド・起動
2. 授業再生を 60〜90 秒以上、TTS 発話ありで録画
3. VLC で目視確認: 「ぶつぶつ」「中央値の口パクズレ」「最大ズレ幅」
4. ログ確認: `[FFmpeg] Audio queue: depth=...` の推移と drops/10s、`[FFmpeg] === 配信終了レポート ===` の fps/drop/slow が B2 と同等を維持しているか
5. MP4 duration 差（音声−映像）が +0.5s 以下に収まっているか

#### C+A で不十分な場合の選択肢
- **D 案**: cap=50, offset=-0.5（保険最大、ぶつぶつ最優先）
- **A 案単独再調整**: cap=30 のまま offset を -0.4 や -0.5 に振る

## 長尺確認（別タスク）

60 秒録画では 30 分長尺のドリフト累積まで検証できていないため、B2/A 完了後に別途実施する。TODO.md 側で分離して管理。

## 参考（診断ログ追加箇所）

`[AVSync]` プレフィックス付きで以下をログ:
- `FfmpegProcess.StartAsync`: 黒フレーム書き込み時、silence プライム時、エンコード開始検知時
- `FfmpegProcess.StartAudioGenerator`: 起動時
- `FfmpegProcess.WriteTtsData`: 初回 TTS enqueue 時
- `FfmpegProcess.MixTtsInto`: TTS chunk 取得時（毎回、audioQ 深度付き）
- `FfmpegProcess.WriteVideoFrame`: 初回実 WGC フレーム書き込み時
- `FfmpegProcess.StopAsync`: summary 行で全マイルストーン

## リスクと対策

| リスク | 影響度 | 対策 |
|--------|--------|------|
| TTS と映像がズレる（初期オフセットが相殺されない） | 中 | `-itsoffset` でどちらかのストリームに補正を入れる |
| 配信モード（RTMP）の挙動が変わる | 低 | 配信側は `OutputMode.Rtmp` のため wallclock 条件分岐に入らない（変更なし） |
| フレーム停止が長時間続く見た目の違和感 | 低 | ドロップ時は直前フレームを表示し続けるが、通常運用では数フレーム程度。速度の揺らぎではなくヒッチとして自然に見える |

## 参考

- 検証記録: `plans/recording-av-sync-verification.md`
- FFmpeg [use_wallclock_as_timestamps](https://ffmpeg.org/ffmpeg-formats.html#Format-Options)（入力フォーマット共通オプション）
- 計測結果（60秒録画、flash カウント 50+）:
  - default: +10.7ms/秒で線形累積 → 長尺で悪化
  - **wallclock: flash 1 以降 ±1フレーム jitter のみ（stdev 95ms、累積 -33ms/50秒）→ 採用**
  - pacer: 実装バグで初期 +2667ms の定数オフセット → 不採用
