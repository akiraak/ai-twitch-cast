"""OBS制御ルート"""

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scripts import state
from src import scene_config
from src.scene_config import CONFIG_PATH, PREFIX

logger = logging.getLogger(__name__)
router = APIRouter()


def _ensure_obs():
    """OBS未接続なら自動接続する"""
    if not state.obs_connected:
        logger.info("OBS未接続のため自動接続します")
        state.obs.connect()
        state.obs_connected = True


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
    _ensure_obs()
    return state.obs.get_scenes()


class SceneSwitch(BaseModel):
    name: str


@router.post("/api/obs/scene")
async def obs_scene(body: SceneSwitch):
    _ensure_obs()
    state.obs.set_scene(body.name)
    return {"ok": True}


@router.post("/api/obs/setup")
async def obs_setup():
    _ensure_obs()
    scene_config.reload()
    result = state.obs.setup_scenes(scene_config.SCENES, scene_config.MAIN_SCENE)
    return {"ok": True, **result}


AVATAR_SOURCE_NAME = f"{PREFIX}アバター"


@router.get("/api/obs/avatar/transform")
async def obs_avatar_transform_get():
    _ensure_obs()
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
    _ensure_obs()
    scene = state.obs.get_scenes()["current"]
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    state.obs.set_source_transform(scene, AVATAR_SOURCE_NAME, update)
    return {"ok": True}


@router.post("/api/obs/avatar/save")
async def obs_avatar_save():
    """現在のアバター位置をscenes.jsonの現在シーンに保存する"""
    _ensure_obs()
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
    _ensure_obs()
    scene = state.obs.get_scenes()["current"]
    transform = state.obs.get_source_transform(scene, TERMINAL_SOURCE_NAME)
    return transform


@router.post("/api/obs/terminal/transform")
async def obs_terminal_transform_set(body: AvatarTransform):
    _ensure_obs()
    scene = state.obs.get_scenes()["current"]
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    state.obs.set_source_transform(scene, TERMINAL_SOURCE_NAME, update)
    return {"ok": True}


@router.post("/api/obs/terminal/save")
async def obs_terminal_save():
    """現在のターミナル位置をscenes.jsonの現在シーンに保存する"""
    _ensure_obs()
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


OVERLAY_SOURCE_NAME = f"{PREFIX}オーバーレイ"


@router.post("/api/obs/overlay/refresh")
async def obs_overlay_refresh():
    """ブラウザソース（オーバーレイ）をリフレッシュする"""
    _ensure_obs()
    state.obs.refresh_browser_source(OVERLAY_SOURCE_NAME)
    return {"ok": True}


@router.post("/api/obs/overlay/enable-audio")
async def obs_overlay_enable_audio():
    """ブラウザソースの音声をOBSミキサーに出力し、モニタリングを有効にする"""
    _ensure_obs()
    state.obs.set_input_settings(OVERLAY_SOURCE_NAME, {"reroute_audio": True})
    # 音声モニタリングを「モニターと出力」に設定
    try:
        state.obs._client.set_input_audio_monitor_type(OVERLAY_SOURCE_NAME, "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT")
    except Exception as e:
        logger.warning("モニタリング設定失敗: %s", e)
    return {"ok": True}


@router.get("/api/obs/diag")
async def obs_diag():
    """OBSソースの診断情報を返す"""
    import httpx
    from src.scene_config import _get_server_base_url

    _ensure_obs()

    result = {
        "server_base_url": _get_server_base_url(),
        "obs_connected": state.obs_connected,
        "overlay_source": None,
        "overlay_url_reachable": None,
        "all_sources": [],
        "errors": [],
    }

    try:
        scene = state.obs.get_scenes()["current"]
        items = state.obs.get_scene_items(scene)
        result["current_scene"] = scene
        result["all_sources"] = items
    except Exception as e:
        result["errors"].append(f"シーン取得失敗: {e}")
        return result

    # オーバーレイソースの詳細
    try:
        settings = state.obs._client.get_input_settings(OVERLAY_SOURCE_NAME)
        overlay_url = settings.input_settings.get("url", "")
        result["overlay_source"] = {
            "name": OVERLAY_SOURCE_NAME,
            "url": overlay_url,
            "width": settings.input_settings.get("width"),
            "height": settings.input_settings.get("height"),
            "reroute_audio": settings.input_settings.get("reroute_audio"),
        }
        # モニタリングタイプを取得
        try:
            mon = state.obs._client.get_input_audio_monitor_type(OVERLAY_SOURCE_NAME)
            result["overlay_source"]["monitor_type"] = mon.monitor_type
        except Exception:
            pass
    except Exception as e:
        result["errors"].append(f"オーバーレイソース取得失敗: {e}")

    # URLにアクセスできるか確認（WSL側から）
    if result["overlay_source"] and result["overlay_source"]["url"]:
        test_url = result["overlay_source"]["url"].split("?")[0]  # cache bust除去
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(test_url)
                result["overlay_url_reachable"] = {
                    "url": test_url,
                    "status": resp.status_code,
                    "content_length": len(resp.text),
                    "has_todo_panel": "todo-panel" in resp.text,
                }
        except Exception as e:
            result["overlay_url_reachable"] = {"url": test_url, "error": str(e)}

    return result


@router.post("/api/obs/teardown")
async def obs_teardown():
    _ensure_obs()
    state.obs.teardown_all()
    state.obs.mute_all_audio()
    return {"ok": True}
