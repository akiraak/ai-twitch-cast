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
    get_character, get_character_id,
    invalidate_character_cache,
)
from src.prompt_builder import LANGUAGE_MODES, get_language_mode, set_language_mode

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
            """SELECT name, note, comment_count, last_seen
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


@router.get("/api/docs/character-prompt")
async def get_character_prompt_doc():
    """会話生成ドキュメントのMarkdownを返す"""
    doc_path = Path(__file__).resolve().parent.parent.parent / "docs" / "character-prompt.md"
    if not doc_path.exists():
        return PlainTextResponse("ドキュメントが見つかりません", status_code=404)
    return PlainTextResponse(doc_path.read_text(encoding="utf-8"))


@router.get("/api/language")
async def get_language():
    """利用可能な言語モードと現在の設定を返す"""
    current = get_language_mode()
    modes = []
    for key, mode in LANGUAGE_MODES.items():
        modes.append({
            "key": key,
            "name": mode["name"],
            "description": mode["description"],
            "rules": mode["rules"],
            "active": key == current,
        })
    return {"current": current, "modes": modes}


@router.post("/api/language")
async def set_language(request: Request):
    """言語モードを変更する"""
    body = await request.json()
    mode = body.get("mode", "")
    if mode not in LANGUAGE_MODES:
        return {"ok": False, "error": f"不明なモード: {mode}"}
    set_language_mode(mode)
    # DBに保存して永続化
    scene_config.save_config_value("language_mode", mode)
    return {"ok": True, "mode": mode}
