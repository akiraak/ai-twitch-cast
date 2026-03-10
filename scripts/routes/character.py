"""キャラクター設定ルート"""

import json

from fastapi import APIRouter
from fastapi import Request
from pydantic import BaseModel

from src import db
from src import scene_config
from src.ai_responder import (
    LANGUAGE_MODES,
    get_character, get_character_id, get_language_mode,
    invalidate_character_cache, set_language_mode,
)

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
    # scenes.jsonに保存して永続化
    try:
        config = {}
        try:
            with open(scene_config.CONFIG_PATH, encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass
        config["language_mode"] = mode
        with open(scene_config.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return {"ok": True, "mode": mode}
