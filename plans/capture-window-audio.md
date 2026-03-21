# キャプチャウィンドウの音を配信に自然に乗せる検証

## ステータス: 検証待ち

## 背景

現在のウィンドウキャプチャ（WGC: Windows Graphics Capture API）は**映像のみ**。キャプチャ対象ウィンドウ（ゲーム・YouTube等）の音声は配信に含まれない。

### 現在の音声パイプライン

```
タイマーベース音声ジェネレータ (10ms間隔, FfmpegProcess.cs:350)
  ├─ 無音チャンク生成 (48kHz stereo f32le)
  ├─ MixBgmInto(chunk)  ← BGMループ再生
  ├─ MixTtsInto(chunk)  ← TTS音声キュー
  ├─ _audioQueue.Enqueue(chunk)
  └─ AudioWriterLoop → Named Pipe → FFmpeg → RTMP

ローカル再生（モニタリング用、配信パイプラインとは独立）
  ├─ TTS: PlayTtsLocally() → WaveOutEvent（デフォルト出力デバイス）
  └─ BGM: WaveOutEvent（デフォルト出力デバイス）
```

音声ソースはTTSとBGMの2つのみ。キャプチャウィンドウの音声を追加するにはこのミキサーに3つ目のソースを組み込む必要がある。

### 既存の制約・前提

- **NAudio 2.2.1** を使用（NAudio.Wasapi.dll含む）
- ターゲット: `net8.0-windows10.0.22621.0`（Windows 11 22H2）
- ウィンドウのHWNDは `CaptureManager.StartCapture(hwnd, ...)` で取得済み
- HWNDからPIDを取得する `GetWindowThreadProcessId` は `WindowEnumerator.cs:28` に既に定義済み
- ローカル再生（TTS/BGM）は WaveOutEvent でデフォルト出力デバイスに出力
- FFmpegへの音声入力は1本のNamed Pipe（`\\.\pipe\winnative_audio_{PID}`）

---

## 方式比較

### 方式A: WASAPI Process Loopback（プロセス単位キャプチャ）

**概要**: `ActivateAudioInterfaceAsync` + `AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS` で特定プロセスの音声のみキャプチャ。

| 項目 | 評価 |
|------|------|
| 音声分離 | ◎ 対象プロセスのみ |
| 二重音声問題 | ◎ なし |
| 実装難度 | △ COM interop必須（NAudio 2.2.1未サポート） |
| OS要件 | ○ Build 20348+（プロジェクト対応済み） |
| 追加依存 | ◎ なし（P/Invoke のみ） |
| 複数キャプチャ対応 | ○ プロセスごとに独立キャプチャ可能 |

