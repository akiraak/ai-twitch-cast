"""教師モード — 画像/URL解析 + 授業スクリプト生成"""

import base64
import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
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

    if teacher_row:
        teacher = json.loads(teacher_row["config"])
        teacher["name"] = teacher_row["name"]
        memory = db.get_character_memory(teacher_row["id"])
        teacher["self_note"] = memory.get("self_note", "")
        teacher["persona"] = memory.get("persona", "")
    else:
        teacher = None
    if student_row:
        student = json.loads(student_row["config"])
        student["name"] = student_row["name"]
        memory = db.get_character_memory(student_row["id"])
        student["self_note"] = memory.get("self_note", "")
        student["persona"] = memory.get("persona", "")
    else:
        student = None
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


def _get_knowledge_model():
    """知識先生のモデル"""
    return os.environ.get("GEMINI_KNOWLEDGE_MODEL",
           os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"))


def _get_entertainment_model():
    """エンタメ先生のモデル"""
    return os.environ.get("GEMINI_ENTERTAINMENT_MODEL",
           os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"))


def _get_director_model():
    """監督のモデル（最高推論力）"""
    return os.environ.get("GEMINI_DIRECTOR_MODEL",
           os.environ.get("GEMINI_CHAT_MODEL", "gemini-3.1-pro-preview"))


def _get_dialogue_model():
    """セリフ個別生成のモデル"""
    return os.environ.get("GEMINI_DIALOGUE_MODEL",
           os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"))


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
        dict: {knowledge, entertainment, plan_sections, director_sections, generations}
            plan_sections: [{section_type, title, summary, emotion, has_question}, ...]
            generations: {knowledge: {...}, entertainment: {...}, director: {...}}
                各エントリ: {system_prompt, user_prompt, raw_output, model, temperature}
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
    knowledge_model = _get_knowledge_model()
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
    entertainment_model = _get_entertainment_model()
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
    director_model = _get_director_model()
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
        director_sections = _parse_json_response(raw_director_output)
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

## display_text (very important)
- display_text is the ONLY visual information viewers see on the stream screen
- It must contain **actual content**, NOT just a title or section name
- Good: "Formal: Good morning / Good afternoon\nInformal: Hi / Hey / What's up?"
- Good: "Q: Your friend says 'What's up?' — what do you reply?\nA) Good morning  B) Not much!  C) How do you do?"
- Bad: "Formal Greetings" (too short, just a title)
- Bad: "Matching Your Responses" (meaningless without content)
- Include key vocabulary, example sentences, comparison tables, quiz choices, etc.
- Use line breaks (\n) to organize content clearly

## Output format (JSON array)
```json
[
  {
    "section_type": "introduction",
    "content": "Speech text (what the host says. No tags)",
    "tts_text": "TTS text (with [lang:xx] tags for non-English parts)",
    "display_text": "Today's Topic: English Greetings\n\nFormal vs Informal — when to use which?",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  },
  {
    "section_type": "explanation",
    "content": "Speech explaining formal greetings",
    "tts_text": "TTS text",
    "display_text": "Formal Greetings:\n• Good morning / afternoon / evening\n• How do you do? (first meeting only)\n• It is a pleasure to meet you.",
    "emotion": "neutral",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  },
  {
    "section_type": "question",
    "content": "Speech for posing the question",
    "tts_text": "TTS text",
    "display_text": "Q: You meet your new boss. What do you say?\nA) Hey!  B) What's up?  C) Good morning",
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

## display_text（非常に重要）
- display_textは視聴者が配信画面で見る**唯一の視覚情報**
- **実際の内容**を書くこと。タイトルやセクション名だけはNG
- 良い例: "フォーマル: Good morning / Good afternoon\nカジュアル: Hi / Hey / What's up?"
- 良い例: "Q: 上司に初めて会う場面。何と言う？\nA) Hey!  B) What's up?  C) Good morning"
- 悪い例: "フォーマルな挨拶"（短すぎ、タイトルだけ）
- 悪い例: "挨拶の使い分け"（内容がない）
- キーワード、例文、比較表、クイズの選択肢などを含める
- 改行(\n)で見やすく整理する

## 出力形式（JSON配列）
```json
[
  {
    "section_type": "introduction",
    "content": "発話テキスト（ちょビが話す内容。タグなし）",
    "tts_text": "TTS用テキスト（英語部分に[lang:en]タグ付き）",
    "display_text": "今日のテーマ: 英語の挨拶\n\nフォーマル vs カジュアル — 使い分けを学ぼう！",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  },
  {
    "section_type": "explanation",
    "content": "フォーマルな挨拶の説明",
    "tts_text": "TTS用テキスト",
    "display_text": "フォーマルな挨拶:\n• Good morning / afternoon / evening\n• How do you do?（初対面のみ）\n• It is a pleasure to meet you.",
    "emotion": "neutral",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  },
  {
    "section_type": "question",
    "content": "問題を出す発話テキスト",
    "tts_text": "TTS用テキスト",
    "display_text": "Q: 新しい上司に会う場面。何と言う？\nA) Hey!  B) What's up?  C) Good morning",
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

        try:
            sections = _parse_json_response(response.text)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning("スクリプト生成のJSONパースに失敗 (attempt=%d): %s", attempt + 1, e)
            continue

        if not isinstance(sections, list):
            last_error = ValueError("スクリプト生成結果が配列ではありません")
            logger.warning("スクリプト生成結果が配列ではありません (attempt=%d)", attempt + 1)
            continue

        break
    else:
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

## display_text (very important)
- display_text is the ONLY visual information viewers see on the stream screen
- It must contain **actual content**, NOT just a title or section name
- Good: "Formal: Good morning / Good afternoon\nInformal: Hi / Hey / What's up?"
- Good: "Q: Your friend says 'What's up?' — what do you reply?\nA) Good morning  B) Not much!  C) How do you do?"
- Bad: "Formal Greetings" (too short, just a title)
- Bad: "Matching Your Responses" (meaningless without content)
- Include key vocabulary, example sentences, comparison tables, quiz choices, etc.
- Use line breaks (\\n) to organize content clearly

## Output format (JSON array)
```json
[
  {{
    "section_type": "introduction",
    "content": "Speech text (what the host says. No tags)",
    "tts_text": "TTS text (with [lang:xx] tags for non-English parts)",
    "display_text": "Today's Topic: English Greetings\\n\\nFormal vs Informal — when to use which?",
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

## display_text（非常に重要）
- display_textは視聴者が配信画面で見る**唯一の視覚情報**
- **実際の内容**を書くこと。タイトルやセクション名だけはNG
- 良い例: "フォーマル: Good morning / Good afternoon\nカジュアル: Hi / Hey / What's up?"
- 良い例: "Q: 上司に初めて会う場面。何と言う？\nA) Hey!  B) What's up?  C) Good morning"
- 悪い例: "フォーマルな挨拶"（短すぎ、タイトルだけ）
- 悪い例: "挨拶の使い分け"（内容がない）
- キーワード、例文、比較表、クイズの選択肢などを含める
- 改行(\\n)で見やすく整理する

## 出力形式（JSON配列）
```json
[
  {{
    "section_type": "introduction",
    "content": "発話テキスト（ちょビが話す内容。タグなし）",
    "tts_text": "TTS用テキスト（英語部分に[lang:en]タグ付き）",
    "display_text": "今日のテーマ: 英語の挨拶\\n\\nフォーマル vs カジュアル — 使い分けを学ぼう！",
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

        try:
            sections = _parse_json_response(response.text)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning("プランベーススクリプト生成のJSONパース失敗 (attempt=%d): %s", attempt + 1, e)
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


# --- セリフ個別生成（v2: キャラごとのLLM呼び出し） ---


def _parse_json_response(text: str):
    """LLMレスポンスからJSONをパースする（壊れたJSONは自動修復）"""
    from src.json_utils import parse_llm_json
    return parse_llm_json(text)


def _build_structure_prompt(en: bool, plan_text: str | None = None) -> str:
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

    return base


def _generate_single_dialogue(
    client,
    character_config: dict,
    role: str,
    section_context: dict,
    dialogue_plan_entry: dict,
    conversation_history: list[dict],
    extracted_text: str,
    lesson_name: str,
    en: bool,
) -> dict:
    """1セリフをキャラのペルソナで生成し、generationメタデータ付きで返す"""
    from src.prompt_builder import build_lesson_dialogue_prompt

    system_prompt = build_lesson_dialogue_prompt(
        char=character_config,
        role=role,
        self_note=character_config.get("self_note"),
        persona=character_config.get("persona"),
    )

    direction = dialogue_plan_entry.get("direction", "")
    key_content = dialogue_plan_entry.get("key_content", "")
    section_type = section_context.get("section_type", "explanation")
    display_text = section_context.get("display_text", "")
    question = section_context.get("question", "")
    answer = section_context.get("answer", "")

    if en:
        user_parts = [f"# Lesson: {lesson_name}", f"# Section: {section_type}"]
        if display_text:
            user_parts.append(f"# Screen display (text visible to viewers — read this content aloud):\n{display_text}")
        if question:
            user_parts.append(f"# Question: {question}")
        if answer:
            user_parts.append(f"# Answer: {answer}")
        if key_content:
            user_parts.append(f"# Key content to mention in this turn: {key_content}")
        user_parts.append(f"\n## Your direction for this turn\n{direction}")
        if conversation_history:
            user_parts.append("\n## Conversation so far")
            for h in conversation_history:
                user_parts.append(f"{h['speaker']}: {h['content']}")
        if extracted_text:
            user_parts.append(f"\n## Source material (reference)\n{extracted_text[:2000]}")
    else:
        user_parts = [f"# 授業: {lesson_name}", f"# セクション: {section_type}"]
        if display_text:
            user_parts.append(f"# 画面表示（視聴者に見えるテキスト — この内容を読み上げること）:\n{display_text}")
        if question:
            user_parts.append(f"# 問題: {question}")
        if answer:
            user_parts.append(f"# 回答: {answer}")
        if key_content:
            user_parts.append(f"# このターンで触れるべき内容: {key_content}")
        user_parts.append(f"\n## このターンの演出指示\n{direction}")
        if conversation_history:
            user_parts.append("\n## ここまでの会話")
            for h in conversation_history:
                user_parts.append(f"{h['speaker']}: {h['content']}")
        if extracted_text:
            user_parts.append(f"\n## 教材テキスト（参考）\n{extracted_text[:2000]}")

    user_prompt = "\n".join(user_parts)
    model = _get_dialogue_model()
    temperature = 1.0

    max_retries = 3
    last_error = None
    raw_output = ""
    for attempt in range(max_retries):
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=temperature,
                max_output_tokens=4096,
            ),
        )
        raw_output = response.text.strip()
        try:
            parsed = _parse_json_response(raw_output)
            break
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning("セリフ生成JSONパース失敗 (attempt=%d, raw=%s): %s",
                           attempt + 1, raw_output[:200], e)
            continue
    else:
        raise ValueError(f"セリフ生成のJSONパースに失敗: {last_error}")

    if not isinstance(parsed, dict):
        parsed = {"content": str(parsed), "tts_text": str(parsed), "emotion": "neutral"}

    return {
        "speaker": role,
        "content": parsed.get("content", ""),
        "tts_text": parsed.get("tts_text", parsed.get("content", "")),
        "emotion": parsed.get("emotion", "neutral"),
        "generation": {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "raw_output": raw_output,
            "model": model,
            "temperature": temperature,
        },
    }


def _generate_section_dialogues(
    client,
    teacher_config: dict,
    student_config: dict,
    section: dict,
    extracted_text: str,
    lesson_name: str,
    en: bool,
    on_progress=None,
) -> list[dict]:
    """1セクション分のdialogue_plan/dialogue_directionsを順次処理し、セリフを個別生成する"""
    # v3: dialogue_directions（監督の直接設計）を優先、なければ従来のdialogue_plan
    dialogue_plan = section.get("dialogue_directions") or section.get("dialogue_plan", [])
    if not dialogue_plan:
        return []

    conversation_history = []
    dialogues = []

    for i, plan_entry in enumerate(dialogue_plan):
        speaker = plan_entry.get("speaker", "teacher")
        config = teacher_config if speaker == "teacher" else student_config

        if on_progress:
            on_progress(speaker, i + 1, len(dialogue_plan))

        dlg = _generate_single_dialogue(
            client=client,
            character_config=config,
            role=speaker,
            section_context=section,
            dialogue_plan_entry=plan_entry,
            conversation_history=conversation_history,
            extracted_text=extracted_text,
            lesson_name=lesson_name,
            en=en,
        )
        dialogues.append(dlg)
        conversation_history.append({
            "speaker": speaker,
            "content": dlg["content"],
        })

    return dialogues


def _director_review(
    client,
    sections_with_dialogues: list[dict],
    extracted_text: str,
    lesson_name: str,
    en: bool,
) -> dict:
    """監督が生成済みセリフをレビューし、改善フィードバックを返す（Phase B-3）

    Returns:
        {
            "reviews": [
                {
                    "section_index": 0,
                    "approved": true/false,
                    "feedback": "改善点の具体的な指摘",
                    "revised_directions": [...]  # approved=falseの場合のみ
                },
                ...
            ],
            "overall_feedback": "全体を通してのコメント",
            "generation": { system_prompt, user_prompt, raw_output, model, temperature }
        }
    """
    if en:
        system_prompt = """You are the "Director" reviewing generated dialogue for a Twitch educational stream.
Review the character AI's generated lines and provide feedback.

## Review criteria

### 1. display_text coverage (MOST IMPORTANT)
- Check that the main content in each section's display_text (example sentences, conversation lines, key phrases) is actually read aloud in the dialogue
- If there is "content shown on screen but never spoken", mark as NOT approved
- Check that important items from tables and lists are mentioned in the dialogue

### 2. Naturalness & character consistency
- Do the teacher and student speak in character?
- Are there awkward or unnatural expressions?

### 3. Flow between sections
- Is there context continuity between sections?
- Does information flow naturally?

### 4. Accuracy & coverage
- Are key points from the source material covered?
- Are there factual errors?

## Output format (JSON)
```json
{
  "reviews": [
    {
      "section_index": 0,
      "approved": true,
      "feedback": "Good coverage of display_text content."
    },
    {
      "section_index": 1,
      "approved": false,
      "feedback": "The example sentence 'Good morning' from display_text is not read aloud.",
      "revised_directions": [
        {"speaker": "teacher", "direction": "...", "key_content": "..."},
        {"speaker": "student", "direction": "...", "key_content": "..."}
      ]
    }
  ],
  "overall_feedback": "Overall comment about the lesson quality"
}
```

### Rules for revised_directions
- Only include revised_directions when approved is false
- revised_directions replaces the original dialogue_directions entirely
- Each entry: speaker, direction (2-3 sentence instruction), key_content (specific content to mention)
- Fix the issues identified in feedback
- Keep the same general flow but ensure display_text content is covered

Output ONLY the JSON object."""
    else:
        system_prompt = """あなたは「監督」です。キャラクターAIが生成したセリフを監修し、ダメ出しを行ってください。

## レビュー観点

### 1. display_text カバー率（最重要）
- 各セクションの display_text に含まれるメインコンテンツ（例文・会話文・キーフレーズ）が
  セリフの中で実際に読み上げられているか確認する
- 「画面に表示されているのに読まれていない内容」があれば不合格
- 表・リストの重要項目もセリフ内で言及されているか

### 2. 自然さ・キャラらしさ
- 先生と生徒の口調がそれぞれのキャラクターに合っているか
- 不自然な言い回しやぎこちない表現がないか

### 3. セクション間の繋がり
- 前後のセクションとの文脈が途切れていないか
- 情報の流れが自然か

### 4. 情報の正確性・網羅性
- 教材の重要ポイントが漏れていないか
- 事実関係に誤りがないか

## 出力形式（JSON）
```json
{
  "reviews": [
    {
      "section_index": 0,
      "approved": true,
      "feedback": "display_text の内容が適切にカバーされています。"
    },
    {
      "section_index": 1,
      "approved": false,
      "feedback": "display_text の例文「Good morning」が読み上げられていません。",
      "revised_directions": [
        {"speaker": "teacher", "direction": "...", "key_content": "..."},
        {"speaker": "student", "direction": "...", "key_content": "..."}
      ]
    }
  ],
  "overall_feedback": "全体を通してのコメント"
}
```

### revised_directions のルール
- approved が false の場合のみ含める
- revised_directions は元の dialogue_directions を完全に置き換える
- 各エントリ: speaker, direction（2〜3文の演出指示）, key_content（必ず言及する内容）
- feedback で指摘した問題を修正する内容にする
- 全体の流れは維持しつつ、display_text の内容カバーを確保する

JSONオブジェクトのみを出力してください。"""

    # ユーザープロンプト: セクション一覧（display_text + 生成済みセリフ）
    if en:
        user_parts = [f"# Lesson: {lesson_name}\n"]
    else:
        user_parts = [f"# 授業: {lesson_name}\n"]

    for i, s in enumerate(sections_with_dialogues):
        display_text = s.get("display_text", "")
        dialogues = s.get("dialogues", [])

        if en:
            user_parts.append(f"## Section {i}: {s.get('section_type', '')} — {s.get('title', '')}")
            if display_text:
                user_parts.append(f"### display_text (shown on screen):\n{display_text}")
            user_parts.append("### Generated dialogue:")
        else:
            user_parts.append(f"## セクション {i}: {s.get('section_type', '')} — {s.get('title', '')}")
            if display_text:
                user_parts.append(f"### display_text（画面表示）:\n{display_text}")
            user_parts.append("### 生成されたセリフ:")

        for dlg in dialogues:
            speaker = dlg.get("speaker", "?")
            content = dlg.get("content", "")
            user_parts.append(f"  {speaker}: {content}")
        user_parts.append("")

    if extracted_text:
        if en:
            user_parts.append(f"# Source material (reference)\n{extracted_text[:3000]}")
        else:
            user_parts.append(f"# 教材テキスト（参考）\n{extracted_text[:3000]}")

    user_prompt = "\n".join(user_parts)
    model = _get_director_model()
    temperature = 1.0

    max_retries = 3
    last_error = None
    raw_output = ""
    for attempt in range(max_retries):
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=temperature,
                max_output_tokens=8192,
            ),
        )
        raw_output = response.text.strip()
        try:
            parsed = _parse_json_response(raw_output)
            if not isinstance(parsed, dict) or "reviews" not in parsed:
                raise ValueError("レビュー結果にreviews配列がありません")
            break
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning("監督レビューJSONパース失敗 (attempt=%d): %s", attempt + 1, e)
            continue
    else:
        raise ValueError(f"監督レビューのJSONパースに失敗: {last_error}")

    # 補完
    for r in parsed["reviews"]:
        r.setdefault("section_index", 0)
        r.setdefault("approved", True)
        r.setdefault("feedback", "")
        if not r["approved"]:
            r.setdefault("revised_directions", [])
            for dd in r.get("revised_directions", []):
                dd.setdefault("speaker", "teacher")
                dd.setdefault("direction", "")
                dd.setdefault("key_content", "")
    parsed.setdefault("overall_feedback", "")

    parsed["generation"] = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "raw_output": raw_output,
        "model": model,
        "temperature": temperature,
    }

    approved_count = sum(1 for r in parsed["reviews"] if r["approved"])
    total_count = len(parsed["reviews"])
    logger.info("監督レビュー完了: %d/%dセクション合格 (model=%s)", approved_count, total_count, model)

    return parsed


def generate_lesson_script_v2(
    lesson_name: str,
    extracted_text: str,
    plan_sections: list[dict] | None = None,
    director_sections: list[dict] | None = None,
    source_images: list[str] = None,
    on_progress=None,
    teacher_config: dict = None,
    student_config: dict = None,
) -> list[dict]:
    """セリフをキャラごとに個別LLM呼び出しで生成する（v2）

    Phase 1: セクション構造 + dialogue_plan 生成（1回のLLM呼び出し）
       → director_sections がある場合はスキップ（v3パス）
    Phase 2: 各セリフをキャラのペルソナで個別生成（セクション間並列）
    """
    def _progress(step, total, msg):
        if on_progress:
            on_progress(step, total, msg)

    en = _is_english_mode()
    client = get_client()

    if director_sections:
        # --- v3パス: 監督の設計をそのまま使う（Phase B-1スキップ） ---
        structure_sections = director_sections
        if en:
            _progress(1, None, "Using director's section design (Phase B-1 skipped)")
        else:
            _progress(1, None, "監督のセクション設計を使用（Phase B-1スキップ）")
        logger.info("v3パス: director_sections使用、Phase B-1スキップ（%dセクション）", len(director_sections))
    else:
        # --- v2フォールバック: Phase 1 セクション構造生成 ---
        if en:
            _progress(1, None, "Generating section structure...")
        else:
            _progress(1, None, "セクション構造を生成中...")

        plan_text = None
        if plan_sections:
            if en:
                plan_text = "\n".join(
                    f"{i+1}. [{s.get('section_type', 'explanation')}] {s.get('title', '')} — {s.get('summary', '')} (emotion: {s.get('emotion', 'neutral')}, pause: {s.get('wait_seconds', 2)}s)"
                    + (" *has question" if s.get("has_question") else "")
                    for i, s in enumerate(plan_sections)
                )
            else:
                plan_text = "\n".join(
                    f"{i+1}. [{s.get('section_type', 'explanation')}] {s.get('title', '')} — {s.get('summary', '')} (感情: {s.get('emotion', 'neutral')}, 間: {s.get('wait_seconds', 2)}秒)"
                    + (" ※問いかけあり" if s.get("has_question") else "")
                    for i, s in enumerate(plan_sections)
                )

        structure_prompt = _build_structure_prompt(en, plan_text)

        parts = _build_image_parts(source_images)
        if en:
            user_text = f"# Lesson title: {lesson_name}\n\n# Source text:\n{extracted_text}"
        else:
            user_text = f"# 授業タイトル: {lesson_name}\n\n# 教材テキスト:\n{extracted_text}"
        parts.append(types.Part(text=user_text))

        max_retries = 3
        last_error = None
        structure_sections = None
        for attempt in range(max_retries):
            if attempt > 0:
                if en:
                    _progress(1, None, f"Retrying structure generation ({attempt + 1}/{max_retries})...")
                else:
                    _progress(1, None, f"セクション構造を再生成中（リトライ {attempt + 1}/{max_retries}）...")
            response = client.models.generate_content(
                model=_get_director_model(),
                contents=[types.Content(parts=parts)],
                config=types.GenerateContentConfig(
                    system_instruction=structure_prompt,
                    response_mime_type="application/json",
                    temperature=1.0,
                    max_output_tokens=8192,
                ),
            )
            try:
                structure_sections = _parse_json_response(response.text)
                if not isinstance(structure_sections, list):
                    raise ValueError("セクション構造が配列ではありません")
                break
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                logger.warning("セクション構造のJSONパース失敗 (attempt=%d): %s", attempt + 1, e)
                continue
        else:
            raise ValueError(f"セクション構造の生成に{max_retries}回失敗: {last_error}")

    # dialogue_directions（v3）またはdialogue_plan（v2）のターン数を集計
    total_turns = sum(
        len(s.get("dialogue_directions") or s.get("dialogue_plan", []))
        for s in structure_sections
    )
    logger.info("Phase 1完了: %dセクション, %dターン", len(structure_sections), total_turns)

    if en:
        _progress(1, 1 + total_turns, f"Structure done: {len(structure_sections)} sections, {total_turns} turns")
    else:
        _progress(1, 1 + total_turns, f"構造完了: {len(structure_sections)}セクション, {total_turns}ターン")

    # --- Phase 2: セリフ個別生成（セクション間並列） ---
    step_lock = threading.Lock()
    current_step = [1]

    def section_worker(sec_idx, section):
        dialogue_plan = section.get("dialogue_directions") or section.get("dialogue_plan", [])
        if not dialogue_plan:
            return sec_idx, []

        def dlg_progress(speaker, turn_num, turn_total):
            with step_lock:
                current_step[0] += 1
                step = current_step[0]
            t_name = teacher_config.get("name", "先生") if speaker == "teacher" else student_config.get("name", "生徒")
            if en:
                msg = f"Section {sec_idx + 1}: {t_name} ({turn_num}/{turn_total})"
            else:
                msg = f"セクション{sec_idx + 1}: {t_name} ({turn_num}/{turn_total})"
            _progress(step, 1 + total_turns, msg)

        dialogues = _generate_section_dialogues(
            client=client,
            teacher_config=teacher_config,
            student_config=student_config,
            section=section,
            extracted_text=extracted_text,
            lesson_name=lesson_name,
            en=en,
            on_progress=dlg_progress,
        )
        return sec_idx, dialogues

    section_dialogues = [None] * len(structure_sections)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(section_worker, i, s)
            for i, s in enumerate(structure_sections)
        ]
        for future in futures:
            sec_idx, dialogues = future.result()
            section_dialogues[sec_idx] = dialogues

    # --- Phase B-3: 監督レビュー ---
    if en:
        _progress(1 + total_turns, 1 + total_turns + 1, "Director reviewing dialogue...")
    else:
        _progress(1 + total_turns, 1 + total_turns + 1, "監督がセリフをレビュー中...")

    sections_for_review = []
    for i, s in enumerate(structure_sections):
        sections_for_review.append({
            **s,
            "dialogues": section_dialogues[i] or [],
        })

    review_result = _director_review(
        client, sections_for_review, extracted_text, lesson_name, en,
    )

    # --- Phase B-4: 再生成（不合格セクションのみ、1回のみ） ---
    rejected = [r for r in review_result["reviews"] if not r.get("approved")]
    review_map = {r["section_index"]: r for r in review_result["reviews"]}

    if rejected:
        regen_turns = sum(len(r.get("revised_directions", [])) for r in rejected)
        if en:
            _progress(1 + total_turns, 1 + total_turns + 1 + regen_turns,
                      f"Director feedback: {len(rejected)} section(s) need revision")
        else:
            _progress(1 + total_turns, 1 + total_turns + 1 + regen_turns,
                      f"監督のフィードバック: {len(rejected)}セクションが不合格")

        regen_step = [0]
        regen_step_lock = threading.Lock()

        def regen_worker(r):
            idx = r["section_index"]
            revised = r.get("revised_directions", [])
            if not revised or idx >= len(structure_sections):
                return idx, section_dialogues[idx]

            # dialogue_directions を差し替えて再生成
            section_copy = {**structure_sections[idx], "dialogue_directions": revised}

            def regen_progress(speaker, turn_num, turn_total):
                with regen_step_lock:
                    regen_step[0] += 1
                    step = regen_step[0]
                t_name = teacher_config.get("name", "先生") if speaker == "teacher" else student_config.get("name", "生徒")
                if en:
                    msg = f"Revising section {idx + 1}: {t_name} ({turn_num}/{turn_total})"
                else:
                    msg = f"セクション{idx + 1}を再生成中: {t_name} ({turn_num}/{turn_total})"
                _progress(1 + total_turns + 1 + step, 1 + total_turns + 1 + regen_turns, msg)

            new_dialogues = _generate_section_dialogues(
                client=client,
                teacher_config=teacher_config,
                student_config=student_config,
                section=section_copy,
                extracted_text=extracted_text,
                lesson_name=lesson_name,
                en=en,
                on_progress=regen_progress,
            )
            return idx, new_dialogues

        with ThreadPoolExecutor(max_workers=3) as executor:
            regen_futures = [executor.submit(regen_worker, r) for r in rejected]
            for future in regen_futures:
                idx, new_dialogues = future.result()
                # 再生成フラグを立てる
                if idx in review_map:
                    review_map[idx]["is_regenerated"] = True
                section_dialogues[idx] = new_dialogues

        logger.info("Phase B-4完了: %dセクションを再生成", len(rejected))

    # --- 結果の組み立て ---
    valid_types = {"introduction", "explanation", "example", "question", "summary"}
    result = []
    for i, s in enumerate(structure_sections):
        # v3: director_sectionsにはtitleが含まれる。v2: plan_sectionsから取得
        if director_sections:
            plan_title = s.get("title", "")
        else:
            plan_title = plan_sections[i].get("title", "") if plan_sections and i < len(plan_sections) else ""
        dialogues = section_dialogues[i] or []

        # レビュー結果をdialoguesデータに埋め込む
        review_info = review_map.get(i)
        review_data = None
        if review_info:
            review_data = {
                "approved": review_info.get("approved", True),
                "feedback": review_info.get("feedback", ""),
                "is_regenerated": review_info.get("is_regenerated", False),
            }

        section = {
            "section_type": s.get("section_type", "explanation"),
            "title": plan_title,
            "content": "",
            "tts_text": "",
            "display_text": s.get("display_text", ""),
            "emotion": s.get("emotion", "neutral"),
            "question": s.get("question", ""),
            "answer": s.get("answer", ""),
            "wait_seconds": int(s.get("wait_seconds", 0)),
        }

        if dialogues:
            # dialoguesにreview情報を含めたJSONを構築
            dialogues_with_meta = {
                "dialogues": dialogues,
            }
            if review_data:
                dialogues_with_meta["review"] = review_data
            # 監督レビューのgeneration情報も保存
            if review_result.get("generation"):
                dialogues_with_meta["review_generation"] = review_result["generation"]
                dialogues_with_meta["review_overall_feedback"] = review_result.get("overall_feedback", "")

            section["dialogues"] = dialogues
            section = _build_section_from_dialogues(section)
            section["dialogues"] = json.dumps(dialogues_with_meta, ensure_ascii=False)
        else:
            section["dialogues"] = ""

        if section["section_type"] not in valid_types:
            section["section_type"] = "explanation"
        result.append(section)

    return result
