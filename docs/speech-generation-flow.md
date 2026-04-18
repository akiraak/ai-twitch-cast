# キャラクター発話生成フロー

キャラクターが発話するすべてのモードにおけるテキスト生成 → TTS音声生成 → 再生の流れを定義する。

## 授業の構造

授業（lesson）は複数の **セクション（section）** で構成される。
各セクションには **display_text**（配信画面に表示する教材テキスト）と、複数の **dialogues**（先生と生徒の対話）が含まれる。

```
授業（lesson）
├── セクション 1: introduction
│   ├── display_text: 画面に表示する教材テキスト
│   └── dialogues（対話）:
│       ├── [0] teacher: 「みんな、いらっしゃい！今日のテーマは英語の挨拶だよ！」
│       ├── [1] teacher: 「How are you?って聞かれたら、いつもどう答えてる？」
│       ├── [2] student: 「私、正直に答えちゃってました！」
│       └── [3] teacher: 「実はそれ、文化の違いなんだよね」
├── セクション 2: explanation
│   ├── display_text: 画面に表示する教材テキスト
│   └── dialogues（対話）:
│       ├── [0] teacher: 「Mariaさんの体験を紹介するね」
│       └── [1] teacher: 「正直に答えたら変な目で見られちゃったんだって」
├── セクション 3: explanation
│   ├── display_text: 画面に表示する教材テキスト
│   └── dialogues（対話）: ...
└── セクション 4: summary
    ├── display_text: 画面に表示する教材テキスト
    └── dialogues（対話）: ...
```

- **display_text** は視聴者が配信画面で見る唯一の視覚情報（例文・比較表・クイズ選択肢など）
- **dialogues** の各エントリは `{speaker, content, tts_text, emotion}` を持つ
- セクションの `section_type` は introduction / explanation / example / question / summary のいずれか

## 全体像

```
┌─────────────────────────────────────────────────────────┐
│                    入力ソース                             │
│  Twitchチャット ┃ 授業教材 ┃ Gitコミット ┃ API直接呼出    │
└───────┬─────────┴────┬─────┴─────┬──────┴──────┬────────┘
        ▼              ▼           ▼              ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ コメント応答  │ │ 授業モード│ │イベント応答│ │ 直接発話  │
│（雑談）      │ │          │ │          │ │          │
└──────┬───────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
       ▼              ▼           ▼              ▼
┌─────────────────────────────────────────────────────────┐
│              テキスト生成（Gemini LLM）                    │
│  キャラのペルソナ（system_prompt）でテキストを生成         │
│  ※モデルは環境変数で切替可能                              │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│              TTS音声生成（Gemini TTS）                     │
│  キャラの声（tts_voice）とスタイル（tts_style）で発声     │
│  ※モデル: GEMINI_TTS_MODEL 環境変数（既定: gemini-2.5-flash-preview-tts）
│  ※出力: WAV 16-bit mono 24kHz                            │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│              再生パイプライン（SpeechPipeline）            │
│  C#アプリ送信 + 字幕 + リップシンク                       │
│  ※感情BlendShapeは呼び出し元で制御（パイプライン外）      │
└─────────────────────────────────────────────────────────┘
```

## キャラクター設定

各キャラクターは以下の設定を持つ。設定はDBの`characters`テーブルの`config` JSONカラムに保存。
`self_note`と`persona`は別テーブル（`character_memory`）で管理される。

| 設定 | 用途 | 例（ちょビ） | 例（なるこ） |
|------|------|-------------|-------------|
| `system_prompt` | テキスト生成時の性格・話し方（日本語） | Twitch配信者、ツッコミ気質… | 元気な生徒、素直… |
| `system_prompt_en` | 英語版の性格・話し方 | Curious Twitch streamer… | Energetic student… |
| `system_prompt_bilingual` | バイリンガル版の性格・話し方 | 日英混在の性格設定 | 日英混在の性格設定 |
| `rules` | 応答ルール（日本語） | 1文40字以内、2文まで | 先生より短めに |
| `rules_en` | 英語版ルール | Max one ! per sentence | Keep it shorter than teacher |
| `rules_bilingual` | バイリンガル版ルール | 日英を自然に混ぜる | 日英を自然に混ぜる |
| `tts_voice` | TTS音声名 | Leda | Aoede |
| `tts_style` | TTS読み上げスタイル（日本語） | にこにこ柔らかトーン | テンション高めハキハキ |
| `tts_style_en` | 英語版TTSスタイル | Warm, cheerful tone | Energetic, upbeat tone |
| `tts_style_bilingual` | バイリンガル版TTSスタイル | 日英を自然に切り替えて | 日英を自然に切り替えて |
| `emotions` | 使用可能な感情一覧 | joy, excited, surprise… | joy, surprise, thinking… |
| `emotion_blendshapes` | 感情→表情マッピング | joy→happy:1.0 | joy→happy:1.0 |
| `self_note` | 今日の記憶メモ（自動更新）※character_memory | 「今日はゲーム配信…」 | — |
| `persona` | 過去応答から抽出した性格特徴 ※character_memory | 「照れ屋でツッコミ好き」 | — |

