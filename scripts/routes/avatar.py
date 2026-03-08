"""アバター制御ルート（VTS + VSF）"""

import json

from fastapi import APIRouter
from pydantic import BaseModel

from scripts import state
from src.scene_config import CONFIG_PATH

router = APIRouter()


# --- VTS ---

@router.post("/api/vts/connect")
async def vts_connect():
    await state.vts.connect()
    state.vts_connected = True
    return {"ok": True}


@router.post("/api/vts/disconnect")
async def vts_disconnect():
    await state.vts.disconnect()
    state.vts_connected = False
    return {"ok": True}


@router.get("/api/vts/model")
async def vts_model():
    return await state.vts.get_model_info()


@router.get("/api/vts/params")
async def vts_params():
    return {"params": await state.vts.get_parameters()}


class ParamSet(BaseModel):
    name: str
    value: float


@router.post("/api/vts/param")
async def vts_param(body: ParamSet):
    await state.vts.set_parameter(body.name, body.value)
    return {"ok": True}


@router.get("/api/vts/hotkeys")
async def vts_hotkeys():
    return {"hotkeys": await state.vts.get_hotkeys()}


class HotkeyTrigger(BaseModel):
    id: str


@router.post("/api/vts/hotkey")
async def vts_hotkey(body: HotkeyTrigger):
    await state.vts.trigger_hotkey(body.id)
    return {"ok": True}


# --- VSF ---

@router.post("/api/vsf/connect")
async def vsf_connect():
    state.vsf.connect()
    state.vsf_connected = True
    state.vsf.apply_default_pose()
    return {"ok": True}


@router.post("/api/vsf/disconnect")
async def vsf_disconnect():
    state.vsf.stop_idle()
    state.vsf.disconnect()
    state.vsf_connected = False
    return {"ok": True}


@router.post("/api/vsf/pose")
async def vsf_pose():
    state.vsf.apply_default_pose()
    return {"ok": True}


class IdleParams(BaseModel):
    scale: float = 1.0


@router.post("/api/vsf/idle")
async def vsf_idle(body: IdleParams):
    state.vsf.start_idle(body.scale)
    return {"ok": True}


@router.post("/api/vsf/stop")
async def vsf_stop():
    state.vsf.stop_idle()
    state.vsf.apply_default_pose()
    return {"ok": True}


class BlendShape(BaseModel):
    name: str
    value: float


@router.post("/api/vsf/blend")
async def vsf_blend(body: BlendShape):
    state.vsf.set_blendshape(body.name, body.value)
    return {"ok": True}


@router.get("/api/vsf/defaults")
async def vsf_defaults_get():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return config.get("vsf_defaults", {"idle_scale": 1.0, "blendshapes": {}})


class VSFDefaults(BaseModel):
    idle_scale: float
    blendshapes: dict[str, float]


@router.post("/api/vsf/defaults/save")
async def vsf_defaults_save(body: VSFDefaults):
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    config["vsf_defaults"] = body.model_dump()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {"ok": True}
