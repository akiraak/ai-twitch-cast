"""オーバーレイルート（WebSocket + 設定）"""

import json
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from scripts import state
from src.scene_config import CONFIG_PATH

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


@router.websocket("/ws/overlay")
async def overlay_ws(websocket: WebSocket):
    await websocket.accept()
    state.overlay_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.overlay_clients.discard(websocket)


@router.get("/overlay", response_class=HTMLResponse)
async def overlay_page():
    return (STATIC_DIR / "overlay.html").read_text(encoding="utf-8")


@router.get("/api/overlay/settings")
async def get_overlay_settings():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return config.get("overlay", {
        "subtitle": {"bottom": 80, "fontSize": 28, "fadeDuration": 3},
        "history": {"top": 30, "right": 30, "fontSize": 18, "maxItems": 5},
    })


class OverlaySettings(BaseModel):
    subtitle: dict
    history: dict


@router.post("/api/overlay/settings")
async def save_overlay_settings(body: OverlaySettings):
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    config["overlay"] = body.model_dump()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")
    await state.broadcast_overlay({"type": "settings_update", **body.model_dump()})
    return {"ok": True}
