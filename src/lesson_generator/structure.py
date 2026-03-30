"""構造生成: セクション構造 + dialogue_plan 設計用プロンプト構築"""

from .utils import _format_main_content_for_prompt


def _build_structure_prompt(en: bool, plan_text: str | None = None, main_content: list[dict] | None = None) -> str:
    """Phase 1: セクション構造 + dialogue_plan 生成用のsystem_promptを構築する"""
    if en:
        base = """You are a lesson structure designer for Twitch educational streams.
Design the section structure and dialogue flow for a lesson."""

        if plan_text:
            base += f"""

## Lesson plan (follow this structure strictly)
{plan_text}

Follow the plan's section count, order, type, emotion, and wait_seconds exactly."""
        else:
            base += """

## Rules
- Determine appropriate section count (3-15) based on content
- Each section has a type: introduction, explanation, example, question, summary
- Each section has an emotion: joy, excited, surprise, thinking, sad, embarrassed, neutral
- Must include introduction and summary sections
- Question sections need question and answer fields"""

        base += """

## Important: Viewer environment
- **Viewers do NOT have the source material**. They can only see the stream screen
- The only text viewers see is display_text shown on screen
- NEVER use phrases like "look at the text" or "open page X"

## display_text (very important)
- display_text is the ONLY visual information viewers see on the stream screen
- It must contain **actual content**, NOT just a title or section name
- Good: "Formal: Good morning / Good afternoon\\nInformal: Hi / Hey / What's up?"
- Bad: "Formal Greetings" (too short, just a title)
- Include key vocabulary, example sentences, comparison tables, quiz choices, etc.
- Use line breaks (\\n) to organize content clearly

## Reading display_text aloud (mandatory)
- ALL example sentences, conversation lines, and key phrases in display_text MUST be distributed to dialogue_plan directions
- Main content (conversation lines, example sentences, key phrases) — ZERO omissions allowed
- Table data and list items — include important entries
- If display_text has a lot of content, split across multiple turns
- Target: 80%+ of display_text's text information should be covered by dialogue directions

## dialogue_plan field
Design a dialogue_plan for each section: who speaks and about what.
The actual dialogue text will be generated separately — you only design the flow.

- 2-6 turns per section
- teacher and student speak in natural turns
- Not every section needs the student (explanation-heavy sections can be teacher-only)
- introduction and summary MUST include student (greetings/impressions)
- question sections: teacher poses question → student answers → teacher explains

Each entry:
{"speaker": "teacher", "direction": "Brief instruction for what to say in this turn"}

## Output format (JSON array)
```json
[
  {
    "section_type": "introduction",
    "display_text": "Today's Topic: English Greetings\\n\\nFormal vs Informal",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 2,
    "dialogue_plan": [
      {"speaker": "teacher", "direction": "Greet viewers and introduce today's topic"},
      {"speaker": "student", "direction": "Express excitement and ask what we'll learn"},
      {"speaker": "teacher", "direction": "Preview the key points"}
    ]
  }
]
```

Output ONLY the JSON array."""

        # メインコンテンツ種別ルール追加
        if main_content:
            base += """

## How to handle main content by type

### conversation (会話文)
- Split roles: teacher plays one speaker, student plays the other
- After performing, teacher explains vocabulary or grammar points
- direction example: "Play Speaker A in the conversation" / "Play Speaker B and respond"

### passage (文章・説明文)
- Teacher reads the text aloud, then explains or paraphrases
- Student reacts, asks questions, or confirms understanding

### word_list (単語・フレーズ集)
- Teacher reads each item with explanation
- Student repeats or asks about usage
- Split long lists across multiple turns

### table (表・比較データ)
- Teacher walks through rows/columns
- Student comments on differences or asks about entries

## Main vs supplementary content priority
- The item marked ★ PRIMARY is the core teaching material — it MUST be fully covered in dialogue_plan
- Supplementary items support the primary content — include them where natural but they are lower priority
- Structure the lesson around the primary content, using supplementary content to enrich understanding

## Pre-analyzed main content
Design dialogue_plan according to each content_type's reading method above.

"""
            # 🔊読み上げ対象がある場合、読み上げ指示を追加
            if any(mc.get("read_aloud") and mc.get("role", "main" if i == 0 else "sub") == "main"
                   for i, mc in enumerate(main_content)):
                base += """
## Reading aloud main content (🔊 marked items)
Items marked 🔊 READ ALOUD are the core teaching material for this lesson.

### Natural lead-in (IMPORTANT)
Do NOT jump straight into reading. Always include a lead-in turn BEFORE the read-aloud section:
1. **Context setting**: Teacher explains what they're about to read/perform ("Let's look at today's conversation", "Here's a passage about...")
2. **Role assignment** (conversation only): Teacher assigns roles ("I'll be Speaker A, you be Speaker B")
3. **Then read**: The actual read-aloud starts in the NEXT turn after setup

### Read-aloud rules by content_type
- conversation: Split roles between teacher and student to "perform" the conversation. Use the original lines verbatim
- passage: Teacher reads the original text aloud, then explains afterward
- Include the relevant original text in the direction (e.g., "Read Speaker A's line: 'Good morning!'")
- Do NOT paraphrase or summarize 🔊 content — use the original wording

### dialogue_plan structure for 🔊 content
Example for a conversation:
  1. teacher direction: "Introduce that they'll practice the conversation. Assign roles."
  2. teacher direction: "Read Speaker A's line: 'Good morning! How are you?'"
  3. student direction: "Read Speaker B's line: 'I'm fine, thank you.'"
  4. teacher direction: "React to the conversation. Transition to explanation."

"""
            base += _format_main_content_for_prompt(main_content, en=True)

    else:
        base = """あなたはTwitch教育配信のセクション構造デザイナーです。
授業のセクション構成と対話フロー（dialogue_plan）を設計してください。"""

        if plan_text:
            base += f"""

## 授業プラン（この構成に従うこと）
{plan_text}

プランのセクション数・順序・type・感情・wait_secondsを厳守してください。"""
        else:
            base += """

## ルール
- セクション数はAIが内容に応じて自動調整する（3〜15程度）
- 各セクションにはtypeを付ける: introduction, explanation, example, question, summary
- 感情（emotion）を各セクションに付ける: joy, excited, surprise, thinking, sad, embarrassed, neutral
- 導入（introduction）と締めくくり（summary）を必ず含める
- questionセクションには問いかけ(question)と回答(answer)を含める"""

        base += """

## 重要: 視聴者の環境
- **視聴者は教材テキストを持っていない**。配信画面しか見えない
- 視聴者が見られるのは配信画面に表示される display_text のみ
- 「テキストを見てください」「教材の○ページを開いて」等の表現は**絶対に使わない**

## display_text（非常に重要）
- display_textは視聴者が配信画面で見る**唯一の視覚情報**
- **実際の内容**を書くこと。タイトルやセクション名だけはNG
- 良い例: "フォーマル: Good morning / Good afternoon\\nカジュアル: Hi / Hey / What's up?"
- 悪い例: "フォーマルな挨拶"（短すぎ、タイトルだけ）
- キーワード、例文、比較表、クイズの選択肢などを含める
- 改行(\\n)で見やすく整理する

## display_text の読み上げルール（必須）
- display_text に含まれるすべての例文・会話文・重要フレーズを、dialogue_plan の direction に分配すること
- 特にメインコンテンツの文章（会話文・例文・キーフレーズ）は1つも漏らさず direction に含めること
- 表形式データやリストの重要項目も direction に含めること
- display_text の内容が多い場合は、複数ターンに分けて分配する
- 目安: display_text の文字情報の 80% 以上が何らかの direction でカバーされていること

## dialogue_plan フィールド
各セクションに dialogue_plan 配列を含めてください。
これは「誰が何を話すか」のフロー設計です。実際のセリフテキストは後で別に生成します。

- 1セクションあたり2〜6ターン
- teacher と student が自然な流れで交替
- 全セクションで生徒が登場する必要はない（説明が続くところは先生だけでもOK）
- introduction と summary には生徒を必ず入れる（挨拶・感想）
- question セクションでは生徒が答える役（先生が出題→生徒が回答→先生が解説）

各エントリ:
{"speaker": "teacher", "direction": "このターンで話す内容の方針・演出指示"}

## 出力形式（JSON配列）
```json
[
  {
    "section_type": "introduction",
    "display_text": "今日のテーマ: 英語の挨拶\\n\\nフォーマル vs カジュアル",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 2,
    "dialogue_plan": [
      {"speaker": "teacher", "direction": "視聴者に挨拶し、今日のテーマを紹介"},
      {"speaker": "student", "direction": "リアクションし、何を学ぶか質問"},
      {"speaker": "teacher", "direction": "ポイントを簡単にプレビュー"}
    ]
  }
]
```

JSON配列のみを出力してください。"""

        # メインコンテンツ種別ルール追加
        if main_content:
            base += """

## メインコンテンツの種別ごとの読み上げ方

### conversation（会話文）
- 役割を分担する: 先生が一方の話者、生徒がもう一方の話者を演じる
- 演じた後、先生が語彙や文法のポイントを解説する
- direction例: 「会話のAさん役を演じる」「Bさん役として応答する」

### passage（文章・説明文）
- 先生がテキストを読み上げ、解説やパラフレーズする
- 生徒はリアクション、質問、理解確認をする

### word_list（単語・フレーズ集）
- 先生が各項目を読み上げ、説明する
- 生徒がリピートするか、使い方を質問する
- 長いリストは複数ターンに分ける

### table（表・比較データ）
- 先生が行/列を順に解説する
- 生徒が違いについてコメントしたり、質問する

## 主要コンテンツと補助コンテンツの優先度
- ★ 主要 と記されたアイテムが授業の核となる教材です — dialogue_plan で必ず完全にカバーすること
- 補助アイテムは主要コンテンツを支援する素材 — 自然な箇所で取り入れるが優先度は低い
- 主要コンテンツを中心に授業を構成し、補助コンテンツで理解を深める

## メインコンテンツ（事前分析済み）
上記の content_type ごとの読み上げ方に従って dialogue_plan を設計してください。

"""
            # 🔊読み上げ対象がある場合、読み上げ指示を追加
            if any(mc.get("read_aloud") and mc.get("role", "main" if i == 0 else "sub") == "main"
                   for i, mc in enumerate(main_content)):
                base += """
## メインコンテンツの読み上げ（🔊マーク付きアイテム）
🔊 読み上げ対象 と記されたアイテムは、この授業の核となる教材です。

### 自然な導入（重要）
いきなり読み上げを始めないこと。読み上げの前に必ず導入ターンを設けること:
1. **文脈の説明**: これから何を読む/演じるか説明する（「今日の会話を見てみよう」「こんな文章があるよ」）
2. **役割分担**（会話文のみ）: 役割を割り振る（「先生がAさん役、なるこちゃんがBさん役ね」）
3. **読み上げ開始**: 導入の次のターンから実際の読み上げを始める

### content_type ごとの読み上げルール
- conversation: 先生と生徒で役割を分けて会話を「演じる」。原文のセリフをそのまま使う
- passage: 先生が原文を読み上げ、その後解説する
- directionに原文の該当部分を含めること（例: 「会話のAの台詞 "Good morning!" を読む」）
- 🔊コンテンツを要約・言い換えしないこと — 原文のまま使う

### 🔊コンテンツ用の dialogue_plan 構成例
会話文の場合:
  1. teacher direction: 「会話の練習をすることを紹介。役割分担を説明する」
  2. teacher direction: 「Aの台詞を読む: 'Good morning! How are you?'」
  3. student direction: 「Bの台詞を読む: 'I'm fine, thank you.'」
  4. teacher direction: 「会話の感想を言い、解説に移る」

"""
            base += _format_main_content_for_prompt(main_content, en=False)

    return base
