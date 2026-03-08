"""Twitch配信情報ルート"""

from fastapi import APIRouter
from pydantic import BaseModel

from scripts import state

router = APIRouter()


@router.get("/api/twitch/channel")
async def get_channel_info():
    return await state.twitch_api.get_channel_info()


class ChannelUpdate(BaseModel):
    title: str | None = None
    game_id: str | None = None
    tags: list[str] | None = None


@router.post("/api/twitch/channel")
async def update_channel_info(body: ChannelUpdate):
    await state.twitch_api.update_channel_info(
        title=body.title,
        game_id=body.game_id,
        tags=body.tags,
    )
    return {"ok": True}


class CategorySearch(BaseModel):
    query: str


@router.post("/api/twitch/categories/search")
async def search_categories(body: CategorySearch):
    results = await state.twitch_api.search_categories(body.query)
    return {"categories": results}
