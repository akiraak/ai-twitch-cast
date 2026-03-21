# 配信開始後40秒間の音声途切れ改善プラン

## ステータス: 完了

## 問題

配信開始後の約40秒間、音声が途切れる（断続的に聞こえなくなる）。

## 現状のアーキテクチャ

```
broadcast.html (TTS/BGM)
  ↓ WebView2が<audio>を再生
Windows Audio Subsystem
  ↓
WASAPI Loopback Capture (AudioLoopback.cs)
  ↓ PCM (f32le 48kHz stereo)
Named Pipe (1MB buffer)
  ↓
FFmpeg (AAC 128k 44100Hz → FLV → RTMP)
  ↓
Twitch
```

### 現在の配信開始シーケンス

```
1. AudioLoopback.Initialize()        — WASAPIフォーマット取得
2. FfmpegProcess(config, audioFormat) — FFmpegプロセス生成
3. _ffmpeg.StartAsync()              — パイプ作成、プロセス起動、接続待ち
   3a. 映像パイプ接続 → 黒フレーム送信
   3b. 音声パイプ接続 → 1秒サイレンス送信 (384KB)
4. _audio.Start(callback)            — WASAPI録音開始、FFmpegパイプに接続
5. _capture.OnFrameReady = callback  — 映像フレーム送信開始
```

### 現在のサイレンス処理

- **初期**: 1秒分 (384,000 bytes = 48000Hz × 2ch × 4bytes × 1s)
- **継続**: 100msチャンク (38,400 bytes) を100ms間隔で送信（実データがない時のみ）
- **二重書き込み防止**: 実データ受信後200ms以内はサイレンス送信スキップ

## 原因分析

### 原因1: FFmpegの入力バッファオーバーフロー（最有力）

FFmpegの `-thread_queue_size 512` は音声入力パケットのキューサイズ。起動直後：

1. FFmpegが映像エンコード（HWエンコーダ初期化）に時間を取られる
2. 音声パイプからの読み取りが遅れる
3. 音声データがthread_queueに蓄積 → 512パケットを超えるとドロップ
4. ドロップされたパケット分の音声が途切れる
5. FFmpegが安定動作になるまで（~40秒）繰り返される

**根拠**: FFmpegのstderrに `Thread message queue blocking` や `Discarding` が出ている可能性。

### 原因2: パイプバッファ蓄積 → タイムスタンプ飛び

1. WASAPIが実データを送り始める
2. FFmpegがまだエンコーダ初期化中で読み取りが遅い
3. 1MB名前付きパイプバッファにデータが蓄積
4. FFmpegが読み取りを再開すると、古いデータが一気に流入
5. FFmpegはデータを「リアルタイム」と解釈 → タイムスタンプがジャンプ
6. FLVマクサーが音声タイムスタンプの不整合を検出 → 音声フレームをドロップ

### 原因3: AAC エンコーダのプライミング不足

- AACエンコーダは最初の数フレーム分のデータが必要（priming samples）
- 1秒の初期サイレンスで大部分はカバーされるが、resampling (48kHz→44100Hz) も加わると遅延が増える

### 原因4: 映像・音声のタイムスタンプ不一致

- 映像: 黒フレーム1枚 → 実フレーム（キャプチャ開始後）
- 音声: 1秒サイレンス → 実データ（WASAPI開始後）
- 映像開始とWASAPI開始にタイムラグがある場合、FFmpegのmuxerがAV syncを取るために音声をドロップする可能性

## 実装方針

### Phase 1: 診断ログ追加（原因特定）

FFmpegのstderrログを分析し、具体的な原因を特定する。

**ファイル**: `FfmpegProcess.cs`

1. `LogStderrAsync()` を改修し、起動後60秒間はstderrの全行をSerilogにも出力する
   - 特に `Thread message queue blocking`, `Discarding`, `Queue input is backward`, `Non-monotone` を監視
2. AudioLoopback の統計ログを起動後30秒間は2秒間隔に変更
3. FFmpegのstderrを `-loglevel warning` → `-loglevel info` に変更（起動直後のみ）

### Phase 2: FFmpeg起動パラメータ最適化

