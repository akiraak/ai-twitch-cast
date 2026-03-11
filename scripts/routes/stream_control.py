"""配信制御ルート（OBS不要版） - StreamController管理"""

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scripts import state
from src import db
from src.scene_config import CONFIG_PATH

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/broadcast/setup")
async def broadcast_setup():
    """xvfb + Chromium + PulseAudio を起動"""
    try:
        await state.stream.setup()
        return {"ok": True}
    except Exception as e:
        logger.error("セットアップ失敗: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/broadcast/teardown")
async def broadcast_teardown():
    """全プロセスを停止"""
    try:
        await state.stream.teardown()
        return {"ok": True}
    except Exception as e:
        logger.error("ティアダウン失敗: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/broadcast/start")
async def broadcast_start():
    """FFmpeg RTMP配信を開始"""
    try:
        await state.stream.start_stream()
        await state.ensure_reader()
        await state.git_watcher.start()
        return {"ok": True}
    except Exception as e:
        logger.error("配信開始失敗: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/broadcast/stop")
async def broadcast_stop():
    """FFmpeg RTMP配信を停止"""
    from src import db

    await state.git_watcher.stop()
    if state.reader.is_running:
        await state.reader.stop()
    if state.current_episode:
        db.end_episode(state.current_episode["id"])
        state.current_episode = None
    await state.stream.stop_stream()
    return {"ok": True}


class SceneRequest(BaseModel):
    name: str


@router.post("/api/broadcast/scene")
async def broadcast_scene(body: SceneRequest):
    """シーンを切り替える"""
    valid_scenes = ["main", "start", "end"]
    if body.name not in valid_scenes:
        raise HTTPException(status_code=400, detail=f"不明なシーン: {body.name} (有効: {valid_scenes})")
    await state.stream.set_scene(body.name)
    return {"ok": True, "scene": body.name}


@router.get("/api/broadcast/scenes")
async def broadcast_scenes():
    """利用可能なシーン一覧を返す"""
    return {
        "scenes": [
            {"name": "main", "label": "メイン"},
            {"name": "start", "label": "開始画面"},
            {"name": "end", "label": "終了画面"},
        ],
    }


class VolumeRequest(BaseModel):
    source: str
    volume: float


def _get_default_volumes():
    """scenes.jsonからデフォルト音量を読み込む"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        return config.get("audio_volumes", {})
    except Exception:
        return {}


def _get_volume(source):
    """DBから音量を取得（なければscenes.jsonのデフォルト値）"""
    val = db.get_setting(f"volume.{source}")
    if val is not None:
        return float(val)
    defaults = _get_default_volumes()
    return defaults.get(source, {"master": 0.8, "tts": 0.8, "bgm": 1.0}.get(source, 1.0))


@router.get("/api/broadcast/volume")
async def broadcast_get_volumes():
    """音量設定を取得"""
    return {
        "master": _get_volume("master"),
        "tts": _get_volume("tts"),
        "bgm": _get_volume("bgm"),
    }


@router.post("/api/broadcast/volume")
async def broadcast_set_volume(body: VolumeRequest):
    """音量を設定してDBに保存し、broadcast.htmlに反映する"""
    if body.source not in ("master", "tts", "bgm"):
        raise HTTPException(status_code=400, detail=f"不明なソース: {body.source}")

    db.set_setting(f"volume.{body.source}", body.volume)

    await state.stream.set_volume(body.source, body.volume)

    return {"ok": True}


# --- アバターキャプチャ ---

class AvatarStreamRequest(BaseModel):
    url: str


def _load_avatar_capture_url():
    """scenes.jsonからavatar_capture_urlを読み込む"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        return config.get("avatar_capture_url", "")
    except Exception:
        return ""


def _save_avatar_capture_url(url: str):
    """avatar_capture_urlをscenes.jsonに保存する"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    config["avatar_capture_url"] = url
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


@router.get("/api/broadcast/avatar")
async def broadcast_get_avatar():
    """アバターキャプチャURLを取得"""
    url = _load_avatar_capture_url()
    return {"url": url}


@router.post("/api/broadcast/avatar")
async def broadcast_set_avatar(body: AvatarStreamRequest):
    """アバターキャプチャURLを設定し、broadcast.htmlに送信"""
    _save_avatar_capture_url(body.url)
    await state.broadcast_to_broadcast({
        "type": "avatar_stream",
        "url": body.url,
    })
    logger.info("アバターストリーム設定: %s", body.url)
    return {"ok": True}


@router.post("/api/broadcast/avatar/stop")
async def broadcast_stop_avatar():
    """アバターストリームを停止"""
    _save_avatar_capture_url("")
    await state.broadcast_to_broadcast({"type": "avatar_stop"})
    logger.info("アバターストリーム停止")
    return {"ok": True}


@router.get("/api/broadcast/status")
async def broadcast_status():
    """配信状態を返す"""
    return state.stream.get_stream_status()


@router.get("/api/broadcast/diag")
async def broadcast_diag():
    """プロセスヘルスチェック"""
    status = state.stream.get_stream_status()
    errors = []

    if status["setup"] and not status["xvfb_running"]:
        errors.append("Xvfbが停止しています")
    if status["setup"] and not status["browser_running"]:
        errors.append("Chromiumが停止しています")
    if status["streaming"] and not status["ffmpeg_running"]:
        errors.append("FFmpegが停止しています")

    return {
        **status,
        "errors": errors,
        "healthy": len(errors) == 0,
    }
