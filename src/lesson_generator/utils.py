"""共通ヘルパー: モデル選択、JSONパース、画像/コンテンツ整形"""

import json
import logging
import os
import re
from pathlib import Path

from google.genai import types

from src.gemini_client import get_client
from src.prompt_builder import get_stream_language

logger = logging.getLogger(__name__)


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


def _parse_json_response(text: str):
    """LLMレスポンスからJSONをパースする（壊れたJSONは自動修復）"""
    from src.json_utils import parse_llm_json
    return parse_llm_json(text)


def _guess_mime(ext: str) -> str:
    ext = ext.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")


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


def get_lesson_characters() -> dict:
    """授業用キャラクター（先生・生徒）を取得する。

    Returns:
        {"teacher": config_dict or None, "student": config_dict or None}
    """
    import json as _json
    from src import db
    from src.character_manager import get_channel_id, seed_all_characters

    channel_id = get_channel_id()
    seed_all_characters(channel_id)

    teacher_row = db.get_character_by_role(channel_id, "teacher")
    student_row = db.get_character_by_role(channel_id, "student")

    if teacher_row:
        teacher = _json.loads(teacher_row["config"])
        teacher["name"] = teacher_row["name"]
        memory = db.get_character_memory(teacher_row["id"])
        teacher["self_note"] = memory.get("self_note", "")
        teacher["persona"] = memory.get("persona", "")
    else:
        teacher = None
    if student_row:
        student = _json.loads(student_row["config"])
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


def _format_main_content_for_prompt(main_content: list[dict], en: bool) -> str:
    """main_content リストをプロンプト用テキストに整形する（role対応）"""
    if not main_content:
        return ""
    lines = []
    for i, mc in enumerate(main_content, 1):
        ct = mc.get("content_type", "passage")
        label = mc.get("label", "")
        content = mc.get("content", "")
        role = mc.get("role", "main" if i == 1 else "sub")
        read_aloud = mc.get("read_aloud", False)
        if role == "main":
            role_tag = "★ PRIMARY" if en else "★ 主要"
        else:
            role_tag = "supplementary" if en else "補助"
        # read_aloud かつ main → 🔊マーカー付き・全文（上限2000文字）
        if read_aloud and role == "main":
            aloud_tag = "🔊 READ ALOUD" if en else "🔊 読み上げ対象"
            lines.append(f"{i}. [{ct}] ({role_tag}) ({aloud_tag}) \"{label}\"")
            preview = content[:2000] + ("..." if len(content) > 2000 else "")
        else:
            lines.append(f"{i}. [{ct}] ({role_tag}) \"{label}\"")
            # コンテンツは先頭200文字まで（プロンプト肥大化防止）
            preview = content[:200] + ("..." if len(content) > 200 else "")
        for line in preview.split("\n"):
            lines.append(f"   {line}")
        lines.append("")
    return "\n".join(lines)
