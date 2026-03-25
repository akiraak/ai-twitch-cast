"""アバター制御ルート（発話）"""

import asyncio
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse
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
            avatar_id=body.avatar_id,
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


class ConversationDemoRequest(BaseModel):
    topic: str


# 会話デモの永続化ディレクトリ
import json as _json
from pathlib import Path as _Path

_CONV_DEMO_DIR = _Path(__file__).resolve().parent.parent.parent / "resources" / "audio" / "conv_demo"


def _save_conv_demo(topic, dialogues, wav_paths, teacher_cfg, student_cfg):
    """会話デモデータをファイルに保存する"""
    _CONV_DEMO_DIR.mkdir(parents=True, exist_ok=True)
    # WAVファイルを移動
    saved_wavs = []
    for i, src in enumerate(wav_paths):
        if src and _Path(src).exists():
            dst = _CONV_DEMO_DIR / f"{i:02d}.wav"
            import shutil
            shutil.move(src, dst)
            saved_wavs.append(str(dst))
        else:
            saved_wavs.append(None)
    # メタデータ保存
    meta = {
        "topic": topic,
        "dialogues": dialogues,
        "wav_paths": saved_wavs,
        "teacher_cfg": teacher_cfg,
        "student_cfg": student_cfg,
    }
    (_CONV_DEMO_DIR / "meta.json").write_text(_json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def _load_conv_demo():
    """保存済み会話デモデータを読み込む"""
    meta_path = _CONV_DEMO_DIR / "meta.json"
    if not meta_path.exists():
        return None
    try:
        return _json.loads(meta_path.read_text())
    except Exception:
        return None


@router.get("/api/debug/conversation-demo/status")
async def conversation_demo_status():
    """会話デモ: 保存済みデータの有無を返す"""
    meta = _load_conv_demo()
    if not meta or not meta.get("dialogues"):
        return {"has_data": False}
    teacher_cfg = meta.get("teacher_cfg", {})
    student_cfg = meta.get("student_cfg", {})
    dialogues = meta["dialogues"]
    items = []
    for dlg in dialogues:
        speaker = dlg.get("speaker", "teacher")
        cfg = teacher_cfg if speaker == "teacher" else student_cfg
        items.append({
            "speaker": cfg.get("name", speaker),
            "content": dlg.get("content", ""),
            "emotion": dlg.get("emotion", "neutral"),
        })
    return {
        "has_data": True,
        "topic": meta.get("topic", ""),
        "dialogues_count": len(dialogues),
        "dialogues": items,
    }


@router.post("/api/debug/conversation-demo/generate")
async def conversation_demo_generate(body: ConversationDemoRequest):
    """会話デモ: スクリプト生成 + TTS事前生成（SSE）"""
    import json as _json
    import logging
    import re
    import tempfile

    from google.genai import types

    from src.gemini_client import get_client
    from src.lesson_generator import _format_character_for_prompt, get_lesson_characters
    from src.tts import synthesize

    logger = logging.getLogger(__name__)

    async def event_stream():
        def _emit(data):
            return f"data: {_json.dumps(data, ensure_ascii=False)}\n\n"

        # --- 1. キャラ取得 ---
        characters = get_lesson_characters()
        teacher_cfg = characters.get("teacher")
        student_cfg = characters.get("student")
        if not teacher_cfg or not student_cfg:
            yield _emit({"ok": False, "error": "先生・生徒キャラがDBに登録されていません"})
            return

        yield _emit({"phase": "generate", "message": "会話スクリプト生成中..."})

        # --- 2. LLMで会話生成 ---
        teacher_desc = _format_character_for_prompt(teacher_cfg, "teacher", en=False)
        student_desc = _format_character_for_prompt(student_cfg, "student", en=False)

        prompt = f"""以下の2人のキャラクターが「{body.topic}」について雑談します。
4往復（8発話）の自然な会話を生成してください。
teacherから始めてください。

{teacher_desc}

{student_desc}

## ルール
- 各発話は1〜2文（短く自然に）
- 感情は各キャラの使用可能な感情から選ぶ
- tts_textはcontentと同じ（英語部分がある場合のみ[lang:en]タグ付き）

## 出力形式（JSON配列のみ）
[
  {{"speaker": "teacher", "content": "発話テキスト", "tts_text": "TTS用テキスト", "emotion": "neutral"}}
]"""

        try:
            client = get_client()
            model = os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview")
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.9,
                    max_output_tokens=4096,
                ),
            )
        except Exception as e:
            logger.error("会話デモLLM呼び出し失敗: %s", e)
            yield _emit({"ok": False, "error": f"会話生成失敗: {e}"})
            return

        text = response.text.strip()
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
        if m:
            text = m.group(1).strip()

        try:
            dialogues = _json.loads(text)
        except _json.JSONDecodeError as e:
            logger.error("会話デモJSONパース失敗: %s", e)
            yield _emit({"ok": False, "error": "会話生成のJSONパースに失敗"})
            return

        if not isinstance(dialogues, list) or len(dialogues) == 0:
            yield _emit({"ok": False, "error": "会話が生成されませんでした"})
            return

        total = len(dialogues)

        # 生成された会話ログを送信
        for i, dlg in enumerate(dialogues):
            speaker = dlg.get("speaker", "teacher")
            cfg = teacher_cfg if speaker == "teacher" else student_cfg
            name = cfg.get("name", speaker)
            yield _emit({
                "phase": "script",
                "index": i,
                "total": total,
                "speaker": name,
                "content": dlg.get("content", ""),
                "emotion": dlg.get("emotion", "neutral"),
            })

        # --- 3. TTS事前生成 ---
        yield _emit({"phase": "tts", "message": f"TTS生成中... (0/{total})"})
        wav_paths = []
        for i, dlg in enumerate(dialogues):
            speaker = dlg.get("speaker", "teacher")
            cfg = teacher_cfg if speaker == "teacher" else student_cfg
            voice = cfg.get("tts_voice")
            style = cfg.get("tts_style")
            tts_text = dlg.get("tts_text", dlg.get("content", ""))

            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, prefix=f"conv_demo_{i:02d}_")
            tmp.close()
            try:
                await asyncio.to_thread(synthesize, tts_text, tmp.name, voice=voice, style=style)
                wav_paths.append(tmp.name)
            except Exception as e:
                logger.warning("会話デモTTS生成失敗 (%d): %s", i, e)
                wav_paths.append(None)

            yield _emit({
                "phase": "tts",
                "message": f"TTS生成中... ({i + 1}/{total})",
                "step": i + 1,
                "total": total,
            })

        # ファイルに保存
        _save_conv_demo(body.topic, dialogues, wav_paths, teacher_cfg, student_cfg)

        yield _emit({"ok": True, "dialogues_count": total})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/api/debug/conversation-demo/play")
