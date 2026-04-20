# 録画モードのAV同期ずれ修正

## ステータス: C→B1→B2→C+A→E まで計測完了。**対症療法の限界に到達**→ 根本方針（α/β/γ/δ）の選定中

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

### C+A: cap=30 + AudioOffset=-0.3（実装済み、計測待ち）

- `FfmpegProcess.cs`: `MaxAudioQueueChunks` 10 → **30**（上限 300ms に緩和） ✅
  - ジッタ吸収余地を確保 → ドロップ激減 → ぶつぶつ解消見込み
  - 最悪遅延 100ms → 300ms（B1 の 1000ms よりは十分マシ）
  - コメントを「B2 100ms」→「C+A 300ms、中間点の根拠」に更新
- `StreamConfig.cs`: `AudioOffset` デフォルトを **0 → -0.3** ✅
  - 平均堆積 ~150ms＋プライム 300ms＋初期遅延 の合計 ~500ms オフセットを補正
  - 「合うとき」「ずれるとき」の中央値をゼロに寄せる
  - XML doc を「B2 で 0」→「C+A で -0.3」に更新
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

### C+A 計測結果（2026-04-19 22:53〜22:57、3分6秒・授業再生）

| 指標 | B2 | **C+A** |
|---|---|---|
| fps | 30 | **30** |
| 映像ドロップ率 | 1.9% | **2.3%**（ほぼ同等） |
| パイプ slow | 3 回 | **1 回**（起動時 h264_qsv 初期化のみ） |
| 音声ドロップ（分換算）| ~211/分 | **~170/分**（あまり減っていない） |
| depth 振る舞い | 最大 10 | **0⇄30 を振動**（cap 到達で drops 継続） |
| ぶつぶつ | あり | **あり**（~4 drops/sec = 40ms/sec 欠損） |

**ドロップ発生の相関:** 起動後 40 秒間は drops=0。35.9 秒の長尺 TTS chunk 投入時点（t=45s）から drops=22→39→38→... と継続。長い TTS 再生中、writer が定常的に ~4% 遅れて _audioQueue が cap=30 を飽和させる。

**推定原因:** 音声パイプバッファが **256KB (666ms) のみ** で FFmpeg 側の消費ジッタを吸収しきれず、`pipe.Write()` が頻繁にブロックして AudioWriterLoop が遅れる。

### E: 音声パイプバッファ 256KB → 1MB（実装済み、計測完了）

- `FfmpegProcess.cs`: `outBufferSize: 256 * 1024` → **`1024 * 1024`**（666ms → 2.67s のジッタ吸収枠） ✅
  - backpressure の発生頻度を下げて AudioWriterLoop の遅れを解消する狙い
  - メモリコストは +768KB のみで影響軽微

#### E 計測結果（2026-04-19 23:42〜23:46、3分36秒・授業再生）

| 指標 | C+A | **E** |
|---|---|---|
| fps | 30 | **30** |
| 映像ドロップ率 | 2.3% | **2.0%**（同等） |
| パイプ slow | 1 回（起動時のみ）| **1 回**（同左） |
| 音声ドロップ（分換算）| ~170/分 | **~114/分**（改善） |
| depth 振る舞い | 0⇄30 を振動 | **最初 90 秒は 0 安定 → 以降 0⇄30 振動に復活** |
| ぶつぶつ | あり | **最初 90 秒はなし、以降再発**（短時間録画では気づかない） |
| ユーザー目視 | ブツブツ・遅れ両方 | **ブツブツ短時間解消、ただし声がかなり遅れる** |

**ドロップ発生の相関:** 23:42:53〜23:44:23（90 秒間）drops=0 でクリーン。23:44:33 から drops=+37/10s で再発。以降 C+A と同じ ~40 drops/10s が継続。

**「音声遅延」の原因（新たな知見）:**
- 1MB パイプには最大 **2.67 秒分**の音声が貯まる
- 音声 PTS は `byte_offset / sample_rate` の **バイトベース計算**で、**wall clock と連動しない**
- 映像は `-use_wallclock_as_timestamps 1` で **到着実時刻**打刻
- 両クロックが乖離すると、音声は映像より「早い PTS」になり → 再生時に **音声が映像に遅れて聞こえる**

### 全対策の総括（対症療法の限界）

