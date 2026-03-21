# リップシンクと音声の4秒ずれ修正プラン

## ステータス: 完了（暫定対応）

## 問題

配信時、アバターの口パク（リップシンク）と実際の音声が約4秒ずれている。
口が先に動き、声が約4秒遅れて聞こえる。

## 現状のアーキテクチャ

### 2つの独立したキャプチャパス

```
【映像パス】（低遅延）
  broadcast.html（VRM口パクアニメーション）
    ↓ WebView2レンダリング
  Windows Graphics Capture API
    ↓ BGRAフレーム
  Named Pipe（8MB, ただしフレーム1.38MB/枚 → 実質バッファ ~200ms）
    ↓
  FFmpeg 映像エンコード → RTMP → Twitch

【音声パス】（高遅延 ← ★問題の根本）
  broadcast.html（<audio>要素でTTS再生）
    ↓ 音声ロード＋再生開始遅延 (~200-500ms)
  Windowsオーディオシステム
    ↓ WASAPI Loopback (~20-50ms)
  ConcurrentQueue → AudioWriterLoop
    ↓
  Named Pipe（1MB = ~2.7秒分のバッファ ← ★最大の遅延源）
    ↓
  FFmpeg 音声エンコード(AAC) → RTMP → Twitch
```

### リップシンクのタイミング（現状）

```
T+0ms:    サーバがWebSocket "lipsync" イベント送信
           → broadcast.htmlが即座に口パクアニメーション開始 ← ★ここが早すぎる
           → lipsyncStart = performance.now() / 1000
T+5ms:    サーバがWebSocket "play_audio" イベント送信
T+10ms:   broadcast.htmlがHTTP GET /api/tts/audio → 音声ロード開始
T+200ms:  canplaythrough → ttsAudio.play() → 音声再生開始
T+250ms:  Windowsオーディオ出力
T+300ms:  WASAPI Loopbackキャプチャ
T+300ms:  ConcurrentQueueに入る
T+300ms:  AudioWriterLoopがNamed Pipeに書き込み
          → パイプバッファに~2.7秒分のデータが溜まっている
T+3000ms: FFmpegがこの音声データを読み取り → エンコード → RTMP送信
```

つまり映像（口パク）はT+0msにキャプチャされるが、対応する音声は約3秒後にFFmpegに到達する。

## 原因分析

### 原因1: ブラウザ内での口パク・音声タイミング不一致（~200-500ms）

`lipsync` WebSocketイベント受信時に即座にアニメーション開始するが、
`play_audio` イベントの音声はHTTPフェッチ→デコード→再生まで200-500msかかる。
口が先に動き始める。

### 原因2: 音声パイプバッファによる持続的遅延（~2.7秒）★最大原因

音声Named Pipeのバッファサイズは1MB。48kHz stereo f32leで約2.7秒分。
起動時に3秒のサイレンスを注入して**パイプバッファを満杯にする**。
その後WASAPI入力がFFmpeg読み取りと同速で流れるため、**バッファレベルが下がらず**、
すべての音声データが~2.7秒の遅延を持つ。

### 原因3: 映像と音声のパイプバッファ差（~2.5秒）

| パイプ | バッファサイズ | 実効遅延 |
|--------|-------------|---------|
| 映像 | 8MB | ~200ms（1フレーム1.38MB、5-6フレーム分） |
| 音声 | 1MB | ~2,700ms（384KB/秒で2.7秒分） |

**差: 約2.5秒**。これが映像パスと音声パスの遅延差の主因。

### 原因4: 初期サイレンス3秒注入（遅延を固定化）

```csharp
// FfmpegProcess.cs StartAsync()
var silenceChunk = new byte[38400]; // 100ms
for (var i = 0; i < 30; i++)       // 30 × 100ms = 3秒
    _audioPipe.Write(silenceChunk, 0, silenceChunk.Length);
```

1MBパイプに1.15MBのサイレンスを書き込む。バッファが溢れてFFmpegが読み取るまで
Write()がブロック。結果として起動完了時にパイプは満杯。

### 合計遅延の内訳

| 要因 | 遅延 |
|------|------|
| ブラウザ音声ロード+再生遅延 | ~300ms |
| 音声パイプバッファ（1MB） | ~2,700ms |
| WASAPI Loopback遅延 | ~50ms |
| ConcurrentQueue + WriterLoop | ~10ms |
| AAC エンコード遅延 | ~23ms |
| 映像パイプバッファ（相殺分） | -200ms |
| **合計** | **~2.9秒** |

サイレンス注入の効果やWASAPI開始遅延を加味すると **約3-4秒** のずれ。

## 修正方針

### Phase 1: ブラウザ内同期修正（最重要・即効性あり）

**ファイル**: `static/broadcast.html`

口パクアニメーションを「WebSocketイベント受信時」ではなく「音声再生開始時」に開始する。

#### 現状:
```javascript
// lipsyncイベント → 即座にアニメーション開始
setLipsync(frames) {
  lipsyncFrames = frames;
  lipsyncStart = performance.now() / 1000;  // ← 今ここで開始
}
```

#### 修正後:
```javascript
// lipsyncイベント → フレームデータを保存のみ
setLipsync(frames) {
  pendingLipsyncFrames = frames;  // 保存のみ、アニメーション未開始
}

// play_audioイベント → 音声ロード＋再生
case 'play_audio':
  ttsAudio.src = data.url;
  ttsAudio.load();
  ttsAudio.oncanplaythrough = () => {
    ttsAudio.oncanplaythrough = null;
    ttsAudio.play().then(() => {
      // 音声再生開始と同時にリップシンク開始
      if (pendingLipsyncFrames) {
        lipsyncFrames = pendingLipsyncFrames;
        lipsyncStart = performance.now() / 1000;
        pendingLipsyncFrames = null;
      }
    }).catch(e => console.error('TTS再生エラー:', e));
  };
```

