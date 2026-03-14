# 現在のシステムアーキテクチャ

## 全体像

```
┌─ WSL2 (Linux) ─────────────────────────────────────────────────────┐
│                                                                     │
│  FastAPI サーバー (port 8080)                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  AI / TTS / DB / Twitch / 制御API                           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│       │WebSocket /ws/broadcast          │HTTP API                   │
│       │(イベント配信)                    │(制御・設定)               │
│       ↓                                 ↓                           │
│  ┌──────────┐                    ┌──────────────┐                   │
│  │ブラウザで │ ← 開発・確認用     │ index.html   │ ← 管理UI         │
│  │broadcast │                    │ (操作パネル)  │                   │
│  │.html表示  │                    └──────────────┘                   │
│  └──────────┘                                                       │
│                                                                     │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ WebSocket /ws/control (制御)
                          │ HTTP (キャプチャ・ストリーム操作)
                          ↓
┌─ Windows ───────────────────────────────────────────────────────────┐
│                                                                     │
│  Electron アプリ (port 9090)                                        │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  配信レンダリング / ウィンドウキャプチャ / FFmpeg配信         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│       │ RTMP (H.264 + AAC)                                         │
│       ↓                                                             │
│  ┌──────────┐                                                       │
│  │ Twitch   │                                                       │
│  └──────────┘                                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3つの実行環境

### 1. WSL2 サーバー（バックエンド）

Python FastAPI。AI・音声・DB・Twitch連携など「頭脳」を担当。

| 処理 | ライブラリ / 技術 | ファイル |
|------|------------------|---------|
| Webサーバー | **FastAPI** + **uvicorn** | `scripts/web.py` |
| AI応答生成 | **Gemini 3 Flash Preview** (`google-generativeai`) | `src/ai_responder.py` |
| 音声合成(TTS) | **Gemini 2.5 Flash TTS** | `src/tts.py` |
| Twitchチャット | **twitchio** (IRC) | `src/twitch_chat.py` |
| DB | **SQLite** (WAL mode, `aiosqlite`) | `src/db.py` |
| コメント処理 | asyncio + スレッドプール | `src/comment_reader.py` |
| トピック自動生成 | Gemini + Google Search + Thinking | `src/topic_talker.py` |
| Git監視 | `git log` ポーリング (10秒間隔) | `src/git_watcher.py` |
| 設定管理 | SQLite + `scenes.json` フォールバック | `src/scene_config.py` |
| WebSocket配信 | FastAPI WebSocket | `scripts/routes/overlay.py` |
| Electron制御 | WebSocket `/ws/control` クライアント | `scripts/routes/capture.py` |

### 2. broadcast.html（配信画面）

ブラウザ上で動作するHTML/JS。映像・音声・UI要素を合成する「画面」。

| 処理 | ライブラリ / 技術 | 備考 |
|------|------------------|------|
| VRMアバター描画 | **Three.js** + **@pixiv/three-vrm** (WebGL) | CDN経由ESM import |
| アイドルアニメ | 自作JS（sine波: 呼吸・揺れ・頭・腕） | requestAnimationFrame |
| まばたき | BlendShape `blink` (80ms, 2-4秒ランダム) | |
| 耳ぴくぴく | BlendShape `ear_stand` (150-300ms) | |
| リップシンク | BlendShape `aa` (30fpsフレーム制御) | |
| 感情表現 | 任意BlendShape制御 | WebSocketイベント |
| 字幕パネル | HTML/CSS (フェードアニメーション) | |
| TODOパネル | HTML/CSS (パルスアニメーション) | |
| トピックパネル | HTML/CSS (ドットアニメーション) | |
| 背景画像 | `<img>` cover表示 | |
| キャプチャ表示 | `<img>` + IPC or HTTPポーリング | |
| レイアウト編集 | 自作JS (ドラッグ・リサイズ・スナップ) | 常時有効 |
| TTS再生 | `<audio>` 要素 | |
| BGM再生 | `<audio loop>` 要素 | |
| サーバー通信 | **WebSocket** `/ws/broadcast` | 単一接続 |

### 3. Electron アプリ（Windows側）

Node.js + Electron。配信レンダリング・キャプチャ・エンコードなど「体」を担当。

| 処理 | ライブラリ / 技術 | 備考 |
|------|------------------|------|
| broadcast.html表示 | **Electron** `BrowserWindow({offscreen: true})` | オフスクリーン |
| フレームキャプチャ | Electron `paint`イベント → `toBitmap()` BGRA | |
| FFmpeg配信 | **FFmpeg** 子プロセス (stdin rawvideo + HTTP audio) | RTMP出力 |
| 音声デコード | **FFmpeg** 子プロセス (MP3/OGG → PCM) or WAVパース | |
| 音声ミキシング | 自作JS（BGM+TTS → PCM, 50msチャンク, 壁時計同期） | |
| 音声配信 | HTTP `/audio-pcm-stream` (s16le 44100Hz stereo) | FFmpegが読む |
| ウィンドウキャプチャ | Electron `desktopCapturer` + `getUserMedia` | canvas→JPEG |
| HTTPサーバー | **Express** | API・スナップショット |
| WebSocketサーバー | **ws** | `/ws/capture`, `/ws/control` |
| フレーム転送 | Electron IPC (`capture-frame-to-broadcast`) | broadcast.htmlへ直接 |

---

## broadcast.html 画面合成の仕組み

broadcast.html は**静的HTMLファイル**（`static/broadcast.html`）で、FastAPIが静的ファイルとして配信する。
サーバーサイドでの動的生成はなく、ページ内のJavaScriptがWebSocket経由でサーバーと通信し、画面を動的に構築する。

### 背景画像

```
┌─ broadcast.html 起動時 ────────────────────────────────────────────┐
│                                                                     │
│  fetch('/api/files/background/list')                               │
│       ↓ レスポンス: { ok, active }                                  │
│  <img id="background"> の src を設定                                │
│  (CSS: position:absolute, z-index:0, object-fit:cover)             │
│                                                                     │
│  WebSocket受信: { type: "background_change", url }                 │
│       ↓                                                            │
│  #background.src = data.url  ← 即座に切り替え                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### VRMアバター

