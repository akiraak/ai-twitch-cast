"""教師モード — 画像/URL解析 + 授業スクリプト生成"""

import base64
import json
import logging
import os
import re
from pathlib import Path

import httpx
from google.genai import types

from src.gemini_client import get_client
from src.prompt_builder import get_stream_language

logger = logging.getLogger(__name__)


# --- キャラクター・対話プロンプト ---

def get_lesson_characters() -> dict:
    """授業用キャラクター（先生・生徒）を取得する。

    Returns:
        {"teacher": config_dict or None, "student": config_dict or None}
    """
    from src import db
    from src.ai_responder import _get_channel_id, seed_all_characters

    channel_id = _get_channel_id()
    seed_all_characters(channel_id)

    teacher_row = db.get_character_by_role(channel_id, "teacher")
    student_row = db.get_character_by_role(channel_id, "student")

    teacher = json.loads(teacher_row["config"]) if teacher_row else None
    student = json.loads(student_row["config"]) if student_row else None
    return {"teacher": teacher, "student": student}


def _format_character_for_prompt(config: dict, role_label: str, en: bool) -> str:
    """キャラ設定からプロンプト用の説明テキストを構築する

    性格（system_prompt）と感情のみ使用。
    rules はシーン依存（コメント応答 vs 授業）なので含めない。
    """
    name = config.get("name", role_label)
    system_prompt = config.get("system_prompt", "")
    emotions = config.get("emotions", {})

    lines = [f"### {role_label}: {name}（speaker: \"{role_label}\"）"]
    if system_prompt:
        lines.append(system_prompt)
    if emotions:
        emotion_list = ", ".join(emotions.keys())
        if en:
            lines.append(f"\n**Available emotions:** {emotion_list}")
        else:
            lines.append(f"\n**使用可能な感情:** {emotion_list}")
    return "\n".join(lines)


def _build_dialogue_prompt(teacher_config: dict, student_config: dict, en: bool) -> str:
    """対話形式のプロンプト追加テキストを構築する"""
    teacher_desc = _format_character_for_prompt(teacher_config, "teacher", en)
    student_desc = _format_character_for_prompt(student_config, "student", en)

    if en:
        return f"""
## Characters
This lesson features two characters in dialogue:

{teacher_desc}

{student_desc}

## dialogues field
Include a dialogues array in each section.
- 2-6 utterances per section
- teacher and student speak in natural turns
- Not every section needs the student (explanation-heavy sections can be teacher-only)
- introduction and summary MUST include student (greetings/impressions)
- question sections: teacher poses question → student answers → teacher explains

Each dialogue entry:
```json
{{
  "speaker": "teacher",
  "content": "Speech text (no tags)",
  "tts_text": "TTS text (with [lang:xx] tags for non-English parts)",
  "emotion": "excited"
}}
```
"""
    else:
        return f"""
## 登場キャラクター
この授業には2人のキャラクターが対話形式で登場します:

{teacher_desc}

{student_desc}

## dialogues フィールド
各セクションに dialogues 配列を含めてください。
- 1セクションあたり2〜6発話
- teacher と student が交互に、または自然な流れで発話
- 全セクションで生徒が登場する必要はない（説明が続くところは先生だけでもOK）
- introduction と summary には生徒を必ず入れる（挨拶・感想）
- question セクションでは生徒が答える役（先生が出題→生徒が回答→先生が解説）

各 dialogue エントリ:
```json
{{
  "speaker": "teacher",
  "content": "発話テキスト（タグなし）",
  "tts_text": "TTS用テキスト（英語部分に[lang:en]タグ付き）",
  "emotion": "excited"
}}
```
"""


