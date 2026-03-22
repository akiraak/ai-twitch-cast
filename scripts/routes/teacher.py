"""教師モードAPI — コンテンツCRUD・画像アップロード・スクリプト生成"""

import asyncio
import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from src import db
from src.lesson_generator import (
    extract_text_from_image,
    extract_text_from_url,
    generate_lesson_script,
)

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

    db.delete_lesson(lesson_id)
    logger.info("コンテンツ削除: %s (id=%d)", lesson["name"], lesson_id)
    return {"ok": True}


# --- 教材ソース ---


@router.post("/api/lessons/{lesson_id}/upload-image")
async def upload_lesson_image(lesson_id: int, file: UploadFile = File(...)):
    """教材画像アップロード"""
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

    # テキスト抽出
    try:
        extracted = extract_text_from_image(str(dest))
    except Exception as e:
        logger.warning("画像テキスト抽出失敗: %s", e)
        extracted = ""

    # DB保存
    rel_path = str(dest.relative_to(PROJECT_DIR))
    source = db.add_lesson_source(
        lesson_id, source_type="image",
        file_path=rel_path, original_name=file.filename or safe_name,
    )

    # 抽出テキストを既存テキストに追記
    if extracted:
        current = lesson.get("extracted_text", "")
        separator = "\n\n---\n\n" if current else ""
        db.update_lesson(lesson_id, extracted_text=current + separator + extracted)

    logger.info("教材画像アップロード: %s → %s", file.filename, rel_path)
    return {"ok": True, "source": source, "extracted_text": extracted}


@router.post("/api/lessons/{lesson_id}/add-url")
async def add_lesson_url(lesson_id: int, body: UrlAdd):
    """URL追加（テキスト自動取得）"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    try:
        extracted = await extract_text_from_url(body.url)
    except Exception as e:
        logger.warning("URL取得失敗: %s — %s", body.url, e)
        return {"ok": False, "error": f"URL取得失敗: {e}"}

    source = db.add_lesson_source(
        lesson_id, source_type="url", url=body.url,
    )

    # 抽出テキストを既存テキストに追記
    if extracted:
        current = lesson.get("extracted_text", "")
        separator = "\n\n---\n\n" if current else ""
        db.update_lesson(lesson_id, extracted_text=current + separator + extracted)

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


# --- スクリプト生成 ---


@router.post("/api/lessons/{lesson_id}/generate-script")
async def generate_script(lesson_id: int):
    """授業スクリプトを生成する（既存セクションは上書き）"""
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

    try:
        sections = await asyncio.to_thread(
            generate_lesson_script,
            lesson["name"], extracted_text, image_paths or None,
        )
    except Exception as e:
        logger.error("スクリプト生成失敗: %s", e)
        return {"ok": False, "error": str(e)}

    # 既存セクションを削除して再生成
    db.delete_lesson_sections(lesson_id)
    saved = []
    for i, s in enumerate(sections):
        sec = db.add_lesson_section(
            lesson_id, order_index=i,
            section_type=s["section_type"],
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
    return {"ok": True, "sections": saved}


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
    db.update_lesson_section(section_id, **updates)
    return {"ok": True}


@router.delete("/api/lessons/{lesson_id}/sections/{section_id}")
async def delete_section(lesson_id: int, section_id: int):
    """セクション削除"""
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