```
┌─ broadcast.html 起動時 ────────────────────────────────────────────┐
│                                                                     │
│  CDN から ESM import:                                              │
│  ├─ three@0.169.0 (Three.js)                                      │
│  └─ @pixiv/three-vrm@3.3.3 (VRMローダー)                          │
│                                                                     │
│  Three.js セットアップ:                                             │
│  ├─ WebGLRenderer (alpha:true, antialias:true)                     │
│  ├─ OrthographicCamera                                             │
│  └─ AmbientLight(0.75) + DirectionalLight(1.0)                    │
│                                                                     │
│  fetch('/api/files/avatar/list') → VRM URL取得                      │
│       ↓                                                            │
│  GLTFLoader + VRMLoaderPlugin で .vrm ファイルをロード              │
│       ↓                                                            │
│  scene.add(vrm.scene) → #avatar-canvas に描画                      │
│  (CSS: position:absolute, z-index:5)                               │
│                                                                     │
│  requestAnimationFrame ループ:                                      │
│  ├─ アイドルアニメ (sine波: 呼吸・揺れ・頭・腕)                     │
│  ├─ まばたき (BlendShape "blink", 80ms, 2-4秒ランダム)              │
│  └─ 耳ぴくぴく (BlendShape "ear_stand", 150-300ms)                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### アバターの発話（字幕＋感情＋リップシンク＋音声）

サーバー側で AI応答 → TTS → WebSocketイベント送信。broadcast.html が受信して表示・再生する。

```
┌─ WSL2サーバー (CommentReader._respond) ────────────────────────────┐
│                                                                     │
│  ① WebSocket送信: { type: "comment",                               │
│        message, response, english }      → 字幕表示トリガー         │
│  ② WebSocket送信: { type: "blendshape",                            │
│        shapes: {...} }                   → 感情表情の変化           │
│  ③ WebSocket送信: { type: "lipsync",                               │
│        frames: [...] }                   → 口パクアニメーション     │
│  ④ WebSocket送信: { type: "play_audio",                            │
│        url: "/api/tts/audio?t=..." }     → 音声再生                │
│                                                                     │
└────────────────────────┬────────────────────────────────────────────┘
                          │ WebSocket /ws/broadcast
                          ↓