def _build_dialogue_output_example(en: bool) -> str:
    """dialogues付きのJSON出力例を構築する"""
    if en:
        return """
## Output format (JSON array)
```json
[
  {
    "section_type": "introduction",
    "display_text": "Text shown on screen",
    "question": "",
    "answer": "",
    "wait_seconds": 2,
    "dialogues": [
      {"speaker": "teacher", "content": "Hello everyone!", "tts_text": "Hello everyone!", "emotion": "excited"},
      {"speaker": "student", "content": "Hi! What are we learning today?", "tts_text": "Hi! What are we learning today?", "emotion": "joy"}
    ]
  }
]
```

Output ONLY the JSON array."""
    else:
        return """
## 出力形式（JSON配列）
```json
[
  {
    "section_type": "introduction",
    "display_text": "画面に表示するテキスト",
    "question": "",
    "answer": "",
    "wait_seconds": 2,
    "dialogues": [
      {"speaker": "teacher", "content": "みんなこんにちは！", "tts_text": "みんなこんにちは！", "emotion": "excited"},
      {"speaker": "student", "content": "こんにちは！今日は何を学ぶの？", "tts_text": "こんにちは！今日は何を学ぶの？", "emotion": "joy"}
    ]
  }
]
```

JSON配列のみを出力してください。"""


def _build_section_from_dialogues(section: dict) -> dict:
    """dialoguesからトップレベルのcontent/tts_text/emotionを自動構築する"""
    dialogues = section.get("dialogues", [])
    if not dialogues:
        return section

    section["content"] = "".join(d["content"] for d in dialogues)
    section["tts_text"] = "".join(d.get("tts_text", d["content"]) for d in dialogues)
    teacher_dlgs = [d for d in dialogues if d["speaker"] == "teacher"]
    section["emotion"] = teacher_dlgs[0]["emotion"] if teacher_dlgs else "neutral"
    return section


def _is_english_mode():
    """配信言語が英語モードかどうかを返す"""
    return get_stream_language()["primary"] != "ja"

_CHAT_MODEL = None


def _get_model():
    global _CHAT_MODEL
    if _CHAT_MODEL is None:
        _CHAT_MODEL = os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview")
    return _CHAT_MODEL


# --- 画像解析 ---

def extract_text_from_image(image_path: str) -> str:
    """画像からテキストを抽出する（Gemini Vision）"""
    client = get_client()
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"画像が見つかりません: {image_path}")

    data = path.read_bytes()
    mime = _guess_mime(path.suffix)

    response = client.models.generate_content(
        model=_get_model(),
        contents=[
            types.Content(parts=[
                types.Part(inline_data=types.Blob(mime_type=mime, data=data)),
                types.Part(text="この画像に含まれるテキストをすべて正確に抽出してください。"
                           "レイアウトを保ちつつ、テキストのみを出力してください。"),
            ]),
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )
    return response.text.strip()


def _guess_mime(ext: str) -> str:
    ext = ext.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")


# --- URL解析 ---

async def extract_text_from_url(url: str) -> str:
    """URLからテキストを取得する"""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        resp = await http.get(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; AI-Twitch-Cast/1.0)"
        })
        resp.raise_for_status()
        html = resp.text

    # HTMLからテキストを抽出（簡易）
    client = get_client()
    response = client.models.generate_content(
        model=_get_model(),
        contents=f"以下のHTMLから、教材として有用なテキスト内容を抽出してください。"
                 f"HTMLタグは除去し、本文テキストのみを返してください。\n\n{html[:30000]}",
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )
    return response.text.strip()


# --- 三者視点プラン生成 ---

def _build_image_parts(source_images: list[str] | None) -> list:
    """画像をGemini用のPartリストに変換する"""
    parts = []
    if source_images:
        for img_path in source_images:
            p = Path(img_path)
            if p.exists():
                data = p.read_bytes()
                mime = _guess_mime(p.suffix)
                parts.append(types.Part(inline_data=types.Blob(mime_type=mime, data=data)))
    return parts


