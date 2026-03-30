"""対話生成: キャラクター取得、プロンプト構築、セリフ個別生成"""

import json
import logging

from google.genai import types

from . import utils

logger = logging.getLogger(__name__)


def get_lesson_characters() -> dict:
    """授業用キャラクター（先生・生徒）を取得する。

    Returns:
        {"teacher": config_dict or None, "student": config_dict or None}
    """
    from src import db
    from src.character_manager import get_channel_id, seed_all_characters

    channel_id = get_channel_id()
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
    adjacent_sections: dict | None = None,
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
        if adjacent_sections:
            idx = adjacent_sections["section_index"]
            total = adjacent_sections["total_sections"]
            user_parts.append(f"# Section position: {idx + 1} / {total}")
            if adjacent_sections.get("prev"):
                p = adjacent_sections["prev"]
                p_text = p["display_text"][:200] if p.get("display_text") else ""
                user_parts.append(f"# Previous section [{p.get('section_type', '')}]: {p.get('title', '')}")
                if p_text:
                    user_parts.append(f"#   Content: {p_text}")
            if adjacent_sections.get("next"):
                n = adjacent_sections["next"]
                n_text = n["display_text"][:200] if n.get("display_text") else ""
                user_parts.append(f"# Next section [{n.get('section_type', '')}]: {n.get('title', '')}")
                if n_text:
                    user_parts.append(f"#   Content: {n_text}")
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
        if adjacent_sections:
            idx = adjacent_sections["section_index"]
            total = adjacent_sections["total_sections"]
            user_parts.append(f"# セクション位置: {idx + 1} / {total}")
            if adjacent_sections.get("prev"):
                p = adjacent_sections["prev"]
                p_text = p["display_text"][:200] if p.get("display_text") else ""
                user_parts.append(f"# 前のセクション [{p.get('section_type', '')}]: {p.get('title', '')}")
                if p_text:
                    user_parts.append(f"#   内容: {p_text}")
            if adjacent_sections.get("next"):
                n = adjacent_sections["next"]
                n_text = n["display_text"][:200] if n.get("display_text") else ""
                user_parts.append(f"# 次のセクション [{n.get('section_type', '')}]: {n.get('title', '')}")
                if n_text:
                    user_parts.append(f"#   内容: {n_text}")
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
    model = utils._get_dialogue_model()
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
            parsed = utils._parse_json_response(raw_output)
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
    adjacent_sections: dict | None = None,
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
            adjacent_sections=adjacent_sections,
        )
        dialogues.append(dlg)
        conversation_history.append({
            "speaker": speaker,
            "content": dlg["content"],
        })

    return dialogues
