"""Web インターフェース（console.py相当）"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import db
from src.ai_responder import (
    get_character, get_character_id, invalidate_character_cache,
    load_character, seed_character,
)
from src.comment_reader import CommentReader
from src.obs_controller import OBSController
from src.scene_config import AVATAR_APP, CONFIG_PATH, MAIN_SCENE, PREFIX, SCENES
from src.vsf_controller import VSFController
from src.vts_controller import VTSController

app = FastAPI()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# --- WebSocket オーバーレイ ---
_overlay_clients: set[WebSocket] = set()


async def broadcast_overlay(event: dict):
    """全接続中のオーバーレイクライアントにイベントを送信する"""
    dead = set()
    for ws in _overlay_clients:
        try:
            await ws.send_json(event)
        except Exception:
            dead.add(ws)
    _overlay_clients.difference_update(dead)


@app.websocket("/ws/overlay")
async def overlay_ws(websocket: WebSocket):
    await websocket.accept()
    _overlay_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _overlay_clients.discard(websocket)


# コントローラー（グローバルで共有）
obs = OBSController()
vts = VTSController()
vsf = VSFController()
reader = CommentReader(vsf=vsf, on_overlay=broadcast_overlay)
_obs_connected = False
_vts_connected = False
_vsf_connected = False


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
            "connected": _obs_connected,
            "stream": obs.get_stream_status() if _obs_connected else None,
        },
        "vts": {"connected": _vts_connected},
        "vsf": {
            "connected": _vsf_connected,
            "idle": vsf.is_idle_running if _vsf_connected else False,
        },
        "reader": {
            "running": reader.is_running,
            "queue": reader.queue_size,
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
    obs.setup_scenes(SCENES, MAIN_SCENE)
    return {"ok": True}


AVATAR_SOURCE_NAME = f"{PREFIX}アバター"


@app.get("/api/obs/avatar/transform")
async def obs_avatar_transform_get():
    scene = obs.get_scenes()["current"]
    transform = obs.get_source_transform(scene, AVATAR_SOURCE_NAME)
    return transform


class AvatarTransform(BaseModel):
    positionX: float | None = None
    positionY: float | None = None
    boundsWidth: float | None = None
    boundsHeight: float | None = None


@app.post("/api/obs/avatar/transform")
async def obs_avatar_transform_set(body: AvatarTransform):
    scene = obs.get_scenes()["current"]
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    obs.set_source_transform(scene, AVATAR_SOURCE_NAME, update)
    return {"ok": True}


@app.post("/api/obs/avatar/save")
async def obs_avatar_save():
    """現在のアバター位置をscenes.jsonの現在シーンに保存する"""
    scene = obs.get_scenes()["current"]
    current_base = scene.removeprefix(PREFIX)

    # OBSから現在のtransformを取得
    obs_transform = obs.get_source_transform(scene, AVATAR_SOURCE_NAME)
    save_keys = ["positionX", "positionY", "boundsType", "boundsWidth", "boundsHeight"]
    transform = {k: obs_transform[k] for k in save_keys if k in obs_transform}

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    found = False
    for scene in config["scenes"]:
        if scene["name"] == current_base:
            for src in scene["sources"]:
                if src["kind"] == "avatar":
                    src["transform"] = transform
                    found = True
                    break
            break

    if not found:
        return {"ok": False, "error": f"シーン '{current_base}' にアバターが見つかりません"}

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return {"ok": True}


@app.post("/api/obs/teardown")
async def obs_teardown():
    obs.teardown_scenes(SCENES)
    return {"ok": True}


# --- Stream ---

_current_episode = None


@app.post("/api/stream/start")
async def stream_start():
    obs.start_stream()
    await _ensure_reader()
    return {"ok": True}


@app.post("/api/stream/stop")
async def stream_stop():
    global _current_episode
    await reader.stop()
    if _current_episode:
        db.end_episode(_current_episode["id"])
        _current_episode = None
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


@app.get("/api/vsf/defaults")
async def vsf_defaults_get():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return config.get("vsf_defaults", {"idle_scale": 1.0, "blendshapes": {}})


class VSFDefaults(BaseModel):
    idle_scale: float
    blendshapes: dict[str, float]


@app.post("/api/vsf/defaults/save")
async def vsf_defaults_save(body: VSFDefaults):
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    config["vsf_defaults"] = body.model_dump()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {"ok": True}


# --- Character ---

@app.get("/api/character")
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


@app.put("/api/character")
async def update_character_api(body: CharacterUpdate):
    char_id = get_character_id()
    config = json.dumps(body.model_dump(), ensure_ascii=False)
    db.update_character(char_id, name=body.name, config=config)
    invalidate_character_cache()
    return {"ok": True}


# --- オーバーレイ ---

@app.get("/overlay", response_class=HTMLResponse)
async def overlay_page():
    return (STATIC_DIR / "overlay.html").read_text(encoding="utf-8")


@app.get("/api/overlay/settings")
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


@app.post("/api/overlay/settings")
async def save_overlay_settings(body: OverlaySettings):
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    config["overlay"] = body.model_dump()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")
    # 接続中のオーバーレイに設定更新を通知
    await broadcast_overlay({"type": "settings_update", **body.model_dump()})
    return {"ok": True}


# --- Start / Init ---

def _load_vsf_defaults():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return config.get("vsf_defaults", {"idle_scale": 1.0, "blendshapes": {}})


async def _ensure_reader():
    """Readerが停止していれば起動する"""
    global _current_episode
    if reader.is_running:
        return
    channel_name = os.environ.get("TWITCH_CHANNEL", "default")
    channel = db.get_or_create_channel(channel_name)
    seed_character(channel["id"])
    character_id = get_character_id()
    show = db.get_or_create_show(channel["id"], "デフォルト")
    if not _current_episode:
        _current_episode = db.start_episode(show["id"], character_id)
    reader.set_episode(_current_episode["id"])
    await reader.start()


@app.post("/api/start")
async def start():
    global _obs_connected, _vts_connected, _vsf_connected
    obs.connect()
    _obs_connected = True
    if AVATAR_APP == "vsf":
        vsf.connect()
        _vsf_connected = True
        vsf.apply_default_pose()
        # 保存されたデフォルト値を適用
        defaults = _load_vsf_defaults()
        if defaults.get("blendshapes"):
            vsf.set_blendshapes(defaults["blendshapes"])
        vsf.start_idle(defaults.get("idle_scale", 1.0))
    else:
        await vts.connect()
        _vts_connected = True
    obs.setup_scenes(SCENES, MAIN_SCENE)
    await _ensure_reader()
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
