# 録画モードのAV同期ずれ修正（クライアント再生と同じ撮影方法）

## ステータス: 承認済み（未実装）

## 背景

`plans/client-video-recording.md` で実装した録画機能で、生成されるMP4の**音と映像がずれる**問題が報告されている。
一方、C#ネイティブアプリ（WebView2 + Windowsスピーカー）で「クライアント再生」している最中はずれを感じない。

ユーザーの要望:
> 録画モードで声がずれる。クライアント再生の時はずれないけど、そのような撮影方法にはできないか

つまり「クライアントで実際に再生されている映像と音をそのまま記録する」方式にしたい、という要件。

## 現状の音声・映像パイプライン

現行の録画は**配信用パイプラインと同じ経路**を使っており、音と映像が別々の経路で生成される:

```
【映像】 WebView2 ─WGC→ BGRA ─NV12変換→ 名前付きパイプ ─┐
                                                         ├→ FFmpeg ─→ MP4
【音声】 TTS/BGM/SE ─C#のタイマーでPCM合成→ 名前付きパイプ ─┘
          （10msタイマー、実時間追跡）

【別系統・同時に動く】
  TTS/BGM/SE ─NAudio WaveOutEvent→ Windowsスピーカー（クライアント再生）
```

- **映像入力** (`FfmpegProcess.StartAsync`): `-framerate 30 -f rawvideo` で FFmpeg に渡す。FFmpeg はフレームに**インデックス×(1/30s)**のPTSを付与する（到着時刻ではない）
- **音声入力**: 10ms タイマーで `Environment.TickCount64` を見ながら「経過した分だけ」PCMを生成し、パイプに書く（**実時間レート**）
- **スピーカー再生**: NAudio `WaveOutEvent` で独立に再生。FFmpegには流れない

## なぜずれるのか（根本原因）

音声は実時間レート、映像は「フレーム到着数×1/30s」で時間が進む。この二つが**別時計**なので、以下で累積ズレが出る:

1. **フレームドロップ**: `WriteVideoFrame` は前フレームの書き込みが未完了（`_writingVideo==true`）ならスキップして `_dropCount++`。ドロップしたフレーム分は映像の時間が進まず、**映像だけ短くなる**（音声は実時間で進む）
2. **NV12変換遅延**: BGRA→NV12変換や書き込み遅延でフレーム間隔が崩れても、FFmpegは「30fps到着」前提で PTS を付けるので補正されない
3. **配信 (RTMP) では目立たない**: 低遅延フラグとTwitch側の同期吸収で一時的なズレは補正されるが、**MP4ファイルはPTSがそのまま残る**ので鑑賞時にずれとして顕在化する

一方、クライアント再生（WebView2の表示 + スピーカー音）は:
- 映像 = WebView2 が vsync に合わせて描画（常に実時間）
- 音声 = NAudio が実時間で再生
- **両者とも OS の実時間クロックに同期している**ので、人間の知覚範囲ではずれを感じない

つまりユーザーが「クライアント再生の時はずれない」と言っているのは、**両方が実時間クロックに乗っているから**。録画もそれと同じ「実時間クロック基準で取り込む」方式にすれば直る。

## 方針

FFmpegに入れる**映像と音声の両方を、実時間クロック基準で取り込む**ように切り替える。録画モード（`OutputMode.File`）限定で有効にし、配信モード（RTMP）は現行維持する。

- **音声**: `WasapiLoopbackCapture` で**Windowsデフォルト出力デバイスのloopback**をキャプチャし、スピーカーに出ている音そのものをFFmpegに流す（タイマーベースジェネレータをバイパス）
- **映像**: FFmpegの入力に `-use_wallclock_as_timestamps 1` を付け、PTSをフレーム番号ではなく**到着実時刻**で付与する。ドロップ時は時間圧縮ではなく**直前フレームの停止**として表現される

## 確定事項

| 項目 | 決定 |
|------|------|
| 録画時の音源 | **Windowsデフォルト出力デバイスのloopback**（スピーカーに出る音＝ユーザーが聴いている音） |
| 録画時のTTS/BGMスピーカー再生 | **継続**（ユーザーが配信を視聴・確認するため） |
| 配信モード | **現行のまま**（タイマーベース音声ジェネレータを維持） |
| 複数出力デバイスがある環境 | v1はデフォルト出力のみ。デバイス選択UIはv2 |
| 他アプリ音の混入 | v1は「録画中は他アプリ音を出さない運用」で回避。仮想デバイス分離はv2 |

## 実装ステップ

### Phase 1: 映像PTSを実時間クロック基準に切り替え

**目的**: 映像フレームのPTSを「到着時刻 = 実時間」で決め、ドロップ時は時間圧縮ではなく**フレームスタックによる時間固定**にする。

1. `FfmpegProcess.StartAsync()` の映像入力引数を録画モード（`config.Mode == OutputMode.File`）で切替:
   - 配信時（現行維持）: `-f rawvideo -pixel_format nv12 -video_size WxH -framerate 30 -i pipe`
   - 録画時: 上記に `-use_wallclock_as_timestamps 1` を追加