### 言語モード別フィールド選択

`get_localized_field(config, field)` （`src/prompt_builder.py`）が言語モードに応じて適切なフィールドを選択する:

| 言語モード | 選択されるフィールド | フォールバック |
|-----------|---------------------|--------------|
| 日本語（primary=ja, sub=none） | `field`（例: `system_prompt`） | — |
| 英語（primary=en, sub=none） | `field_en`（例: `system_prompt_en`） | `field` |
| バイリンガル（sub!=none） | `field_bilingual`（例: `system_prompt_bilingual`） | `field` |

未設定の言語版は日本語版にフォールバックするため、既存キャラは即座に壊れない。

## モード別フロー

---

### 1. コメント応答（雑談モード）

最もキャラの個性が反映されるモード。

```
Twitchチャット受信
  │
  ▼
comment_reader._respond()
  │
  ├─ シングルキャラ: generate_response()
  │    system_prompt = build_system_prompt(
  │      char,              ← キャラ設定dict全体
  │      stream_context,    ← タイトル・TODO・授業情報
  │      self_note,         ← 今日の記憶
  │      persona,           ← 性格特徴
  │    )
  │    ※会話履歴（直近2時間10件）とユーザーメモは
  │      generate_response()内で別途マルチターンに組み込み
  │    → Gemini LLM → {speech, tts_text, emotion, translation, se}
  │
  └─ マルチキャラ: generate_multi_response()
       system_prompt = build_multi_system_prompt(
         teacher_char,           ← 先生キャラの全設定
         student_char,           ← 生徒キャラの全設定
         stream_context,         ← 配信情報
         self_note, persona,     ← 先生のメモ・ペルソナ
         student_self_note,      ← 生徒のメモ
         student_persona,        ← 生徒のペルソナ
       )
       → Gemini LLM → [{speaker, speech, tts_text, emotion, translation, se}, ...]
  │
  ▼
感情適用: apply_emotion(emotion, gesture=None, avatar_id, character_config)  ← パイプライン外
  │       gestureが未指定の場合、EMOTION_GESTURESから自動マッピング
  ▼
各発話ごとに:
  speech_pipeline.speak(
    text,
    voice    = char.tts_voice,
    style    = char.tts_style,
    subtitle = {author, trigger_text, result},
    chat_result, post_to_chat,    ← チャット投稿用
    tts_text = 言語タグ付きテキスト,
    se       = SE情報dict,
    avatar_id = "teacher"/"student",
  )
  │
  ▼
感情リセット: apply_emotion("neutral", avatar_id, character_config)
```

**キャラ個性の反映度: ★★★★★**

- テキスト: キャラ自身のsystem_prompt + self_note + personaで生成
- 声: キャラ固有のvoice/style
- 表情: キャラのemotion_blendshapes

ファイル: `src/comment_reader.py`（`_respond`）、`src/ai_responder.py`（`generate_response`、`generate_multi_response`）、`src/prompt_builder.py`（`build_system_prompt`、`build_multi_system_prompt`）

---

### 2. 授業モード

Claude Codeで手動生成 → JSONインポート → TTS事前生成 → 授業再生 の流れで構成。

#### 全体フロー