def generate_lesson_plan(lesson_name: str, extracted_text: str, source_images: list[str] = None,
                         on_progress=None) -> dict:
    """三者視点で授業プランを生成する（3回のLLM呼び出し）

    Args:
        on_progress: コールバック(step, total, message) で進捗を通知

    Returns:
        dict: {knowledge: str, entertainment: str, plan_sections: list[dict]}
            plan_sections: [{section_type, title, summary, emotion, has_question}, ...]
    """
    def _progress(step, total, msg):
        if on_progress:
            on_progress(step, total, msg)

    client = get_client()
    image_parts = _build_image_parts(source_images)
    en = _is_english_mode()

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
    resp1 = client.models.generate_content(
        model=_get_model(),
        contents=[types.Content(parts=parts1)],
        config=types.GenerateContentConfig(
            system_instruction=knowledge_prompt,
            temperature=0.5,
            max_output_tokens=4096,
        ),
    )
    knowledge_text = resp1.text.strip()
    logger.info("知識先生の分析完了（%d文字）", len(knowledge_text))

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
    resp2 = client.models.generate_content(
        model=_get_model(),
        contents=[types.Content(parts=parts2)],
        config=types.GenerateContentConfig(
            system_instruction=entertainment_prompt,
            temperature=0.8,
            max_output_tokens=4096,
        ),
    )
    entertainment_text = resp2.text.strip()
    logger.info("エンタメ先生の構成完了（%d文字）", len(entertainment_text))

    if en:
        _progress(3, 3, "Director integrating the plan...")
    else:
        _progress(3, 3, "監督がプランを統合中...")

    # --- 呼び出し3: 監督 / Director ---
    if en:
        director_prompt = """You are the "Director". Integrate the Knowledge Expert's and Entertainment Expert's proposals to finalize the lesson plan.

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

## Output format (JSON array)
```json
[
  {
    "section_type": "introduction",
    "title": "Short specific title (max 5 words, e.g.: Greetings, Quiz Time, Wrap-up)",
    "summary": "Overview of what this section covers (2-3 sentences)",
    "emotion": "excited",
    "has_question": false,
    "wait_seconds": 2
  }
]
```

### section_type options
- introduction: Opening (Setup)
- explanation: Teaching (Development)
- example: Examples & analogies
- question: Viewer interaction
- summary: Wrap-up (Resolution)

### emotion options
- joy, excited, surprise, thinking, sad, embarrassed, neutral

Output ONLY the JSON array."""
    else:
        director_prompt = """あなたは「監督」です。知識先生とエンタメ先生の提案を統合し、最終的な授業プランを決定してください。

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

## 出力形式（JSON配列）
```json
[
  {
    "section_type": "introduction",
    "title": "10文字以内の具体的なタイトル（例: 基本の挨拶、クイズタイム、まとめ）",
    "summary": "このセクションで扱う内容の概要（2〜3文）",
    "emotion": "excited",
    "has_question": false,
    "wait_seconds": 2
  }
]
```

### section_type の選択肢
- introduction: 導入（起）
- explanation: 説明（承）
- example: 具体例・例え話
- question: 視聴者への問いかけ
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
    resp3 = client.models.generate_content(
        model=_get_model(),
        contents=[types.Content(parts=parts3)],
        config=types.GenerateContentConfig(
            system_instruction=director_prompt,
            response_mime_type="application/json",
            temperature=0.5,
            max_output_tokens=4096,
        ),
    )

    # JSONパース
    plan_text = resp3.text.strip()
    plan_text = re.sub(r'^```(?:json)?\s*\n?', '', plan_text)
    plan_text = re.sub(r'\n?\s*```$', '', plan_text)
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', plan_text, re.DOTALL)
    if m:
        plan_text = m.group(1).strip()

    try:
        plan_sections = json.loads(plan_text)
    except json.JSONDecodeError as e:
        logger.error("監督のプランJSONパース失敗 (pos=%s): %s...", e.pos, plan_text[:500])
        raise ValueError("プラン生成のJSONパースに失敗しました。再度お試しください。")

    if not isinstance(plan_sections, list):
        raise ValueError("プラン生成結果が配列ではありません")

    # 必須フィールド補完
    valid_types = {"introduction", "explanation", "example", "question", "summary"}
    for s in plan_sections:
        if s.get("section_type") not in valid_types:
            s["section_type"] = "explanation"
        s.setdefault("title", "")
        s.setdefault("summary", "")
        s.setdefault("emotion", "neutral")
        s.setdefault("has_question", s.get("section_type") == "question")
        # 間のデフォルト: questionは10秒、それ以外は2秒
        default_wait = 10 if s.get("section_type") == "question" else 2
        s.setdefault("wait_seconds", default_wait)

    logger.info("監督の最終プラン完了（%dセクション）", len(plan_sections))

    return {
        "knowledge": knowledge_text,
        "entertainment": entertainment_text,
        "plan_sections": plan_sections,
    }


# --- スクリプト生成 ---

def generate_lesson_script(lesson_name: str, extracted_text: str, source_images: list[str] = None,
                           on_progress=None, student_config: dict = None) -> list[dict]:
    """教材テキスト（+ 画像）から授業スクリプトを生成する

    Args:
        lesson_name: 授業コンテンツ名
        extracted_text: 抽出済みテキスト
        source_images: 画像ファイルパスのリスト（Gemini Vision用）
        on_progress: コールバック(step, total, message) で進捗を通知
        student_config: 生徒キャラ設定（Noneなら従来の一人語り形式）

    Returns:
        list[dict]: セクション一覧
            [{section_type, content, tts_text, display_text, emotion,
              question, answer, wait_seconds, dialogues}, ...]
    """
    def _progress(step, total, msg):
        if on_progress:
            on_progress(step, total, msg)

    en = _is_english_mode()
    if en:
        _progress(1, 2, "Generating script with LLM...")
    else:
        _progress(1, 2, "LLMでスクリプト生成中...")
    client = get_client()

    if en:
        system_prompt = """You are a lesson script generation AI.
