# キャラクター発話生成フロー

キャラクターが発話するすべてのモードにおけるテキスト生成 → TTS音声生成 → 再生の流れを定義する。

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
| `system_prompt` | テキスト生成時の性格・話し方 | Twitch配信者、ツッコミ気質… | 元気な生徒、素直… |
| `rules` | 応答ルール（文字数制限等） | 1文40字以内、2文まで | 先生より短めに |
| `tts_voice` | TTS音声名 | Despina | Aoede |
| `tts_style` | TTS読み上げスタイル | にこにこ柔らかトーン | テンション高めハキハキ |
| `emotions` | 使用可能な感情一覧 | joy, excited, surprise… | joy, surprise, thinking… |
| `emotion_blendshapes` | 感情→表情マッピング | joy→happy:1.0 | joy→happy:1.0 |
| `self_note` | 今日の記憶メモ（自動更新） | 「今日はゲーム配信…」 | — |
| `persona` | 過去応答から抽出した性格特徴 | 「照れ屋でツッコミ好き」 | — |

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

構成設計と個別セリフ生成が分離されている。

```
教材テキスト + 画像
  │
  ▼
[Phase A: プラン生成]  ← キャラ設定は不使用
  知識エキスパート → 教材分析・重要概念抽出
  エンタメエキスパート → 起承転結・物語構造設計
  監督 → 統合してセクション構成を決定
  → plan_sections: [{section_type, title, summary, emotion, ...}]
  │
  ▼
[Phase B: スクリプト生成]  ← キャラ設定は「参考情報」として添付
  1回のLLM呼び出しで全セクション・全キャラのセリフを一括生成
  system_prompt に以下を含む:
    - 授業スクリプト生成ルール
    - キャラの system_prompt（参考として）
    - キャラの emotions（選択肢として）
    ※ rules, self_note, persona は含まれない
  → sections: [{content, tts_text, display_text, dialogues, ...}]
  │
  ▼
[Phase C: TTS事前生成]  ← スクリプト生成直後に実行
  対話モード:
    各dialogue発話ごとに synthesize(
      tts_text,
      voice = speaker別のtts_voice,
      style = speaker別のtts_style
    )
    → section_{oi}_dlg_{di}.wav

  単話者モード:
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

**キャラ個性の反映度: ★★★☆☆**

- テキスト: スクリプト生成AIが「キャラならこう言うだろう」と推測して書く
- 声: キャラ固有のvoice/style ✓
- 表情: キャラのemotion_blendshapes ✓
- **課題**: セリフがキャラ自身の言葉ではなく、第三者（スクリプト生成AI）の推測

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

| モード | テキスト生成 | voice/style | emotion | self_note/persona | 個性度 |
|--------|-------------|-------------|---------|-------------------|--------|
| コメント応答 | キャラ自身のプロンプト | ✓ | ✓ | ✓ | ★★★★★ |
| イベント応答 | キャラ自身のプロンプト | ✓ | ✓ | - | ★★★★☆ |
| 授業スクリプト | 第三者が推測して書く | ✓ | ✓ | - | ★★★☆☆ |
| 直接発話 | 外部指定 | ✓ | - | - | ★★☆☆☆ |

## 課題: 授業モードのキャラ個性

### 現状の問題

授業モードのスクリプト生成では、1回のLLM呼び出しで全キャラのセリフを一括生成している。キャラのsystem_promptは「参考情報」として渡されるだけで、**キャラ自身がセリフを考えているわけではない**。

コメント応答モードでは各キャラのペルソナで個別に応答を生成するため、キャラの個性が自然に出る。授業モードではこの仕組みがない。

### 改善の方向性

#### 案A: プロンプト強化（最小変更）

現状の1回LLM呼び出しを維持しつつ、プロンプトを強化:

- 「teacher発話はこのペルソナになりきって書け」と明示
- 各キャラのself_note/personaもプロンプトに含める
- コスト・速度は変わらない

#### 案B: セリフ個別生成（キャラ別LLM）

台本の骨格（誰が何の話をするか）は一括生成し、各セリフはキャラ別のプロンプトで個別生成:

```
[一括] 台本骨格生成
  → section[0]: teacher「テーマ紹介」→ student「リアクション」→ ...

[個別] 各セリフをキャラのsystem_promptで生成
  → ちょビのペルソナ + 文脈 → ちょビらしいセリフ
  → なるこのペルソナ + 文脈 → なるこらしいリアクション
```

- キャラの個性が最も反映される
- LLM呼び出し回数が増える（セリフ数に比例）
- 前後の文脈を渡す設計が必要

#### 案C: 2段階生成（折衷）

1段目で全体を一括生成し、2段目で各キャラのペルソナによるリライト:

```
[1段目] 一括スクリプト生成（現状通り）
[2段目] 各キャラのsystem_promptで自分のセリフをリライト
```

- 構成の整合性を保ちつつ個性を追加
- LLM呼び出しは+2回（先生分・生徒分）
- 速度への影響は小さい
