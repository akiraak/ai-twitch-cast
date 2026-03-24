"""教師モードAPI — コンテンツCRUD・画像アップロード・スクリプト生成"""

import asyncio
import json as _json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src import db
from src.lesson_generator import (
    extract_text_from_image,
    extract_text_from_url,
    generate_lesson_plan,
    generate_lesson_script,
    generate_lesson_script_from_plan,
)
from src.lesson_runner import LESSON_AUDIO_DIR, _cache_path, clear_tts_cache, get_tts_cache_info
from src.speech_pipeline import SpeechPipeline
from src.tts import synthesize

router = APIRouter()
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
LESSON_IMAGES_DIR = PROJECT_DIR / "resources" / "images" / "lessons"
LESSON_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.strip(". ")
    return name[:200] if name else "untitled"


# --- コンテンツ CRUD ---


class LessonCreate(BaseModel):
    name: str


class LessonUpdate(BaseModel):
    name: str | None = None


class SectionUpdate(BaseModel):
    content: str | None = None
    tts_text: str | None = None
    display_text: str | None = None
    emotion: str | None = None
    question: str | None = None
    answer: str | None = None
    wait_seconds: int | None = None


class SectionReorder(BaseModel):
    section_ids: list[int]


class UrlAdd(BaseModel):
    url: str


@router.get("/api/lessons")
async def list_lessons():
    """全コンテンツ一覧"""
    lessons = db.get_all_lessons()
    return {"ok": True, "lessons": lessons}


@router.post("/api/lessons")
async def create_lesson(body: LessonCreate):
    """コンテンツ新規作成"""
    lesson = db.create_lesson(body.name)
    logger.info("コンテンツ作成: %s (id=%d)", body.name, lesson["id"])
    return {"ok": True, "lesson": lesson}


# --- 授業制御（{lesson_id}パスより前に定義する必要あり） ---

def _get_lesson_runner():
    """CommentReaderからLessonRunnerを取得する"""
    from scripts import state
    return state.reader.lesson_runner


@router.post("/api/lessons/pause")
async def pause_lesson():
    """授業を一時停止する"""
    runner = _get_lesson_runner()
    await runner.pause()
    return {"ok": True, "status": runner.get_status()}


@router.post("/api/lessons/resume")
async def resume_lesson():
    """授業を再開する"""
    runner = _get_lesson_runner()
    await runner.resume()
    return {"ok": True, "status": runner.get_status()}


@router.post("/api/lessons/stop")
async def stop_lesson():
    """授業を停止する"""
    runner = _get_lesson_runner()
    await runner.stop()
    return {"ok": True, "status": runner.get_status()}


@router.get("/api/lessons/status")
async def lesson_status():
    """授業ステータスを取得する"""
    runner = _get_lesson_runner()
    return {"ok": True, "status": runner.get_status()}


# --- 間のスケール（{lesson_id}パスより前に定義） ---


class PaceScaleUpdate(BaseModel):
    pace_scale: float


@router.get("/api/lessons/pace-scale")
async def get_pace_scale():
    """間のスケール値を取得する"""
    val = db.get_setting("lesson.pace_scale", "1.0")
    return {"ok": True, "pace_scale": float(val)}


@router.put("/api/lessons/pace-scale")
async def set_pace_scale(body: PaceScaleUpdate):
    """間のスケール値を設定する"""
    scale = max(0.5, min(2.0, body.pace_scale))
    db.set_setting("lesson.pace_scale", str(scale))
    return {"ok": True, "pace_scale": scale}


@router.get("/api/lessons/{lesson_id}")
async def get_lesson(lesson_id: int):
    """コンテンツ詳細（ソース＋セクション付き）"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    sources = db.get_lesson_sources(lesson_id)
    sections = db.get_lesson_sections(lesson_id)
    return {"ok": True, "lesson": lesson, "sources": sources, "sections": sections}


@router.put("/api/lessons/{lesson_id}")
async def update_lesson(lesson_id: int, body: LessonUpdate):
    """コンテンツ名更新"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if updates:
        db.update_lesson(lesson_id, **updates)
    return {"ok": True}