Based on the source text (and images), generate a Twitch stream lesson script.

## Important: Viewer environment
- **Viewers do NOT have the source material**. They can only see the stream screen
- The only text viewers see is display_text shown on screen
- NEVER use phrases like "look at the text" or "open page X of the material"
- Any content you want viewers to reference (examples, diagrams, terms) MUST be in display_text, and say "check the screen" or "I'll put it on screen"
- The speech (content/tts_text) alone should convey the full meaning. display_text is supplementary visual support

## Rules
- Teach faithfully based on the source material, making it easy to understand
- Teach entirely in English
- AI determines section count based on content (roughly 3-15)
- Each section has a type: introduction, explanation, example, question, summary
- Each section has an emotion: joy, excited, surprise, thinking, sad, embarrassed, neutral
- Question sections include a question and answer
- Must include introduction and conclusion

## content vs tts_text (important)
- content: Text shown in subtitles. NO tags or markup ever
- tts_text: Text sent to TTS. Same as content, but add [lang:xx]...[/lang] tags for **non-English** language parts
  - xx = ja, es, ko, fr, zh etc.
  - Example: content="Let's learn こんにちは today" → tts_text="Let's learn [lang:ja]こんにちは[/lang] today"
  - If English only, no tags needed (same as content)

## Output format (JSON array)
```json
[
  {
    "section_type": "introduction",
    "content": "Speech text (what the host says. No tags)",
    "tts_text": "TTS text (with [lang:xx] tags for non-English parts)",
    "display_text": "Text shown on screen (key points, examples, etc.)",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  },
  {
    "section_type": "question",
    "content": "Speech for posing the question",
    "tts_text": "TTS text",
    "display_text": "Question shown on screen",
    "emotion": "thinking",
    "question": "Question for viewers",
    "answer": "Correct answer and explanation",
    "wait_seconds": 8
  }
]
```

Output ONLY the JSON array. No other text."""
    else:
        system_prompt = """あなたは授業スクリプト生成AIです。
教材のテキスト（と画像）をもとに、Twitch配信の授業スクリプトを生成してください。

