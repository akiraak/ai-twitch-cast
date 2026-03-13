# 音が鳴らない問題 + 配信画面UI表示問題 修正プラン

## ステータス: 実装済み（検証待ち）

## Context

BGM音声が配信で鳴らない問題。WSL2配信（xvfb + PulseAudio）では音が出ていたが、Electron配信に移行後に鳴らなくなった。
加えて、配信画面に編集用ツールバーが表示されている問題も発見。

## 問題1: BGMが配信で鳴らない

### 再現手順
1. Electronアプリ起動 → BGMが自動再生される（ブラウザ内では鳴っている）
2. 配信を開始する（FFmpeg起動）
3. 別のPCで配信を見ると音が鳴っていない

### WSL2 vs Electron 音声パイプライン比較

#### WSL2（動作していた）
```
Chromium(broadcast.html) → <audio>.play() → PulseAudio "broadcast" sink
FFmpeg: -f pulse -i broadcast.monitor → AAC → RTMP
```
- PulseAudioが**システムレベル**でブラウザの全音声を自動キャプチャ
- コード不要。`<audio>.play()` が鳴れば自動的にFFmpegに届く

#### Electron（鳴らない）
```
broadcast.html → IPC(audio-play-url) → main.js fetchAndDecodeToPcm()
  → HTTP fetch from WSL2 → WAV/MP3デコード → ミキサー → audioStreamRes.write()
FFmpeg: -f s16le -i http://127.0.0.1:9090/audio-pcm-stream → AAC → RTMP
```
- 自前のIPC+HTTP経由でPCMデータを**明示的に**送る必要がある

### 根本原因

#### 1. タイミング問題（最重要）
- BGMはElectronアプリ起動直後（WebSocket接続時）に自動再生される
- この時点でFFmpegは未起動 → `audioStreamRes`がnull
- IPC `audio-play-url` ハンドラが**ログなしで`return`** → BGMデータが破棄される
- 配信開始後、FFmpegが接続しても**BGMのIPC通知は既に処理済み** → 誰もBGMをFFmpegに送らない

#### 2. MP3非対応
- BGMファイルはMP3形式だが、`processAudioUrl`はWAVしか対応していなかった
- `parseWavHeader()`がnullを返し、`WAVヘッダー解析失敗`でreturn

#### 3. BGMとTTSの競合
- `writeAudioAtRealtime()`が1つの`currentAudioTimer`を共有
- TTS再生時にBGMが強制停止、TTS終了後もBGM復帰なし

#### 4. ブラウザ側 `play()` が `load()` 完了前に呼ばれる
- `bgmAudio.load()` → 即 `bgmAudio.play()`。`AbortError`発生の可能性

### 修正内容

#### Step 1: `pendingBgmUrl` でタイミング問題を解決
- `win-capture-app/main.js` IPC `audio-play-url` ハンドラ: BGMの場合、`audioStreamRes`がnullなら`pendingBgmUrl`にURLを保存
- `/audio-pcm-stream` エンドポイント: FFmpeg接続時に保存済みBGM URLがあれば即座に`processBgmUrl()`で再生開始

#### Step 2: MP3デコード対応
- `decodeAudioToPcm()` 追加: FFmpegでMP3/OGG/M4A等をraw PCM (s16le 44100Hz stereo) にデコード
- `fetchAndDecodeToPcm()` 追加: WAVならパーサー、非WAVならFFmpegデコードの共通関数

#### Step 3: BGM+TTSミキサー
- `startMixer()` / `stopMixer()`: 50msチャンクでBGMとTTSを加算合成して同時再生
- BGMは自動ループ、TTSは1回再生
- 旧`writeAudioAtRealtime()`はレガシー互換で残存

#### Step 4: broadcast.html — `canplaythrough` 待機
- TTS/BGM両方で`oncanplaythrough`イベント後に`play()`を呼ぶ
- `onerror`ハンドラも追加

#### Step 5: その他
- `scripts/routes/avatar.py`: `/api/tts/audio` に `Cache-Control: no-cache` 追加
- `src/comment_reader.py`: ファイル削除前に `self._current_audio = None` で参照クリア

#### Step 6: 診断ログ強化
- main.js: 全音声処理ステップにalog追加（200件バッファ）
- broadcast.html: オーディオイベントの詳細ログ（`[Broadcast]`プレフィックスでalogに転送）
- `/audio/log` API: `state`オブジェクトに全状態を構造化出力

## 問題2: 配信画面に編集ツールバーが表示される

### 再現手順
1. Electronアプリでプレビューウィンドウを開く → 右側に配信制御UI、左側にプレビュー（正常）
2. 配信を開始する
3. 別のPCで配信を見ると、画面上部にウィンドウ追加・保存ボタン等の編集ツールバーが表示されている

### 根本原因
`broadcastWindow`（オフスクリーン、FFmpegキャプチャ対象）のURLに`?embedded`パラメータがない。

```
previewWindow:   /preview?token=... → iframe → /broadcast?token=...&embedded  → ツールバー非表示 ✓
broadcastWindow: /broadcast?token=...                                          → ツールバー表示 ✗
```

broadcast.htmlのロジック:
```javascript
const isEmbedded = new URLSearchParams(location.search).has('embedded') || window.parent !== window;
if (isEmbedded) document.body.classList.add('embedded');
```
```css
body.embedded .edit-toolbar { display: none; }
```

### 修正内容
`win-capture-app/main.js` の `openBroadcastWindow()`:
```javascript
// 修正前
const broadcastUrl = `${serverUrl}/broadcast?token=${token}`;
// 修正後
const broadcastUrl = `${serverUrl}/broadcast?token=${token}&embedded`;
```

## 対象ファイル
1. `win-capture-app/main.js` — pendingBgmUrl + MP3デコード + ミキサー + embedded + ログ強化
2. `static/broadcast.html` — canplaythrough待機 + ログ強化
3. `scripts/routes/avatar.py` — Cache-Control追加
4. `src/comment_reader.py` — ファイル削除前クリーンアップ

## 検証方法
1. `curl http://localhost:8080/api/status` でサーバー応答確認
2. Electronアプリをリビルド＋デプロイ
3. アプリ起動 → BGM自動再生を確認
4. 配信開始 → `curl http://localhost:8080/api/broadcast/audio-log` でログ確認
   - `BGM URL保存 (配信開始待ち)` → `保存済みBGM再生開始` の流れを確認
   - `mixer_active: true`, `bgm_loaded: true` を確認
5. 別PCで配信視聴 → BGM音声が聞こえるか確認
6. 別PCで配信視聴 → 編集ツールバーが表示されていないか確認
7. デバッグ詳細: `memory/audio-debug.md` 参照
