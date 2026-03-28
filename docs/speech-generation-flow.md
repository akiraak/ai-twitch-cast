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
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│              TTS音声生成（Gemini 2.5 Flash TTS）          │
│  キャラの声（tts_voice）とスタイル（tts_style）で発声     │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│              再生パイプライン（SpeechPipeline）            │
│  C#アプリ送信 + 字幕 + リップシンク + 感情BlendShape      │
└─────────────────────────────────────────────────────────┘
```

## キャラクター設定

各キャラクターは以下の設定を持つ。すべてDBの`characters`テーブルに保存。

| 設定 | 用途 | 例（ちょビ） | 例（なるこ） |
|------|------|-------------|-------------|
| `system_prompt` | テキスト生成時の性格・話し方（日本語） | Twitch配信者、ツッコミ気質… | 元気な生徒、素直… |
| `system_prompt_en` | 英語版の性格・話し方 | Curious Twitch streamer… | Energetic student… |
| `system_prompt_bilingual` | バイリンガル版の性格・話し方 | 日英混在の性格設定 | 日英混在の性格設定 |
| `rules` | 応答ルール（日本語） | 1文40字以内、2文まで | 先生より短めに |
| `rules_en` | 英語版ルール | Max one ! per sentence | Keep it shorter than teacher |
| `rules_bilingual` | バイリンガル版ルール | 日英を自然に混ぜる | 日英を自然に混ぜる |
| `tts_voice` | TTS音声名 | Despina | Aoede |
| `tts_style` | TTS読み上げスタイル（日本語） | にこにこ柔らかトーン | テンション高めハキハキ |
| `tts_style_en` | 英語版TTSスタイル | Warm, cheerful tone | Energetic, upbeat tone |
| `tts_style_bilingual` | バイリンガル版TTSスタイル | 日英を自然に切り替えて | 日英を自然に切り替えて |
| `emotions` | 使用可能な感情一覧 | joy, excited, surprise… | joy, surprise, thinking… |
| `emotion_blendshapes` | 感情→表情マッピング | joy→happy:1.0 | joy→happy:1.0 |
| `self_note` | 今日の記憶メモ（自動更新） | 「今日はゲーム配信…」 | — |
| `persona` | 過去応答から抽出した性格特徴 | 「照れ屋でツッコミ好き」 | — |

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
  ├─ シングルキャラ: generate_ai_response()
  │    system_prompt = build_system_prompt(
  │      char.system_prompt,    ← キャラの性格
  │      char.rules,            ← 応答ルール
  │      char.emotions,         ← 感情選択肢
  │      char.self_note,        ← 今日の記憶
  │      char.persona,          ← 性格特徴
  │      会話履歴,               ← 直近2時間10件
  │      配信コンテキスト,        ← タイトル・TODO・授業情報
  │      ユーザーメモ             ← 視聴者ごとの記録
  │    )
  │    → Gemini LLM → {speech, emotion, translation}
  │
  └─ マルチキャラ: generate_multi_ai_response()
       system_prompt = build_multi_system_prompt(
         teacher_char,  ← 先生キャラの全設定
         student_char,  ← 生徒キャラの全設定
         応答分配ガイド   ← 先生単独60%, 両者25%, 生徒先15%…
       )
       → Gemini LLM → [{speaker, speech, emotion}, ...]
  │
  ▼
各発話ごとに:
  speech_pipeline.speak(
    text,
    voice  = char.tts_voice,    ← キャラ固有の声
    style  = char.tts_style,    ← キャラ固有のスタイル
    avatar_id = "teacher"/"student"
  )
```

**キャラ個性の反映度: ★★★★★**

- テキスト: キャラ自身のsystem_prompt + self_note + personaで生成
- 声: キャラ固有のvoice/style
- 表情: キャラのemotion_blendshapes

---

### 2. 授業モード

プラン設計 → セクション構造生成 → セリフ個別生成 の3段階で構成。
セリフは各キャラのペルソナ付きで個別にLLM生成する（v2方式）。

