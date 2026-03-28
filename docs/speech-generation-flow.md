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
| `tts_voice` | TTS音声名 | Despina | Aoede |
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
感情適用: apply_emotion(emotion, avatar_id, character_config)  ← パイプライン外
  │
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

プラン設計 → セクション構造生成 → セリフ個別生成 → 監督レビュー → TTS事前生成 → 授業再生 の流れで構成。
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
  → director_sections: [{section_type, title, display_text, emotion, wait_seconds,
                         question, answer, dialogue_directions: [{speaker, direction, key_content}]}]
  │
  ▼
[Phase B-1: セクション構造 + dialogue_plan 生成]  ← director_sectionsがあればスキップ
  system_prompt = _build_structure_prompt()
  入力: プランテキスト + 教材テキスト + 画像 + main_content（content_type別ルール）
  出力: 各セクションの display_text / question / answer / dialogue_plan
  → [{section_type, display_text, dialogue_plan: [{speaker, direction}], ...}]
  │
  ▼
[Phase B-2: セリフ個別生成]  ← dialogue_plan/dialogue_directions の各エントリごとにLLM呼び出し
  セクション間は最大3並列（ThreadPoolExecutor、generate_lesson_script_v2内）
  セクション内は順次処理（会話履歴を蓄積するため）
  各セリフ: _generate_single_dialogue()
    system_prompt = build_lesson_dialogue_prompt(char, role, self_note, persona)
    user_prompt = セクション情報 + 演出指示 + key_content + ここまでの会話 + 教材テキスト
    → {content, tts_text, emotion, generation: {system_prompt, user_prompt, raw_output, model, temperature}}
  │
  ▼
[Phase B-3: 監督レビュー]  ← _director_review()
  5つのレビュー観点で品質検証:
    1. display_text読み上げ網羅性（例文・会話・キーフレーズが話されているか）
    2. キャラクター一貫性（先生/生徒が役割に合った発話か）
    3. セクション間の流れ（文脈連続性・情報フロー）
    4. 正確性・網羅性（教材の要点カバー・事実誤認なし）
    5. コンテンツ種別準拠（main_contentのcontent_typeに応じた読み方）
  → 各セクションに approved / feedback / revised_directions
  │
  ▼
[Phase B-4: 再生成]  ← レビュー不合格セクションのみ
  revised_directionsで再生成（1回限り、不合格セクションのみ）
  │
  ▼
[Phase C: TTS事前生成]  ← スクリプト生成直後に実行（scripts/routes/teacher.py内）
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
[Phase D: 授業再生]
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

- テキスト: 各セリフがキャラのペルソナ付きで個別生成 ✓
- 声: キャラ固有のvoice/style ✓
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
  │     ※出力: マークダウン見出し付きの構造化テキスト（JSONではない）
  │
  ├─▶ エンタメエキスパート（Entertainment Expert）
  │     「起承転結の構成」「オチの設計」「演出ポイント（クイズ・例え話・感情の起伏）」
  │     ※出力: マークダウン見出し付きの構造化テキスト（JSONではない）
  │
  └─▶ 監督（Director）
        知識 + エンタメの提案を統合し、最終セクション構成を決定
        各セクションの構造を出力
        → JSON配列: [{section_type, title, display_text, emotion, wait_seconds,
                       question, answer, dialogue_directions}]
```

ファイル: `src/lesson_generator.py`（`generate_lesson_plan`）

| エキスパート | モデル（環境変数） | 出力形式 |
|-------------|-------------------|---------|
| 知識 | `GEMINI_KNOWLEDGE_MODEL`（既定: gemini-3-flash-preview） | テキスト |
| エンタメ | `GEMINI_ENTERTAINMENT_MODEL`（既定: gemini-3-flash-preview） | テキスト |
| 監督 | `GEMINI_DIRECTOR_MODEL`（既定: gemini-3.1-pro-preview） | JSON |

**監督の出力スキーマ**:

```json
{
  "section_type": "introduction|explanation|example|question|summary",
  "title": "10文字以内（日本語）/ 5語以内（英語）",
  "display_text": "視聴者が配信画面で見る実際の内容",
  "emotion": "joy|excited|surprise|thinking|sad|embarrassed|neutral",
  "wait_seconds": 2,
  "question": "",
  "answer": "",
  "dialogue_directions": [
    {
      "speaker": "teacher|student",
      "direction": "2-3文の具体的な演出指示",
      "key_content": "必ず言及すべき教材の具体的内容"
    }
  ]
}
```

**wait_secondsのガイドライン**:
- 自然な会話: 1-2秒
- 重要ポイント: 3-4秒
- 驚きの事実・ツイスト: 4-5秒
- 問いかけ: 8-15秒
- まとめ・オチ: 2-3秒

**戻り値**: `generate_lesson_plan()` は `plan_sections`（レガシー互換）と `director_sections`（v3形式、dialogue_directions含む）の両方を返す。

#### Phase B-1: セクション構造 + dialogue_plan 生成の詳細

`_build_structure_prompt()` で構築されるシステムプロンプトの主要指示:

- **display_text**: 視聴者が配信画面で見る唯一の視覚情報。タイトルだけはNG、実際のコンテンツ（例文・比較表・クイズ選択肢等）を含める
- **dialogue_plan**: 各セクションの「誰が何を話すか」のフロー設計。1セクション2〜6ターン
  - introduction/summaryには生徒を必ず入れる
  - questionでは生徒が答える役
- **出力形式**: JSON配列。各エントリに `dialogue_plan: [{speaker, direction}]` を含む

**コンテンツ種別ルール**: `main_content` が提供された場合、content_type別の読み上げルールがプロンプトに追加される:
- `conversation`: 先生/生徒で役割分担して会話文を読む
- `passage`: 先生が読み+解説、生徒がリアクション
- `word_list`: 先生が読み+解説、生徒が繰り返し/質問
- `table`: 先生が行/列を説明、生徒がコメント

**director_sectionsがある場合**: Phase B-1はスキップされ、監督の出力（`dialogue_directions`含む）がそのまま使われる（v3パス）。

ユーザープロンプト:
```
# 授業タイトル: {lesson_name}