@router.delete("/api/lessons/{lesson_id}")
async def delete_lesson(lesson_id: int):
    """コンテンツ削除（画像ファイルも削除）"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    # 画像ファイル削除
    sources = db.get_lesson_sources(lesson_id)
    for src in sources:
        if src["file_path"]:
            p = PROJECT_DIR / src["file_path"]
            if p.exists():
                p.unlink()

    # TTSキャッシュ削除
    clear_tts_cache(lesson_id)

    db.delete_lesson(lesson_id)
    logger.info("コンテンツ削除: %s (id=%d)", lesson["name"], lesson_id)
    return {"ok": True}


# --- 教材ソース ---


def _clear_lesson_data(lesson_id: int):
    """既存のソース・セクション・抽出テキスト・TTSキャッシュを全削除する"""
    # TTSキャッシュ削除
    clear_tts_cache(lesson_id)
    # 画像ファイル削除
    sources = db.get_lesson_sources(lesson_id)
    for src in sources:
        if src["file_path"]:
            p = PROJECT_DIR / src["file_path"]
            if p.exists():
                p.unlink()
    # レッスン画像ディレクトリも空なら削除
    lesson_dir = LESSON_IMAGES_DIR / str(lesson_id)
    if lesson_dir.exists():
        try:
            lesson_dir.rmdir()
        except OSError:
            pass
    # DB削除
    db.delete_lesson_sections(lesson_id)
    for src in sources:
        db.delete_lesson_source(src["id"])
    db.update_lesson(lesson_id, extracted_text="")


@router.post("/api/lessons/{lesson_id}/clear-sources")
async def clear_lesson_sources(lesson_id: int):
    """既存ソース・セクション・抽出テキストを全クリアする"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    _clear_lesson_data(lesson_id)
    return {"ok": True}


@router.post("/api/lessons/{lesson_id}/upload-image")
async def upload_lesson_image(lesson_id: int, file: UploadFile = File(...)):
    """教材画像アップロード（ファイル保存のみ、テキスト抽出は別）"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in IMAGE_EXTENSIONS:
        return {"ok": False, "error": f"非対応の形式: {ext}"}

    # ファイル保存
    lesson_dir = LESSON_IMAGES_DIR / str(lesson_id)
    lesson_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(Path(file.filename).stem) + ext
    dest = lesson_dir / safe_name
    counter = 1
    while dest.exists():
        dest = lesson_dir / f"{_sanitize_filename(Path(file.filename).stem)}_{counter}{ext}"
        counter += 1

    content = await file.read()
    dest.write_bytes(content)

    rel_path = str(dest.relative_to(PROJECT_DIR))
    source = db.add_lesson_source(
        lesson_id, source_type="image",
        file_path=rel_path, original_name=file.filename or safe_name,
    )

    logger.info("教材画像アップロード: %s → %s", file.filename, rel_path)
    return {"ok": True, "source": source}


@router.post("/api/lessons/{lesson_id}/extract-text")
async def extract_lesson_text(lesson_id: int):
    """全ソースからテキストを抽出する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    sources = db.get_lesson_sources(lesson_id)
    if not sources:
        return {"ok": False, "error": "ソースがありません"}

    texts = []
    for src in sources:
        if src["source_type"] == "image" and src["file_path"]:
            try:
                t = await asyncio.to_thread(
                    extract_text_from_image, str(PROJECT_DIR / src["file_path"]),
                )
                if t:
                    texts.append(t)
            except Exception as e:
                logger.warning("画像テキスト抽出失敗 (%s): %s", src["file_path"], e)

    extracted = "\n\n---\n\n".join(texts) if texts else ""
    db.update_lesson(lesson_id, extracted_text=extracted)
    # テキスト変更でセクションを無効化
    db.delete_lesson_sections(lesson_id)

    logger.info("テキスト抽出完了: lesson=%d, %d件, %d文字", lesson_id, len(texts), len(extracted))
    return {"ok": True, "extracted_text": extracted}


