"""トピック管理ルート"""

import os

from fastapi import APIRouter

from scripts import state
from src import db

router = APIRouter()


async def _notify_overlay():
    """トピック状態をオーバーレイに通知する"""
    status = state.topic_talker.get_status()
    status["type"] = "topic_update"
    await state.broadcast_overlay(status)


@router.get("/api/topic")
async def get_topic():
    """現在のトピック状態を取得する"""
    status = state.topic_talker.get_status()
    status["model"] = os.environ.get("GEMINI_TOPIC_MODEL", "gemini-3-flash-preview")
    return status


@router.post("/api/topic")
async def set_topic(body: dict):
    """トピックを設定する"""
    title = body.get("title", "").strip()
    if not title:
        return {"ok": False, "error": "タイトルが必要です"}
    description = body.get("description", "").strip()
    topic = await state.topic_talker.set_topic(title, description)
    await _notify_overlay()
    return {"ok": True, "topic": topic}


@router.delete("/api/topic")
async def clear_topic():
    """トピックを解除する"""
    await state.topic_talker.clear_topic()
    await _notify_overlay()
    return {"ok": True}


@router.get("/api/topic/scripts")
async def get_scripts():
    """現在のトピックの発話履歴を取得する"""
    topic = db.get_active_topic()
    if not topic:
        return {"scripts": [], "generating": state.topic_talker._generating}
    scripts = db.get_spoken_scripts(topic["id"])
    return {
        "scripts": scripts,
        "generating": state.topic_talker._generating,
    }


@router.post("/api/topic/speak")
async def speak_now():
    """手動で1つ発話する（テスト用）"""
    script = await state.topic_talker.get_next()
    if not script:
        return {"ok": False, "error": "発話するスクリプトがありません"}
    try:
        await state.reader.speak_event("トピック", script["content"])
        await _notify_overlay()
        return {"ok": True, "content": script["content"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/topic/pause")
async def pause_topic():
    """自発的発話を一時停止する"""
    state.topic_talker._paused = True
    await _notify_overlay()
    return {"ok": True, "paused": True}


@router.post("/api/topic/resume")
async def resume_topic():
    """自発的発話を再開する"""
    state.topic_talker._paused = False
    await _notify_overlay()
    return {"ok": True, "paused": False}


@router.post("/api/topic/settings")
async def update_settings(body: dict):
    """自発的発話の設定を更新する"""
    if "idle_threshold" in body:
        state.topic_talker.idle_threshold = int(body["idle_threshold"])
    if "min_interval" in body:
        state.topic_talker.min_interval = int(body["min_interval"])
    return {"ok": True, **state.topic_talker.get_status()}