**ファイル**: `FfmpegProcess.cs`

#### 2a. 音声入力にリアルタイム制約を追加
```
-use_wallclock_as_timestamps 1  (音声入力の前)
```
名前付きパイプからの読み取りにウォールクロックタイムスタンプを使用。バッファ蓄積による古いデータのタイムスタンプ問題を回避。

#### 2b. thread_queue_sizeの増大
```
-thread_queue_size 1024  (現在の512→1024)
```
起動直後のバースト的なデータ到着に対応。

#### 2c. 音声フィルタで非同期リサンプル
```
-af aresample=async=1:first_pts=0
```
音声ストリームのタイムスタンプギャップを自動補完。途切れた部分にサイレンスを挿入し、タイムスタンプの連続性を保証。

#### 2d. FLV muxer フラグ
```
-flvflags no_duration_filesize
```
FLVヘッダの不必要なシーク（パイプ出力では不可能）を防止。

### Phase 3: 初期サイレンスの増量と改善

**ファイル**: `FfmpegProcess.cs`

1. 初期サイレンスを1秒→3秒に増量（384KB → 1,152KB）
   - FFmpegの内部バッファ（AAC encoder + resampler + muxer）のプライミングに十分な量を確保
2. サイレンス送信をチャンク分割（100ms単位で送信）
   - パイプバッファの一時的な負荷を軽減

### Phase 4: WASAPI開始タイミングの最適化

**ファイル**: `MainForm.cs`

1. FFmpegの初期化完了後、WASAPI開始前に500ms待機
   - FFmpegがパイプの読み取りを開始するまでの余裕を確保
2. WASAPI開始直後に500ms分のサイレンスを追加送信
   - WASAPIがデータを生成するまでの空白期間をカバー

```csharp
// 現在:
await _ffmpeg.StartAsync();
_audio.Start((data, offset, count) => _ffmpeg.WriteAudioData(data, offset, count));

// 改善後:
await _ffmpeg.StartAsync();
await Task.Delay(500); // FFmpegの読み取り開始を待つ
_audio.Start((data, offset, count) => _ffmpeg.WriteAudioData(data, offset, count));
```

### Phase 5: AudioLoopbackの起動時バッファリング

**ファイル**: `AudioLoopback.cs`

起動直後のWASAPIデータの流量を安定させるため：

1. WASAPI開始後、最初の1秒間はサイレンスタイマーの間隔を50msに短縮
   - 実データとサイレンスの切り替わりによる隙間を減らす
2. 起動後5秒間は二重書き込み防止のガード時間を100msに短縮
   - 実データが安定するまでは積極的にサイレンスを補填

## 実装ステップ

### Step 1: Phase 1（診断）
- FFmpeg stderr詳細ログ追加
- AudioLoopback統計ログ頻度変更
- → **実際に配信してログを確認、原因を確定**

### Step 2: Phase 2（FFmpegパラメータ）
- `-use_wallclock_as_timestamps 1` 追加
- `-af aresample=async=1:first_pts=0` 追加
- `-thread_queue_size 1024` に変更
- `-flvflags no_duration_filesize` 追加

### Step 3: Phase 3-5（サイレンス・タイミング）
- 初期サイレンス3秒化
- WASAPI開始前の待機追加
- サイレンスタイマーの起動時動作調整

### Step 4: 検証
- 配信開始して最初の60秒間の音声を確認
- FFmpegログで警告・エラーが出ていないか確認
- AudioLoopback統計でデータ/サイレンスの比率を確認

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| aresample=async=1 が音声品質を劣化 | TTS/BGM音質低下 | first_pts=0指定で最小限の影響に抑える |
| 初期サイレンス3秒で配信開始が遅く感じる | UX | 元々40秒途切れるよりはマシ |
| use_wallclock_as_timestamps が映像とずれる | AV sync | 音声入力のみに適用 |
| Task.Delay(500) でフレーム送信が先行 | 映像のみ配信される期間 | 初期サイレンスで音声パイプは埋まっている |

## 優先度

Phase 2 (FFmpegパラメータ) が最も効果が高く、リスクが低い。Phase 1の診断と並行して実施推奨。
