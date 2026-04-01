"""教師モードAPI — コンテンツCRUD・画像アップロード・スクリプト生成"""

import asyncio
import json as _json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from src import db
from src.lesson_generator import (
    extract_main_content,
    extract_text_from_image,
    extract_text_from_url,
    get_lesson_characters,
)
from src.lesson_runner import clear_tts_cache, get_tts_cache_info
from src.prompt_builder import get_stream_language, set_stream_language


def _with_lang(lang: str):
    """一時的に配信言語を切り替えるコンテキストマネージャ的ヘルパー。
    戻り値は元の言語設定を復元する関数。"""
    prev = get_stream_language()
    if lang == "en":
        set_stream_language("en", "none", "low")
    elif lang == "ja":
        set_stream_language("ja", "en", "low")
    else:
        set_stream_language(prev["primary"], prev["sub"], prev["mix"])

    def restore():
        set_stream_language(prev["primary"], prev["sub"], prev["mix"])
    return restore

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


class SectionImport(BaseModel):
    sections: list[dict]
    plan_summary: str | None = None


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
    """コンテンツ詳細（ソース＋セクション＋言語別プラン付き）"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    sources = db.get_lesson_sources(lesson_id)
    sections = db.get_lesson_sections(lesson_id)
    # 言語別プラン
    plans_list = db.get_lesson_plans(lesson_id)
    plans = {}
    for p in plans_list:
        plan_data = {
            "knowledge": p["knowledge"],
            "entertainment": p["entertainment"],
            "plan_json": p["plan_json"],
        }
        # v3: 監督出力とメタデータ
        if p.get("director_json"):
            plan_data["director_json"] = p["director_json"]
        if p.get("plan_generations"):
            plan_data["plan_generations"] = p["plan_generations"]
        plans[p["lang"]] = plan_data
    # generator別にグループ化
    sections_by_generator: dict[str, list] = {}
    for s in sections:
        gen = s.get("generator", "gemini")
        sections_by_generator.setdefault(gen, []).append(s)
    return {"ok": True, "lesson": lesson, "sources": sources, "sections": sections,
            "sections_by_generator": sections_by_generator, "plans": plans}


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

    # メインコンテンツ識別
    main_content = []
    if extracted:
        try:
            main_content = await asyncio.to_thread(extract_main_content, extracted)
        except Exception as e:
            logger.warning("メインコンテンツ識別失敗: %s", e)

    main_content_json = _json.dumps(main_content, ensure_ascii=False) if main_content else ""
    db.update_lesson(lesson_id, extracted_text=extracted, main_content=main_content_json)
    # テキスト変更でセクションを無効化
    db.delete_lesson_sections(lesson_id)

    logger.info("テキスト抽出完了: lesson=%d, %d件, %d文字, main_content=%d件",
                lesson_id, len(texts), len(extracted), len(main_content))
    return {"ok": True, "extracted_text": extracted, "main_content": main_content}


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

    # メインコンテンツ識別
    main_content = []
    if extracted:
        try:
            main_content = await asyncio.to_thread(extract_main_content, extracted)
        except Exception as e:
            logger.warning("メインコンテンツ識別失敗: %s", e)

    main_content_json = _json.dumps(main_content, ensure_ascii=False) if main_content else ""
    db.update_lesson(lesson_id, extracted_text=extracted, main_content=main_content_json)

    logger.info("URL追加: %s → lesson %d, main_content=%d件", body.url, lesson_id, len(main_content))
    return {"ok": True, "source": source, "extracted_text": extracted, "main_content": main_content}


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


# --- プラン手動編集 ---


class PlanUpdate(BaseModel):
    plan_knowledge: str | None = None
    plan_entertainment: str | None = None
    plan_json: str | None = None
    lang: str = "ja"


@router.put("/api/lessons/{lesson_id}/plan")
async def update_plan(lesson_id: int, body: PlanUpdate):
    """プランを手動編集する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    knowledge = body.plan_knowledge or ""
    entertainment = body.plan_entertainment or ""
    plan_json = body.plan_json or ""

    if knowledge or entertainment or plan_json:
        db.upsert_lesson_plan(lesson_id, body.lang,
                              knowledge=knowledge, entertainment=entertainment, plan_json=plan_json)
        # 後方互換
        db.update_lesson(lesson_id, plan_knowledge=knowledge,
                         plan_entertainment=entertainment, plan_json=plan_json)
    return {"ok": True}



# --- セクション インポート ---


VALID_SECTION_TYPES = {"introduction", "explanation", "example", "question", "summary"}
VALID_EMOTIONS = {"joy", "excited", "surprise", "thinking", "sad", "embarrassed", "neutral"}


