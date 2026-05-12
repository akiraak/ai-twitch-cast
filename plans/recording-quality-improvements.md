# 録画モード 品質改善：起動黒フレーム除去 / 画質・ファイルサイズ / 配信領域クロップ

> 関連: [recording-screen-capture-alternative.md](recording-screen-capture-alternative.md)（親プラン：別アプローチ全体）
> 関連: [recording-av-sync-fix.md](recording-av-sync-fix.md)（旧方式の AV 同期 — 役割分担対象）
> 関連: [client-video-recording.md](client-video-recording.md)（録画機能本体）

## ステータス: 進行中（Step 1+2 完了（実機確認済み 2026-05-11）/ Step 3.5 完了 / Step 3・4・5・6 未着手）

## 検証ログ（2026-05-11）

### Step 1 単独試行 (`logs/recorder.log` 16:09:11)

`Initial primer frame sent (..., source=real-frame)` は出ていたが先頭 9 秒は黒のまま、再生し直しでは前回画面が残った状態に。原因は 2 つ:

1. **WGC 初回フレームが黒**: capture session 開始直後の最初の `frame_arrived` は DWM 合成前で未初期化バッファ（黒）が返ることがある
2. **静止コンテンツで `frame_arrived` がほぼ来ない**: 最初の 5 秒で WGC frames=22（≒4 fps）→ 5〜10 秒で +259（≒52 fps）。broadcast.html が描画していない期間は WGC が発火しない

### A+B (keepalive pump 33ms タイマー追加) 試行 (`logs/recorder.log` 16:24:11)

**video frames=2 で停滞・28 秒後にやっと ffmpeg が Stream mapping** → デッドロック発生。pump が 33ms ごとに `WriteVideoFrame` を呼んで video pipe buffer 8MB（≒ 2 frames）を満杯にし、ffmpeg の audio stream init を待ってる間にパイプ書き込みがブロック → スレッドプール消費 → audio capture 遅延 → 全体停滞。

### Step 1+2 中間版 試行 (`logs/recorder.log` 16:34:19)

`-fps_mode cfr` + 500ms primer 遅延で先頭は黒ではなく実画面（primer）になったが、**最初の 5〜6 秒間が静止画**として残った。ユーザー観察「broadcast.html は普通に動いていた」を踏まえて再度ログを精査すると:

- `wgc_frames=2194` (47.7 秒で 46 fps) — WGC frame_arrived は実際は高頻度発火
- 一方で `video frames=20 at t=5.0s` (4 fps) — WriteVideoFrame は 5 秒で 20 回しか成功してない
- ffmpeg は audio stream init 完了に 5 秒待っており、その間 video pipe は probe 用にしか読まない
- → video pipe buffer 8MB（≒ 2 frames）が満杯になり、PocLoopback の同期 `_videoPipe.Write` が**ブロック**
- → WGC frame_arrived の callback が連鎖ブロックして冒頭 frame が drop される

「broadcast.html 静止」ではなく「ffmpeg audio probe 待ち × 同期 pipe 書き込み」が真の主因だった。

### 最終対策

- pump 撤回（pipe デッドロックを起こすため）
- `_latestFrame` の毎フレーム更新と 500ms 待機後の primer 取得は維持（WGC 初回黒バッファ対策）
- `-fps_mode cfr -r 30` で frame 補填（万一 WGC 発火が遅い瞬間があっても 30 fps grid 維持）
- **`-analyzeduration 0 -probesize 32`** を audio input に付け、ffmpeg の 5 秒待機を撤去。これで encoder pipeline が即起動し、video pipe を 30 fps で連続消費 → PocLoopback の WriteVideoFrame もブロックされず冒頭から実画面が記録される（**今回の本命修正**）

## 背景

[recording-screen-capture-alternative.md](recording-screen-capture-alternative.md) Step 4 前半で「PocLoopback サブプロセスから WGC キャプチャする」設計に着地し、AV 同期 ±20ms / 字幕進行ともに合格した。実機録画 `videos/broadcast_20260511_143725.mp4` で動作確認済み。

