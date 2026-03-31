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
from src.content_analyzer import analyze_content
from src.lesson_generator import (
    extract_main_content,
    extract_text_from_image,
    extract_text_from_url,
    get_lesson_characters,
)
from src.lesson_runner import _cache_path, _dlg_cache_path, clear_tts_cache, get_tts_cache_info
from src.prompt_builder import get_stream_language, set_stream_language
from src.speech_pipeline import SpeechPipeline
from src.tts import synthesize


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


# --- プラン生成 ---


@router.post("/api/lessons/{lesson_id}/generate-plan")
async def generate_plan(lesson_id: int, lang: str = "ja"):
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

        restore_lang = _with_lang(lang)

        async def run_generation():
            try:
                return await asyncio.to_thread(
                    generate_lesson_plan,
                    lesson["name"], extracted_text, image_paths or None,
                    on_progress=on_progress,
                )
            finally:
                restore_lang()

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
            # DB保存（言語別テーブル）
            plan_json_str = _json.dumps(plan["plan_sections"], ensure_ascii=False)
            director_json_str = _json.dumps(plan.get("director_sections", []), ensure_ascii=False)
            generations_str = _json.dumps(plan.get("generations", {}), ensure_ascii=False)
            db.upsert_lesson_plan(
                lesson_id, lang,
                knowledge=plan["knowledge"],
                entertainment=plan["entertainment"],
                plan_json=plan_json_str,
                director_json=director_json_str,
                plan_generations=generations_str,
                generator="gemini",
            )
            # 後方互換: lessons テーブルにも保存
            db.update_lesson(
                lesson_id,
                plan_knowledge=plan["knowledge"],
                plan_entertainment=plan["entertainment"],
                plan_json=plan_json_str,
            )
            logger.info("プラン生成完了: lesson=%d, sections=%d", lesson_id, len(plan["plan_sections"]))
            result = {
                "ok": True,
                "knowledge": plan["knowledge"],
                "entertainment": plan["entertainment"],
                "plan_sections": plan["plan_sections"],
                "director_sections": plan.get("director_sections", []),
                "generations": plan.get("generations", {}),
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


# --- スクリプト生成 ---


@router.post("/api/lessons/{lesson_id}/generate-script")
async def generate_script(lesson_id: int, lang: str = "ja"):
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

    # 指定言語のプランがあればプランベースで生成
    plan_sections = None
    director_sections = None
    lang_plan = db.get_lesson_plan(lesson_id, lang)
    if lang_plan and lang_plan.get("plan_json"):
        try:
            plan_sections = _json.loads(lang_plan["plan_json"])
        except Exception:
            pass
    if lang_plan and lang_plan.get("director_json"):
        try:
            director_sections = _json.loads(lang_plan["director_json"])
        except Exception:
            pass
    # フォールバック: lessons テーブルのプラン
    if not plan_sections:
        plan_json_str = lesson.get("plan_json", "")
        if plan_json_str:
            try:
                plan_sections = _json.loads(plan_json_str)
            except Exception:
                pass

    # メインコンテンツ取得
    main_content = None
    mc_str = lesson.get("main_content", "")
    if mc_str:
        try:
            main_content = _json.loads(mc_str)
        except Exception:
            pass

    # キャラ取得（先生・生徒が揃えばv2対話モード）
    characters = get_lesson_characters()
    teacher_config = characters.get("teacher")
    student_config = characters.get("student")

    async def event_stream():
        # 指定言語のGemini生成スクリプトとTTSキャッシュを削除
        clear_tts_cache(lesson_id, lang=lang, generator="gemini")
        db.delete_lesson_sections(lesson_id, lang=lang, generator="gemini")

        progress_queue = asyncio.Queue()

        def on_progress(step, total, message):
            progress_queue.put_nowait({"step": step, "total": total, "message": message})

        restore_lang = _with_lang(lang)

        async def run_generation():
            try:
                # 先生・生徒が揃っている場合はv2（キャラ個別LLM呼び出し）
                if teacher_config and student_config:
                    return await asyncio.to_thread(
                        generate_lesson_script_v2,
                        lesson["name"], extracted_text, plan_sections,
                        director_sections=director_sections,
                        source_images=image_paths or None,
                        on_progress=on_progress,
                        teacher_config=teacher_config,
                        student_config=student_config,
                        main_content=main_content,
                    )
                elif plan_sections:
                    return await asyncio.to_thread(
                        generate_lesson_script_from_plan,
                        lesson["name"], extracted_text, plan_sections, image_paths or None,
                        on_progress=on_progress,
                        student_config=student_config,
                    )
                else:
                    return await asyncio.to_thread(
                        generate_lesson_script,
                        lesson["name"], extracted_text, image_paths or None,
                        on_progress=on_progress,
                        student_config=student_config,
                    )
            finally:
                restore_lang()

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
            gen_result = task.result()
            # v2パイプラインはdict（sections + analysis）、非v2はlist
            if isinstance(gen_result, dict):
                sections = gen_result["sections"]
                embedded_analysis = gen_result.get("analysis")
            else:
                sections = gen_result
                embedded_analysis = None
            saved = []
            for i, s in enumerate(sections):
                # v3: director_sectionsから該当セクションのdialogue_directionsを取得
                dd_str = ""
                if director_sections and i < len(director_sections):
                    dd = director_sections[i].get("dialogue_directions", [])
                    if dd:
                        dd_str = _json.dumps(dd, ensure_ascii=False)
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
                    lang=lang,
                    dialogues=s.get("dialogues", ""),
                    dialogue_directions=dd_str,
                    generator="gemini",
                )
                saved.append(sec)
            logger.info("スクリプト生成完了: lesson=%d, sections=%d", lesson_id, len(saved))

            # --- TTS音声の事前生成 ---
            # 対話モードのキャラ設定を取得
            characters = get_lesson_characters()
            teacher_cfg = characters.get("teacher") or {}
            student_cfg = characters.get("student") or {}
            teacher_voice = teacher_cfg.get("tts_voice")
            student_voice = student_cfg.get("tts_voice")
            teacher_style = teacher_cfg.get("tts_style")
            student_style = student_cfg.get("tts_style")

            # 各セクションのTTS生成単位を計算
            tts_jobs = []  # (cached_path, tts_text, voice, style, label)
            for s in saved:
                oi = s["order_index"]
                dlgs_raw = s.get("dialogues", "")
                dlgs = []
                if dlgs_raw:
                    try:
                        parsed = _json.loads(dlgs_raw) if isinstance(dlgs_raw, str) else dlgs_raw
                        # v4: {dialogues: [...], review: {...}} 形式に対応
                        if isinstance(parsed, dict) and "dialogues" in parsed:
                            dlgs = parsed["dialogues"]
                        else:
                            dlgs = parsed
                    except Exception:
                        pass

                if dlgs:
                    # 対話モード: 各dialogue発話のTTSを個別生成
                    for di, dlg in enumerate(dlgs):
                        speaker = dlg.get("speaker", "teacher")
                        voice = teacher_voice if speaker == "teacher" else student_voice
                        style = teacher_style if speaker == "teacher" else student_style
                        tts_text = dlg.get("tts_text", dlg.get("content", ""))
                        cached = _dlg_cache_path(lesson_id, oi, di, lang=lang)
                        tts_jobs.append((cached, tts_text, voice, style,
                                         f"セクション{oi + 1} 発話{di + 1}"))
                else:
                    # 単話者モード: セクションを文分割してTTS生成
                    content = s["content"]
                    tts_text = s.get("tts_text") or content
                    c_parts = SpeechPipeline.split_sentences(content)
                    t_parts = SpeechPipeline.split_sentences(tts_text)
                    for pi, _part in enumerate(c_parts):
                        part_tts = t_parts[pi] if pi < len(t_parts) else _part
                        cached = _cache_path(lesson_id, oi, pi, lang=lang)
                        tts_jobs.append((cached, part_tts, None, None,
                                         f"セクション{oi + 1} パート{pi + 1}"))

            total_parts = len(tts_jobs)
            generated = 0
            tts_errors = 0
            for cached, tts_text, voice, style, label in tts_jobs:
                generated += 1
                progress_msg = f"TTS生成中: {label} ({generated}/{total_parts})"
                yield f"data: {_json.dumps({'step': generated, 'total': total_parts, 'message': progress_msg, 'phase': 'tts'}, ensure_ascii=False)}\n\n"

                cached.parent.mkdir(parents=True, exist_ok=True)
                try:
                    kwargs = {}
                    if voice:
                        kwargs["voice"] = voice
                    if style:
                        kwargs["style"] = style
                    await asyncio.to_thread(synthesize, tts_text, str(cached), **kwargs)
                    logger.info("[tts-cache] 生成: %s", cached)
                except Exception as e:
                    logger.warning("[tts-cache] 生成失敗 (%s): %s", label, e)
                    tts_errors += 1

            logger.info("TTS事前生成完了: lesson=%d, %d/%d パート (エラー: %d)",
                        lesson_id, generated - tts_errors, total_parts, tts_errors)

            # 品質分析（パイプライン埋め込み or フォールバック）
            if embedded_analysis:
                analysis_dict = embedded_analysis
                analysis_dict["lesson_id"] = lesson_id
            else:
                section_dicts = [dict(s) for s in saved]
                analysis = analyze_content(section_dicts, lang=lang)
                analysis.lesson_id = lesson_id
                analysis_dict = analysis.to_dict()
            db.update_lesson(lesson_id, analysis_json=_json.dumps(analysis_dict, ensure_ascii=False))
            logger.info("品質分析完了: lesson=%d, score=%.1f/%s, rank=%s",
                        lesson_id, analysis_dict.get("total_score", 0),
                        analysis_dict.get("max_score", 0), analysis_dict.get("rank", "?"))

            result = {"ok": True, "sections": saved, "tts_generated": generated - tts_errors, "tts_errors": tts_errors, "analysis": analysis_dict}
        except Exception as e:
            logger.error("スクリプト生成失敗: %s", e)
            result = {"ok": False, "error": str(e)}

        yield f"data: {_json.dumps(result, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
async def start_lesson(lesson_id: int, lang: str = "ja", generator: str = "gemini"):
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
async def get_tts_cache(lesson_id: int, lang: str = "ja", generator: str = "gemini"):
    """TTSキャッシュ状況を取得する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    sections = get_tts_cache_info(lesson_id, lang=lang, generator=generator)
    return {"ok": True, "sections": sections}


@router.post("/api/lessons/{lesson_id}/analyze")
async def analyze_lesson(lesson_id: int, lang: str = "ja"):
    """コンテンツ品質分析（アルゴリズム指標）"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    sections = db.get_lesson_sections(lesson_id, lang=lang)
    if not sections:
        return {"ok": False, "error": "セクションがありません。先にスクリプトを生成してください"}

    section_dicts = [dict(s) for s in sections]
    result = analyze_content(section_dicts, lang=lang)

    result.lesson_id = lesson_id
    analysis_dict = result.to_dict()
    db.update_lesson(lesson_id, analysis_json=_json.dumps(analysis_dict, ensure_ascii=False))
    return {"ok": True, "analysis": analysis_dict}


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