## 重要: 視聴者の環境
- **視聴者は教材テキストを持っていない**。配信画面しか見えない
- 視聴者が見られるのは配信画面に表示される display_text のみ
- 「テキストを見てください」「教材の○ページを開いて」等の表現は**絶対に使わない**
- 参照してほしい内容（例文・図表・用語）は必ず display_text に含め、「画面を見てください」「画面に出しますね」と言う
- 発話（content/tts_text）だけで内容が伝わるようにする。display_text は補足・視覚的サポート

## ルール
- 教材の内容に忠実に、わかりやすく教える授業スクリプトを作る
- バイリンガル（日本語と英語を自然に混ぜる）で教える
- セクション数はAIが内容に応じて自動調整する（3〜15程度）
- 各セクションにはtypeを付ける: introduction, explanation, example, question, summary
- 感情（emotion）を各セクションに付ける: joy, excited, surprise, thinking, sad, embarrassed, neutral
- questionセクションには問いかけ(question)と回答(answer)を含める
- 導入と締めくくりを必ず含める

## contentとtts_textの違い（重要・厳守）
- content: 字幕に表示するテキスト。タグやマークアップは絶対に含めない
- tts_text: TTS音声合成に送信するテキスト。contentと同じ内容だが、**日本語以外の言語部分に [lang:xx]...[/lang] タグを付ける**
  - xx = en, es, ko, fr, zh 等の言語コード
  - 例: content="Helloは挨拶だよ" → tts_text="[lang:en]Hello[/lang]は挨拶だよ"
  - 例: content="How are you?って聞かれたら..." → tts_text="[lang:en]How are you?[/lang]って聞かれたら..."
  - 例: content="appleはりんごのことだね" → tts_text="[lang:en]apple[/lang]はりんごのことだね"
  - 日本語のみの場合はタグ不要（contentと同じ内容にする）
  - **英語の単語1つでも必ずタグを付ける**。タグがないと日本語アクセントで読まれてしまう

## 英語発音のルール
- 英語の単語・フレーズ・例文はネイティブ英語の発音で読み上げさせる
- tts_textで英語部分を必ず [lang:en]...[/lang] で囲むことが最重要
- 英語の例文を紹介するときは、contentでも自然な導入をする（「画面に出しますね」等）

## 出力形式（JSON配列）
```json
[
  {
    "section_type": "introduction",
    "content": "発話テキスト（ちょビが話す内容。タグなし）",
    "tts_text": "TTS用テキスト（英語部分に[lang:en]タグ付き）",
    "display_text": "画面に表示するテキスト（要点・例文など自由形式）",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  },
  {
    "section_type": "question",
    "content": "問題を出す発話テキスト",
    "tts_text": "TTS用テキスト",
    "display_text": "画面に表示する問題文",
    "emotion": "thinking",
    "question": "視聴者への問いかけ",
    "answer": "正解と解説",
    "wait_seconds": 8
  }
]
```