しかし「視聴可能な録画」としてはまだ 3 つの粗が残っており、本プランでこれを潰す。

1. **起動時に約 9.3 秒の黒フレームが先頭に入る**（[recording-screen-capture-alternative.md](recording-screen-capture-alternative.md) Step 4 残課題に記載済み）
2. **画質と圧縮率のバランスが未調整**（`-preset veryfast` / 既定 CRF / `+frag_keyframe` 等、PoC 暫定値のまま）
3. **ウィンドウ全体を録画していて、タイトルバー・右サイドメニュー・下部ステータスバーが映る**（CLAUDE.md「配信動画のクロップ＆音量ノーマライズ」では後処理で `crop=1280:720:1:38` を 2 パス ffmpeg で剥がしているが、録画時にやれば後処理が不要になる）

いずれも「録画パイプラインを置換した」段階では本筋ではなかったが、配信切り出しやアップロードを実運用するうえで効いてくる。

## 起動黒フレームの根本原因（コード解析）

`win-native-app/PocLoopback/FfmpegRunner.cs:122-145` の primer 黒フレーム送出と、`win-native-app/PocLoopback/Program.cs:149-179` の起動シーケンスが組み合わさって以下が起きている。

1. `screen.Start(hwnd)` で WGC キャプチャ開始
2. `firstFrame.Task.WaitAsync(5s)` で **最初の WGC フレームの「サイズだけ」**を待つ（`OnFrame` は `firstFrame.TrySetResult((w, h))` だけ呼んでフレームバイト列は捨てる）
3. `FfmpegRunner.StartAsync` の中で：
   - video pipe 接続待ち
   - **全ピクセル 0（α=0）の 1280×720×4 byte の黒フレーム** を 1 枚 video pipe に書く（`FfmpegRunner.cs:125-135`）
   - audio pipe 接続待ち
4. ここまで完了してから `screen.OnFrame = (...) => ffmpeg.WriteVideoFrame(...)` を差し替え（`Program.cs:178`）
5. WGC は **画面の更新があったときにだけ** frame_arrived を発火する（broadcast.html が静止していると数秒～十数秒空くことがある）

→ FFmpeg は `-use_wallclock_as_timestamps 1` で映像 PTS を「読んだ wall clock」で打刻するため、`(1) 黒フレーム読み取り時刻` から `(2) 次の実フレーム読み取り時刻` までの空白がそのまま MP4 先頭の黒として残る。Step 4 実測で 9.3s。

primer 黒フレーム自体は撤去できない（FFmpeg が rawvideo 入力で **最初の 1 フレームを読まないと audio pipe を open しない** 仕様のため）。**「primer を本物の最初の実フレームに置き換える」** のが構造的な解決策。

## 方針

### 課題 1：起動黒フレーム除去 — 「最初の実フレームを primer にする」

**A 案（採用候補）：first-real-frame priming**

- `ScreenCapture` の最初の `OnFrame` で **サイズだけでなく BGRA バイト列もコピーして保持**
- `FfmpegRunner.StartAsync` に「primer として書き出すバイト列」を引数で受け取る（fallback で従来の黒）
- video pipe 接続直後にこの「保持された最初の実フレーム」を書き出す
- audio pipe 接続完了 → コールバック差し替え → 通常運用へ

これだけで PTS 0 の地点に黒ではなく実フレームが入り、その後の WGC 発火までの「静止」も「黒」ではなく「最後に見えていた絵で停止」になる。

**B 案（A と組み合わせる）：静止時のフレームポンプ（last-frame keepalive）**