@router.post("/api/lessons/{lesson_id}/add-url")
async def add_lesson_url(lesson_id: int, body: UrlAdd):
    """URL追加（既存データを全クリアして置き換え、テキスト自動抽出）"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    try:
        extracted = await extract_text_from_url(body.url)
    except Exception as e:
        logger.warning("URL取得失敗: %s — %s", body.url, e)
        return {"ok": False, "error": f"URL取得失敗: {e}"}

    # 既存データを全クリア
    _clear_lesson_data(lesson_id)

    source = db.add_lesson_source(
        lesson_id, source_type="url", url=body.url,
    )
    db.update_lesson(lesson_id, extracted_text=extracted)

    logger.info("URL追加: %s → lesson %d", body.url, lesson_id)
    return {"ok": True, "source": source, "extracted_text": extracted}


@router.delete("/api/lessons/{lesson_id}/sources/{source_id}")
async def delete_lesson_source(lesson_id: int, source_id: int):
    """教材ソース削除"""
    sources = db.get_lesson_sources(lesson_id)
    source = next((s for s in sources if s["id"] == source_id), None)
    if not source:
        return {"ok": False, "error": "ソースが見つかりません"}

    # 画像ファイル削除
    if source["file_path"]:
        p = PROJECT_DIR / source["file_path"]
        if p.exists():
            p.unlink()

    db.delete_lesson_source(source_id)
    return {"ok": True}


# --- プラン生成 ---


@router.post("/api/lessons/{lesson_id}/generate-plan")
async def generate_plan(lesson_id: int):
    """三者視点（知識・エンタメ・校長）で授業プランを生成する（SSE進捗付き）"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    extracted_text = lesson.get("extracted_text", "")
    if not extracted_text:
        return {"ok": False, "error": "教材テキストがありません。画像またはURLを追加してください。"}

    # 画像パスを収集
    sources = db.get_lesson_sources(lesson_id)
    image_paths = [
        str(PROJECT_DIR / s["file_path"])
        for s in sources
        if s["source_type"] == "image" and s["file_path"]
    ]

    async def event_stream():
        progress_queue = asyncio.Queue()

        def on_progress(step, total, message):
            progress_queue.put_nowait({"step": step, "total": total, "message": message})

        async def run_generation():
            return await asyncio.to_thread(
                generate_lesson_plan,
                lesson["name"], extracted_text, image_paths or None,
                on_progress=on_progress,
            )

        task = asyncio.create_task(run_generation())

        while not task.done():
            try:
                progress = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                yield f"data: {_json.dumps(progress, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                pass

        # drain remaining progress events
        while not progress_queue.empty():
            progress = progress_queue.get_nowait()
            yield f"data: {_json.dumps(progress, ensure_ascii=False)}\n\n"

        try:
            plan = task.result()
            # DB保存
            db.update_lesson(
                lesson_id,
                plan_knowledge=plan["knowledge"],
                plan_entertainment=plan["entertainment"],
                plan_json=_json.dumps(plan["plan_sections"], ensure_ascii=False),
            )
            logger.info("プラン生成完了: lesson=%d, sections=%d", lesson_id, len(plan["plan_sections"]))
            result = {
                "ok": True,
                "knowledge": plan["knowledge"],
                "entertainment": plan["entertainment"],
                "plan_sections": plan["plan_sections"],
            }
        except Exception as e:
            logger.error("プラン生成失敗: %s", e)
            result = {"ok": False, "error": str(e)}

        yield f"data: {_json.dumps(result, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class PlanUpdate(BaseModel):
    plan_knowledge: str | None = None
    plan_entertainment: str | None = None
    plan_json: str | None = None


