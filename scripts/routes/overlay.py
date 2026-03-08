"""オーバーレイルート（WebSocket + 設定）"""

import json
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from scripts import state
from src.scene_config import CONFIG_PATH

router = APIRouter()

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_DIR / "static"
TODO_PATH = PROJECT_DIR / "TODO.md"


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


@router.get("/api/todo")
async def get_todo():
    """TODO.mdの内容を返す"""
    if TODO_PATH.exists():
        return {"content": TODO_PATH.read_text(encoding="utf-8")}
    return {"content": ""}


@router.post("/api/overlay/todo/toggle")
async def toggle_todo():
    """オーバーレイのTODO表示をトグルする"""
    await state.broadcast_overlay({"type": "todo_toggle"})
    return {"ok": True}


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