# 教材テキスト:
{extracted_text}
```

ファイル: `src/lesson_generator.py`（`_build_structure_prompt`）

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

**ユーザープロンプト**:
```
# 授業: {lesson_name}
# セクション: {section_type}
# 画面表示: {display_text（先頭200文字）}
# 問題: {question}（questionセクションのみ）
# 回答: {answer}（questionセクションのみ）

## このターンの演出指示
{dialogue_plan/dialogue_directionsのdirection}

## 重要コンテンツ（key_content、v3のみ）
{dialogue_directionsのkey_content}

## ここまでの会話（2ターン目以降）
teacher: {前のセリフ}
student: {前のセリフ}
...

## 教材テキスト（参考）
{extracted_text（先頭2000文字）}
```

**dialogue_plan vs dialogue_directions**: 2つの形式が並存する。
- v2（レガシー）: `dialogue_plan: [{speaker, direction}]` — key_contentなし
- v3（現行）: `dialogue_directions: [{speaker, direction, key_content}]` — key_content付き

**キャラメモリの取得**: `get_lesson_characters()`（`src/lesson_generator.py`）でキャラ設定に加え、`self_note` と `persona` もDBから取得し、プロンプトに含める。

**生成メタデータ**: 各セリフに `generation` フィールドが付与され、`system_prompt`・`user_prompt`・`raw_output`・`model`・`temperature` が記録される。管理画面で全文表示可能。

**会話履歴の蓄積**: セクション内で順次処理し、前のセリフが「ここまでの会話」に追加される。これにより自然な対話の流れが維持される。

ファイル: `src/prompt_builder.py`（`build_lesson_dialogue_prompt`）、`src/lesson_generator.py`（`_generate_single_dialogue`、`_generate_section_dialogues`、`get_lesson_characters`）

#### Phase B-3: 監督レビューの詳細

`_director_review()` で生成されたセリフの品質を検証する。

**レビュー観点**:
1. **display_text読み上げ網羅性（最重要）**: 画面に表示されている例文・会話・キーフレーズが実際にセリフ内で話されているか
2. **キャラクター一貫性**: 先生/生徒がそれぞれの役割に合った発話をしているか
3. **セクション間の流れ**: 文脈の連続性、自然な情報フロー
4. **正確性・網羅性**: 教材の要点がカバーされているか、事実誤認がないか
5. **コンテンツ種別準拠**（main_contentがある場合）: content_typeに応じた読み方になっているか

**出力**: 各セクションに `approved`（合格/不合格）、`feedback`（具体的な指摘）、`revised_directions`（不合格時の修正指示）を付与。

**モデル**: 監督と同じ `GEMINI_DIRECTOR_MODEL`（gemini-3.1-pro-preview）を使用。

ファイル: `src/lesson_generator.py`（`_director_review`）

#### Phase B-4: 再生成

レビューで不合格となったセクションのみ、`revised_directions` を使って再生成する。

- 不合格セクションの `dialogue_directions` を `revised_directions` で差し替え
- `_generate_section_dialogues()` を再度呼び出し（ThreadPoolExecutor(max_workers=3)で並列）
- **1回限り**: カスケードする再生成は行わない

ファイル: `src/lesson_generator.py`（`generate_lesson_script_v2` 内）

#### Phase C: TTS事前生成の詳細

スクリプト生成完了直後に `scripts/routes/teacher.py` 内で実行される。

**対話モード**:
- 各dialogue発話ごとに `synthesize(tts_text, cached_path, voice=voice, style=style)`
- ファイル名: `section_{order_index:02d}_dlg_{dlg_index:02d}.wav`
- voice/styleは各speakerのキャラ設定から直接取得（`cfg.get("tts_voice")`）

**単話者モード**:
- content/tts_textを文分割 → 各パートごとに synthesize()
- ファイル名: `section_{order_index:02d}_part_{part_index:02d}.wav`

**キャッシュディレクトリ**: `resources/audio/lessons/{lesson_id}/{lang}/`（言語別キャッシュ）

ファイル: `scripts/routes/teacher.py`（スクリプト生成エンドポイント内）、`src/lesson_runner.py`（`_cache_path`、`_dlg_cache_path`）

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

Phase B-3: 監督レビュー
  → display_textの内容が各セリフで触れられているか確認
  → 全セクション approved → Phase B-4はスキップ

Phase C: TTS事前生成（4回）
  [0] voice=Despina style=にこにこ柔らか → section_00_dlg_00.wav
  [1] voice=Despina style=にこにこ柔らか → section_00_dlg_01.wav
  [2] voice=Aoede  style=少年テンション高め → section_00_dlg_02.wav
  [3] voice=Despina style=にこにこ柔らか → section_00_dlg_03.wav
```