#### 全体フロー

```
教材テキスト + 画像
  │
  ▼
[Phase A: プラン生成]  ← キャラ設定は不使用（3人のエキスパートLLM）
  知識エキスパート → 教材分析・重要概念抽出
  エンタメエキスパート → 起承転結・物語構造設計
  監督 → 統合してセクション構成を決定
  → plan_sections: [{section_type, title, summary, emotion, wait_seconds, ...}]
  │
  ▼
[Phase B-1: セクション構造 + dialogue_plan 生成]  ← 1回のLLM呼び出し
  system_prompt = _build_structure_prompt()
  入力: プランテキスト + 教材テキスト + 画像
  出力: 各セクションの display_text / question / answer / dialogue_plan
  → [{section_type, display_text, dialogue_plan: [{speaker, direction}, ...], ...}]
  │
  ▼
[Phase B-2: セリフ個別生成]  ← dialogue_plan の各エントリごとにLLM呼び出し
  セクション間は最大3並列（ThreadPoolExecutor）
  セクション内は順次処理（会話履歴を蓄積するため）
  各セリフ: _generate_single_dialogue()
    system_prompt = キャラのペルソナ（system_prompt + emotions）
    user_prompt = セクション情報 + 演出指示 + ここまでの会話 + 教材テキスト
    → {content, tts_text, emotion, generation: {プロンプト全文, raw_output}}
  │
  ▼
[Phase C: TTS事前生成]  ← スクリプト生成直後に実行
  対話モード:
    各dialogue発話ごとに synthesize(
      tts_text,
      voice = speaker別のtts_voice,
      style = get_localized_field(config, "tts_style")  ← 言語モード対応
    )
    → section_{oi}_dlg_{di}.wav

  単話者モード（キャラ未設定時のフォールバック）:
    content/tts_textを文分割 → 各パートごとに synthesize()
    → section_{oi}_part_{pi}.wav
  │
  ▼
[Phase D: 授業再生]
  LessonRunner → 各セクション順次再生
  対話モード:
    事前生成済みwavをキャッシュから読み込み
    → speech_pipeline.speak(wav_path=cached, voice, style, avatar_id)
  単話者モード:
    事前生成済みwavをキャッシュから読み込み
    → speech_pipeline.speak(wav_path=cached, avatar_id="teacher")
```

**キャラ個性の反映度: ★★★★★**

- テキスト: 各セリフがキャラのペルソナ付きで個別生成 ✓
- 声: キャラ固有のvoice/style（言語モード対応） ✓
- 表情: キャラのemotion_blendshapes ✓
- self_note/persona も含む ✓
- 言語モードに応じてプロンプト全体が適切な言語で構築される ✓

#### Phase A: プラン生成の詳細（3人のエキスパート）

教材を3つの視点で分析し、最終プランを決定する。各エキスパートは独立したLLM呼び出し。

```
教材テキスト
  │
  ├─▶ 知識エキスパート（Knowledge Expert）
  │     「教えるべき要点」「推奨学習順序」「注意すべき誤解・難所」「推奨セクション構成」
  │
  ├─▶ エンタメエキスパート（Entertainment Expert）
  │     「起承転結の構成」「オチの設計」「演出ポイント（クイズ・例え話・感情の起伏）」
  │
  └─▶ 監督（Director）
        知識 + エンタメの提案を統合し、最終セクション構成を決定
        各セクションの section_type / title / summary / emotion / wait_seconds を出力
        ※ titleは10文字以内（日本語）/ 5語以内（英語）
        ※ wait_seconds: 説明1-2秒、重要ポイント3-4秒、問いかけ8-15秒
        → JSON配列: [{section_type, title, summary, emotion, has_question, wait_seconds}]
```

ファイル: `src/lesson_generator.py`

| エキスパート | 関数/行 | LLMモデル |
|-------------|---------|-----------|
| 知識 | 行315-359 | gemini-2.5-flash |
| エンタメ | 行381-467 | gemini-2.5-flash |
| 監督 | 行492-600 | gemini-2.5-flash |