- `ScreenCapture` 内で「最後に渡したフレーム」を保持し、`fps` 間隔（33ms@30fps）の `System.Threading.Timer` で WGC 未発火期間も同じバイト列を再送
- 既に WGC frame_arrived が頻発しているときはタイマー側を no-op にする（cooldown / `Stopwatch` で前回送出から 30ms 経過時のみ pump）
- これで「静止コンテンツでも frame が来ない」問題が静止画フリーズではなく「最終フレームを保持」として表れる
- AV ドリフトには影響しない（wallclock PTS 基準なので、frame 数が増えるだけで時刻軸はずれない）

A 案だけでも起動黒フレームは消えるが、長時間録画中に broadcast.html が静止し続けると WGC が止まる可能性があり、B 案で keepalive する保険を入れる。**実装は A → B の順で段階導入**し、A 単独で起動黒フレームが消えることをまず確認する。

**C 案（不採用）：post-process で trim**

- 録画停止後に ffmpeg で「先頭の黒区間を blackdetect → -ss で切る」二度がけ
- 録画フローに後処理ステップが増え、AV 同期再計測が必要になる。実用化までのコストが高い

**D 案（不採用）：`-tune zerolatency`**

- libx264 warmup を抑える効果はあるが zerolatency は **画質劣化**とトレードオフ。録画は遅延よりも画質を優先する設計（[FfmpegProcess.cs:217-218 のコメント参照](../win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs)）と矛盾する。さらに warmup は数百 ms オーダーで、9.3s の主因ではない（主因は WGC 静止）

### 課題 3：配信領域のみ録画する（ウィンドウクローム除外）

現状、PocLoopback は WinNativeApp ウィンドウ全体を WGC キャプチャしている（`ScreenCapture.cs:31-57` の `GraphicsCaptureItem.TryCreateFromWindowId`）。実際の broadcast canvas は 1280×720 だが、出力 MP4 にはタイトルバー（上 38px 程度）・右サイドバー・下部ステータスバーが含まれる。

これを後処理で剥がす運用が `CLAUDE.md > 配信動画のクロップ＆音量ノーマライズ` に書かれているが、

```
crop=1280:720:1:38
```

毎回 2 パス ffmpeg を回すのは手間で、AV 同期再エンコードのリスクも 1 段増える。**録画時にクロップした状態で書き出す** ようにする。

**A 案（採用決定）：C# 側でクロップしてからパイプに流す**

- `ScreenCapture` に「crop 矩形 (x, y, w, h)」を渡す
- 内部の staging buffer から該当矩形だけを `_frameBuffer` に詰める（`mapped.RowPitch` ベースでオフセット計算）
- `FfmpegRunner` のコンストラクタ `videoWidth / videoHeight` は **crop 後の値**（1280×720）になる
- FFmpeg `-video_size` も crop 後サイズ → パイプ転送量も削減（1682×759 → 1280×720 で約 -45%）
- 既存の `crop=trunc(iw/2)*2:trunc(ih/2)*2` filter は、crop 矩形が偶数次元（1280×720）なら不要

**B 案（不採用）：FFmpeg 側で `-vf "crop=1280:720:1:38"` を当てる**

- C# 側のキャプチャはフルサイズのまま、FFmpeg filter で抜く
- メリット: コード変更は FfmpegRunner.cs のみ
- デメリット: パイプ帯域は減らない、フィルタ分の CPU が乗る、設計として「録画パイプラインに後処理が紛れ込む」のが汚い

**C 案（将来検討）：WebView2 子 HWND を直接 WGC でキャプチャ**

- 親プラン `recording-screen-capture-alternative.md` の決定 B2「WebView2 が描画している HWND だけをキャプチャ」と同じ
- HWND 取得 API（`FindWindowEx` で `Chrome_WidgetWin_0` / `Chrome_RenderWidgetHostHWND` を探す等）の安定性検証が必要で、Edge WebView2 バージョン依存
- A 案で運用が回るなら見送る。Edge ランタイム更新時にクロップ座標が変わるリスクが顕在化したら再検討

**渡し方の選択肢**