┌─ broadcast.html ────────────────────────────────────────────────────┐
│                                                                      │
│  ① "comment" イベント:                                              │
│     #subtitle パネルに author / response / english を表示            │
│     (フェードイン 0.4s, z-index:20, 画面下部中央)                    │
│                                                                      │
│  ② "blendshape" イベント:                                           │
│     vrm.expressionManager で任意のBlendShapeを適用                   │
│     (例: happy, sad, angry → アバターの表情が変化)                   │
│                                                                      │
│  ③ "lipsync" イベント:                                              │
│     BlendShape "aa" を30fpsで制御 → 口パクアニメーション            │
│                                                                      │
│  ④ "play_audio" イベント:                                           │
│     ├─ [ブラウザ直接表示時] <audio>要素で再生                       │
│     └─ [Electron内] IPC → main.jsが音声デコード → ミキサーへ       │
│                                                                      │
│  ⑤ "speaking_end" イベント:                                         │
│     字幕フェードアウト (1.5s)、BlendShapeリセット                    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### broadcast.html WebSocketイベント一覧

| イベントタイプ | 方向 | 内容 |
|---------------|------|------|
| `comment` | サーバー→画面 | 字幕表示（message, response, english） |
| `speaking_end` | サーバー→画面 | 字幕フェードアウト |
| `play_audio` | サーバー→画面 | TTS音声再生（url） |
| `blendshape` | サーバー→画面 | 感情表情（shapes） |
| `lipsync` | サーバー→画面 | リップシンクフレーム（frames） |
| `lipsync_stop` | サーバー→画面 | リップシンク停止 |
| `background_change` | サーバー→画面 | 背景画像切り替え（url） |
| `avatar_vrm_change` | サーバー→画面 | VRMモデル切り替え（url） |
| `todo_update` | サーバー→画面 | TODOパネル更新（markdown） |
| `topic` | サーバー→画面 | トピックパネル更新 |
| `bgm_play` / `bgm_stop` | サーバー→画面 | BGM制御 |
| `volume_update` | サーバー→画面 | 音量変更 |

---

## FFmpegの役割

FFmpegは**Windows側Electronアプリ内の子プロセス**として動作し、broadcast.htmlのレンダリング結果を映像・音声エンコードしてTwitchに配信する。