| 対策 | キュー | パイプ | オフセット | ブツブツ | 遅延 | 副作用 |
|---|---|---|---|---|---|---|
| 原始 | cap=100 | 256KB | 0（死にコード） | なし | 2秒遅れ | — |
| B1 | cap=100 | 256KB | -0.5 配線 | なし | 改善 | 映像 fps↓ ドロップ↑ |
| B2 | cap=10 | 256KB | 0 | **あり** | 0.5s ばらつき | 解消 |
| C+A | cap=30 | 256KB | -0.3 | あり（軽） | 同左 | 解消 |
| E | cap=30 | **1MB** | -0.3 | 短時間なし/累積再発 | **遅れ増大** | 解消 |

**全対策に共通する根本原因（判明）:**
- 音声 generator は **wall clock** で real-time 生成（10ms タイマー）
- FFmpeg の音声消費は恒常的に **~2-4% 遅い**（AAC 44.1kHz リサンプル / encoder delay / I/O ジッタの累積）
- この差分は蓄積され、どこかで吸収が必要：
  - **小バッファ** → cap 飽和 → 古 chunk drop = **ブツブツ**
  - **大バッファ** → pipe 満タン → wall clock と PTS 乖離 = **音声遅延**

**つまり cap / buffer size のチューニングは「どの歪みに振り分けるか」の選択でしかなく、両方同時には満たせない。根治には generator 側か PTS 打刻側の設計変更が必要。**

## 根本解決プラン（選定中）

### プラン α: 音声入力にも `-use_wallclock_as_timestamps 1`

- FFmpeg が音声 chunk を read した **arrival wall clock** を PTS に打刻
- 映像と同じクロックで揃うので、パイプに貯まっても PTS は wall clock 基準
- **変更箇所最小**: `FfmpegProcess.cs` の音声入力 args に 1 行追加
- リスク: raw PCM での実挙動は要実測（chunk 単位での粒度になる）

### プラン β: キュー撤廃、generator が直接 pipe.Write

- `_audioQueue` と `AudioWriterLoop` を削除、generator の 10ms タイマーが pipe.Write 直接
- パイプが満タンなら generator が自然にブロック → FFmpeg の消費レートに追従
- レート追従は達成されるが、wall clock ≠ PTS の問題は残る
- 実装変更は大きい（既存の非同期設計を捨てる）

### プラン γ: α ＋ β の組合せ

- 消費レート追従（β）＋ PTS 実時刻打刻（α）
- 最も堅牢だが、効果の切り分けが難しい

### プラン δ: `aresample=async` で出力側再同期

- `-af aresample=async=1000:first_pts=0` を音声出力に追加
- FFmpeg が音声を wall clock に合わせて自動でリサンプル（必要に応じてサンプル挿入/削除）
- 既知の安定パターン。音質に軽微な影響
- PTS ずれは FFmpeg 側で自動吸収

### 推奨順序
1. **α を単独で試す**（最小変更、結果が劇的なら一発解決）
2. α で不十分なら **α ＋ δ** に進む（FFmpeg 標準機能で安定補正）
3. それでも不十分なら β（キュー撤廃）

## 多角検証（追補 2026-04-20）

α 実装に進む前に、過去の失敗と各プランを多角的に再検証した結果を記録する。

### 過去の失敗の本質的再解釈

| 対策 | 表面の失敗 | **本質的な失敗原因** |
|---|---|---|
| B1 `-itsoffset -0.5` | 映像 fps ↓、ドロップ ↑ | `-itsoffset` は mux 側で「音声到着を待つ」意味になり、back-pressure が映像パイプに波及した。「遅延補正」ではなく「入力遅延」として作用 |
| B2 cap=10 | ブツブツ | キュー上限 = ジッタ吸収能力のトレードオフ。下げると古チャンク破棄が頻発する設計的限界 |
| C+A cap=30 | 長尺 TTS 投入時に drops 復活 | 定常 ~4% クロックずれ前提では、**どの cap でも蓄積は時間とともに必ず cap に到達**する（時間の問題にすぎない） |
| E pipe 1MB | 最初クリーン／後半ブツブツ＋音声遅延 | パイプは「蓄積場所」にしかならない。**音声 PTS は byte_offset/sample_rate のバイト計算なので wall clock と連動しない**（根本原因の核心） |

**共通教訓**: FFmpeg の raw PCM 入力では、何もしないと PTS = byte_offset / sample_rate という固定計算になる。この仕様を変えない限り、キュー／バッファのどこを触っても「ブツブツ ⇄ 遅延」のトレードオフでしかなく根治しない。