JSON配列のみを出力してください。他のテキストは不要です。"""

    # 対話モード: 生徒キャラがいればdialogues指示を追加
    dialogue_mode = False
    if student_config:
        characters = get_lesson_characters()
        teacher_cfg = characters.get("teacher")
        if teacher_cfg:
            dialogue_mode = True
            # 出力形式セクションを対話版に差し替え
            if en:
                system_prompt = system_prompt.rsplit("## Output format", 1)[0]
            else:
                system_prompt = system_prompt.rsplit("## 出力形式", 1)[0]
            system_prompt += _build_dialogue_prompt(teacher_cfg, student_config, en)
            system_prompt += _build_dialogue_output_example(en)

    parts = _build_image_parts(source_images)

    if en:
        user_text = f"# Lesson title: {lesson_name}\n\n# Source text:\n{extracted_text}"
    else:
        user_text = f"# 授業タイトル: {lesson_name}\n\n# 教材テキスト:\n{extracted_text}"
    parts.append(types.Part(text=user_text))

    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
        if attempt > 0:
            if en:
                _progress(1, 2, f"Retrying script generation ({attempt + 1}/{max_retries})...")
            else:
                _progress(1, 2, f"LLMでスクリプト再生成中（リトライ {attempt + 1}/{max_retries}）...")
        response = client.models.generate_content(
            model=_get_model(),
            contents=[types.Content(parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )

        _progress(2, 2, "JSONパース・セクション整理中...")

        # JSONパース
        text = response.text.strip()
        # ```json ... ``` を除去（マルチライン対応）
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        # 先頭/末尾の ``` だけ残っている場合も除去
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?\s*```$', '', text)

        try:
            sections = json.loads(text)
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning("スクリプト生成のJSONパースに失敗 (attempt=%d, pos=%s): %s...（全%d文字）",
                           attempt + 1, e.pos, text[:500], len(text))
            continue

        if not isinstance(sections, list):
            last_error = ValueError("スクリプト生成結果が配列ではありません")
            logger.warning("スクリプト生成結果が配列ではありません (attempt=%d)", attempt + 1)
            continue

        # パース成功
        break
    else:
        # 全リトライ失敗
        if isinstance(last_error, json.JSONDecodeError):
            raise ValueError(f"スクリプト生成のJSONパースに{max_retries}回失敗しました。再度お試しください。")
        raise ValueError(str(last_error))

    # 必須フィールドの補完（プランなし — titleなし）
    valid_types = {"introduction", "explanation", "example", "question", "summary"}
    result = []
    for s in sections:
        dialogues_raw = s.get("dialogues", [])

        section = {
            "section_type": s.get("section_type", "explanation"),
            "content": s.get("content", ""),
            "tts_text": s.get("tts_text", s.get("content", "")),
            "display_text": s.get("display_text", ""),
            "emotion": s.get("emotion", "neutral"),
            "question": s.get("question", ""),
            "answer": s.get("answer", ""),
            "wait_seconds": int(s.get("wait_seconds", 0)),
        }
        # 対話モードならdialoguesからcontent/tts_text/emotionを自動構築
        if dialogue_mode and dialogues_raw:
            section["dialogues"] = dialogues_raw  # リストのまま渡す
            section = _build_section_from_dialogues(section)
        # dialoguesをJSON文字列に変換してDB保存用にする
        section["dialogues"] = json.dumps(dialogues_raw, ensure_ascii=False) if dialogues_raw else ""
        if section["section_type"] not in valid_types:
            section["section_type"] = "explanation"
        result.append(section)

    return result


def generate_lesson_script_from_plan(
    lesson_name: str,
    extracted_text: str,
    plan_sections: list[dict],
    source_images: list[str] = None,
    on_progress=None,
    student_config: dict = None,
) -> list[dict]:
    """プランに基づいて授業スクリプトを生成する

    Args:
        lesson_name: 授業コンテンツ名
        extracted_text: 抽出済みテキスト
        plan_sections: 監督の最終プラン
        source_images: 画像ファイルパスのリスト
        on_progress: コールバック(step, total, message) で進捗を通知
        student_config: 生徒キャラ設定（Noneなら従来の一人語り形式）

    Returns:
        list[dict]: セクション一覧（generate_lesson_scriptと同じ形式）
    """
    def _progress(step, total, msg):
        if on_progress:
            on_progress(step, total, msg)

    en = _is_english_mode()
    if en:
        _progress(1, 2, "Generating script from plan...")
    else:
        _progress(1, 2, "プランに基づいてスクリプト生成中...")
    client = get_client()

    # プランを読みやすいテキストに変換
    if en:
        plan_text = "\n".join(
            f"{i+1}. [{s.get('section_type', 'explanation')}] {s.get('title', '')} — {s.get('summary', '')} (emotion: {s.get('emotion', 'neutral')}, pause: {s.get('wait_seconds', 2)}s)"
            + (" *has question" if s.get("has_question") else "")
            for i, s in enumerate(plan_sections)
        )
    else:
        plan_text = "\n".join(
            f"{i+1}. [{s.get('section_type', 'explanation')}] {s.get('title', '')} — {s.get('summary', '')} (感情: {s.get('emotion', 'neutral')}, 間: {s.get('wait_seconds', 2)}秒)"
            + (f" ※問いかけあり" if s.get("has_question") else "")
            for i, s in enumerate(plan_sections)
        )

    if en:
        system_prompt = f"""You are a lesson script generation AI.
