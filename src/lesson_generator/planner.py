"""レッスンプラン生成: 三者視点（知識先生・エンタメ先生・監督）"""

import json
import logging

from google.genai import types

from . import utils

logger = logging.getLogger(__name__)


def generate_lesson_plan(lesson_name: str, extracted_text: str, source_images: list[str] = None,
                         on_progress=None) -> dict:
    """三者視点で授業プランを生成する（3回のLLM呼び出し）

    Args:
        on_progress: コールバック(step, total, message) で進捗を通知

    Returns:
        dict: {knowledge, entertainment, plan_sections, director_sections, generations}
            plan_sections: [{section_type, title, summary, emotion, has_question}, ...]
            generations: {knowledge: {...}, entertainment: {...}, director: {...}}
                各エントリ: {system_prompt, user_prompt, raw_output, model, temperature}
    """
    def _progress(step, total, msg):
        if on_progress:
            on_progress(step, total, msg)

    client = utils.get_client()
    image_parts = utils._build_image_parts(source_images)
    en = utils._is_english_mode()

    if en:
        user_text = f"# Lesson title: {lesson_name}\n\n# Source text:\n{extracted_text}"
    else:
        user_text = f"# 授業タイトル: {lesson_name}\n\n# 教材テキスト:\n{extracted_text}"

    if en:
        _progress(1, 3, "Knowledge Expert analyzing source material...")
    else:
        _progress(1, 3, "知識先生が教材を分析中...")

    # --- 呼び出し1: 知識先生 / Knowledge Expert ---
    if en:
        knowledge_prompt = """You are the "Knowledge Expert". As the subject lead, analyze the source material and organize the key concepts to teach.

## Your role
- Accurately grasp the core of the material and identify key points to teach
- Design the optimal learning sequence (prerequisites → core → application)
- Point out common misconceptions and tricky areas
- Don't miss important facts, numbers, or concepts in the material

## Output format
Output in the following structure:

### Key points to teach
(Listed by importance)

### Recommended learning sequence
(Prerequisites → main topic → advanced)

### Common misconceptions & pitfalls
(Where learners tend to struggle)

### Recommended section structure
(Overview of what each section should cover)"""
    else:
        knowledge_prompt = """あなたは「知識先生」です。教科主任として、教材を分析し授業で教えるべき内容を整理してください。

## あなたの役割
- 教材の核心を正確に把握し、教えるべき要点を洗い出す
- 学習者にとって最適な順序（前提知識→核心→応用）を設計する
- よくある誤解や注意すべきポイントを指摘する
- 教材に含まれる重要な事実・数値・概念を漏らさない

## 出力形式
以下の構成でテキストを出力してください:

### 教えるべき要点
（重要度順にリスト）

### 推奨する学習順序
（前提→本題→発展の流れ）

### 注意すべき誤解・難所
（学習者がつまずきやすいポイント）

### 推奨セクション構成
（各セクションで扱うべき内容の概要）"""

    parts1 = image_parts + [types.Part(text=user_text)]
    knowledge_model = utils._get_knowledge_model()
    resp1 = client.models.generate_content(
        model=knowledge_model,
        contents=[types.Content(parts=parts1)],
        config=types.GenerateContentConfig(
            system_instruction=knowledge_prompt,
            temperature=1.0,
            max_output_tokens=4096,
        ),
    )
    knowledge_text = resp1.text.strip()
    knowledge_generation = {
        "system_prompt": knowledge_prompt,
        "user_prompt": user_text,
        "raw_output": knowledge_text,
        "model": knowledge_model,
        "temperature": 1.0,
    }
    logger.info("知識先生の分析完了（%d文字, model=%s）", len(knowledge_text), knowledge_model)

    if en:
        _progress(2, 3, "Entertainment Expert designing story arc...")
    else:
        _progress(2, 3, "エンタメ先生が起承転結を設計中...")

    # --- 呼び出し2: エンタメ先生 / Entertainment Expert ---
    if en:
        entertainment_prompt = """You are the "Entertainment Expert". As a popular Twitch instructor who keeps viewers entertained, structure the lesson using a compelling narrative arc.

## Your role
- Building on the Knowledge Expert's analysis, restructure the lesson using a **4-act narrative arc** (Setup → Development → Twist → Resolution)
- Design a structure that keeps viewers watching until the end

## Narrative arc guidelines

### [Setup] Hook & Introduction
- Grab viewer attention instantly with a question or surprising fact
- "Wait, really?" — create a compelling entry point

### [Development] Build-up
- Layer knowledge step by step
- Plant seeds (set up reveals for the Twist)
- Use relatable analogies to aid understanding

### [Twist] Surprise & Reversal
- Flip conventional wisdom, reveal surprising facts
- "Actually, it turns out..." "But here's the catch..."
- Pay off the setups from Development

### [Resolution] Payoff & Conclusion
- The moment everything clicks. A satisfying "Aha!" conclusion
- "And that's why..." — wrap up in one memorable line
- Leave viewers wanting to share what they learned

## Other techniques
- Optimal placement of quizzes and questions
- Emotional dynamics (where to excite, where to provoke thought)
- Humor and analogy ideas

## Output format
Output in the following structure:

### Narrative arc structure
(Overview and intent for each act)

### Payoff design
(What's the "Aha!" moment you want to deliver?)

### Production notes
(Placement of quizzes, analogies, emotional dynamics)"""
    else:
        entertainment_prompt = """あなたは「エンタメ先生」です。Twitch配信で視聴者を楽しませる人気講師として、授業を起承転結で構成してください。

## あなたの役割
- 知識先生の分析を踏まえつつ、**起承転結**の物語構造で授業を再構成する
- 視聴者が最後まで見たくなる構成を設計する

## 起承転結の設計指針

### 【起】導入・フック
- 視聴者の興味を一瞬で掴む問いかけや意外な事実
- 「え、そうなの？」と思わせる入り口

### 【承】展開・積み上げ
- 知識を段階的に積み上げる
- 伏線を張る（後の「転」で回収するネタを仕込む）
- 身近な例え話で理解を助ける

### 【転】転換・驚き
- 常識を覆す展開、意外な事実
- 「実はこうだった！」「でもここが落とし穴で…」
- 承で張った伏線の回収

### 【結】オチ・締め
- 学んだことが全部繋がる瞬間。「なるほど！」と腹落ちする締め
- 「だから○○なんです！」という一言でまとまるオチ
- 視聴者が誰かに話したくなるような余韻

## その他の演出
- クイズや問いかけの最適な配置
- 感情の起伏（どこで盛り上げ、どこで考えさせるか）
- ユーモアや例え話のアイデア

## 出力形式
以下の構成でテキストを出力してください:

### 起承転結の構成
（各パートの概要と演出意図）

### オチの設計
（最後に視聴者に届けたい「なるほど！」は何か）

### 演出ポイント
（クイズ・例え話・感情の起伏の配置）"""

    if en:
        parts2 = [types.Part(text=f"{user_text}\n\n---\n\n# Knowledge Expert's analysis:\n{knowledge_text}")]
    else:
        parts2 = [types.Part(text=f"{user_text}\n\n---\n\n# 知識先生の分析:\n{knowledge_text}")]
    entertainment_model = utils._get_entertainment_model()
    resp2 = client.models.generate_content(
        model=entertainment_model,
        contents=[types.Content(parts=parts2)],
        config=types.GenerateContentConfig(
            system_instruction=entertainment_prompt,
            temperature=1.0,
            max_output_tokens=4096,
        ),
    )
    entertainment_text = resp2.text.strip()
    entertainment_user_prompt = parts2[0].text
    entertainment_generation = {
        "system_prompt": entertainment_prompt,
        "user_prompt": entertainment_user_prompt,
        "raw_output": entertainment_text,
        "model": entertainment_model,
        "temperature": 1.0,
    }
    logger.info("エンタメ先生の構成完了（%d文字, model=%s）", len(entertainment_text), entertainment_model)

    if en:
        _progress(3, 3, "Director integrating the plan...")
    else:
        _progress(3, 3, "監督がプランを統合中...")

    # --- 呼び出し3: 監督 / Director ---
    if en:
        director_prompt = """You are the "Director". Integrate the Knowledge Expert's and Entertainment Expert's proposals to design the complete lesson — section structure, on-screen content, and dialogue flow.

## Your role

### Overall balance
- Balance the Knowledge Expert's accuracy/coverage with the Entertainment Expert's narrative arc
- Prevent information overload — keep section count appropriate (3-15)
- Adopt entertainment elements without compromising accuracy

### Writing titles
- **Max 5 words** — the section's content should be clear at a glance
- Use specific nouns/verbs (Bad: "Introduction & Hook" → Good: "Today's Topic", "Core Vocabulary")
- Purpose: viewers see the progress panel and instantly know where they are

### Fix inconsistencies
- Check flow between sections for contradictions
- Ensure no undefined terms are used before being explained
- Reorder if needed for clarity

### Pacing ("wait_seconds")
Set appropriate **wait_seconds** (pause after each section) for pacing:

- **Natural conversation/explanation**: 1-2 seconds (keep tempo)
- **After key points**: 3-4 seconds (give viewers time to think)
- **After surprising facts/twists**: 4-5 seconds (let it sink in)
- **Questions**: 8-15 seconds (time for viewers to think/chat)
- **Final summary/payoff**: 2-3 seconds (closing pause)

### Viewer environment (IMPORTANT)
- **Viewers do NOT have the source material**. They can only see the stream screen
- The only text viewers see is display_text shown on screen
- NEVER use phrases like "look at the text" or "open page X"

### display_text (VERY IMPORTANT)
- display_text is the ONLY visual information viewers see on the stream screen
- It must contain **actual content**, NOT just a title or section name
- Good: "Formal: Good morning / Good afternoon\\nInformal: Hi / Hey / What's up?"
- Bad: "Formal Greetings" (too short, just a title)
- Include key vocabulary, example sentences, comparison tables, quiz choices, etc.
- Use line breaks (\\n) to organize content clearly

### Reading display_text aloud (MANDATORY)
- ALL example sentences, conversation lines, and key phrases in display_text MUST be distributed to key_content fields in dialogue_directions
- Main content (conversation lines, example sentences, key phrases) — ZERO omissions allowed in key_content
- Table data and list items — include important entries in key_content
- If display_text has a lot of content, split across multiple turns
- Target: 80%+ of display_text's text information should be covered by some key_content

### dialogue_directions
Design the dialogue flow for each section: who speaks, what they say, and what content to cover.
The actual dialogue text will be generated separately by character AIs — you design the blueprint.

- 2-6 turns per section
- teacher and student speak in natural turns
- Not every section needs the student (explanation-heavy sections can be teacher-only)
- introduction and summary MUST include student (greetings/impressions)
- question sections: teacher poses question → student answers → teacher explains

Each entry has:
- "speaker": "teacher" or "student"
- "direction": Specific instruction for this turn (2-3 sentences). Include emotional tone and presentation style, not just content
- "key_content": The specific material content this turn MUST mention (e.g. a vocabulary word, fact, or concept from the source material). Empty string if no specific content required

### Section transitions (IMPORTANT)
- For sections after the first: include a transition cue in the FIRST dialogue_direction entry that references the previous section
  - Example: direction: "Briefly reference the greeting patterns from the previous section, then transition to informal alternatives"
- For sections before the last: include a forward-looking cue in the LAST dialogue_direction entry
  - Example: direction: "Wrap up and tease the next topic — casual slang expressions"
- These cues ensure natural flow when each section's dialogue is generated independently

## Output format (JSON array)
```json
[
  {
    "section_type": "introduction",
    "title": "Short specific title (max 5 words)",
    "display_text": "Today's Topic: English Greetings\\n\\n'How are you?' — what does it really mean?\\n\\nIt's totally different from Japanese '元気？'!",
    "emotion": "excited",
    "wait_seconds": 2,
    "question": "",
    "answer": "",
    "dialogue_directions": [
      {"speaker": "teacher", "direction": "Greet viewers energetically. Introduce today's theme 'the real meaning of English greetings' and tease that 'How are you?' is deeper than it seems", "key_content": "How are you? — its real meaning"},
      {"speaker": "student", "direction": "React confidently: 'How are you? is easy! You just say I'm fine, right?' Show overconfidence", "key_content": "I'm fine, thank you — the textbook answer"},
      {"speaker": "teacher", "direction": "Smile and hint: 'Actually... natives almost never say that.' Announce that this lesson will reveal the secret", "key_content": "Natives rarely use 'I'm fine'"}
    ]
  }
]
```

### section_type options
- introduction: Opening (Setup)
- explanation: Teaching (Development)
- example: Examples & analogies
- question: Viewer interaction (set question and answer fields)
- summary: Wrap-up (Resolution)

### emotion options
- joy, excited, surprise, thinking, sad, embarrassed, neutral

Output ONLY the JSON array."""
    else:
        director_prompt = """あなたは「監督」です。知識先生とエンタメ先生の提案を統合し、授業の完全な設計（セクション構成・画面表示内容・対話フロー）を決定してください。

## あなたの役割

### 全体のバランス調整
- 知識先生の正確性・網羅性とエンタメ先生の起承転結・演出を両立させる
- 詰め込みすぎを防ぎ、適切なセクション数（3〜15）に調整する
- 知識の正確性を損なわない範囲でエンタメ要素を採用する

### titleの書き方
- **10文字以内**で、そのセクションの内容が一目で分かるようにする
- 具体的な名詞・動詞を使う（NG: 「導入・フック」「知識の積み上げ」→ OK: 「今日のテーマ」「基本単語」）
- 視聴者が進捗パネルを見て「今どこをやっているか」すぐ分かることが目的

### 矛盾・分かりにくさの修正
- セクション間の流れに矛盾がないかチェックする
- 前のセクションで説明していない用語を使っていないか確認する
- 分かりにくい構成があれば順序を入れ替える

### 「間」（ま）の設計
各セクションに適切な **wait_seconds**（セクション終了後の間）を設定してください。
間は授業のリズムを作る重要な要素です。

- **自然な会話・説明**: 1〜2秒（テンポよく次へ）
- **重要なポイントの後**: 3〜4秒（視聴者に考える時間を与える）
- **驚きの事実・転換の後**: 4〜5秒（余韻を残す）
- **問いかけ（question）**: 8〜15秒（視聴者が考える・チャットで答える時間）
- **最後のまとめ・オチ**: 2〜3秒（締めの余韻）

### 視聴者の環境（重要）
- **視聴者は教材テキストを持っていない**。配信画面しか見えない
- 視聴者が見られるのは配信画面に表示される display_text のみ
- 「テキストを見てください」「教材の○ページを開いて」等の表現は**絶対に使わない**

### display_text（非常に重要）
- display_textは視聴者が配信画面で見る**唯一の視覚情報**
- **実際の内容**を書くこと。タイトルやセクション名だけはNG
- 良い例: "フォーマル: Good morning / Good afternoon\\nカジュアル: Hi / Hey / What's up?"
- 悪い例: "フォーマルな挨拶"（短すぎ、タイトルだけ）
- キーワード、例文、比較表、クイズの選択肢などを含める
- 改行(\\n)で見やすく整理する

### display_text の読み上げルール（必須）
- display_text に含まれるすべての例文・会話文・重要フレーズを、dialogue_directions の key_content に分配すること
- 特にメインコンテンツの文章（会話文・例文・キーフレーズ）は1つも漏らさず key_content に含めること
- 表形式データやリストの重要項目も key_content に含めること
- display_text の内容が多い場合は、複数ターンに分けて分配する
- 目安: display_text の文字情報の 80% 以上が何らかの key_content でカバーされていること

### dialogue_directions（対話フロー設計）
各セクションに dialogue_directions 配列を含めてください。
「誰が・何を・どう話すか」の設計図です。実際のセリフはキャラクターAIが別途生成します。

- 1セクションあたり2〜6ターン
- teacher と student が自然な流れで交替
- 全セクションで生徒が登場する必要はない（説明が続くところは先生だけでもOK）
- introduction と summary には生徒を必ず入れる（挨拶・感想）
- question セクションでは生徒が答える役（先生が出題→生徒が回答→先生が解説）

各エントリ:
- "speaker": "teacher" または "student"
- "direction": このターンの具体的な演出指示（2〜3文）。感情や話し方も含める
- "key_content": このターンで必ず言及すべき教材の具体的内容（単語・事実・概念など）。特にない場合は空文字

### セクション間のつなぎ（重要）
- 最初以外のセクション: 最初の dialogue_direction に、前セクションの内容を参照するつなぎを含めること
  - 例: direction: 「先ほどの挨拶パターンに軽く触れつつ、カジュアルな表現の説明へ移る」
- 最後以外のセクション: 最後の dialogue_direction に、次セクションへの予告を含めること
  - 例: direction: 「まとめた上で、次のスラング表現について軽く予告する」
- セリフは各セクション独立で生成されるため、これらのつなぎ指示が自然な流れを作る鍵となる

## 出力形式（JSON配列）
```json
[
  {
    "section_type": "introduction",
    "title": "10文字以内の具体的なタイトル",
    "display_text": "今日のテーマ: 英語の挨拶\\n\\n『How are you?』の本当の意味とは？\\n\\n日本語の『元気？』とは全然違う！",
    "emotion": "excited",
    "wait_seconds": 2,
    "question": "",
    "answer": "",
    "dialogue_directions": [
      {"speaker": "teacher", "direction": "視聴者に元気よく挨拶。今日のテーマ『英語の挨拶の本当の意味』を紹介し、「How are you?って実はすごく奥が深い」と興味を引く", "key_content": "How are you? の本当の意味"},
      {"speaker": "student", "direction": "「え、How are you?なんて簡単じゃん！I'm fine って答えればいいんでしょ？」と自信満々に反応する", "key_content": "I'm fine, thank you の定型文"},
      {"speaker": "teacher", "direction": "「ふふ、実はそれ…ネイティブはほぼ使わないんだよ」と意外な事実を予告。この授業で秘密を解き明かすと宣言", "key_content": "I'm fine はネイティブが使わない"}
    ]
  }
]
```

### section_type の選択肢
- introduction: 導入（起）
- explanation: 説明（承）
- example: 具体例・例え話
- question: 視聴者への問いかけ（question と answer フィールドを設定）
- summary: まとめ・締め（結）

### emotion の選択肢
- joy, excited, surprise, thinking, sad, embarrassed, neutral

JSON配列のみを出力してください。"""

    if en:
        parts3 = [types.Part(text=(
            f"# Knowledge Expert's analysis:\n{knowledge_text}\n\n"
            f"---\n\n# Entertainment Expert's structure:\n{entertainment_text}"
        ))]
    else:
        parts3 = [types.Part(text=(
            f"# 知識先生の分析:\n{knowledge_text}\n\n"
            f"---\n\n# エンタメ先生の構成:\n{entertainment_text}"
        ))]
    director_model = utils._get_director_model()
    resp3 = client.models.generate_content(
        model=director_model,
        contents=[types.Content(parts=parts3)],
        config=types.GenerateContentConfig(
            system_instruction=director_prompt,
            response_mime_type="application/json",
            temperature=1.0,
            max_output_tokens=8192,
        ),
    )

    # 監督の生出力を保存（パース前）
    raw_director_output = resp3.text

    # JSONパース（壊れたJSONは自動修復）
    try:
        director_sections = utils._parse_json_response(raw_director_output)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("監督のプランJSONパース失敗: %s (先頭500文字: %s)", e, resp3.text[:500])
        raise ValueError("プラン生成のJSONパースに失敗しました。再度お試しください。")

    if not isinstance(director_sections, list):
        raise ValueError("プラン生成結果が配列ではありません")

    # 必須フィールド補完（v3形式）
    valid_types = {"introduction", "explanation", "example", "question", "summary"}
    for s in director_sections:
        if s.get("section_type") not in valid_types:
            s["section_type"] = "explanation"
        s.setdefault("title", "")
        s.setdefault("display_text", "")
        s.setdefault("emotion", "neutral")
        s.setdefault("question", "")
        s.setdefault("answer", "")
        # 間のデフォルト: questionは10秒、それ以外は2秒
        default_wait = 10 if s.get("section_type") == "question" else 2
        s.setdefault("wait_seconds", default_wait)
        # dialogue_directionsのデフォルト・補完
        if "dialogue_directions" not in s:
            s["dialogue_directions"] = []
        for dd in s["dialogue_directions"]:
            dd.setdefault("speaker", "teacher")
            dd.setdefault("direction", "")
            dd.setdefault("key_content", "")

    # 互換用: plan_sections（旧形式のメタデータ）を生成
    plan_sections = []
    for s in director_sections:
        plan_sections.append({
            "section_type": s["section_type"],
            "title": s["title"],
            "summary": s.get("display_text", "")[:200],  # display_textの先頭をsummaryとして流用
            "emotion": s["emotion"],
            "has_question": s["section_type"] == "question",
            "wait_seconds": s["wait_seconds"],
        })

    director_user_prompt = parts3[0].text
    director_generation = {
        "system_prompt": director_prompt,
        "user_prompt": director_user_prompt,
        "raw_output": raw_director_output,
        "model": director_model,
        "temperature": 1.0,
    }

    logger.info("監督の最終プラン完了（%dセクション, model=%s）", len(director_sections), director_model)

    return {
        "knowledge": knowledge_text,
        "entertainment": entertainment_text,
        "plan_sections": plan_sections,
        "director_sections": director_sections,
        "generations": {
            "knowledge": knowledge_generation,
            "entertainment": entertainment_generation,
            "director": director_generation,
        },
    }