```
┌─ Electron (Windows) ───────────────────────────────────────────────┐
│                                                                     │
│  broadcast.html BrowserWindow (offscreen: true)                    │
│       │ paint イベント (30fps)                                      │
│       ↓ toBitmap() → BGRA生データ (1920×1080×4 = 約8MB/frame)     │
│                                                                     │
│  音声ミキサー                                                       │
│       │ TTS + BGM → PCM (s16le, 48kHz, stereo)                     │
│       ↓ HTTP /audio-pcm-stream で配信                               │
│                                                                     │
│  ┌─ FFmpeg 子プロセス ─────────────────────────────────────────┐   │
│  │                                                               │   │
│  │  入力1 (映像): pipe:0 (stdin)                                │   │
│  │    -f rawvideo -pixel_format bgra                            │   │
│  │    -video_size 1920x1080 -framerate 30                       │   │
│  │                                                               │   │
│  │  入力2 (音声): http://localhost:9090/audio-pcm-stream        │   │
│  │    -f s16le -ar 48000 -ac 2                                  │   │
│  │                                                               │   │
│  │  エンコード:                                                  │   │
│  │    映像: libx264, preset ultrafast, CRF 20, 5000kbps         │   │
│  │    音声: AAC 128kbps, 44100Hz                                │   │
│  │                                                               │   │
│  │  出力: -f flv → rtmp://live-tyo.twitch.tv/app/{streamKey}   │   │
│  │                                                               │   │
│  │  バックプレッシャー制御:                                       │   │
│  │    stdin.writableLength > 8MB → フレームドロップ              │   │
│  │                                                               │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**FFmpegがやっていること:**
1. **映像エンコード** — Electronの paint イベントから受け取ったBGRA生フレームをH.264に圧縮
2. **音声エンコード** — ミキサーが合成したPCM音声（TTS+BGM）をAACに圧縮
3. **Muxing** — 映像と音声をFLVコンテナに多重化
4. **配信** — RTMPプロトコルでTwitch Ingestサーバーに送出

**FFmpegがやっていないこと:**
- 画面のレンダリング（→ broadcast.html + Electron）
- 音声の合成やミキシング（→ Electron main.js の音声ミキサー）
- 配信の開始・停止判断（→ WSL2サーバーからの制御）

---

## Go Live（配信開始〜Twitch配信）の全体フロー

```
ユーザーが管理UI (index.html) で「Go Live」ボタンを押す
  │
  │ POST /api/broadcast/go-live
  ↓
┌─ WSL2 サーバー (stream_control.py) ────────────────────────────────┐
│                                                                     │
│  broadcast_go_live():                                              │
│  ├─ _ensure_electron()  ← Electronアプリの起動確認                  │
│  ├─ _electron_stream_start():                                      │
│  │   ├─ .env から TWITCH_STREAM_KEY 取得                           │
│  │   ├─ WSL2 IP アドレス取得（serverUrl）                          │
│  │   └─ WebSocket /ws/control に送信:                              │
│  │       { action: "start_stream",                                 │
│  │         streamKey, serverUrl }                                   │
│  │                                                                  │
│  ├─ CommentReader 起動（Twitchチャット接続）                        │
│  ├─ GitWatcher 起動                                                │
│  ├─ エピソード作成（DB）                                            │
│  └─ .server_state ファイル作成                                      │
│                                                                     │
└────────────────────────┬────────────────────────────────────────────┘
                          │ WebSocket /ws/control
                          ↓
┌─ Electron (main.js) ───────────────────────────────────────────────┐
│                                                                     │
│  "start_stream" アクション受信:                                     │
│  ├─ BrowserWindow 作成 (offscreen: true)                           │
│  │   └─ http://[WSL2_IP]:8080/broadcast?token=xxx&embedded ロード  │
│  ├─ FFmpeg 子プロセス起動（映像stdin + 音声HTTP → RTMP）           │
│  ├─ paint イベントリスナー登録                                      │
│  └─ 音声ミキサー起動                                                │
│       │                                                             │
│       │ RTMP (H.264 + AAC)                                         │
│       ↓                                                             │
│  Twitch Ingest サーバー (live-tyo.twitch.tv)                       │
│       ↓                                                             │
│  視聴者に配信                                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**配信の責任分担まとめ:**

| 役割 | 担当 |
|------|------|
| 配信開始・停止の指示 | WSL2サーバー (`stream_control.py`) |
| broadcast.html の画面レンダリング | Electron BrowserWindow (offscreen) |
| 映像・音声のエンコード＋RTMP送出 | FFmpeg（Electron内の子プロセス） |
| 音声ミキシング（TTS+BGM→PCM） | Electron main.js |
| AI応答・TTS生成・イベント配信 | WSL2サーバー |
| Twitchチャット送受信 | WSL2サーバー (twitchio IRC) |

