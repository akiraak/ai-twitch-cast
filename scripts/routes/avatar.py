"""アバター制御ルート（発話）"""

import asyncio

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src import db
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
    asyncio.create_task(state.reader.speak_event(body.event_type, body.detail, voice=body.voice))
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
    asyncio.create_task(state.reader.speak_event("TTSテスト", detail))
    return {"ok": True}


class EmotionTestRequest(BaseModel):
    emotion: str


@router.post("/api/tts/test-emotion")
async def tts_test_emotion(body: EmotionTestRequest):
    """指定感情でテスト発話する（感情に合ったセリフをAIが生成）"""
    from src.ai_responder import get_character
    char = get_character()
    emotions = char.get("emotions", {})
    emotion_desc = emotions.get(body.emotion, body.emotion)
    detail = (
        f"Say a very short phrase (1 sentence, in Japanese) that naturally expresses "
        f"the emotion '{body.emotion}' ({emotion_desc}). "
        f"Be expressive and match the emotion."
    )
    asyncio.create_task(state.reader.speak_event("感情テスト", detail))
    return {"ok": True}


class WebUIChatRequest(BaseModel):
    message: str


@router.post("/api/chat/webui")
async def chat_webui(body: WebUIChatRequest):
    """WebUIからアバターに会話を送る（AI応答→TTS→字幕、Twitch投稿なし）"""
    await state.ensure_reader()
    result = await state.reader.respond_webui(body.message)
    return result


class ChatMessage(BaseModel):
    message: str


@router.post("/api/chat/send")
async def chat_send(body: ChatMessage):
    """Twitchチャットにメッセージを送信する"""
    await state.reader._chat.send_message(body.message)
    return {"ok": True}


@router.get("/api/chat/history")
async def chat_history(limit: int = 50, offset: int = 0):
    """チャット履歴をタイムライン形式で返す（新しい順）"""
    conn = db.get_connection()
    total_comments = conn.execute("SELECT COUNT(*) as cnt FROM comments").fetchone()["cnt"]
    total_avatar = conn.execute("SELECT COUNT(*) as cnt FROM avatar_comments").fetchone()["cnt"]
    total = total_comments + total_avatar
    rows = conn.execute(
        """SELECT * FROM (
               SELECT 'comment' as type, u.name as author, c.text as trigger_text,
                      NULL as speech, NULL as emotion, c.created_at
               FROM comments c JOIN users u ON c.user_id = u.id
               UNION ALL
               SELECT 'avatar_comment' as type, NULL as author, ac.trigger_text,
                      ac.text as speech, ac.emotion, ac.created_at
               FROM avatar_comments ac
           ) ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()
    return {"comments": [dict(r) for r in rows], "total": total, "offset": offset, "limit": limit}


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

