"""キャラクター設定ルート"""

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from src import db
from src import scene_config
from src.ai_responder import (
    generate_persona_from_prompt,
    generate_self_note,
    get_character, get_character_id,
    invalidate_character_cache,
)
from src.prompt_builder import SUPPORTED_LANGUAGES, MIX_LEVELS, build_language_rules, build_tts_style, get_stream_language, set_stream_language

router = APIRouter()


@router.get("/api/character")
async def get_character_api():
    char = get_character()
    char_id = get_character_id()
    return {"id": char_id, **char}


class CharacterUpdate(BaseModel):
    name: str
    system_prompt: str
    rules: list[str]
    emotions: dict[str, str]
    emotion_blendshapes: dict[str, dict[str, float]]


@router.put("/api/character")
async def update_character_api(body: CharacterUpdate):
    char_id = get_character_id()
    config = json.dumps(body.model_dump(), ensure_ascii=False)
    db.update_character(char_id, name=body.name, config=config)
    invalidate_character_cache()
    return {"ok": True}


@router.get("/api/character/layers")
async def get_character_layers():
    """プロンプト第2〜4層の現在の状態を返す"""
    char = get_character()
    char_name = char.get("name", "ちょビ")
    char_id = get_character_id()

    # 第2層・第3層: character_memory テーブルから取得
    memory = db.get_character_memory(char_id)
    persona = memory.get("persona", "")
    self_note = memory.get("self_note", "")

    # 第4層: 視聴者メモ（メモがあるユーザーのみ）
    viewer_notes = []
    try:
        conn = db.get_connection()
        rows = conn.execute(
            """SELECT id, name, note, comment_count, last_seen
               FROM users WHERE note != '' AND name != ?
               ORDER BY last_seen DESC NULLS LAST LIMIT 30""",
            (char_name,),
        ).fetchall()
        viewer_notes = [dict(r) for r in rows]
    except Exception:
        pass

    return {
        "persona": persona,
        "self_note": self_note,
        "viewer_notes": viewer_notes,
    }


class MemoryUpdate(BaseModel):
    text: str


@router.put("/api/character/persona")
async def update_persona(body: MemoryUpdate):
    """ペルソナ（第2層）を手動更新する"""
    char_id = get_character_id()
    db.update_character_persona(char_id, body.text)
    return {"ok": True}



class ViewerNoteUpdate(BaseModel):
    user_id: int
    note: str


@router.put("/api/character/viewer-note")
async def update_viewer_note(body: ViewerNoteUpdate):
    """視聴者メモを手動更新する"""
    db.update_user_note(body.user_id, body.note)
    return {"ok": True}


@router.post("/api/character/persona/generate")
async def generate_persona_api():
    """システムプロンプトからペルソナを初期生成する"""
    import asyncio
    persona = await asyncio.to_thread(generate_persona_from_prompt)
    if persona:
        char_id = get_character_id()
        db.update_character_persona(char_id, persona)
    return {"ok": True, "persona": persona}


@router.post("/api/character/self-note/generate")
async def generate_self_note_api():
    """直近の会話からセルフメモを再生成する"""
    import asyncio
    char_id = get_character_id()
    memory = db.get_character_memory(char_id)
    recent = db.get_recent_comments(50, 2)
    current_note = memory.get("self_note", "")
    new_note = await asyncio.to_thread(generate_self_note, recent, current_note)
    if new_note is not None:
        db.update_character_self_note(char_id, new_note)
    return {"ok": True, "self_note": new_note}


@router.get("/api/docs/character-prompt")
async def get_character_prompt_doc():
    """会話生成ドキュメントのMarkdownを返す"""
    doc_path = Path(__file__).resolve().parent.parent.parent / "docs" / "character-prompt.md"
    if not doc_path.exists():
        return PlainTextResponse("ドキュメントが見つかりません", status_code=404)
    return PlainTextResponse(doc_path.read_text(encoding="utf-8"))


@router.get("/api/language")
async def get_language():
    """配信言語設定と選択肢一覧を返す"""
    lang = get_stream_language()
    languages = [{"code": k, "name": v} for k, v in SUPPORTED_LANGUAGES.items()]
    return {
        "primary": lang["primary"],
        "sub": lang["sub"],
        "mix": lang["mix"],
        "languages": languages,
        "mix_levels": list(MIX_LEVELS),
        "text_rules": build_language_rules(),
        "tts_style": build_tts_style(),
    }


@router.post("/api/language")
async def set_language(request: Request):
    """配信言語を変更する"""
    body = await request.json()
    primary = body.get("primary", "")
    sub = body.get("sub", "none")
    mix = body.get("mix", "low")
    try:
        set_stream_language(primary, sub, mix)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    # DBに保存して永続化
    scene_config.save_config_value("stream_lang_primary", primary)
    scene_config.save_config_value("stream_lang_sub", sub)
    scene_config.save_config_value("stream_lang_mix", mix)
    return {"ok": True, "primary": primary, "sub": sub, "mix": mix}
