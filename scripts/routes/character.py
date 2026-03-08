"""キャラクター設定ルート"""

import json

from fastapi import APIRouter
from pydantic import BaseModel

from src import db
from src.ai_responder import (
    get_character, get_character_id, invalidate_character_cache,
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
