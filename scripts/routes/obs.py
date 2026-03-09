"""OBS制御ルート"""

import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from scripts import state
from src import scene_config
from src.scene_config import CONFIG_PATH, PREFIX

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/obs/connect")
async def obs_connect():
    state.obs.connect()
    state.obs_connected = True
    return {"ok": True}


@router.post("/api/obs/disconnect")
async def obs_disconnect():
    state.obs.disconnect()
    state.obs_connected = False
    return {"ok": True}


@router.get("/api/obs/scenes")
async def obs_scenes():
    return state.obs.get_scenes()


class SceneSwitch(BaseModel):
    name: str


@router.post("/api/obs/scene")
async def obs_scene(body: SceneSwitch):
    state.obs.set_scene(body.name)
    return {"ok": True}


@router.post("/api/obs/setup")
async def obs_setup():
    scene_config.reload()
    # ターミナルのtransformをログ出力して確認
    for sc in scene_config.SCENES:
        for src in sc["sources"]:
            if src.get("name") == TERMINAL_SOURCE_NAME:
                logger.info("Setup: ターミナルtransform=%s", src.get("transform"))
    state.obs.setup_scenes(scene_config.SCENES, scene_config.MAIN_SCENE)
    return {"ok": True}


AVATAR_SOURCE_NAME = f"{PREFIX}アバター"


@router.get("/api/obs/avatar/transform")
async def obs_avatar_transform_get():
    scene = state.obs.get_scenes()["current"]
    transform = state.obs.get_source_transform(scene, AVATAR_SOURCE_NAME)
    return transform


class AvatarTransform(BaseModel):
    positionX: float | None = None
    positionY: float | None = None
    boundsWidth: float | None = None
    boundsHeight: float | None = None


@router.post("/api/obs/avatar/transform")
async def obs_avatar_transform_set(body: AvatarTransform):
    scene = state.obs.get_scenes()["current"]
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    state.obs.set_source_transform(scene, AVATAR_SOURCE_NAME, update)
    return {"ok": True}


@router.post("/api/obs/avatar/save")
async def obs_avatar_save():
    """現在のアバター位置をscenes.jsonの現在シーンに保存する"""
    scene = state.obs.get_scenes()["current"]
    current_base = scene.removeprefix(PREFIX)

    obs_transform = state.obs.get_source_transform(scene, AVATAR_SOURCE_NAME)
    save_keys = ["positionX", "positionY", "boundsType", "boundsWidth", "boundsHeight"]
    transform = {k: obs_transform[k] for k in save_keys if k in obs_transform}

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    found = False
    for sc in config["scenes"]:
        if sc["name"] == current_base:
            for src in sc["sources"]:
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


TERMINAL_SOURCE_NAME = f"{PREFIX}ターミナル"


@router.get("/api/obs/terminal/transform")
async def obs_terminal_transform_get():
    scene = state.obs.get_scenes()["current"]
    transform = state.obs.get_source_transform(scene, TERMINAL_SOURCE_NAME)
    return transform


@router.post("/api/obs/terminal/transform")
async def obs_terminal_transform_set(body: AvatarTransform):
    scene = state.obs.get_scenes()["current"]
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    state.obs.set_source_transform(scene, TERMINAL_SOURCE_NAME, update)
    return {"ok": True}


@router.post("/api/obs/terminal/save")
async def obs_terminal_save():
    """現在のターミナル位置をscenes.jsonの現在シーンに保存する"""
    scene = state.obs.get_scenes()["current"]
    current_base = scene.removeprefix(PREFIX)
    logger.info("ターミナル保存: シーン='%s', base='%s'", scene, current_base)

    obs_transform = state.obs.get_source_transform(scene, TERMINAL_SOURCE_NAME)
    save_keys = ["positionX", "positionY", "boundsType", "boundsWidth", "boundsHeight"]
    transform = {k: obs_transform[k] for k in save_keys if k in obs_transform}
    logger.info("ターミナル保存: transform=%s", transform)

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    found = False
    for sc in config["scenes"]:
        if sc["name"] == current_base:
            for src in sc["sources"]:
                if src.get("kind") == "window_capture" and src.get("name") == "ターミナル":
                    src["transform"] = transform
                    found = True
                    break
            break

    if not found:
        logger.warning("ターミナル保存: シーン '%s' にターミナルが見つかりません", current_base)
        return {"ok": False, "error": f"シーン '{current_base}' にターミナルが見つかりません"}

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")

    logger.info("ターミナル保存: scenes.jsonに書き込み完了")
    return {"ok": True}


@router.post("/api/obs/teardown")
async def obs_teardown():
    state.obs.teardown_scenes(scene_config.SCENES)
    state.obs.mute_all_audio()
    return {"ok": True}