**NAudio 2.2.1の対応状況（調査済み）**:
- `WasapiLoopbackCapture` はシステム全体のみ。**Process Loopback未サポート**
- [NAudio Issue #878](https://github.com/naudio/NAudio/issues/878) で開発中だが未マージ
- → **COM API直接呼び出しが必要**

**必要なCOM構造体**:
```csharp
// ActivateAudioInterfaceAsync + AUDIOCLIENT_ACTIVATION_PARAMS
[StructLayout(LayoutKind.Sequential)]
struct AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS {
    public uint TargetProcessId;
    public PROCESS_LOOPBACK_MODE ProcessLoopbackMode;
}

enum PROCESS_LOOPBACK_MODE {
    INCLUDE_TARGET_PROCESS_TREE = 0,  // ← 使うのはこれ
    EXCLUDE_TARGET_PROCESS_TREE = 1,
}
```

**参考実装**: [Microsoft Application Loopback Audio Sample](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/)

---

### 方式B: WASAPI System Loopback（システム全体キャプチャ）

**概要**: NAudio `WasapiLoopbackCapture` でデフォルト出力デバイスの全音声をキャプチャ。

| 項目 | 評価 |
|------|------|
| 音声分離 | ✕ 全アプリの音が混ざる |
| 二重音声問題 | ✕ あり（後述） |
| 実装難度 | ◎ NAudio標準APIのみ |
| OS要件 | ◎ 全Windows対応 |
| 追加依存 | ◎ なし |
| 複数キャプチャ対応 | △ システム全体で1つ |

**二重音声問題の詳細**:
```
現在の音声フロー（配信中）:
  TTS → PlayTtsLocally() → WaveOutEvent → スピーカー ─┐
  TTS → DecodeWav() → MixTtsInto() → FFmpeg ──────────┼→ 配信
  BGM → StartBgmPlayback() → WaveOutEvent → スピーカー ┘  （TTS/BGMが2重）
```

System Loopbackはスピーカー出力をキャプチャするため、ローカル再生中のTTS/BGMも拾う。
FFmpegミキサーにも別途 MixTtsInto/MixBgmInto で送っているため、配信では2重に聞こえる。

**二重音声の回避策**:

| 対策 | 実現性 | トレードオフ |
|------|--------|-------------|
| ローカル再生を停止し、Loopbackのみにする | △ | ユーザーがPC上でモニタリングできなくなる |
| FFmpegミキサーの TTS/BGM ミキシングを無効化し、Loopback1本にする | ○ | 配信内の音量をC#側で個別制御できなくなる（OSの音量ミキサーに依存） |
| TTS/BGMを別の出力デバイスに送る | △ | 複数オーディオデバイスが必要、設定が複雑 |

---

### 方式C: Virtual Audio Cable（仮想デバイス経由）

**概要**: VB-CABLE等のサードパーティ仮想オーディオデバイスを使い、対象アプリの出力先を変更。

| 項目 | 評価 |
|------|------|
| 音声分離 | ○ デバイス単位 |
| 二重音声問題 | ○ デバイス分離で回避 |
| 実装難度 | ○ NAudio標準API |
| OS要件 | ◎ 全Windows対応 |
| 追加依存 | ✕ サードパーティソフト必須 |
| 複数キャプチャ対応 | △ デバイス数分 |

自動化困難。ユーザーが手動でアプリの出力先を変更する必要があり、「全自動配信」の理念に合わない。

---

### 方式D: FFmpeg側で複数音声入力を受ける

**概要**: FFmpegコマンドに2つ目の音声入力（Named Pipe or デバイス）を追加し、`amix`フィルタで合成。

| 項目 | 評価 |
|------|------|
| 音声分離 | ○（入力次第） |
| 二重音声問題 | ○（入力次第） |
| 実装難度 | △ FFmpegコマンドライン大幅変更 |
| OS要件 | ◎ |
| 追加依存 | ◎ |
| 複数キャプチャ対応 | △ |

```
# 現在のFFmpegコマンド（概要）
ffmpeg -f rawvideo -i pipe:video -f f32le -i pipe:audio_mix -c:v h264 -c:a aac -f flv rtmp://...

# 方式D: 2パイプ＋amixフィルタ
ffmpeg -f rawvideo -i pipe:video \
       -f f32le -i pipe:audio_tts_bgm \
       -f f32le -i pipe:audio_capture \
       -filter_complex "[1:a][2:a]amix=inputs=2" \
       -c:v h264 -c:a aac -f flv rtmp://...
```

問題: FFmpegの`amix`は遅延が発生しやすく、ライブ配信の音声同期が難しい。現在のC#ミキサーの方が制御性が高い。

---

## 評価まとめ

| 方式 | 音声品質 | 分離精度 | 実装コスト | 運用コスト | 自動化 | 総合 |
|------|---------|---------|-----------|-----------|--------|------|
| **A: Process Loopback** | ◎ | ◎ | △（COM interop） | ◎ | ◎ | **★★★★☆** |
| B: System Loopback | ◎ | ✕ | ◎ | △（二重音声対策） | ○ | ★★☆☆☆ |
| C: Virtual Cable | ◎ | ○ | ○ | ✕（手動設定） | ✕ | ★☆☆☆☆ |
| D: FFmpeg amix | ○ | ○ | △ | ○ | ○ | ★★☆☆☆ |

---

## 推奨: 方式A（WASAPI Process Loopback）

**理由**:
1. 対象プロセスの音声のみキャプチャ → 二重音声問題なし
2. `INCLUDE_TARGET_PROCESS_TREE` モードでブラウザ等のマルチプロセスアプリにも対応
3. COM interopは複雑だが、Microsoftの[公式サンプル](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/)がC++で存在し、C#への移植は定型的
4. 既存のAudioGeneratorミキサーに `MixCaptureAudioInto()` を追加するだけで統合可能
5. 「全自動配信」の理念に最も合致（追加設定不要）

---

## 実装ステップ

### Phase 1: PoC（プロセス音声キャプチャの実証）

1. `ActivateAudioInterfaceAsync` の P/Invoke 定義を作成
2. `AUDIOCLIENT_ACTIVATION_PARAMS` + `PROCESS_LOOPBACK_PARAMS` 構造体定義
3. `IActivateAudioInterfaceCompletionHandler` コールバック実装
4. 最小限のコンソールアプリで特定PIDの音声をWAVファイルに保存
5. 音声フォーマットの確認（出力は通常 float32/48kHz/stereo だが、プロセスによって異なる可能性）

### Phase 2: ミキサー統合

1. `Capture/ProcessAudioCapture.cs` 新規作成
   - Process Loopback の開始/停止
   - キャプチャデータ → 48kHz stereo f32le への変換（リサンプリング）
   - ConcurrentQueue でバッファリング
2. `FfmpegProcess` に `MixCaptureAudioInto(chunk)` を追加（MixBgmIntoと同パターン）
3. `CaptureManager.StartCapture()` でビデオキャプチャと同時に音声キャプチャも開始
4. 音量制御: `_captureAudioVolume` フィールド + `SetCaptureAudioVolume()` メソッド

### Phase 3: UI・制御

1. キャプチャ音声の音量スライダー（broadcast.htmlの設定パネル）
2. WebSocket `/ws/control` 経由で音量変更を配信アプリに伝達
3. キャプチャ開始APIに `withAudio` オプション追加（デフォルトtrue）
4. 配信アプリのコントロールパネルに音声キャプチャ状態表示

### Phase 4: 品質調整

1. **A/V同期**: WGCとProcess Loopbackの遅延差を測定し補正
   - WGC: 約2-3フレーム（66-100ms @30fps）の映像遅延
   - WASAPI: バッファサイズ依存（10-20ms）の音声遅延
   - 映像の方が遅れるため、音声側にもディレイバッファが必要な可能性
2. **ダッキング**: TTS再生中にキャプチャ音声を自動減衰（-6dB〜-12dB）
3. **無音検出**: プロセスが音を出していない時にリソースを節約

---

## リスクと対策

| リスク | 影響度 | 対策 |
|--------|--------|------|
| COM interop実装の複雑さ | 中 | MS公式サンプルを参考に定型的な移植。失敗時は方式Bにフォールバック |
| プロセスが音声を出さないケース（IDE等） | 低 | 無音時は何もしない（既存BGM/TTSと同じ動作） |
| マルチプロセスアプリの音声取りこぼし | 低 | `INCLUDE_TARGET_PROCESS_TREE` で子プロセスも含める |
| A/V同期ずれ | 中 | ディレイバッファで補正。既存の `AudioOffset` 機構を拡張 |
| TTS発話中にキャプチャ音声が邪魔 | 中 | ダッキング（TTS再生検知 → キャプチャ音量を自動低減） |
| 高負荷時の音声途切れ | 低 | ConcurrentQueue + ドロップカウンター（既存パターン踏襲） |
| 対象プロセスが排他モード音声を使用 | 低 | 排他モードのプロセスはLoopbackキャプチャ不可。ゲームでは稀 |

---

## 方式Bへのフォールバック判断基準

以下の場合は方式B（System Loopback）に切り替える:
- COM interopの実装が安定せず、音声が断続的に途切れる
- Process Loopbackが特定のアプリ（ゲームエンジン等）で機能しない

方式Bの場合の二重音声対策:
- FFmpegミキサーの TTS/BGM ミキシングを無効化し、全音声をLoopbackから取得
- 音量制御はOSのアプリ音量ミキサー経由（C#から `ISimpleAudioVolume` で制御可能）
- ローカル再生はそのまま維持（ユーザーのモニタリング用）

---

## 関連ファイル

| ファイル | 役割 |
|----------|------|
| `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs` | 音声ミキサー（AudioGenerator, MixBgmInto, MixTtsInto） |
| `win-native-app/WinNativeApp/Streaming/TtsDecoder.cs` | TTS WAV→PCM変換（フォーマット変換パターンの参考） |
| `win-native-app/WinNativeApp/Capture/CaptureManager.cs` | ウィンドウキャプチャ管理（音声キャプチャ連携先） |
| `win-native-app/WinNativeApp/Capture/WindowEnumerator.cs` | `GetWindowThreadProcessId` 定義済み（PID取得） |
| `win-native-app/WinNativeApp/MainForm.cs` | 統合制御（キャプチャ開始/停止、TTS/BGMローカル再生） |
| `static/js/broadcast-main.js` | 音量UI（キャプチャ音量スライダー追加先） |

## 参考リソース

- [Microsoft Application Loopback Audio Sample](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/) — C++リファレンス実装
- [AUDIOCLIENT_ACTIVATION_PARAMS](https://learn.microsoft.com/en-us/windows/win32/api/audioclientactivationparams/ns-audioclientactivationparams-audioclient_activation_params) — COM構造体定義
- [NAudio Issue #878](https://github.com/naudio/NAudio/issues/878) — Process Loopback対応の開発状況
- [ActivateAudioInterfaceAsync](https://learn.microsoft.com/en-us/windows/win32/api/mmdeviceapi/nf-mmdeviceapi-activateaudiointerfaceasync) — COMエントリポイント