#### Phase B-1: セクション構造 + dialogue_plan 生成の詳細

`_build_structure_prompt()` で構築されるシステムプロンプトの主要指示:

- **display_text**: 視聴者が配信画面で見る唯一の視覚情報。タイトルだけはNG、実際のコンテンツ（例文・比較表・クイズ選択肢等）を含める
- **dialogue_plan**: 各セクションの「誰が何を話すか」のフロー設計。1セクション2〜6ターン
  - introduction/summaryには生徒を必ず入れる
  - questionでは生徒が答える役
- **出力形式**: JSON配列。各エントリに `dialogue_plan: [{speaker, direction}]` を含む

プランがある場合、プランテキストがシステムプロンプトに埋め込まれる:
```
1. [introduction] 挨拶の常識？ — 英語の挨拶の奥深さを... (感情: excited, 間: 10秒) ※問いかけあり
2. [explanation] Mariaの困惑 — ... (感情: thinking, 間: 4秒)
...
```

ユーザープロンプト:
```
# 授業タイトル: {lesson_name}

# 教材テキスト:
{extracted_text}
```

ファイル: `src/lesson_generator.py` 行1196-1337（`_build_structure_prompt`）、行1562-1600（LLM呼び出し）

#### Phase B-2: セリフ個別生成の詳細

`_generate_single_dialogue()` で各セリフを生成。`build_lesson_dialogue_prompt()`（`src/prompt_builder.py`）でシステムプロンプトを構築し、言語モードに応じて全セクションが適切な言語で生成される。

```python
system_prompt = build_lesson_dialogue_prompt(
    char=character_config,
    role=role,
    self_note=character_config.get("self_note"),
    persona=character_config.get("persona"),
)
```

**システムプロンプトの構成**（言語モードにより日本語/英語で構築）:

1. **キャラ紹介** — "あなたは「{name}」です…" / "You are '{name}'…"
2. **キャラ system_prompt** — `get_localized_field(char, "system_prompt")` で言語版を選択
3. **ルール** — `get_localized_field(char, "rules")` で言語版を選択
4. **自分の記憶メモ** — self_note（授業でも使用）
5. **ペルソナ** — persona（授業でも使用）
6. **言語ルール** — 言語モード別の発話言語指示（英語のみ/バイリンガル混ぜ）
7. **感情ガイド** — emotion の使い分け
8. **出力形式** — JSON `{content, tts_text, emotion}` + tts_text の言語タグルール

**日本語モードの例**:
```
あなたは「ちょビ」です。Twitch教育配信のキャラクターとして自然に話してください。

{キャラのsystem_prompt全文}

ルール:
{キャラのrules}

使用可能な感情: {emotions一覧}

出力形式:
- content: 字幕テキスト（タグなし）
- tts_text: contentと同じだが、日本語以外に [lang:xx]...[/lang] タグを付ける
- emotion: 使用可能な感情から選ぶ
- JSONオブジェクトのみ出力: {"content": "...", "tts_text": "...", "emotion": "..."}
```

**英語モードの例**:
```
You are 'Chobi'. Speak naturally as a character in a Twitch educational stream.

{キャラのsystem_prompt_en全文}

Rules:
{キャラのrules_en}

Available emotions: {emotions一覧}

Output format:
- content: subtitle text (no tags)
- tts_text: same as content, but wrap non-English parts with [lang:xx]...[/lang]
- emotion: choose from available emotions
- Output ONLY a JSON object: {"content": "...", "tts_text": "...", "emotion": "..."}
```

**ユーザープロンプト**:
```
# 授業: {lesson_name}
# セクション: {section_type}
# 画面表示: {display_text（先頭200文字）}
# 問題: {question}（questionセクションのみ）
# 回答: {answer}（questionセクションのみ）

## このターンの演出指示
{dialogue_planのdirection}

## ここまでの会話（2ターン目以降）
teacher: {前のセリフ}
student: {前のセリフ}
...

## 教材テキスト（参考）
{extracted_text（先頭2000文字）}
```