**効果**: ブラウザ内で口パクと音声が完全同期。WGCとWASAPIが同じ瞬間をキャプチャするため、映像パスと音声パスの差がそのまま配信上のずれになる。

### Phase 2: 音声パイプバッファ縮小（遅延差の根本解消）

**ファイル**: `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs`

#### 2a. 音声パイプバッファを1MB→64KBに縮小

```csharp
// 現状: 1MB → ~2.7秒分のバッファ
_audioPipe = new NamedPipeServerStream(
    _audioPipeName, PipeDirection.Out, 1,
    PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
    outBufferSize: 1024 * 1024, inBufferSize: 0);  // 1MB

// 修正: 64KB → ~170ms分のバッファ（映像パイプの200msに近い）
_audioPipe = new NamedPipeServerStream(
    _audioPipeName, PipeDirection.Out, 1,
    PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
    outBufferSize: 64 * 1024, inBufferSize: 0);  // 64KB
```

**効果**: 音声パイプ遅延を2.7秒→170msに削減。映像パイプ遅延(200ms)とほぼ同等になり、パイプ起因のずれがほぼ解消。

#### 2b. 初期サイレンスを3秒→300msに縮小

AACエンコーダのプライミングに最低限必要な量（~100ms分のデータ）＋マージン。

```csharp
// 現状: 30チャンク × 100ms = 3秒
for (var i = 0; i < 30; i++)
    _audioPipe.Write(silenceChunk, 0, silenceChunk.Length);

// 修正: 3チャンク × 100ms = 300ms（AACプライミングの最小要件）
for (var i = 0; i < 3; i++)
    _audioPipe.Write(silenceChunk, 0, silenceChunk.Length);
```

**効果**: パイプバッファを事前に満杯にしない。64KBパイプに115.2KBの書き込みは一部ブロックするが、300msなのですぐに解消。

### Phase 3: ConcurrentQueueの上限縮小

**ファイル**: `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs`

```csharp
// 現状: 500チャンク（~5秒分）
private const int MaxAudioQueueChunks = 500;

// 修正: 50チャンク（~500ms分）
private const int MaxAudioQueueChunks = 50;
```

**理由**: パイプバッファが64KBになったため、AudioWriterLoopがブロックされる頻度が上がる。
キュー上限を50に下げて、古いデータが大量に蓄積するのを防ぐ。
50チャンク ≈ 500msのバッファは一時的な書き込みブロックを吸収するのに十分。

### Phase 4: サイレンスタイマーの調整

**ファイル**: `win-native-app/WinNativeApp/Streaming/AudioLoopback.cs`

パイプバッファが小さくなったため、サイレンス注入の頻度・ガードを再調整。

- サイレンスチャンクサイズ: 38,400バイト（100ms）のまま
- ガード時間: 200ms（変更なし）
- 初期ガード: 100ms（変更なし）

パイプバッファが小さいため、サイレンス注入がパイプバッファ上で占める割合が増える。
だが音声途切れ防止のために必要なので、まずは変更なしで検証。

## 実装ステップ

### Step 1: Phase 1（broadcast.html修正）
1. `pendingLipsyncFrames` 変数を追加
2. `setLipsync()` をフレーム保存のみに変更
3. `play_audio` ハンドラで `ttsAudio.play()` 成功時にリップシンク開始
4. `lipsync_stop` ハンドラで `pendingLipsyncFrames` もクリア
5. ブラウザで動作確認（開発者ツールのコンソールでタイミング確認）

### Step 2: Phase 2-3（C#アプリ修正）
1. 音声パイプバッファを64KBに縮小
2. 初期サイレンスを300msに縮小
3. ConcurrentQueue上限を50に変更
4. ビルド＋ローカル配信テスト

### Step 3: 配信テスト・調整
1. Twitchで配信開始
2. 口パクと音声のタイミングを確認
3. まだずれがある場合、FFmpegの `-itsoffset` で微調整
   ```
   -itsoffset -0.3 (音声入力の前に追加、値はテストで調整)
   ```

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| パイプバッファ縮小でFFmpegへの音声供給が不安定に | 音声途切れ | ConcurrentQueueが吸収。改善しない場合は128KBに拡大 |
| 初期サイレンス縮小でAACプライミング不足 | 配信開始時に音が割れる | 300msで不足なら500msに増やす。最悪1秒に |
| play()のPromise解決が遅い環境がある | 口パクが遅れて始まる | playingイベントにフォールバック |
| AudioWriterLoopのパイプ書き込みブロック頻度増加 | CPU使用率微増 | Thread.Sleep(1)で待機するためCPU影響は最小限 |

## Phase 1だけでどこまで改善するか

Phase 1（ブラウザ内同期）だけでも、口パクと音声がブラウザ内で完全同期するため、
**映像パスと音声パスの遅延差（~2.5秒）がそのまま残る** が、
「口が先に動いて声が後から聞こえる」→「口と声が同時に遅れる」に変わる。
視聴者にとっては口パクと音声が合って見えるため、**体感的には大幅改善**。

Phase 2で音声パイプバッファを縮小すれば、遅延差自体が~170ms程度に縮まり、
ほぼ完全にリップシンクが合う。

## 推奨実装順

1. **Phase 1** → 最も効果が高く、リスクが最も低い。broadcast.htmlのJS変更のみ
2. **Phase 2** → Phase 1で体感改善した後、さらに遅延を詰める
3. **Phase 3** → Phase 2と同時に実施
4. **Phase 4** → Phase 2-3の結果を見てから判断
