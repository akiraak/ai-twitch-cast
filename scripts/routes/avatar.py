"""アバター制御ルート（発話）"""

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


class TtsTestRequest(BaseModel):
    primary_lang: str = "日本語"
    secondary_lang: str = "英語"


@router.post("/api/tts/test")
async def tts_test(body: TtsTestRequest):
    """指定言語でテストテキストを生成してTTS再生する"""
    langs = {body.primary_lang, body.secondary_lang}
    no_use = []
    if "日本語" not in langs:
        no_use.append("Japanese")
    if "英語" not in langs:
        no_use.append("English")
    restriction = f" Do NOT use {', '.join(no_use)}." if no_use else ""
    detail = (
        f"Say a short greeting (1 sentence) mixing {body.primary_lang} and {body.secondary_lang}."
        f"{restriction}"
    )
    asyncio.ensure_future(state.reader.speak_event("TTSテスト", detail))
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