Follow the lesson plan below **strictly** to generate a Twitch stream lesson script.

## Lesson plan (follow this structure)
{plan_text}

## Important: Viewer environment
- **Viewers do NOT have the source material**. They can only see the stream screen
- The only text viewers see is display_text shown on screen
- NEVER use phrases like "look at the text" or "open page X"
- Any content you want viewers to reference MUST be in display_text, and say "check the screen"
- The speech (content/tts_text) alone should convey the full meaning. display_text is supplementary

## Rules
- Strictly follow the plan's section count, order, type, emotion, and wait_seconds
- Expand each section's summary into speech text
- Teach entirely in English
- Sections with has_question=true must include question and answer
- Stay faithful to the source material
- Use wait_seconds values from the plan as-is

## content vs tts_text (important)
- content: Text shown in subtitles. NO tags or markup ever
- tts_text: Text sent to TTS. Same as content, but add [lang:xx]...[/lang] tags for **non-English** parts
  - xx = ja, es, ko, fr, zh etc.
  - Example: content="Let's learn こんにちは today" → tts_text="Let's learn [lang:ja]こんにちは[/lang] today"
  - If English only, no tags needed (same as content)

## Output format (JSON array)
```json
[
  {{
    "section_type": "introduction",
    "content": "Speech text (what the host says. No tags)",
    "tts_text": "TTS text (with [lang:xx] tags for non-English parts)",
    "display_text": "Text shown on screen",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  }}
]
```

Output ONLY the JSON array."""
    else:
        system_prompt = f"""あなたは授業スクリプト生成AIです。
以下の授業プランに**忠実に従って**、Twitch配信の授業スクリプトを生成してください。

## 授業プラン（この構成に従うこと）
{plan_text}

## 重要: 視聴者の環境
- **視聴者は教材テキストを持っていない**。配信画面しか見えない
- 視聴者が見られるのは配信画面に表示される display_text のみ
- 「テキストを見てください」「教材の○ページを開いて」等の表現は**絶対に使わない**
- 参照してほしい内容（例文・図表・用語）は必ず display_text に含め、「画面を見てください」「画面に出しますね」と言う
- 発話（content/tts_text）だけで内容が伝わるようにする。display_text は補足・視覚的サポート

## ルール
- プランのセクション数・順序・type・感情・wait_secondsを厳守する
- 各セクションの概要（summary）に沿った内容を発話テキストとして展開する
- バイリンガル（日本語と英語を自然に混ぜる）で教える
- has_question=trueのセクションには問いかけ(question)と回答(answer)を含める
- 教材テキストの内容に忠実に
- wait_secondsはプランの値をそのまま使う（セクション終了後の間）

## contentとtts_textの違い（重要・厳守）
- content: 字幕に表示するテキスト。タグやマークアップは絶対に含めない
- tts_text: TTS音声合成に送信するテキスト。contentと同じ内容だが、**日本語以外の言語部分に [lang:xx]...[/lang] タグを付ける**
  - xx = en, es, ko, fr, zh 等の言語コード
  - 例: content="Helloは挨拶だよ" → tts_text="[lang:en]Hello[/lang]は挨拶だよ"
  - 例: content="How are you?って聞かれたら..." → tts_text="[lang:en]How are you?[/lang]って聞かれたら..."
  - 例: content="appleはりんごのことだね" → tts_text="[lang:en]apple[/lang]はりんごのことだね"
  - 日本語のみの場合はタグ不要（contentと同じ内容にする）
  - **英語の単語1つでも必ずタグを付ける**。タグがないと日本語アクセントで読まれてしまう