```
教材画像 / URL
  │
  ▼
[テキスト抽出]（管理画面 Step 1）
  画像 → extract_text_from_image()（Gemini Vision）
  URL  → extract_text_from_url()（aiohttp + BeautifulSoup）
  → extracted_text（DB保存）
  │
  ▼
[スクリプト生成]（Claude Code手動）
  prompts/lesson_generate.md に従い、Claude Codeで授業スクリプトを生成
  キャラクター設定・教材テキストを参照し、対話形式のJSONを作成
  管理画面の「生成プロンプト」セクションでプロンプト閲覧・AI編集も可能
  │
  ▼
[JSONインポート]（管理画面 Step 2）
  管理画面「JSONインポート」ボタン or POST /api/lessons/{id}/import-sections
  → sections（DB保存、generator=claude）
  │
  ▼
[TTS事前生成]（管理画面 Step 3）
  対話モード:
    各dialogue発話ごとに synthesize(
      tts_text,
      voice = speaker別のtts_voice,
      style = speaker別のtts_style,
    )
    → section_{oi}_dlg_{di}.wav

  単話者モード（生徒キャラ未設定時のフォールバック）:
    content/tts_textを文分割 → 各パートごとに synthesize()
    → section_{oi}_part_{pi}.wav

  キャッシュ: resources/audio/lessons/{lesson_id}/{lang}/ に保存
  │
  ▼
[授業再生]（管理画面 Step 4）
  LessonRunner → 各セクション順次再生
  対話モード:
    事前生成済みwavをキャッシュから読み込み（キャッシュミス時は動的生成）
    パイプライン先読み: 現在の発話再生中に次の発話のTTSを並行生成
    → speech_pipeline.speak(wav_path=cached, voice, style, avatar_id)
  単話者モード:
    事前生成済みwavをキャッシュから読み込み
    → speech_pipeline.speak(wav_path=cached, avatar_id="teacher")
  ペース制御: lesson.pace_scale（DB設定、デフォルト1.0）でセクション間の間隔を調整
```

**キャラ個性の反映度: ★★★★★**

- テキスト: Claude Codeがキャラ設定を参照して生成 ✓
- 声: キャラ固有のvoice/style ✓
- 表情: キャラのemotion_blendshapes ✓

#### TTS事前生成の詳細

管理画面 Step 3 または TTS生成ボタンで実行される。

**対話モード**:
- 各dialogue発話ごとに `synthesize(tts_text, cached_path, voice=voice, style=style)`
- ファイル名: `section_{order_index:02d}_dlg_{dlg_index:02d}.wav`
- voice/styleは各speakerのキャラ設定から直接取得（`cfg.get("tts_voice")`）

**単話者モード**:
- content/tts_textを文分割 → 各パートごとに synthesize()
- ファイル名: `section_{order_index:02d}_part_{part_index:02d}.wav`

**キャッシュディレクトリ**: `resources/audio/lessons/{lesson_id}/{lang}/`（言語別キャッシュ）

ファイル: `scripts/routes/teacher.py`、`src/lesson_runner.py`（`_cache_path`、`_dlg_cache_path`）

---

### 3. イベント応答

Gitコミット通知、作業開始・停止など。

```
イベント発生（コミット検出 / API呼出）
  │
  ▼
comment_reader.speak_event(event_type, detail, voice=None, style=None, avatar_id="teacher", multi=True)
  │
  ├─ シングル (multi=False もしくは生徒キャラなし):
  │    generate_event_response(event_type, detail, last_event_responses)
  │    system_prompt にキャラの system_prompt + emotions を含む
  │    直前3件のイベント応答を含めて繰り返し防止
  │    → {speech, tts_text, emotion, translation}
  │
  └─ マルチ (multi=True かつ生徒キャラあり):
       generate_multi_event_response(event_type, detail, characters, last_event_responses)
       先生と生徒の2〜3往復（配列は2〜4エントリ）
       → [{speaker, speech, tts_text, emotion, translation}, ...]
  │
  ▼
感情適用: apply_emotion(emotion, gesture=None, avatar_id, character_config)  ← パイプライン外
  │       gestureが未指定の場合、EMOTION_GESTURESから自動マッピング
  ▼
speech_pipeline.speak(text, voice, style, avatar_id, subtitle, chat_result, tts_text, post_to_chat)
  │
  ▼
感情リセット: apply_emotion("neutral", avatar_id, character_config)
```

**キャラ個性の反映度: ★★★★☆**

- テキスト: キャラのsystem_promptで生成 ✓
- 声: キャラ固有のvoice/style ✓
- ただしself_note/personaは不使用（イベントは短い一言なので十分）

ファイル: `src/comment_reader.py`（`speak_event`）、`src/ai_responder.py`（`generate_event_response`、`generate_multi_event_response`）

---

### 4. 直接発話（API経由）