### α が効くメカニズム（一段深い検証）

`use_wallclock_as_timestamps` は **demuxer option** で、FFmpeg が pipe から read した時刻を PTS に打刻する仕様。意味するところ:

- パイプに 2.67 秒貯まっていても、read は FFmpeg の消費速度に従うため、PTS は常に「今の壁時計」
- 映像も同じく read 時刻 PTS なので、**両者は FFmpeg の内部時計で自動同期**する
- キュー／バッファの蓄積遅延は PTS に一切反映されない（相対同期が崩れない）

**理論上は α 単独で根治しうる**。補足:

- 黒フレーム／silence プライム 300ms に FFmpeg init 完了時刻（~600ms）が打刻される現象は映像側と同じ → **両ストリーム同じ初期遅延で吸収される想定**（定数オフセット／ゼロ相殺）
- 10ms tick の時刻ジッタが PTS ジッタになる（±数ms）が、チャンク内サンプルは線形展開なので可聴域ではない

### 各プラン単独での限界

| プラン | 単独での効果 | 判定 |
|---|---|---|
| α | read 時刻 PTS で wall clock 同期、パイプ遅延が PTS に出ない | **根治候補** |
| β | 消費レート追従は達成するが、**バイトベース PTS 計算は残る**（映像 wallclock と合わない） | 単独では不可 |
| γ (α+β) | α が read 時刻 PTS を打つなら**パイプ蓄積は PTS 上は無害**なので β は不要 | α 後の保険 |
| δ | α なしでは「バイトベース PTS を壁時計に近づける」だけで音質影響のみが残る | α の併用前提 |

### プランに欠けていた考察（追加すべき論点）

1. **F 案（AAC 出力 `-ar 44100` → `48000`）の扱い**
   - DONE.md には「解消しない場合は F 案に進む」と記載があるが、本プランには反映されていない
   - 入力 48kHz → 出力 44.1kHz のリサンプル除去で AAC encoder delay の一部が削減される可能性
   - **α と独立に効く対策**なので、α 効果確認後の追加改善候補として残すべき

2. **silence プライム 300ms の妥当性再検証**
   - α を入れると init 時刻プライミングが映像と同じパターンになる
   - 本来目的（encoder preroll）なら必要、back-pressure 回避なら不要
   - α 後に外せるかは別検証

3. **`scripts/verify_av_sync.py` に音声側計測がない**
   - 現状は映像 PTS ドリフトのみ。α の検証には**音声 PTS の wall clock 追従**も計測すべき
   - `ffprobe -show_packets -select_streams a` で音声 PTS を取得し、映像 PTS との差を時系列で出す拡張が必要

4. **一度に複数変数を触らない（C+A の反省）**
   - C+A は cap と offset を同時に変えたため、どちらが効いたか分析が曖昧になった
   - α 実装時は**音声入力 args に 1 行追加のみ**
   - cap / offset / pipe 1MB は既存値を維持し、α 単独効果を切り分ける
   - 効果が明確に出たら段階的に既存の対症療法をロールバックして本質を確定させる

### 検証段取り（α 実装後）

**Step 1: α 単独実装**
- `FfmpegProcess.cs` の音声入力 args ブロックに `-use_wallclock_as_timestamps 1` を 1 行追加
- cap=30 / offset=-0.3 / pipe 1MB は維持（切り分けのため）
- 授業再生 60〜90 秒（**長尺 TTS を含む**）で VLC 目視＋`[AVSync]` ログ＋`ffprobe` で音声 PTS 計測

**Step 2: 効果ありなら対症療法を段階的ロールバック**
- cap=100（B1 前）／ offset=0 / pipe 256KB に戻し、α 単独で根治することを確定
- silence プライムも削減可能か確認

**Step 3: 残差があれば α + δ**
- `-af aresample=async=1000:first_pts=0` を追加
- それでも残るなら F 案（`-ar 48000`）

### α で失敗した場合の代替ルート

- raw PCM での `-use_wallclock_as_timestamps` 挙動が想定と異なるケース（chunk 粒度・tick ジッタ・init 時刻打刻問題）が発現したら、δ に直接進むのも選択肢
- δ でも足りなければ γ（β 追加でキュー撤廃）を最終手段とする
- **β 単独には進まない**（バイトベース PTS が残るため根治にならないと判定済み）

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