`PocLoopback` への CLI 引数として渡す:

```
--crop 1:38:1280:720           # x:y:w:h（明示）
--crop-broadcast               # 上記のショートカット（デフォルト値を使う）
--crop none                    # 後方互換: ウィンドウ全体（現状）
```

`MainForm` から子プロセス起動するときは `--crop-broadcast` を既定で付ける。デバッグ目的でフル録画したい場合だけ `--crop none` を渡せる構造。デフォルト値（1, 38, 1280, 720）は `scenes.json` ではなく **コード内定数** に持つ（ウィンドウサイズが固定 1280×720 + chrome に依存する物理値なので、設定として外出しする意味は薄い。将来 chrome が変わったらコードを直す）。

### 課題 2：画質とファイルサイズの改善 — エンコーダ設定の見直し

現状（`FfmpegRunner.cs:88-94`）:

```
-c:v libx264 -preset veryfast -pix_fmt yuv420p
-g {fps*2}
-c:a aac -b:a 192k -ar 48000
-movflags +faststart+frag_keyframe
```

問題点と改善方針:

| 項目 | 現状 | 提案 | 理由 |
|------|------|------|------|
| プリセット | `veryfast` | `medium`（既定）または `slow` | 録画は配信と違い CPU 余裕がある。同じ画質ならファイルサイズが 20〜30% 減る |
| レート制御 | 既定（CRF 23 相当） | `-crf 20`（明示） | 数値を明示することで意図が読める。20 は「ほぼ無劣化」と言われる範囲 |
| `+frag_keyframe` | **付いている** | **除去** | 本家 `WinNativeApp/Streaming/FfmpegProcess.cs:209-216` で「VLC が moov の nb_frames=60 を全長と誤読してループ再生する」症状の対策として除去済み。PocLoopback も同じ症状を踏む可能性が高い |
| 音声ビットレート | 192k | 128k | loopback 音声（TTS+BGM 合成済み）は素材が clean なので 128k AAC で十分。サイズに直接効く（60s で約 -480KB） |
| HW エンコーダ | 未対応 | h264_nvenc / h264_qsv 検出 → 不在時 libx264 fallback | 本家 `FfmpegProcess.cs:1059-1137` の `ResolveEncoder` ロジックを流用すれば、対応 GPU では CPU 負荷を大きく下げられる。録画と配信を同時に走らせる将来シナリオで効く |
| キーフレーム間隔 | `-g fps*2`（2 秒） | 維持 | 配信切り出し時のシーク粒度として妥当 |
| `pix_fmt` | yuv420p | 維持 | YouTube / Twitch / 一般プレイヤー互換 |
| crop | `crop=trunc(iw/2)*2:trunc(ih/2)*2` | 維持 | yuv420p の偶数次元要件 |

**段階的に効果を切り分ける**ため、以下の順に変更して都度 60s 録画で見比べる：

1. `+frag_keyframe` 除去（VLC 互換性確認）
2. `-preset medium` ＋ `-crf 20` 追加
3. 音声 `-b:a 128k`
4. HW エンコーダ（任意・別ステップ）

HW エンコーダは「画質/サイズ比は libx264 medium に劣るが速い」という別軸の最適化。本タスクの主目的は「画質とファイルサイズ」なので、libx264 のチューニングを先に行い、HW は将来オプションとする。

## 実装ステップ

### Step 1: A 案実装（first-real-frame priming）

- `win-native-app/PocLoopback/ScreenCapture.cs`
  - 「最初のフレームの BGRA バイト列＋サイズ」を内部に保持するロジックを追加
  - 公開: `byte[]? FirstFrame { get; }` または `TryGetFirstFrame(out byte[], out int w, out int h)`
- `win-native-app/PocLoopback/Program.cs`
  - `firstFrame.Task` 待機後、`screen` から最初のフレームバイト列を取得
  - `ffmpeg.StartAsync(initialPrimer: firstFrameBytes)` のように渡す