`POST /api/avatar/speak` で外部から直接テキストを指定。内部的にはイベント応答と同じフローでAIテキスト生成も行われる。

```
APIリクエスト {event_type: "手動", detail: "配信の調子を報告して", voice: "Leda"（任意）}
  │
  ▼
state.reader.speak_event(event_type, detail, voice=voice)
  │  ※speak_event()はAIでテキスト生成する（キャラのsystem_prompt使用）
  │  ※detailは「何を話すか」の指示であり、そのまま読み上げるわけではない
  ▼
（以降はイベント応答と同じフロー）
```

**キャラ個性の反映度: ★★★★☆**

- テキスト: キャラのsystem_promptでAI生成 ✓（外部テキストは指示として使われる）
- 声: キャラ固有のvoice/style ✓（voiceパラメータで上書き可能）

ファイル: `scripts/routes/avatar.py`（`avatar_speak`）

---

## 共通再生パイプライン

すべてのモードが最終的に通る経路。**感情BlendShapeは呼び出し元で制御され、パイプライン内には含まれない。**

```
speech_pipeline.speak(text, voice, style, subtitle, chat_result, tts_text,
                      post_to_chat, se, wav_path, avatar_id)
  │
  ├─ [SE再生] SEがあればC#アプリに送信し、SE長 + 0.3秒待機
  │    音量: min(1.0, se² × master²) × track_volume
  │
  ├─ [TTS生成] wav_pathがなければ動的生成
  │    synthesize(tts_text or text, output_path, voice=voice, style=style)
  │    → Gemini TTS API呼び出し
  │    → WAV 16-bit mono 24kHz
  │
  ├─ [素材準備] リップシンク振幅解析 + 音声長取得（並行）
  │
  ├─ [C#アプリ送信] send_tts_to_native_app()
  │    WAV → base64 → WebSocket "tts_audio"
  │    音量: min(1.0, tts² × master²)
  │    → C#: デコード → ローカル再生 + FFmpegパイプ
  │
  ├─ [字幕発火] WebSocket /ws/broadcast "comment"
  │
  ├─ [リップシンク発火] WebSocket /ws/broadcast "lipsync" (autostart: true)
  │
  ├─ [チャット投稿] 音声再生開始2秒後に遅延投稿（asyncio.create_task）
  │
  ├─ [待機] asyncio.sleep(音声長 + 0.1秒)
  │
  ├─ [リップシンク停止] WebSocket "lipsync_stop"
  │
  └─ [クリーンアップ] テンプファイル削除（キャッシュ済みWAVは保持）
```

**感情BlendShapeの適用**: `apply_emotion()` は `speak()` の呼び出し元（comment_reader / lesson_runner）が `speak()` の前後で個別に呼び出す。speak前に感情適用 → speak → speak後にneutralリセット、のパターン。

**複数エントリ掛け合いの並列TTS事前生成**: マルチキャラの掛け合い（2〜4エントリ）・Claude Code実況会話では、全エントリのTTSを `generate_tts()` + `asyncio.create_task` で並列起動し、先頭から順に `await` → `speak(wav_path=事前生成WAV)` で再生する。`speak(wav_path=...)` 指定時はTTS生成をスキップして再生のみ行うため、エントリ間の「間」は `asyncio.sleep(0.3)` の固定値に詰まる。

```
LLM生成 → TTS生成1・2・3を並列起動 → [1をawait→再生] → [2をawait→再生] → [3をawait→再生]
                                        ^^^^^^^^^^^^^^^ 先頭が再生中に後続は生成済み
```

従来は各エントリごとに直列でTTS生成→再生していたため、3エントリで 1〜4.5秒の余計な待ちが発生していた。並列化後は 0.6秒（0.3秒×2）固定。

- 呼び出し箇所: `comment_reader.speak_event()` / `respond_webui()` / `_respond()`
- `_respond()` の2エントリ目以降は `_segment_queue` に `tts_task` として格納され、`_speak_segment()` が `await tts_task` してから再生する
- コメント割り込み時は `_segment_queue.clear()` 前に未完了タスクを `cancel()` する（リーク防止）
- `generate_tts()` は失敗時 `None` を返し、`speak(wav_path=None)` は通常の生成パスにフォールバックする

