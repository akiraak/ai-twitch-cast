"""トピック管理ルート"""

import asyncio
import logging
import os
from pathlib import Path

from fastapi import APIRouter

from scripts import state
from src import db

router = APIRouter()
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
RESOURCES_DIR = PROJECT_DIR / "resources"


async def _notify_overlay():
    """トピック状態をオーバーレイに通知する（画像URL含む）"""
    status = state.topic_talker.get_status()
    status["type"] = "topic_update"
    # トピック画像がある場合はURLリストを含める
    image_urls = state.topic_talker.get_image_urls()
    if image_urls:
        status["image_urls"] = image_urls
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
    """手動でトピック発話する（複数セグメント対応）"""
    segments = await state.topic_talker.get_next()
    if not segments:
        return {"ok": False, "error": "発話するスクリプトがありません"}
    try:
        # 1文目は即座に発話
        await state.reader._speak_topic_segment(segments[0])
        # 2文目以降はトピックキューに入れる
        for seg in segments[1:]:
            state.reader._topic_queue.append(seg)
        await _notify_overlay()
        contents = [s["content"] for s in segments]
        return {"ok": True, "segments": contents, "count": len(segments)}
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


@router.post("/api/topic/lesson")
async def start_lesson(body: dict):
    """授業モードを開始する（画像 or URL → コンテキスト生成 → スクリプト生成 → トピック設定）

    Body:
        source: "images" or "url"
        files: list[str] - 画像ファイル名リスト（source="images"の場合）
        url: str - URL（source="url"の場合）
    """
    from src.ai_responder import analyze_images, analyze_url, generate_lesson_script

    source = body.get("source", "")
    if source not in ("images", "url"):
        return {"ok": False, "error": "sourceは'images'または'url'を指定してください"}

    try:
        context = ""
        title = "授業"
        description = ""
        image_urls = []
        num_images = 0

        if source == "images":
            files = body.get("files", [])
            if not files:
                return {"ok": False, "error": "画像ファイルが指定されていません"}
            teaching_dir = RESOURCES_DIR / "images" / "teaching"
            image_paths = []
            for f in files:
                path = teaching_dir / f
                if not path.exists():
                    return {"ok": False, "error": f"ファイルが見つかりません: {f}"}
                image_paths.append(str(path))
            image_urls = [f"/resources/images/teaching/{f}" for f in files]
            num_images = len(image_paths)

            # Geminiで画像解析 → コンテキスト生成
            logger.info("[lesson] 画像解析中... (%d枚)", num_images)
            context = await asyncio.to_thread(
                analyze_images, image_paths,
                "この教材の内容を詳細にテキスト化してください。テキスト・図表・数式などすべての情報を含めてください。"
            )
            title = "授業"

        elif source == "url":
            url = body.get("url", "").strip()
            if not url:
                return {"ok": False, "error": "URLが指定されていません"}

            # URL解析 → コンテキスト生成
            logger.info("[lesson] URL解析中... %s", url)
            page = await asyncio.to_thread(analyze_url, url)
            title = page.get("title", "") or "授業"
            context = f"タイトル: {page['title']}\n\n{page['text']}"
            description = page["title"]
            if page.get("image_url"):
                image_urls = [page["image_url"]]

        # スクリプト生成
        logger.info("[lesson] スクリプト生成中...")
        scripts = await asyncio.to_thread(
            generate_lesson_script, context, num_images=num_images,
        )
        if not scripts:
            return {"ok": False, "error": "スクリプト生成に失敗しました"}

        # トピック設定（画像URL・コンテキスト付き）
        topic = await state.topic_talker.set_topic(
            title, description,
            image_urls=image_urls, context=context,
        )

        # スクリプトをDBに保存（topic_scriptsテーブル）
        db_scripts = []
        for i, s in enumerate(scripts):
            db_scripts.append({
                "content": s.get("content", ""),
                "emotion": "neutral",
                "sort_order": i,
            })
        db.add_topic_scripts(topic["id"], db_scripts)

        await _notify_overlay()
        logger.info("[lesson] 授業開始: %s (%dステップ)", title, len(scripts))
        return {
            "ok": True,
            "topic": topic,
            "scripts": scripts,
            "script_count": len(scripts),
        }
    except Exception as e:
        logger.error("[lesson] 授業開始失敗: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)}


@router.get("/api/topic/lesson/status")
async def lesson_status():
    """授業モードの状態を取得する"""
    status = state.topic_talker.get_status()
    status["has_context"] = state.topic_talker.get_context() is not None
    status["image_urls"] = state.topic_talker.get_image_urls()
    return status