@router.post("/api/lessons/{lesson_id}/import-sections")
async def import_sections(
    lesson_id: int, body: SectionImport,
    lang: str = "ja", generator: str = "claude"
):
    """外部生成されたセクションをインポートする"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    if not body.sections:
        return {"ok": False, "error": "セクションが空です"}

    # フォーマット検証
    errors = []
    for i, s in enumerate(body.sections):
        if not s.get("section_type"):
            errors.append(f"セクション{i}: section_type が必須です")
        elif s["section_type"] not in VALID_SECTION_TYPES:
            errors.append(f"セクション{i}: 不明な section_type: {s['section_type']}")
        if not s.get("content"):
            errors.append(f"セクション{i}: content が必須です")
        if not s.get("tts_text"):
            errors.append(f"セクション{i}: tts_text が必須です")
        if not s.get("display_text"):
            errors.append(f"セクション{i}: display_text が必須です")
        emotion = s.get("emotion", "neutral")
        if emotion not in VALID_EMOTIONS:
            errors.append(f"セクション{i}: 不明な emotion: {emotion}")
    if errors:
        return {"ok": False, "error": "検証エラー", "details": errors}

    # 該当 (lesson_id, lang, generator) のセクションを削除
    db.delete_lesson_sections(lesson_id, lang=lang, generator=generator)

    # DB保存
    saved = []
    for i, s in enumerate(body.sections):
        # dialogues/dialogue_directions: dictやlistならJSON文字列に変換
        dialogues = s.get("dialogues", "")
        if isinstance(dialogues, (list, dict)):
            dialogues = _json.dumps(dialogues, ensure_ascii=False)
        dialogue_directions = s.get("dialogue_directions", "")
        if isinstance(dialogue_directions, (list, dict)):
            dialogue_directions = _json.dumps(dialogue_directions, ensure_ascii=False)

        sec = db.add_lesson_section(
            lesson_id, order_index=i,
            section_type=s["section_type"],
            title=s.get("title", ""),
            content=s["content"],
            tts_text=s["tts_text"],
            display_text=s["display_text"],
            emotion=s.get("emotion", "neutral"),
            question=s.get("question", ""),
            answer=s.get("answer", ""),
            wait_seconds=s.get("wait_seconds", 3),
            lang=lang,
            dialogues=dialogues,
            dialogue_directions=dialogue_directions,
            generator=generator,
        )
        saved.append(sec)

    # plan_summary があればプランとして保存
    if body.plan_summary:
        db.upsert_lesson_plan(
            lesson_id, lang,
            knowledge=body.plan_summary,
            generator=generator,
        )

    logger.info("セクションインポート: lesson=%d, lang=%s, generator=%s, sections=%d",
                lesson_id, lang, generator, len(saved))
    return {"ok": True, "sections": saved, "count": len(saved)}


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
async def start_lesson(lesson_id: int, lang: str = "ja", generator: str = "claude"):
    """授業を開始する"""
    runner = _get_lesson_runner()
    # 授業再生中は配信言語も一時的に合わせる
    _with_lang(lang)
    try:
        await runner.start(lesson_id, lang=lang, generator=generator)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "status": runner.get_status()}


# --- TTSキャッシュ ---


@router.get("/api/lessons/{lesson_id}/tts-cache")
async def get_tts_cache(lesson_id: int, lang: str = "ja", generator: str = "claude"):
    """TTSキャッシュ状況を取得する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    sections = get_tts_cache_info(lesson_id, lang=lang, generator=generator)
    return {"ok": True, "sections": sections}



@router.delete("/api/lessons/{lesson_id}/tts-cache")
async def delete_tts_cache(lesson_id: int, lang: str | None = None, generator: str | None = None):
    """全TTSキャッシュを削除する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    clear_tts_cache(lesson_id, lang=lang, generator=generator)
    logger.info("TTSキャッシュ全削除: lesson=%d, lang=%s, generator=%s", lesson_id, lang or "all", generator or "all")
    return {"ok": True}


@router.delete("/api/lessons/{lesson_id}/tts-cache/{order_index}")
async def delete_tts_cache_section(lesson_id: int, order_index: int, lang: str = "ja", generator: str | None = None):
    """特定セクションのTTSキャッシュを削除する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    clear_tts_cache(lesson_id, order_index=order_index, lang=lang, generator=generator)
    logger.info("TTSキャッシュ削除: lesson=%d, section=%d, lang=%s, generator=%s", lesson_id, order_index, lang, generator or "all")
    return {"ok": True}
