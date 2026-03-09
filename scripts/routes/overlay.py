"""オーバーレイルート（WebSocket + 設定 + TODO表示）"""

import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from scripts import state
from src.scene_config import CONFIG_PATH

router = APIRouter()
logger = logging.getLogger(__name__)

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
        "todo": {"width": 460, "fontSize": 15, "titleFontSize": 18},
    })


@router.get("/api/todo")
async def get_todo():
    """TODO.mdから未完了タスクを返す"""
    if not TODO_PATH.exists():
        return {"items": []}
    text = TODO_PATH.read_text(encoding="utf-8")
    items = []
    for line in text.splitlines():
        m = re.match(r"\s*-\s*\[\s*\]\s*(.*)", line)
        if m:
            items.append(m.group(1).strip())
    return {"items": items}


@router.post("/api/overlay/preview")
async def preview_overlay_settings(request: Request):
    """設定をファイルに保存せずオーバーレイにリアルタイム反映する"""
    body = await request.json()
    await state.broadcast_overlay({"type": "settings_update", **body})
    return {"ok": True}


@router.post("/api/overlay/settings")
async def save_overlay_settings(request: Request):
    body = await request.json()
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    config["overlay"] = body
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")
    await state.broadcast_overlay({"type": "settings_update", **body})
    return {"ok": True}
