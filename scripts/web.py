"""Web インターフェース（console.py相当）"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.obs_controller import OBSController
from src.scene_config import AVATAR_APP, SCENES
from src.vsf_controller import VSFController
from src.vts_controller import VTSController

app = FastAPI()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# コントローラー（グローバルで共有）
obs = OBSController()
vts = VTSController()
vsf = VSFController()
_obs_connected = False
_vts_connected = False
_vsf_connected = False


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
            "connected": _obs_connected,
            "stream": obs.get_stream_status() if _obs_connected else None,
        },
        "vts": {"connected": _vts_connected},
        "vsf": {
            "connected": _vsf_connected,
            "idle": vsf.is_idle_running if _vsf_connected else False,
        },
    }


# --- OBS ---

@app.post("/api/obs/connect")
async def obs_connect():
    global _obs_connected
    obs.connect()
    _obs_connected = True
    return {"ok": True}


@app.post("/api/obs/disconnect")
async def obs_disconnect():
    global _obs_connected
    obs.disconnect()
    _obs_connected = False
    return {"ok": True}


@app.get("/api/obs/scenes")
async def obs_scenes():
    scenes = obs._client.get_scene_list()
    return {
        "current": scenes.current_program_scene_name,
        "scenes": [s["sceneName"] for s in scenes.scenes],
    }


class SceneSwitch(BaseModel):
    name: str


@app.post("/api/obs/scene")
async def obs_scene(body: SceneSwitch):
    obs._client.set_current_program_scene(body.name)
    return {"ok": True}


@app.post("/api/obs/setup")
async def obs_setup():
    obs.setup_scenes(SCENES)
    return {"ok": True}


@app.post("/api/obs/teardown")
async def obs_teardown():
    obs.teardown_scenes(SCENES)
    return {"ok": True}


# --- Stream ---

@app.post("/api/stream/start")
async def stream_start():
    obs.start_stream()
    return {"ok": True}


@app.post("/api/stream/stop")
async def stream_stop():
    obs.stop_stream()
    return {"ok": True}


# --- VTS ---

@app.post("/api/vts/connect")
async def vts_connect():
    global _vts_connected
    await vts.connect()
    _vts_connected = True
    return {"ok": True}


@app.post("/api/vts/disconnect")
async def vts_disconnect():
    global _vts_connected
    await vts.disconnect()
    _vts_connected = False
    return {"ok": True}


@app.get("/api/vts/model")
async def vts_model():
    return await vts.get_model_info()


@app.get("/api/vts/params")
async def vts_params():
    return {"params": await vts.get_parameters()}


class ParamSet(BaseModel):
    name: str
    value: float


@app.post("/api/vts/param")
async def vts_param(body: ParamSet):
    await vts.set_parameter(body.name, body.value)
    return {"ok": True}


@app.get("/api/vts/hotkeys")
async def vts_hotkeys():
    return {"hotkeys": await vts.get_hotkeys()}


class HotkeyTrigger(BaseModel):
    id: str


@app.post("/api/vts/hotkey")
async def vts_hotkey(body: HotkeyTrigger):
    await vts.trigger_hotkey(body.id)
    return {"ok": True}


# --- VSF ---

@app.post("/api/vsf/connect")
async def vsf_connect():
    global _vsf_connected
    vsf.connect()
    _vsf_connected = True
    vsf.apply_default_pose()
    return {"ok": True}


@app.post("/api/vsf/disconnect")
async def vsf_disconnect():
    global _vsf_connected
    vsf.stop_idle()
    vsf.disconnect()
    _vsf_connected = False
    return {"ok": True}


@app.post("/api/vsf/pose")
async def vsf_pose():
    vsf.apply_default_pose()
    return {"ok": True}


class IdleParams(BaseModel):
    scale: float = 1.0


@app.post("/api/vsf/idle")
async def vsf_idle(body: IdleParams):
    vsf.start_idle(body.scale)
    return {"ok": True}


@app.post("/api/vsf/stop")
async def vsf_stop():
    vsf.stop_idle()
    vsf.apply_default_pose()
    return {"ok": True}


class BlendShape(BaseModel):
    name: str
    value: float


@app.post("/api/vsf/blend")
async def vsf_blend(body: BlendShape):
    vsf.set_blendshape(body.name, body.value)
    return {"ok": True}


# --- Init ---

@app.post("/api/init")
async def init():
    global _obs_connected, _vts_connected, _vsf_connected
    obs.connect()
    _obs_connected = True
    if AVATAR_APP == "vsf":
        vsf.connect()
        _vsf_connected = True
        vsf.apply_default_pose()
    else:
        await vts.connect()
        _vts_connected = True
    obs.setup_scenes(SCENES)
    obs.set_scene(SCENES[0]["name"])
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