**キャラメモリの取得**: `get_lesson_characters()`（`src/lesson_generator.py`）でキャラ設定に加え、`self_note` と `persona` もDBから取得し、プロンプトに含める。

**生成メタデータ**: 各セリフに `generation` フィールドが付与され、`system_prompt`・`user_prompt`・`raw_output`・`model`・`temperature` が記録される。管理画面で全文表示可能。

**会話履歴の蓄積**: セクション内で順次処理し、前のセリフが「ここまでの会話」に追加される。これにより自然な対話の流れが維持される。

ファイル: `src/prompt_builder.py`（`build_lesson_dialogue_prompt`）、`src/lesson_generator.py`（`_generate_single_dialogue`、`_generate_section_dialogues`、`get_lesson_characters`）

#### 生成フローの具体例（Lesson #20 日本語 introduction）

LLM呼び出し5回（構造1回 + セリフ4回）で1セクションが完成する。

```
Phase B-1: セクション構造生成（1回のLLM呼び出し）
  → display_text: "今日のテーマ: 英語の挨拶\n\n『How are you?』の本当の意味とは？..."
  → dialogue_plan:
      [0] teacher: "視聴者に挨拶し、テーマを紹介"
      [1] teacher: "視聴者へ問いかけ: How are you?と聞かれたら..."
      [2] student: "先生の問いかけに反応し、自分の経験を述べる"
      [3] teacher: "授業で秘密を紐解くことをプレビュー"

Phase B-2: セリフ個別生成（4回のLLM呼び出し、順次処理）
  │
  ├─ [0] ちょビ（teacher）ペルソナ + 演出指示 + 教材テキスト
  │   → content: "みんな、いらっしゃい！ちょビだよ〜。..."
  │   → tts_text: "...[lang:en]How are you?[/lang]って、本当はどんな意味..."
  │   → emotion: neutral
  │
  ├─ [1] ちょビ（teacher）ペルソナ + 演出指示 + 会話[0]
  │   → content: "みんなは『How are you?』って聞かれたら、いつもどう答えてる？..."
  │   → emotion: thinking
  │
  ├─ [2] なるこ（student）ペルソナ + 演出指示 + 会話[0,1]
  │   → content: "あー！ちょビ先生！私、やっちゃってたかも〜！..."
  │   → emotion: surprise
  │
  └─ [3] ちょビ（teacher）ペルソナ + 演出指示 + 会話[0,1,2]
      → content: "あ〜！やっぱやっちゃってたか〜！..."
      → emotion: surprise

Phase C: TTS事前生成（4回）
  [0] voice=Despina style=にこにこ柔らか → section_0_dlg_0.wav
  [1] voice=Despina style=にこにこ柔らか → section_0_dlg_1.wav
  [2] voice=Aoede  style=少年テンション高め → section_0_dlg_2.wav
  [3] voice=Despina style=にこにこ柔らか → section_0_dlg_3.wav
```

#### 生成方式の選択ロジック

`scripts/routes/teacher.py` 行521-563 でキャラ設定の有無により自動選択:

| 条件 | 方式 | 説明 |
|------|------|------|
| teacher + student キャラあり | `generate_lesson_script_v2()` | セリフ個別LLM生成（推奨） |
| プランあり、キャラなし | `generate_lesson_script_from_plan()` | プランベース一括生成 |
| どちらもなし | `generate_lesson_script()` | 教材テキストから直接一括生成 |

---

### 3. イベント応答

Gitコミット通知、作業開始・停止など。

```
イベント発生（コミット検出 / API呼出）
  │
  ▼
comment_reader.speak_event(event_type, detail)
  │
  ├─ シングル: generate_event_response()
  │    system_prompt にキャラの system_prompt + emotions を含む
  │    → {speech, emotion}
  │
  └─ マルチ: generate_multi_event_response()
       先生70%単独、30%両者
       → [{speaker, speech, emotion}, ...]
  │
  ▼
speech_pipeline.speak(text, voice, style, avatar_id)
```