---

## データフロー

### コメント応答（最も頻繁な処理）

```
視聴者がTwitchチャットに投稿
  │
  │ twitchio (IRC)
  ↓
┌─ WSL2 ──────────────────────────────────────────────────────────┐
│                                                                  │
│  TwitchChat._on_message()                                       │
│       ↓                                                         │
│  CommentReader._respond()                                       │
│       │                                                         │
│       ├─ DB: ユーザー情報取得 (note, 会話履歴)                    │
│       ├─ Gemini: AI応答生成 (キャラ設定+文脈+履歴)               │
│       ├─ DB: コメント・応答を保存                                │
│       ├─ Gemini TTS: 音声合成 → WAVファイル                      │
│       ├─ WebSocket: 字幕表示イベント送信                         │
│       ├─ WebSocket: 音声URL送信                                  │
│       ├─ WebSocket: 感情BlendShape送信                           │
│       ├─ WebSocket: リップシンクフレーム送信                      │
│       └─ Twitch: チャットに応答投稿 (2秒遅延)                    │
│                                                                  │
└──────────────────────┬───────────────────────────────────────────┘
                       │ WebSocket /ws/broadcast
                       ↓
┌─ broadcast.html ─────────────────────────────────────────────────┐
│                                                                   │
│  1. 字幕パネル表示 (フェードイン 0.4s)                            │
│  2. 感情BlendShape適用 → アバター表情変化                         │
│  3. リップシンク開始 (30fps口パク)                                │
│  4. TTS音声再生                                                   │
│     ├─ [Electron内] → IPC → main.jsが音声デコード → ミキサーへ   │
│     └─ [ブラウザ]   → <audio>要素で直接再生                      │
│  5. 再生完了 → 字幕フェードアウト (1.5s)                          │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### ウィンドウキャプチャ（配信中の映像合成）

```
┌─ Windows ────────────────────────────────────────────────────────┐
│                                                                   │
│  desktopCapturer.getSources()                                    │
│       ↓ ウィンドウ一覧                                           │
│  getUserMedia({chromeMediaSource: 'desktop', sourceId})          │
│       ↓ MediaStream                                              │
│  capture-renderer.js: canvas描画 → toBlob('image/jpeg')         │
│       ↓ IPC: capture-frame                                       │
│  main.js                                                         │
│       ├─→ IPC: capture-frame-to-broadcast → broadcast.html      │
│       │   (直接転送、ネットワーク不要)                            │
│       └─→ WebSocket /ws/capture → プレビューウィンドウ           │
│           (バイナリ: 1byteインデックス + JPEG)                    │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## 配信していないとき vs 配信中

### 常時動作（サーバー起動中は常に）

