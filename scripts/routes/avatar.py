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
    pattern: str = "greeting"


# テストパターン定義
_TTS_PATTERNS = {
    "greeting": "Say a short greeting to viewers (1 sentence).",
    "topic": "Share a fun fact or interesting tidbit about something you like (1 sentence).",
    "react": "React to a viewer saying 'I just started learning programming' (1 sentence).",
    "question": "Ask viewers a casual question to start a conversation (1 sentence).",
    "story": "Tell a short story or anecdote about something funny that happened recently (3-4 sentences).",
    "explain": "Explain something interesting you know about (a technology, a hobby, or a random topic) in detail (3-4 sentences).",
}


@router.post("/api/tts/test")
async def tts_test(body: TtsTestRequest):
    """配信言語設定でテスト発話する"""
    import random
    from src.prompt_builder import get_stream_language, SUPPORTED_LANGUAGES
    lang = get_stream_language()
    p_name = SUPPORTED_LANGUAGES.get(lang["primary"], lang["primary"])

    pattern = _TTS_PATTERNS.get(body.pattern)
    if not pattern:
        pattern = random.choice(list(_TTS_PATTERNS.values()))

    if lang["sub"] != "none":
        s_name = SUPPORTED_LANGUAGES.get(lang["sub"], lang["sub"])
        detail = f"{pattern} Mix {p_name} and {s_name}."
    else:
        detail = f"{pattern} Speak in {p_name}."
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


@router.post("/api/tts/test-multi")
async def tts_test_multi():
    """連続発話テスト（長文生成→句読点分割→順次再生）"""
    import random
    from src.ai_responder import generate_topic_line
    from src.speech_pipeline import SpeechPipeline

    topics = [
        ("最近ハマっていること", "最近自分が夢中になっていることについて具体的に語る"),
        ("プログラミングの面白さ", "プログラミングの魅力やエピソードを語る"),
        ("好きな食べ物", "好きな食べ物について熱く語る"),
        ("朝型と夜型", "自分はどっち派か、理由も含めて語る"),
        ("AIの未来", "AIがこれからどうなるか、自分の考えを語る"),
    ]
    title, desc = random.choice(topics)

    result = await asyncio.to_thread(
        generate_topic_line, title, description=desc,
    )

    # 句読点で自動分割してセグメント化
    content_parts = SpeechPipeline.split_sentences(result["content"])
    tts_parts = SpeechPipeline.split_sentences(result.get("tts_text", result["content"]))
    segments = []
    for i, content in enumerate(content_parts):
        tts_text = tts_parts[i] if i < len(tts_parts) else content
        segments.append({
            "content": content,
            "emotion": result["emotion"],
            "tts_text": tts_text,
            "translation": result.get("translation", "") if i == 0 else "",
        })

    async def _play():
        await state.ensure_reader()
        await state.reader._speak_topic_segment(segments[0])
        for seg in segments[1:]:
            state.reader._topic_queue.append(seg)

    asyncio.create_task(_play())
    contents = [s["content"] for s in segments]
    return {"ok": True, "segments": contents, "count": len(segments)}


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

