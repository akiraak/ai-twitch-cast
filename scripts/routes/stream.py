"""配信制御ルート"""

import asyncio

from fastapi import APIRouter

from scripts import state
from src import db

router = APIRouter()


@router.post("/api/stream/start")
async def stream_start():
    state.obs.start_stream()
    await state.ensure_reader()
    await state.git_watcher.start()
    asyncio.ensure_future(state.reader.speak_event("配信開始", "配信が始まりました！視聴者に挨拶してください"))
    return {"ok": True}


@router.post("/api/stream/stop")
async def stream_stop():
    await state.git_watcher.stop()
    await state.reader.stop()
    if state.current_episode:
        db.end_episode(state.current_episode["id"])
        state.current_episode = None
    state.obs.stop_stream()
    return {"ok": True}