- `win-native-app/PocLoopback/FfmpegRunner.cs`
  - `StartAsync(CancellationToken, byte[]? primer = null)` に拡張
  - primer 引数があれば黒フレームの代わりにそれを使う。null なら従来通り黒フレーム（後方互換）
- ビルド: `./poc-loopback.sh --build-only`
- 検証: 60s 録画 → VLC で先頭 1 秒以内に実画面が映ること、`ffprobe -show_packets -select_streams v` で `pts_time=0.000` から黒以外のフレームが入っていること（`-vframes 1 -f image2 first.png` で目視）

### Step 2: B 案実装（last-frame keepalive pump）

- `ScreenCapture` 内に `System.Threading.Timer`（33ms / 30fps）を追加
- 「直近 N ms（例 50ms）に WGC frame_arrived が来ていなければ最後のフレームを再送」する pump メソッド
- Stop 時にタイマーを止める
- **ロック設計**: 現状 `ScreenCapture.cs:71` の `cb(_frameBuffer!, w, h)` は `lock (_lock)` の **外** で呼ばれている。pump 側からも同じ `_frameBuffer` 参照を渡すと、サイズ変化時に `_frameBuffer = new byte[...]` で再確保された瞬間に古い参照が消える競合が起きうる。次のいずれかで保護する:
  - (a) `OnFrameArrived` / pump 両方で `cb` 呼び出しまで `lock (_lock)` の内側に含める
  - (b) `_frameBuffer` 参照を呼び出し直前にローカル変数にスナップショット (`var buf = _frameBuffer; cb(buf, w, h);`) して、再確保があっても呼び出し中の参照が GC されないようにする
  - 採用は (b) を基本とする（A 案で primer に保持する参照と同じ寿命管理になり一貫する）。pump 側は `_lock` 内で `(buf, w, h) = (_frameBuffer, _lastW, _lastH);` を取り、ロック外で `cb(buf, w, h)` を呼ぶ
- 検証: broadcast.html を静止させた状態で 60s 録画 → 黒/フリーズが入らないこと、`ffprobe -count_frames` で frame_count が `60*30 = 1800` 付近になること

### Step 3: エンコーダ設定改善

`FfmpegRunner.cs:89-94` のエンコーダ引数を以下の順で 1 段ずつ変更し、毎回 60s 録画で `ls -l` のファイルサイズと VLC 目視を記録：

1. `+frag_keyframe` 除去 → VLC で再生（ループ再生症状が出ないか）
2. `-preset medium` + `-crf 20` → 1 と比較してファイルサイズと画質
3. `-b:a 128k` → さらに比較

`FfmpegRunner` のコンストラクタに `EncoderConfig`（preset / crf / audioBitrate）を渡せるようにしておくと A/B 試験しやすい（プラン段階では future-proof として軽く設計するだけ）。

### Step 3.5: 配信領域クロップ（課題 3 / A 案）

- `win-native-app/PocLoopback/Program.cs`
  - CLI: `--crop x:y:w:h` / `--crop-broadcast` / `--crop none` のパース
  - デフォルトは `--crop-broadcast` 相当（1, 38, 1280, 720）。後方互換が必要な箇所では `--crop none` を明示
- `win-native-app/PocLoopback/ScreenCapture.cs`
  - `Start(IntPtr hwnd, CropRect? crop)` に拡張
  - `ExtractBgra` の中で staging buffer から該当矩形だけ抜く（`mapped.RowPitch` を使い行毎にコピーするロジックは既にある `else` 分岐の応用）
  - `OnFrame` に渡すバイト列は crop 後サイズ。`_frameBuffer` のサイズも `cw * ch * 4` に変更
- `win-native-app/PocLoopback/FfmpegRunner.cs`
  - コンストラクタ `videoWidth / videoHeight` は crop 後の値を受け取る
  - WGC 由来の入力次元が **既に偶数（1280×720）** なら `-vf "crop=trunc(iw/2)*2:trunc(ih/2)*2"` は不要。CropRect 指定時は外す