```
┌─ WSL2 サーバー (常時) ───────────────────────────────────────────┐
│                                                                   │
│  FastAPI                                                         │
│  ├─ HTTP API (設定変更、ファイル管理、DB閲覧)                     │
│  ├─ WebSocket /ws/broadcast (broadcast.html接続待ち)             │
│  ├─ TODO.md ファイル監視 (2秒ポーリング → WebSocket通知)         │
│  └─ 静的ファイル配信 (/static, /resources, /bgm)                 │
│                                                                   │
│  ブラウザアクセス可能:                                             │
│  ├─ http://localhost:8080/          → 管理UI (index.html)        │
│  └─ http://localhost:8080/broadcast → 配信画面プレビュー          │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘

┌─ Electron (常時 ※起動している場合) ─────────────────────────────┐
│                                                                   │
│  Express HTTP サーバー (port 9090)                                │
│  ├─ ウィンドウキャプチャ管理 (追加・削除・一覧)                    │
│  ├─ WebSocket /ws/control (WSL2からの制御受付)                    │
│  └─ WebSocket /ws/capture (プレビュー用フレーム配信)              │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### Go Live（配信開始）で追加される処理

```
┌─ WSL2 サーバー (配信中に追加) ───────────────────────────────────┐
│                                                                   │
│  + CommentReader 起動                                            │
│  │  ├─ TwitchChat接続 (twitchio IRC)                             │
│  │  ├─ コメント受信キュー                                        │
│  │  ├─ AI応答生成 → TTS → WebSocket配信                          │
│  │  ├─ 無言時の自動発話 (TopicTalker, 30秒アイドル)              │
│  │  └─ ユーザーメモ更新 (15分バッチ)                              │
│  │                                                                │
│  + GitWatcher 起動                                                │
│  │  ├─ git logポーリング (10秒間隔)                               │
│  │  └─ 新コミット検出 → バッチ通知 (60秒クールダウン)             │
│  │                                                                │
│  + TopicTalker 稼働                                               │
│  │  ├─ トピック自動ローテーション (10分 or 5発話)                  │
│  │  └─ Gemini + Google Search + Thinking でトピック生成           │
│  │                                                                │
│  + エピソード作成 (DBに配信セッション記録)                         │
│  + .server_state ファイル作成 (再起動時の自動復旧用)              │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘

┌─ Electron (配信中に追加) ────────────────────────────────────────┐
│                                                                   │
│  + broadcast.html オフスクリーンウィンドウ起動                     │
│  │  └─ WSL2サーバーからロード                                     │
│  │     http://[WSL2_IP]:8080/broadcast?token=xxx&embedded        │
│  │                                                                │
│  + FFmpeg 子プロセス起動                                          │
│  │  ├─ 映像入力: broadcast.html paint → BGRA rawvideo → stdin   │
│  │  ├─ 音声入力: HTTP /audio-pcm-stream (s16le PCM)             │
│  │  └─ 出力: H.264+AAC → FLV → RTMP → Twitch                   │
│  │                                                                │
│  + 音声ミキサー起動                                               │
│  │  ├─ TTS: WAVフェッチ → PCMデコード → ミキサーへ               │
│  │  ├─ BGM: MP3/OGGフェッチ → FFmpegデコード → ミキサーへ        │
│  │  └─ 50msチャンクでミキシング → HTTP PCMストリーム → FFmpegへ   │
│  │                                                                │
│  + paintイベントリスナー                                          │
│     └─ 30fps: toBitmap() → BGRA → FFmpeg stdin (8MB超でドロップ) │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### 比較表

| 処理 | 常時 | 配信中のみ |
|------|:---:|:---:|
| FastAPI HTTP API | ○ | ○ |
| WebSocket /ws/broadcast | ○ (待機) | ○ (イベント配信) |
| TODO.md監視 | ○ | ○ |
| Twitchチャット受信 | | ○ |
| AI応答生成 | | ○ |
| TTS音声合成 | | ○ |
| トピック自動発話 | | ○ |
| Git監視 | | ○ |
| ユーザーメモ更新 | | ○ |
| Electronキャプチャ管理 | ○ (起動時) | ○ |
| broadcast.htmlオフスクリーン | | ○ |
| FFmpegエンコード+RTMP | | ○ |
| 音声ミキシング | | ○ |
| paintフレーム送出 | | ○ |

---

## 音声パイプライン詳細

配信中の音声は複雑な経路を辿る:

```
┌─ WSL2 ─────────────────────────────────────────────────────┐
│                                                             │
│  Gemini TTS API                                            │
│       ↓ PCM 16bit mono 24kHz                               │
│  WAVファイル保存 (/tmp/*.wav)                                │
│       ↓ URL                                                 │
│  WebSocket: {type: "play_audio", url: "/api/tts/audio?t="} │
│                                                             │
└────────────────────────┬────────────────────────────────────┘
                         │ WebSocket /ws/broadcast
                         ↓
┌─ broadcast.html (Electron内) ──────────────────────────────┐
│                                                             │
│  受信: play_audio イベント                                   │
│       ↓                                                     │
│  window.audioCapture.notifyPlayAudio(url)                  │
│       ↓ IPC: audio-play-url                                │
│                                                             │
└────────────────────────┬────────────────────────────────────┘
                         │ Electron IPC
                         ↓
┌─ Electron main.js ─────────────────────────────────────────┐
│                                                             │
│  HTTP fetch: WSL2サーバーからWAVダウンロード                  │
│       ↓                                                     │
│  WAVヘッダパース → PCM抽出                                   │
│       ↓                                                     │
│  リサンプル (24kHz → 44.1kHz, 線形補間)                      │
│  モノ → ステレオ変換                                         │
│       ↓                                                     │
│  ミキサー (50msチャンク)                                     │
│  ┌──────────────────────────────────┐                       │
│  │  BGM PCM ──┐                     │                       │
│  │            ├→ 加算(飽和) → 出力   │                       │
│  │  TTS PCM ──┘                     │                       │
│  │                                  │                       │
│  │  壁時計同期でドリフト補正          │                       │
│  │  RMSレベル計算 → /audio/levels    │                       │
│  └──────────────────────────────────┘                       │
│       ↓ PCM (s16le, 44100Hz, stereo)                       │
│  HTTP レスポンス /audio-pcm-stream                           │
│       ↓                                                     │
│  FFmpeg 音声入力                                             │
│       ↓ AAC 128kbps                                         │
│  RTMP → Twitch                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 通信プロトコル一覧

| 経路 | プロトコル | 方向 | 用途 |
|------|----------|------|------|
| ブラウザ → WSL2サーバー | HTTP REST | 双方向 | 設定変更・状態取得 |
| broadcast.html ↔ WSL2サーバー | WebSocket `/ws/broadcast` | 双方向 | イベント配信（字幕・音声・設定） |
| WSL2サーバー → Electron | WebSocket `/ws/control` | req/res | 制御コマンド（配信開始・停止等） |
| Electron → プレビュー | WebSocket `/ws/capture` | サーバー→クライアント | キャプチャフレーム配信 |
| Electron内 IPC | Electron IPC | 双方向 | フレーム転送・音声URL通知 |
| Electron → FFmpeg | stdin パイプ | 一方向 | BGRAフレーム |
| Electron → FFmpeg | HTTP ストリーム | 一方向 | PCM音声 |
| FFmpeg → Twitch | RTMP | 一方向 | H.264+AAC映像配信 |
| WSL2サーバー → Twitch | IRC (twitchio) | 双方向 | チャット送受信 |
| WSL2サーバー → Gemini | HTTPS | req/res | AI応答・TTS・トピック生成 |

---

## サーバー起動・復旧フロー

```
./run.sh
  ├─ .env読み込み (WEB_PORT等)
  ├─ 既存プロセス停止 (PIDファイル + ポートチェック)
  ├─ uvicorn起動 (--reloadなし)
  │
  ↓ FastAPI startup
  ├─ キャラクター設定ロード (DB → メモリ)
  ├─ 言語モード復元 (DB)
  ├─ TODO.md監視開始 (2秒ポーリング)
  │
  ├─ .server_state が存在する場合 (前回配信中に停止)
  │   ↓ バックグラウンドで _restore_session()
  │   ├─ CommentReader再起動 (Twitchチャット接続)
  │   ├─ GitWatcher再起動
  │   ├─ broadcast.html WebSocket接続待ち (30秒)
  │   └─ .pending_commit があれば読み上げ
  │
  ↓ 通常運用開始
  (HTTPリクエスト待ち)

  ↓ コミット時
  post-commit hook → .pending_commit保存 → サーバーkill
  → run.shが再起動ループで自動復帰 → 上記復旧フロー
```

---

## ステータス
- 作成日: 2026-03-14
- 状態: 現行アーキテクチャの記録