#### 生成方式の選択ロジック

`scripts/routes/teacher.py` のスクリプト生成エンドポイントで、キャラ設定の有無により自動選択:

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
comment_reader.speak_event(event_type, detail, voice=None, style=None, avatar_id="teacher")
  │
  ├─ シングル: generate_event_response(event_type, detail, last_event_responses)
  │    system_prompt にキャラの system_prompt + emotions を含む
  │    直前3件のイベント応答を含めて繰り返し防止
  │    → {speech, tts_text, emotion, translation}
  │
  └─ マルチ: generate_multi_event_response(event_type, detail, characters, last_event_responses)
       先生約70%単独、約30%両者
       → [{speaker, speech, tts_text, emotion, translation, se}, ...]
  │
  ▼
感情適用: apply_emotion(emotion, avatar_id, character_config)  ← パイプライン外
  │
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
APIリクエスト {event_type: "手動", detail: "配信の調子を報告して", voice: "Despina"（任意）}
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

**speaking_endイベント**: `notify_overlay_end()` で `"speaking_end"` イベントが送信される。これも呼び出し元がspeak後に呼び出す。

ファイル: `src/speech_pipeline.py`（`speak`、`_speak_impl`、`apply_emotion`、`send_tts_to_native_app`、`send_se_to_native_app`）

## キャラ個性の反映度まとめ

| モード | テキスト生成 | voice/style | emotion | self_note/persona | 言語対応 | 個性度 |
|--------|-------------|-------------|---------|-------------------|---------|--------|
| コメント応答 | キャラ自身のプロンプト | ✓ | ✓ | ✓ | ✓ | ★★★★★ |
| イベント応答 | キャラ自身のプロンプト | ✓ | ✓ | - | - | ★★★★☆ |
| 授業スクリプト | キャラ個別LLM生成（v2） | ✓ | ✓ | ✓ | ✓ | ★★★★★ |
| 直接発話 | キャラプロンプトでAI生成 | ✓ | ✓ | - | - | ★★★★☆ |

## 授業モードの実装履歴

### v3/v4（現行・推奨）: 監督主導 + セリフ個別LLM生成 + 監督レビュー

`generate_lesson_script_v2()` — Phase Aで監督が `director_sections`（`dialogue_directions` + `key_content` 含む）を出力し、Phase B-2で各セリフをキャラのペルソナ付きで個別にLLM生成、Phase B-3で監督がレビュー・Phase B-4で不合格セクションを再生成する方式。

- セクション間は最大3並列（ThreadPoolExecutor）で高速化
- セクション内は会話履歴を蓄積するため順次処理
- 各セリフに `generation` メタデータ（プロンプト全文・raw_output）が付与され、管理画面で検証可能
- teacher/student キャラが両方DBに存在する場合に自動選択
- **言語モード対応**: `build_lesson_dialogue_prompt()` でプロンプト全体が言語モードに応じた言語で構築される（日本語/英語/バイリンガル）
- **self_note/persona対応**: `get_lesson_characters()` でキャラメモリを取得し、セリフ生成プロンプトに含める
- **コンテンツ種別対応**: `extract_main_content()` でcontent_typeを識別し、構造生成・レビューに反映
- **監督レビュー**: display_text網羅性・キャラ一貫性・content_type準拠を検証し、不合格セクションを再生成
- **v4データ形式**: dialogues + review メタデータを含む `{dialogues: [...], review: {...}}` 形式

### 旧方式（フォールバック）

キャラ未設定時に使用される:

- `generate_lesson_script_from_plan()` — プランベースの一括生成
- `generate_lesson_script()` — 教材テキストからの直接一括生成

いずれも1回のLLM呼び出しで全セリフを生成するため、キャラの個性反映度は低い（★★★☆☆）。