**キャラ個性の反映度: ★★★★☆**

- テキスト: キャラのsystem_promptで生成 ✓
- 声: キャラ固有のvoice/style ✓
- ただしself_note/personaは不使用（イベントは短い一言なので十分）

---

### 4. 直接発話（API経由）

`POST /api/avatar/speak` で外部から直接テキストを指定。

```
APIリクエスト {text: "こんにちは", character: "teacher"}
  │
  ▼
speak_event() → speech_pipeline.speak()
```

**キャラ個性の反映度: ★★☆☆☆**

- テキスト: 外部指定（キャラ設定は不使用）
- 声: キャラ固有のvoice/style ✓

---

## 共通再生パイプライン

すべてのモードが最終的に通る経路。

```
speech_pipeline.speak(text, voice, style, avatar_id, wav_path, ...)
  │
  ├─ [SE再生] SEがあればTTS前に再生（0.3秒間隔）
  │
  ├─ [TTS生成] wav_pathがなければ動的生成
  │    synthesize(tts_text, output_path, voice=voice, style=style)
  │    → Gemini 2.5 Flash TTS API呼び出し
  │    → WAV 16-bit mono 24kHz
  │
  ├─ [リップシンク] WAVの振幅解析 → フレーム配列
  │
  ├─ [C#アプリ送信] send_tts_to_native_app()
  │    WAV → base64 → WebSocket "tts_audio"
  │    → C#: デコード → ローカル再生 + FFmpegパイプ
  │
  ├─ [字幕発火] WebSocket /ws/broadcast "comment"
  │
  ├─ [リップシンク発火] WebSocket /ws/broadcast "lipsync"
  │
  ├─ [感情BlendShape] emotion → emotion_blendshapes → アバター表情
  │
  └─ [待機] asyncio.sleep(音声長 + 0.1秒)
```

## キャラ個性の反映度まとめ

| モード | テキスト生成 | voice/style | emotion | self_note/persona | 言語対応 | 個性度 |
|--------|-------------|-------------|---------|-------------------|---------|--------|
| コメント応答 | キャラ自身のプロンプト | ✓ | ✓ | ✓ | ✓ | ★★★★★ |
| イベント応答 | キャラ自身のプロンプト | ✓ | ✓ | - | - | ★★★★☆ |
| 授業スクリプト | キャラ個別LLM生成（v2） | ✓ | ✓ | ✓ | ✓ | ★★★★★ |
| 直接発話 | 外部指定 | ✓ | - | - | - | ★★☆☆☆ |

## 授業モードの実装履歴

### v2（現行・推奨）: セリフ個別LLM生成

`generate_lesson_script_v2()` — Phase B-1で台本骨格（dialogue_plan）を一括生成し、Phase B-2で各セリフをキャラのペルソナ付きで個別にLLM生成する方式。

- セクション間は最大3並列（ThreadPoolExecutor）で高速化
- セクション内は会話履歴を蓄積するため順次処理
- 各セリフに `generation` メタデータ（プロンプト全文・raw_output）が付与され、管理画面で検証可能
- teacher/student キャラが両方DBに存在する場合に自動選択
- **言語モード対応**: `build_lesson_dialogue_prompt()` でプロンプト全体が言語モードに応じた言語で構築される（日本語/英語/バイリンガル）
- **self_note/persona対応**: `get_lesson_characters()` でキャラメモリを取得し、セリフ生成プロンプトに含める
- **TTSスタイル言語対応**: `get_localized_field()` で `tts_style_en` / `tts_style_bilingual` を自動選択

### 旧方式（フォールバック）

キャラ未設定時に使用される:

- `generate_lesson_script_from_plan()` — プランベースの一括生成
- `generate_lesson_script()` — 教材テキストからの直接一括生成

いずれも1回のLLM呼び出しで全セリフを生成するため、キャラの個性反映度は低い（★★★☆☆）。