## 英語発音のルール
- 英語の単語・フレーズ・例文はネイティブ英語の発音で読み上げさせる
- tts_textで英語部分を必ず [lang:en]...[/lang] で囲むことが最重要
- 英語の例文を紹介するときは、contentでも自然な導入をする（「画面に出しますね」等）

## 出力形式（JSON配列）
```json
[
  {{
    "section_type": "introduction",
    "content": "発話テキスト（ちょビが話す内容。タグなし）",
    "tts_text": "TTS用テキスト（英語部分に[lang:en]タグ付き）",
    "display_text": "画面に表示するテキスト（要点・例文など自由形式）",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  }}
]
```

JSON配列のみを出力してください。"""

    # 対話モード: 生徒キャラがいればdialogues指示を追加
    dialogue_mode = False
    if student_config:
        characters = get_lesson_characters()
        teacher_cfg = characters.get("teacher")
        if teacher_cfg:
            dialogue_mode = True
            if en:
                system_prompt = system_prompt.rsplit("## Output format", 1)[0]
            else:
                system_prompt = system_prompt.rsplit("## 出力形式", 1)[0]
            system_prompt += _build_dialogue_prompt(teacher_cfg, student_config, en)
            system_prompt += _build_dialogue_output_example(en)

    parts = _build_image_parts(source_images)
    if en:
        user_text = f"# Lesson title: {lesson_name}\n\n# Source text:\n{extracted_text}"
    else:
        user_text = f"# 授業タイトル: {lesson_name}\n\n# 教材テキスト:\n{extracted_text}"
    parts.append(types.Part(text=user_text))

    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
        if attempt > 0:
            if en:
                _progress(1, 2, f"Retrying plan-based script generation ({attempt + 1}/{max_retries})...")
            else:
                _progress(1, 2, f"プランベーススクリプト再生成中（リトライ {attempt + 1}/{max_retries}）...")
        response = client.models.generate_content(
            model=_get_model(),
            contents=[types.Content(parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )

        _progress(2, 2, "JSONパース・セクション整理中...")

        text = response.text.strip()
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?\s*```$', '', text)

        try:
            sections = json.loads(text)
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning("プランベーススクリプト生成のJSONパース失敗 (attempt=%d, pos=%s)", attempt + 1, e.pos)
            continue

        if not isinstance(sections, list):
            last_error = ValueError("スクリプト生成結果が配列ではありません")
            continue

        break
    else:
        if isinstance(last_error, json.JSONDecodeError):
            raise ValueError(f"スクリプト生成のJSONパースに{max_retries}回失敗しました。再度お試しください。")
        raise ValueError(str(last_error))

    # 必須フィールドの補完 + プランのtitleをマージ
    valid_types = {"introduction", "explanation", "example", "question", "summary"}
    result = []
    for i, s in enumerate(sections):
        plan_title = plan_sections[i].get("title", "") if i < len(plan_sections) else ""
        dialogues_raw = s.get("dialogues", [])

        section = {
            "section_type": s.get("section_type", "explanation"),
            "title": plan_title,
            "content": s.get("content", ""),
            "tts_text": s.get("tts_text", s.get("content", "")),
            "display_text": s.get("display_text", ""),
            "emotion": s.get("emotion", "neutral"),
            "question": s.get("question", ""),
            "answer": s.get("answer", ""),
            "wait_seconds": int(s.get("wait_seconds", 0)),
        }
        if dialogue_mode and dialogues_raw:
            section["dialogues"] = dialogues_raw
            section = _build_section_from_dialogues(section)
        section["dialogues"] = json.dumps(dialogues_raw, ensure_ascii=False) if dialogues_raw else ""
        if section["section_type"] not in valid_types:
            section["section_type"] = "explanation"
        result.append(section)

    return result
