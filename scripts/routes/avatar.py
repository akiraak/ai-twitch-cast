"""アバター制御ルート（VTS + 発話）"""

import asyncio

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from scripts import state

router = APIRouter()


class SpeakRequest(BaseModel):
    event_type: str = "手動"
    detail: str
    voice: str | None = None


@router.post("/api/avatar/speak")
async def avatar_speak(body: SpeakRequest):
    """アバターにイベント発話させる＆現在の作業として表示"""
    # オーバーレイに現在の作業を通知
    await state.broadcast_overlay({
        "type": "current_task",
        "task": body.detail,
    })
    asyncio.ensure_future(state.reader.speak_event(body.event_type, body.detail, voice=body.voice))
    return {"ok": True}


class ChatMessage(BaseModel):
    message: str


@router.post("/api/chat/send")
async def chat_send(body: ChatMessage):
    """Twitchチャットにメッセージを送信する"""
    await state.reader._chat.send_message(body.message)
    return {"ok": True}


@router.get("/api/tts/audio")
async def tts_audio():
    """現在のTTS音声ファイルを返す"""
    audio_path = getattr(state.reader, "_current_audio", None)
    if audio_path and audio_path.exists():
        return FileResponse(
            str(audio_path), media_type="audio/wav",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return {"error": "no audio"}


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


