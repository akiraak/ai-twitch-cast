# TTS音声を直接FFmpegパイプに書き込む（WASAPI迂回）

## ステータス: 完了

## 背景

現在、TTS音声は以下の経路でFFmpegに到達する：

```
TTS WAV → broadcast.html <audio> → スピーカー → WASAPI Loopback回収 → FFmpeg
```

この「ブラウザ→スピーカー→WASAPI回収」の迂回が約500msの遅延を生み、映像（WGCで即座にキャプチャ）とずれる。
現状は `LIPSYNC_DELAY_MS = 500` で口パク開始を遅らせて補正しているが、環境依存の固定値でありローカルプレビューでは逆にずれる。

## 目標

TTS音声をC#アプリがサーバーから直接取得し、FFmpegの音声パイプに書き込む。
WASAPIループバックはBGMキャプチャにのみ使用する。

## 改善後のアーキテクチャ

```
TTS WAV → サーバー → C#アプリ（WebSocket /ws/control）
                        ├→ PCMリサンプル（24kHz mono 16bit → 48kHz stereo f32le）
                        ├→ ミキサー（TTS PCM + WASAPI BGM PCM）→ FFmpeg音声パイプ
                        └→ broadcast.htmlに play_audio 送信（プレビュー + リップシンク用）

BGM → broadcast.html <audio> → スピーカー → WASAPI Loopback → ミキサー → FFmpeg音声パイプ
```

### 配信時の動作
1. サーバーがTTS WAVを生成
2. サーバーが `/ws/control` 経由でC#アプリにTTS WAVデータを送信（新規メッセージタイプ）
3. C#アプリがPCMリサンプルし、ミキサーバッファに投入
4. 同時にサーバーは `play_audio` + `lipsync` をbroadcast.htmlに送信
5. broadcast.htmlはTTSを **ミュート再生**（`ttsAudio.volume = 0`）→ リップシンク + プレビューの口パクのみ
6. ミキサーがWASAPI（BGMのみ）+ TTS PCMを加算合成 → FFmpegパイプに書き込み
7. リップシンクは `LIPSYNC_DELAY_MS = 0` → play()と同時に開始

### 非配信時の動作
- C#アプリにTTSデータは送らない（または送っても無視）
- broadcast.htmlのTTSは通常音量で再生（`ttsAudio.volume = 通常値`）
- プレビューで口パクと音声が同期

## メリット

- **LIPSYNC_DELAY_MS が不要** — TTS音声が映像と同じタイミングでFFmpegに到達
- **プレビューも配信も同期** — ブラウザは通常再生、FFmpegには直接書き込み
- **環境非依存** — オーディオドライバやBluetooth等に影響されない
- **音声品質向上** — WASAPI Loopbackの変換ロスなし（TTS分）

## 実装ステップ

### Step 1: サーバー→C#アプリへのTTS送信

**ファイル**: `src/comment_reader.py`, `scripts/routes/stream_control.py`

1. `_speak()` でTTS WAV生成後、WebSocket `/ws/control` 経由でC#アプリにWAVバイナリを送信
2. 新規メッセージタイプ: `{"action": "tts_audio", "data": "<base64 WAV>"}`
3. 配信中フラグに基づいて送信（非配信時は送信しない）

### Step 2: C#アプリのPCMリサンプル

**ファイル**: `win-native-app/WinNativeApp/Streaming/TtsDecoder.cs`（新規）

1. WAVバイナリを受信
2. NAudioで24kHz mono 16bit → 48kHz stereo f32le にリサンプル
   - `WaveFormatConversionStream` or `MediaFoundationResampler`
3. リサンプル後のPCMバイト配列をミキサーに渡す

### Step 3: オーディオミキサー

**ファイル**: `win-native-app/WinNativeApp/Streaming/AudioMixer.cs`（新規）

1. 2チャンネル入力: WASAPI（BGM）+ TTS（直接PCM）
2. 同じフォーマット（48kHz stereo f32le）でサンプル単位の加算合成
3. クリッピング防止（-1.0〜1.0にクランプ）
4. 出力: ConcurrentQueue → AudioWriterLoop → FFmpegパイプ（既存の仕組みを流用）

#### ミキサーの動作
```
100msチャンクごと:
  bgm_chunk = WASAPIから受信したBGMデータ（なければ無音）
  tts_chunk = TTSバッファから読み出し（なければ無音）
  mixed = bgm_chunk + tts_chunk  // サンプル単位加算
  → キューに投入
```

### Step 4: 配信時のブラウザTTSミュート

**ファイル**: `static/broadcast.html`

1. 配信状態をWebSocketまたはAPIで取得
2. 配信中: `ttsAudio.volume = 0`（再生はする＝リップシンク駆動のため）
3. 非配信: `ttsAudio.volume = 通常値`
4. `LIPSYNC_DELAY_MS = 0` に変更（遅延補正不要）

### Step 5: 音量制御

**ファイル**: `win-native-app/WinNativeApp/Streaming/AudioMixer.cs`

1. TTS音量: `master × tts` をミキサーで適用（サーバーからWebSocket経由で音量取得）
2. BGM音量: ブラウザ側で既に適用済み（WASAPIで取得する音声は音量適用後）
3. マスター音量: TTS分のみミキサーで適用（BGMは既にブラウザ側でmaster適用済み）

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| WAVデータのWebSocket送信が重い | 5秒のTTS ≈ 240KB（24kHz 16bit mono）、base64で320KB | 許容範囲。バイナリWebSocketにすれば240KB |
| ミキサーのチャンク境界問題 | TTS開始/終了がWASAPIチャンクと非整列 | TTSバッファをリングバッファ化、残りは無音パディング |
| リサンプル品質 | NAudio MediaFoundationResamplerは高品質 | テストで確認 |
| BGM音量がブラウザ側で適用済み | ミキサーでBGMの音量制御ができない | 現状と同じ（ブラウザが制御）なので問題なし |
| 配信開始/停止時のTTSミュート切替 | タイミングによっては一瞬二重再生 | stream_status変更時に即座にvolume切替 |

## テスト計画

1. C#アプリ単体テスト: WAV → PCMリサンプル → 正しいフォーマット出力を確認
2. ミキサーテスト: BGM + TTS の加算合成が正しいことを確認
3. 配信テスト: Twitchでリップシンクと音声が遅延なく同期
4. プレビューテスト: ローカルWebView2で口パクと音声が同期
5. 非配信テスト: ブラウザ通常再生で問題なし