- `win-native-app/WinNativeApp/MainForm.cs:1550` 周辺（`StartRecordingAsync`）
  - 子プロセス起動引数に `--crop-broadcast` を追加（変更は 1 行）
- **依存連鎖の確認**: `ScreenCapture` 側でクロップすると `OnFrame` callback が返す `(w, h)` は crop 後サイズになる → `Program.cs:159` の `size = await firstFrame.Task` も crop 後サイズ → `FfmpegRunner` 作成時に渡す `videoWidth/Height` も自動的に crop 後になる。Step 1（A 案 primer）で保持する最初のフレームバイト列も crop 後の長さ（1280×720×4 = 3.7MB）になる。**現状の Program.cs の制御フローは変えずに済む**
- 検証:
  - 60s 録画 → VLC 目視でタイトルバー・サイドバー・ステータスバーが映っていないこと
  - `ffprobe -show_entries stream=width,height` で 1280×720 になっていること
  - AV 同期回帰がないこと（バケット内 diff ±20ms）
  - パイプ転送量が減っていること（`[Main] t=... bytes=...` ログで video bytes が 45% ほど減ることを確認）
  - **DPI awareness 実機確認**: WinNativeApp ウィンドウを 100% モニタと高 DPI（150% / 200%）モニタの両方に置いた状態で 60s 録画し、`ffprobe -show_entries stream=width,height` がいずれも 1280×720 を返すこと。ウィンドウサイズの物理ピクセル差で crop 矩形がずれていないことを確認（プロジェクト内に DPI manifest / `SetHighDpiMode` 設定が明示的に見当たらないため要実測）

### Step 4（任意）: HW エンコーダ対応

- `FfmpegProcess.cs:1059-1137` の `ResolveEncoder` / `BuildEncoderArgs` のロジックを `PocLoopback/FfmpegRunner.cs` 用に簡約コピー（NVENC → AMF → QSV → libx264）
- 録画は配信と違い `-tune ll` / `-rc cbr` ではなく **画質優先** の設定にする（NVENC なら `-preset p7 -rc vbr -cq 20` など）
- 検証: GPU 付き環境と無し環境（libx264 fallback）の両方で 60s 録画が完走すること

### Step 5: 計測と AV 同期回帰確認

- `scripts/verify_av_sync.py --no-flash debug-ss/<新録画>.mp4` で AV ドリフト確認（[recording-screen-capture-alternative.md Step 3](recording-screen-capture-alternative.md) で拡張済み）
- バケット内 diff ±20ms、end offset ±30ms の合格基準（Step 4 前半と同じ）を維持していること

### Step 6: ドキュメント更新と TODO.md 反映

- DONE.md に各 Step の結果を追記
- TODO.md の該当行（`最初の黒のみ映像を削除` / `画質とファイルサイズの改善`）を完了済みとして削除、または所要時間と所感を残す
- [recording-screen-capture-alternative.md](recording-screen-capture-alternative.md) Step 4「残課題: 起動 black frame 約 9 秒」を「解消済み（本プラン参照）」に更新
- CLAUDE.md「配信動画のクロップ＆音量ノーマライズ」セクションに、PocLoopback の新エンコーダ設定（CRF/preset）を追記

## 想定される懸念点と対策

