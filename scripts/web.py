"""Web インターフェース（console.py相当）"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from scripts import state
from scripts.routes.avatar import router as avatar_router
from scripts.routes.character import router as character_router
from scripts.routes.obs import router as obs_router
from scripts.routes.overlay import router as overlay_router
from scripts.routes.stream import router as stream_router
from scripts.routes.twitch import router as twitch_router
from src.ai_responder import load_character
from src import scene_config
from src.scene_config import AVATAR_APP

app = FastAPI()

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ルーターを登録
app.include_router(obs_router)
app.include_router(stream_router)
app.include_router(avatar_router)
app.include_router(character_router)
app.include_router(overlay_router)
app.include_router(twitch_router)


# --- 環境設定 ---

ENV_KEYS = [
    ("OBS_WS_HOST", "OBS WebSocket ホスト"),
    ("OBS_WS_PORT", "OBS WebSocket ポート"),
    ("OBS_WS_PASSWORD", "OBS WebSocket パスワード"),
    ("AVATAR_APP", "アバターアプリ (vts/vsf)"),
    ("VTS_HOST", "VTube Studio ホスト"),
    ("VTS_PORT", "VTube Studio ポート"),
    ("VSF_OSC_HOST", "VSeeFace OSC ホスト"),
    ("VSF_OSC_PORT", "VSeeFace OSC ポート"),
    ("TWITCH_TOKEN", "Twitch トークン"),
    ("TWITCH_CLIENT_ID", "Twitch Client ID"),
    ("TWITCH_CHANNEL", "Twitch チャンネル"),
    ("GEMINI_API_KEY", "Gemini API キー"),
    ("TTS_VOICE", "TTS 音声"),
]

MASK_KEYS = {"OBS_WS_PASSWORD", "TWITCH_TOKEN", "GEMINI_API_KEY"}


@app.get("/api/env")
async def get_env():
    result = []
    for key, label in ENV_KEYS:
        value = os.environ.get(key, "")
        if key in MASK_KEYS and value:
            value = "***"
        result.append({"key": key, "label": label, "value": value})
    return result


# --- ページ ---

@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# --- ステータス ---

@app.get("/api/status")
async def get_status():
    return {
        "avatar_app": AVATAR_APP,
        "obs": {
            "connected": state.obs_connected,
            "stream": state.obs.get_stream_status() if state.obs_connected else None,
        },
        "vts": {"connected": state.vts_connected},
        "vsf": {
            "connected": state.vsf_connected,
            "idle": state.vsf.is_idle_running if state.vsf_connected else False,
        },
        "reader": {
            "running": state.reader.is_running,
            "queue": state.reader.queue_size,
        },
    }


# --- セットアップ & 配信開始 ---

@app.post("/api/start")
async def start():
    state.obs.connect()
    state.obs_connected = True
    if AVATAR_APP == "vsf":
        state.vsf.connect()
        state.vsf_connected = True
        state.vsf.apply_default_pose()
        defaults = state.load_vsf_defaults()
        if defaults.get("blendshapes"):
            state.vsf.set_blendshapes(defaults["blendshapes"])
        state.vsf.start_idle(defaults.get("idle_scale", 1.0))
    else:
        await state.vts.connect()
        state.vts_connected = True
    scene_config.reload()
    state.obs.setup_scenes(scene_config.SCENES, scene_config.MAIN_SCENE)
    await state.ensure_reader()
    return {"ok": True}


@app.on_event("startup")
async def startup_seed():
    """起動時にキャラクターをDBにシードする"""
    try:
        load_character()
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