async def conversation_demo_play():
    """会話デモ: 保存済みの会話を再生する"""
    meta = _load_conv_demo()
    if not meta or not meta.get("dialogues"):
        return {"ok": False, "error": "生成済みの会話がありません。先に生成してください"}

    dialogues = meta["dialogues"]
    wav_paths = meta.get("wav_paths", [])
    topic = meta.get("topic", "")
    teacher_cfg = meta.get("teacher_cfg", {})
    student_cfg = meta.get("student_cfg", {})

    async def _play():
        await state.ensure_reader()
        for i, dlg in enumerate(dialogues):
            speaker = dlg.get("speaker", "teacher")
            avatar_id = speaker
            cfg = teacher_cfg if speaker == "teacher" else student_cfg
            voice = cfg.get("tts_voice")
            style = cfg.get("tts_style")
            content = dlg.get("content", "")
            tts_text = dlg.get("tts_text", content)
            emotion = dlg.get("emotion", "neutral")
            from pathlib import Path
            wav_str = wav_paths[i] if i < len(wav_paths) else None
            wav = Path(wav_str) if wav_str else None

            reader = state.reader
            reader._speech.apply_emotion(emotion, avatar_id=avatar_id)
            await reader._speech.speak(
                content, voice=voice, style=style, avatar_id=avatar_id,
                tts_text=tts_text, wav_path=wav,
                subtitle={
                    "author": cfg.get("name", speaker),
                    "trigger_text": f"[会話デモ] {topic}",
                    "result": {"speech": content, "emotion": emotion},
                },
            )
            reader._speech.apply_emotion("neutral", avatar_id=avatar_id)
            await reader._speech.notify_overlay_end()

    asyncio.create_task(_play())
    return {"ok": True, "dialogues_count": len(dialogues)}


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