@router.put("/api/lessons/{lesson_id}/plan")
async def update_plan(lesson_id: int, body: PlanUpdate):
    """プランを手動編集する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    updates = {}
    if body.plan_knowledge is not None:
        updates["plan_knowledge"] = body.plan_knowledge
    if body.plan_entertainment is not None:
        updates["plan_entertainment"] = body.plan_entertainment
    if body.plan_json is not None:
        updates["plan_json"] = body.plan_json
    if updates:
        db.update_lesson(lesson_id, **updates)
    return {"ok": True}


# --- スクリプト生成 ---


@router.post("/api/lessons/{lesson_id}/generate-script")
async def generate_script(lesson_id: int):
    """授業スクリプトを生成する（既存セクションは上書き、SSE進捗付き）"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    extracted_text = lesson.get("extracted_text", "")
    if not extracted_text:
        return {"ok": False, "error": "教材テキストがありません。画像またはURLを追加してください。"}

    # 画像パスを収集
    sources = db.get_lesson_sources(lesson_id)
    image_paths = [
        str(PROJECT_DIR / s["file_path"])
        for s in sources
        if s["source_type"] == "image" and s["file_path"]
    ]

    # プランがあればプランベースで生成
    plan_json_str = lesson.get("plan_json", "")
    plan_sections = None
    if plan_json_str:
        try:
            plan_sections = _json.loads(plan_json_str)
        except Exception:
            pass

    async def event_stream():
        progress_queue = asyncio.Queue()

        def on_progress(step, total, message):
            progress_queue.put_nowait({"step": step, "total": total, "message": message})

        async def run_generation():
            if plan_sections:
                return await asyncio.to_thread(
                    generate_lesson_script_from_plan,
                    lesson["name"], extracted_text, plan_sections, image_paths or None,
                    on_progress=on_progress,
                )
            else:
                return await asyncio.to_thread(
                    generate_lesson_script,
                    lesson["name"], extracted_text, image_paths or None,
                    on_progress=on_progress,
                )

        task = asyncio.create_task(run_generation())

        while not task.done():
            try:
                progress = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                yield f"data: {_json.dumps(progress, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                pass

        # drain remaining progress events
        while not progress_queue.empty():
            progress = progress_queue.get_nowait()
            yield f"data: {_json.dumps(progress, ensure_ascii=False)}\n\n"

        try:
            sections = task.result()
            # TTSキャッシュ・既存セクションを削除して再生成
            clear_tts_cache(lesson_id)
            db.delete_lesson_sections(lesson_id)
            saved = []
            for i, s in enumerate(sections):
                sec = db.add_lesson_section(
                    lesson_id, order_index=i,
                    section_type=s["section_type"],
                    title=s.get("title", ""),
                    content=s["content"],
                    tts_text=s["tts_text"],
                    display_text=s["display_text"],
                    emotion=s["emotion"],
                    question=s.get("question", ""),
                    answer=s.get("answer", ""),
                    wait_seconds=s.get("wait_seconds", 0),
                )
                saved.append(sec)
            logger.info("スクリプト生成完了: lesson=%d, sections=%d", lesson_id, len(saved))

            # --- TTS音声の事前生成 ---
            total_parts = 0
            section_parts_list = []
            for s in saved:
                content = s["content"]
                tts_text = s.get("tts_text") or content
                c_parts = SpeechPipeline.split_sentences(content)
                t_parts = SpeechPipeline.split_sentences(tts_text)
                section_parts_list.append((s, c_parts, t_parts))
                total_parts += len(c_parts)

            generated = 0
            tts_errors = 0
            for s, c_parts, t_parts in section_parts_list:
                oi = s["order_index"]
                for pi, _part in enumerate(c_parts):
                    generated += 1
                    part_tts = t_parts[pi] if pi < len(t_parts) else _part
                    progress_msg = f"TTS生成中: セクション{oi + 1} パート{pi + 1} ({generated}/{total_parts})"
                    yield f"data: {_json.dumps({'step': generated, 'total': total_parts, 'message': progress_msg, 'phase': 'tts'}, ensure_ascii=False)}\n\n"

                    cached = _cache_path(lesson_id, oi, pi)
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        await asyncio.to_thread(synthesize, part_tts, str(cached))
                        logger.info("[tts-cache] 生成: %s", cached)
                    except Exception as e:
                        logger.warning("[tts-cache] 生成失敗 (section=%d, part=%d): %s", oi, pi, e)
                        tts_errors += 1

            logger.info("TTS事前生成完了: lesson=%d, %d/%d パート (エラー: %d)",
                        lesson_id, generated - tts_errors, total_parts, tts_errors)

            result = {"ok": True, "sections": saved, "tts_generated": generated - tts_errors, "tts_errors": tts_errors}
        except Exception as e:
            logger.error("スクリプト生成失敗: %s", e)
            result = {"ok": False, "error": str(e)}

        yield f"data: {_json.dumps(result, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- セクション編集 ---