| 懸念 | 対策 |
|------|------|
| **A 案で WGC 最初のフレームバイト列を保持する間にメモリ二重消費** | 1280×720×4 = 3.7MB を 1 枚分。`ScreenCapture._frameBuffer` を `Volatile.Read` で参照取りすれば copy 不要。Stop 時に null クリア |
| **B 案 pump で WGC frame_arrived と競合** | Pump 側で「前回送出から 30ms 未満なら no-op」のクールダウンを必ず入れる。さらに `_lock` を共有して `WriteVideoFrame` を 1 本化する |
| **`-preset medium` で CPU 上限に当たり録画ドロップ** | フォールバックで `veryfast` に戻せる引数構成にする（`EncoderConfig` の意義）。ドロップは `ffprobe -count_frames` の不足で検出 |
| **`-crf 20` で配信切り出しが想定より重くなる** | YouTube アップロードや Twitch アーカイブ用途では問題ないサイズ。debug-ss のように cropped 後の使い方なら影響なし |
| **`+frag_keyframe` 除去でクラッシュ時の moov 未書き込みリスク** | 本家でも同じトレードオフを受け入れて除去済み。正常 stop（stdin "stop" → graceful exit）で faststart relocation が走るため moov は正しく書かれる |
| **HW エンコーダ環境差で動作不安定** | ResolveEncoder の fallback が libx264 に落ちるので最悪挙動は現状と同じ。Step 4 は任意扱い |
| **クロップ座標 (1, 38, 1280, 720) がウィンドウ chrome 変更で破綻** | デフォルト値はコード内定数。`--crop x:y:w:h` で上書き可能にしておく。chrome が変わったら 1 か所直すだけで済む。長期的には課題 3 C 案（WebView2 HWND 直接キャプチャ）に移行可能 |
| **クロップ座標を間違えると broadcast 領域の端が切れる** | 1280×720 + (1, 38) は CLAUDE.md / 既存 debug-ss 手順と整合済み。Step 3.5 検証で VLC 目視で確認 |
| **WinNativeApp ウィンドウが OS DPI スケーリングで論理サイズと物理サイズが食い違う** | WGC は物理ピクセルで返すので、ウィンドウ自体が DPI awareness を持つ前提で 1280×720 + (1, 38) が成立。WinNativeApp は WinForms + WebView2 で per-monitor DPI aware なので影響なし（要 Step 3.5 で実機確認） |

## 完了条件

- [x] Step 1+2: 最新スナップショット primer ＋ 500ms 遅延 ＋ ffmpeg `-fps_mode cfr -r 30` ＋ ffmpeg audio input `-analyzeduration 0 -probesize 32`。**実機確認済み（2026-05-11）**: 録画動画の先頭から実画面が動き音声も飛びなく流れる。B 案 pump はデッドロックを起こしたため撤回
- [ ] Step 3: エンコーダ設定改善。`+frag_keyframe` 除去 → preset/crf 調整 → 音声 128k。ファイルサイズと画質を記録
- [x] Step 3.5: 配信領域クロップ。`ScreenCapture` に `CropRect` 追加 / `Program.cs` に `--crop` 系 CLI 追加 / `MainForm` に `--crop-broadcast` 追加。実機 60s 録画で chrome が映らず 1280×720 で出力されること・AV 同期回帰なしを確認済み
- [ ] Step 4: （任意）HW エンコーダ対応
- [ ] Step 5: AV 同期回帰なし（バケット内 diff ±20ms、end offset ±30ms 維持）
- [ ] Step 6: DONE.md / TODO.md / 親プラン更新（Step 3.5 分は反映済み）

## 参考

- [recording-screen-capture-alternative.md](recording-screen-capture-alternative.md) — 親プラン（Step 4 残課題に本プラン課題が記載済み）
- `win-native-app/PocLoopback/FfmpegRunner.cs:88-94` — 現エンコーダ引数
- `win-native-app/PocLoopback/FfmpegRunner.cs:122-145` — 起動黒フレーム送出箇所
- `win-native-app/PocLoopback/Program.cs:149-179` — 起動シーケンス（WGC → FFmpeg → callback 差し替え）
- `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs:209-216` — 本家での `+frag_keyframe` 除去理由
- `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs:1059-1137` — HW エンコーダ自動検出ロジック（流用候補）
- x264 CRF: <https://trac.ffmpeg.org/wiki/Encode/H.264#crf>
