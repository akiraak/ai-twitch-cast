"""オーバーレイルート（WebSocket + 設定）"""

import json
import logging
import math
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from scripts import state
from src.scene_config import CONFIG_PATH, PREFIX

router = APIRouter()
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_DIR / "static"
TODO_PATH = PROJECT_DIR / "TODO.md"
BGM_SOURCE_NAME = f"{PREFIX}BGM"


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


BGM_DIR = PROJECT_DIR / "resources" / "audio" / "bgm"


def _linear_to_db(volume: float) -> float:
    """0.0〜1.0のリニア音量をdBに変換する"""
    if volume <= 0:
        return -100.0
    return 20 * math.log10(volume)


@router.get("/api/bgm/list")
async def bgm_list():
    """BGMファイル一覧を返す"""
    files = sorted(p.stem for p in BGM_DIR.glob("*.mp3")) if BGM_DIR.exists() else []
    return {"tracks": files}


class BGMControl(BaseModel):
    action: str  # play, stop, volume
    track: str | None = None
    volume: float | None = None


@router.post("/api/bgm")
async def bgm_control(body: BGMControl):
    """BGM再生制御（OBSメディアソース経由）"""
    if not state.obs_connected:
        return {"ok": False, "error": "OBS未接続"}

    try:
        if body.action == "play" and body.track:
            file_path = BGM_DIR / f"{body.track}.mp3"
            if not file_path.exists():
                return {"ok": False, "error": "ファイルが見つかりません"}
            if body.volume is not None:
                state.obs.set_media_volume(BGM_SOURCE_NAME, _linear_to_db(body.volume))
            state.obs.play_media(BGM_SOURCE_NAME, file_path)
            logger.info("BGM再生: %s", body.track)
        elif body.action == "stop":
            state.obs.stop_media(BGM_SOURCE_NAME)
            logger.info("BGM停止")
        elif body.action == "volume" and body.volume is not None:
            state.obs.set_media_volume(BGM_SOURCE_NAME, _linear_to_db(body.volume))
        return {"ok": True}
    except Exception as e:
        logger.warning("BGM制御エラー: %s", e)
        return {"ok": False, "error": str(e)}


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