2. 必要に応じて `-vf setpts=PTS-STARTPTS` で開始時刻を0に寄せる（初期フレームPTSマイナス対策）
3. ドロップ時の挙動検証: WebView2が一時的にブロックされてもフレームは実時間で埋まる（直前フレームの複製）ことを確認

### Phase 2: WASAPI Loopback を録画音源として追加

**目的**: タイマーベース音声ジェネレータをバイパスし、**Windowsのデフォルト出力デバイスのloopbackキャプチャ** をFFmpegに流す。

1. `win-native-app/WinNativeApp/Streaming/LoopbackCaptureSource.cs` 新規作成
   - NAudio `WasapiLoopbackCapture` のラッパー
   - `Start(Action<byte[], int, int> onData)` / `Stop()` / `Dispose()`
   - `WaveFormat` を外部に公開（FFmpeg音声入力フォーマット構築用）
2. `FfmpegProcess` の音声入力引数生成 (`BuildAudioFormatArgs`) は既にWaveFormatを受け取る実装になっているので、そのまま流用
3. `MainForm.StartPipelineAsync(config)` で録画モードの分岐:
   - **録画**: `LoopbackCaptureSource` を生成 → `FfmpegProcess` にそのWaveFormatを渡して構築 → FFmpeg起動後に `loopback.Start((data, offset, count) => _ffmpeg.WriteAudioData(data, offset, count))` を呼ぶ。`StartAudioGenerator()` は呼ばない
   - **配信**: 現行通り（`FfmpegProcess` をデフォルト音声フォーマットで起動 → `StartAudioGenerator()`）
4. 音声入力にも `-use_wallclock_as_timestamps 1` を付与（loopbackはPCMストリームなので明示したほうが安全）
5. `StopRecordingAsync` で `LoopbackCaptureSource` を確実に停止 → Dispose → アップロードフローへ

### Phase 3: 状態遷移とエラー処理

1. `WasapiLoopbackCapture` のデバイス初期化失敗時はエラーログを出し、UIにトースト（「ループバック取得に失敗したため録画を中止しました」）→ 録画を開始しない（Standby復帰）
2. loopbackキャプチャ中にデフォルト出力デバイスが切り替わった場合の挙動をログで確認し、必要なら再接続処理を入れる（v1は切れたらそのまま終了ログだけでも可）
3. 録画停止のシーケンスで loopback → FFmpeg の順で止める（FFmpeg先に止めるとパイプ書き込みで例外）

### Phase 4: 検証

1. **同期テスト**: 1秒ごとにビープ音 + 画面に点滅タイマー（既存の字幕パネルなどを流用）を出して録画→再生時の音声−映像ずれを目視/計測
2. **長尺テスト**: 30分録画でずれが累積しないこと
3. **負荷テスト**: 意図的にCPU負荷を上げてフレームドロップが起きてもずれない（フレームが固まるだけ）こと
4. **配信モード回帰**: RTMP配信は従来通り動くこと（現行パス無変更）
5. **既存テストスイート**: `python3 -m pytest tests/ -q -m "not slow"`

## リスクと対策

| リスク | 影響度 | 対策 |
|--------|--------|------|
| loopback が他アプリの音も拾う | 中 | v1は運用で回避。v2で仮想デバイス分離を検討 |
| WASAPI 出力デバイス切替で loopback が切れる | 中 | 切断検知→録画終了ログ。v2で自動再接続 |
| `-use_wallclock_as_timestamps` で初期フレームPTSがマイナスになる | 低 | `-vf setpts=PTS-STARTPTS` / `-af aresample=async=1` で補正 |
| 初期黒フレーム / 初期サイレンスの扱い | 低 | 現行の「初期300msサイレンス」送信は録画時は不要（loopbackが開始後すぐに無音PCMを流す） |
| loopback起動中にFFmpegがまだ音声パイプを受け付けていない | 中 | 現行のパイプ接続待ちの後に `loopback.Start()` を呼ぶ順序を守る |

## 関連ファイル

| ファイル | 役割 |
|----------|------|
| `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs` | 映像入力引数の分岐（wallclock PTS）、録画モード時の `StartAudioGenerator` スキップ |
| `win-native-app/WinNativeApp/Streaming/StreamConfig.cs` | 必要なら録画用フラグ追加（`Mode == OutputMode.File` で判定できるなら不要） |
| `win-native-app/WinNativeApp/MainForm.cs` | `StartPipelineAsync` の音声源分岐（録画=loopback / 配信=generator）、`StopRecordingAsync` の停止順序 |
| `win-native-app/WinNativeApp/Streaming/LoopbackCaptureSource.cs` | **新規**: `WasapiLoopbackCapture` ラッパー |
| `plans/client-video-recording.md` | 既存プラン。本プランはその上の修正として位置付け |

## 参考

- [NAudio WasapiLoopbackCapture](https://github.com/naudio/NAudio/wiki/Recording-WASAPI-Loopback)
- [FFmpeg use_wallclock_as_timestamps](https://ffmpeg.org/ffmpeg-formats.html#Format-Options) — 入力フォーマット共通オプション
- FFmpeg `-vsync`/`-fps_mode` ドキュメント — CFR/VFR の取り扱い
