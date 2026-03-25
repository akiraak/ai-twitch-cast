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


class VoiceSampleRequest(BaseModel):
    voice: str | None = None
    style: str | None = None
    avatar_id: str = "teacher"


# 声サンプル用プロンプト（バリエーション豊富、短文〜長文混在）
_VOICE_SAMPLE_PROMPTS = [
    # --- 短め（1文）---
    "配信を見てくれている視聴者に、今日初めて来てくれた人に向けて歓迎の一言を。",
    "好きな食べ物について一言で熱く語って。",
    "今朝あった小さな幸せを報告して。",
    "視聴者に突然クイズを出して（答えは言わないで）。",
    "今日の天気を超テンション高めに実況して。",
    # --- 中くらい（2〜3文）---
    "最近ハマっていることについて語って。なぜハマったか、どこが面白いかも含めて（2〜3文で）。",
    "昨日見た夢の話をして。できるだけ詳しく、でもちょっとオチをつけて（2〜3文で）。",
    "プログラミングの面白さを、プログラミングを知らない人に向けて説明して（2〜3文で）。",
    "配信中に起きた面白いハプニングのエピソードを作って話して（2〜3文で）。",
    "お気に入りの場所について、そこの魅力を伝えて（2〜3文で）。",
    "朝型 vs 夜型、自分の立場を熱弁して（2〜3文で）。",
    # --- 長め（3〜5文）---
    "AIについて思うことを自由に語って。未来への期待も不安も含めて正直に（3〜5文で）。",
    "もし1日だけ別の職業を体験できるなら何がいい？理由と妄想を膨らませて（3〜5文で）。",
    "子供の頃に夢中だったことと、今の自分との繋がりについて語って（3〜5文で）。",
    "無人島に3つだけ持っていけるとしたら何を持っていく？理由も詳しく（3〜5文で）。",
    "配信を始めたきっかけと、続けている理由を視聴者に話して（3〜5文で）。",
    "最近感動したこと（映画、本、出来事なんでも）について熱く語って（3〜5文で）。",
    "自分の長所と短所を正直に語って。短所はちょっと面白おかしく（3〜5文で）。",
    "10年後の自分に手紙を書くつもりで語りかけて（3〜5文で）。",
]


@router.post("/api/tts/voice-sample")
async def tts_voice_sample(body: VoiceSampleRequest):
    """キャラクタータブから声のサンプルを再生する（フォーム上のvoice/styleで試聴）"""
    import random
    from src.prompt_builder import get_stream_language, SUPPORTED_LANGUAGES

    lang = get_stream_language()
    p_name = SUPPORTED_LANGUAGES.get(lang["primary"], lang["primary"])

    prompt = random.choice(_VOICE_SAMPLE_PROMPTS)
    if lang["sub"] != "none":
        s_name = SUPPORTED_LANGUAGES.get(lang["sub"], lang["sub"])
        detail = f"{prompt} Mix {p_name} and {s_name}."
    else:
        detail = f"{prompt} Speak in {p_name}."

    await state.ensure_reader()
    asyncio.create_task(
        state.reader.speak_event(
            "ボイスサンプル", detail,
            voice=body.voice or None,
            style=body.style or None,
        )
    )
    return {"ok": True}


@router.post("/api/tts/test-multi")
async def tts_test_multi():
    """連続発話テスト（長文生成→句読点分割→順次再生）"""
    import random
    from src.ai_responder import generate_event_response
    from src.speech_pipeline import SpeechPipeline

    topics = [
        "最近自分が夢中になっていることについて具体的に語ってください（3〜4文で詳しく）",
        "プログラミングの魅力やエピソードを語ってください（3〜4文で詳しく）",
        "好きな食べ物について熱く語ってください（3〜4文で詳しく）",
        "朝型と夜型、自分はどっち派か理由も含めて語ってください（3〜4文で詳しく）",
        "AIがこれからどうなるか、自分の考えを語ってください（3〜4文で詳しく）",
    ]
    detail = random.choice(topics)

    result = await asyncio.to_thread(
        generate_event_response, "連続発話テスト", detail,
    )

    # 句読点で自動分割してセグメント化
    content_parts = SpeechPipeline.split_sentences(result["speech"])
    tts_parts = SpeechPipeline.split_sentences(result.get("tts_text", result["speech"]))
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
        await state.reader._speak_segment(segments[0])
        for seg in segments[1:]:
            state.reader._segment_queue.append(seg)

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