**Claude Code実況のチェーン再生（バッチ送信）**: `claude_watcher._play_conversation()` は上記の並列事前生成をさらに進め、**全エントリのWAVをC#アプリへ一括送信してC#側キューで順次再生する** 構成を採る。`_wait_tts_complete` のポーリング余剰（中央値2.4秒）・エントリ間 pause（0.3秒）・送信レイテンシ（0.23秒）がすべて消え、視聴者体感の無音が0秒に近づく。

```
[Python]
  全エントリの TTS 並列生成 → SpeechPipeline.speak_batch(entries)
  speak_batch 内:
    各エントリの WAV を base64 化（並列）
    capture_client.send_tts_batch(items)  ← 一括送信
    各エントリについて:
      await get_tts_entry_event(id).wait()  ← C# から Push 受信
      apply_emotion / notify_overlay / lipsync 発火
    await batch_complete_event.wait()

[C#]
  tts_audio_batch 受信 → _ttsLocalQueue に全件 enqueue
  配信中: 全 PCM を _ffmpeg.WriteTtsData（ミキサーが自動チェーン再生）
  ローカル: DequeueAndPlayNextLocal() で1件ずつ再生
    → Push「tts_entry_started {id}」 → waveOut.Play()
    → PlaybackStopped（自然終了）→ 次エントリを Dequeue → 繰り返し
  キュー空で Push「tts_batch_complete」
```

- 呼び出し箇所: `claude_watcher._play_conversation()` のみ（他モードは上記の直列パスを維持）
- 割り込み時: `comment_reader.queue_size > 0` を監視タスクが検知 → `capture_client.cancel_tts_batch()` で C# キューをクリア、進行中の WaveOut を Stop。C# は `tts_batch_complete (cancelled=true)` を Push して `speak_batch` を抜けさせる
- ローカル再生とFFmpegミキサーのタイムラインは僅かにズレる可能性があるが、視聴体感に影響しない範囲。字幕・口パクはローカル再生基準（＝WebView2内 broadcast.html と同じ時間軸）で発火する
- `PlayTtsLocally` は「新しい PlayTtsLocally 呼び出しで上書きされていない（`_ttsWaveOut == waveOut`）」を自然終了判定に使い、Stop 由来では次エントリへ進まない

**ジェスチャー連動**: `apply_emotion()` は `gesture` パラメータを受け取る（省略可）。未指定の場合、`EMOTION_GESTURES` マッピングから感情に対応するジェスチャーが自動選択される:

| emotion | gesture |
|---------|---------|
| joy | nod |
| surprise | surprise |
| thinking | head_tilt |
| excited | happy_bounce |
| sad | sad_droop |
| grateful | bow |

ジェスチャーが決定された場合、BlendShapeイベントに `gesture` フィールドが追加されて broadcast.html に送信される。

**speaking_endイベント**: `notify_overlay_end()` で `"speaking_end"` イベントが送信される。これも呼び出し元がspeak後に呼び出す。

ファイル: `src/speech_pipeline.py`（`speak`、`_speak_impl`、`apply_emotion`、`send_tts_to_native_app`、`send_se_to_native_app`）

## キャラ個性の反映度まとめ

| モード | テキスト生成 | voice/style | emotion | self_note/persona | 言語対応 | 個性度 |
|--------|-------------|-------------|---------|-------------------|---------|--------|
| コメント応答 | キャラ自身のプロンプト | ✓ | ✓ | ✓ | ✓ | ★★★★★ |
| イベント応答 | キャラ自身のプロンプト | ✓ | ✓ | - | - | ★★★★☆ |
| 授業スクリプト | キャラ個別LLM生成（v2） | ✓ | ✓ | ✓ | ✓ | ★★★★★ |
| 直接発話 | キャラプロンプトでAI生成 | ✓ | ✓ | - | - | ★★★★☆ |

## 環境変数一覧（モデル選択）

各LLM呼び出しで使用するモデルは環境変数で切替可能。すべて多段フォールバックチェーンを持つ。

| 環境変数 | 用途 | フォールバックチェーン | 使用箇所 |
|---------|------|----------------------|---------|
| `GEMINI_CHAT_MODEL` | チャット・イベント応答・ユーザーメモ生成・プロンプトAI編集 | → `gemini-3-flash-preview` | `ai_responder.py`（全生成関数）、`avatar.py`（デモ会話）、`prompts.py`（AI編集） |
| `GEMINI_TTS_MODEL` | TTS音声合成 | → `gemini-2.5-flash-preview-tts` | `tts.py`（`generate_audio`） |