@router.put("/api/lessons/{lesson_id}/sections/reorder")
async def reorder_sections(lesson_id: int, body: SectionReorder):
    """セクション並び替え"""
    db.reorder_lesson_sections(lesson_id, body.section_ids)
    return {"ok": True}


@router.put("/api/lessons/{lesson_id}/sections/{section_id}")
async def update_section(lesson_id: int, section_id: int, body: SectionUpdate):
    """セクション個別更新"""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True}

    # tts_text または content が変更された場合、該当セクションのTTSキャッシュを削除
    if "tts_text" in updates or "content" in updates:
        # セクションの order_index を取得
        sections = db.get_lesson_sections(lesson_id)
        sec = next((s for s in sections if s["id"] == section_id), None)
        if sec:
            clear_tts_cache(lesson_id, order_index=sec["order_index"])
            logger.info("TTSキャッシュ削除: lesson=%d, section order=%d", lesson_id, sec["order_index"])

    db.update_lesson_section(section_id, **updates)
    return {"ok": True}


@router.delete("/api/lessons/{lesson_id}/sections/{section_id}")
async def delete_section(lesson_id: int, section_id: int):
    """セクション削除"""
    # TTSキャッシュ削除
    sections = db.get_lesson_sections(lesson_id)
    sec = next((s for s in sections if s["id"] == section_id), None)
    if sec:
        clear_tts_cache(lesson_id, order_index=sec["order_index"])

    db.delete_lesson_section(section_id)
    return {"ok": True}


@router.post("/api/lessons/{lesson_id}/start")
async def start_lesson(lesson_id: int):
    """授業を開始する"""
    runner = _get_lesson_runner()
    try:
        await runner.start(lesson_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "status": runner.get_status()}


# --- TTSキャッシュ ---


@router.get("/api/lessons/{lesson_id}/tts-cache")
async def get_tts_cache(lesson_id: int):
    """TTSキャッシュ状況を取得する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    sections = get_tts_cache_info(lesson_id)
    return {"ok": True, "sections": sections}


@router.delete("/api/lessons/{lesson_id}/tts-cache")
async def delete_tts_cache(lesson_id: int):
    """全TTSキャッシュを削除する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    clear_tts_cache(lesson_id)
    logger.info("TTSキャッシュ全削除: lesson=%d", lesson_id)
    return {"ok": True}


@router.delete("/api/lessons/{lesson_id}/tts-cache/{order_index}")
async def delete_tts_cache_section(lesson_id: int, order_index: int):
    """特定セクションのTTSキャッシュを削除する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    clear_tts_cache(lesson_id, order_index=order_index)
    logger.info("TTSキャッシュ削除: lesson=%d, section=%d", lesson_id, order_index)
    return {"ok": True}
