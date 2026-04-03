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
    _load_prompt,
    verify_lesson,
    evaluate_lesson_quality,
    evaluate_category_fit,
    determine_targets,
    improve_sections,
    load_learnings,
    analyze_learnings,
    save_learnings_to_files,
    improve_prompt,
    apply_prompt_diff,
    create_category_prompt,
    _format_character_for_prompt,
    _format_main_content_for_prompt,
)
from src.lesson_runner import clear_tts_cache, get_tts_cache_info
from src.prompt_builder import get_stream_language, set_stream_language
from src.tts_pregenerate import pregenerate_lesson_tts


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

# --- TTS事前生成タスクレジストリ ---
# Key: "{lesson_id}_{lang}_{generator}_{version}"
# Value: {"task": asyncio.Task, "cancel_event": asyncio.Event, "status": dict}
_tts_pregen_tasks: dict[str, dict] = {}


def _tts_pregen_key(lesson_id: int, lang: str, generator: str, version_number: int) -> str:
    return f"{lesson_id}_{lang}_{generator}_{version_number}"


def _start_tts_pregeneration(
    lesson_id: int, lang: str, generator: str, version_number: int
) -> str:
    """TTS事前生成タスクをバックグラウンドで起動する。

    既存タスクがあればキャンセルしてから新規起動。
    Returns: タスクキー
    """
    key = _tts_pregen_key(lesson_id, lang, generator, version_number)

    # 既存タスクがあればキャンセル
    existing = _tts_pregen_tasks.get(key)
    if existing and not existing["task"].done():
        existing["cancel_event"].set()

    cancel_event = asyncio.Event()
    status = {
        "state": "running",
        "total": 0,
        "completed": 0,
        "generated": 0,
        "cached": 0,
        "failed": 0,
        "error": None,
    }

    def on_progress(completed: int, total: int, result: dict):
        status["total"] = total
        status["completed"] = completed
        status["generated"] = result["generated"]
        status["cached"] = result["cached"]
        status["failed"] = result["failed"]

    async def run():
        try:
            result = await pregenerate_lesson_tts(
                lesson_id, lang, generator, version_number,
                cancel_event=cancel_event, on_progress=on_progress,
            )
            status["total"] = result["total"]
            status["generated"] = result["generated"]
            status["cached"] = result["cached"]
            status["failed"] = result["failed"]
            status["completed"] = result["total"] if not result["cancelled"] else status["completed"]
            status["state"] = "completed"
        except Exception as e:
            logger.exception("[tts-pregen] タスクエラー: key=%s", key)
            status["state"] = "error"
            status["error"] = str(e)

    task = asyncio.create_task(run())
    _tts_pregen_tasks[key] = {
        "task": task,
        "cancel_event": cancel_event,
        "status": status,
    }
    logger.info("[tts-pregen] タスク開始: %s", key)
    return key


def _get_tts_pregen_status(lesson_id: int, lang: str = "ja", generator: str = "claude",
                            version_number: int | None = None) -> dict:
    """TTS事前生成の進捗を返す。タスクがなければ idle を返す。"""
    if version_number is None:
        # 該当lesson_idのタスクを検索
        prefix = f"{lesson_id}_"
        for k, v in _tts_pregen_tasks.items():
            if k.startswith(prefix):
                return {**v["status"]}
        return {"state": "idle"}

    key = _tts_pregen_key(lesson_id, lang, generator, version_number)
    entry = _tts_pregen_tasks.get(key)
    if not entry:
        return {"state": "idle"}
    return {**entry["status"]}


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.strip(". ")
    return name[:200] if name else "untitled"


# --- コンテンツ CRUD ---


class LessonCreate(BaseModel):
    name: str
    category: str = ""


class LessonUpdate(BaseModel):
    name: str | None = None
    category: str | None = None


class SectionUpdate(BaseModel):
    content: str | None = None
    tts_text: str | None = None
    display_text: str | None = None
    emotion: str | None = None
    question: str | None = None
    answer: str | None = None
    wait_seconds: int | None = None
    display_properties: dict | None = None


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
    lesson = db.create_lesson(body.name, category=body.category)
    logger.info("コンテンツ作成: %s (id=%d)", body.name, lesson["id"])
    return {"ok": True, "lesson": lesson}


# --- カテゴリ CRUD ---


class CategoryCreate(BaseModel):
    slug: str
    name: str
    description: str = ""
    prompt_content: str = ""


@router.get("/api/lesson-categories")
async def list_categories():
    """カテゴリ一覧"""
    categories = db.get_categories()
    return {"ok": True, "categories": categories}


@router.post("/api/lesson-categories")
async def create_category(body: CategoryCreate):
    """カテゴリ作成"""
    existing = db.get_category_by_slug(body.slug)
    if existing:
        return {"ok": False, "error": f"slug '{body.slug}' は既に存在します"}
    cat = db.create_category(body.slug, body.name,
                             description=body.description, prompt_content=body.prompt_content)
    logger.info("カテゴリ作成: %s (%s)", body.name, body.slug)
    return {"ok": True, "category": cat}


@router.delete("/api/lesson-categories/{category_id}")
async def delete_category(category_id: int):
    """カテゴリ削除（関連授業のcategoryは空文字にリセット）"""
    db.delete_category(category_id)
    return {"ok": True}


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


# --- 学習ループ（{lesson_id}パスより前に定義する必要あり） ---


class AnalyzeLearningsRequest(BaseModel):
    category: str = ""  # 空 = 全カテゴリ


class ImprovePromptRequest(BaseModel):
    category: str = ""  # 空 = 共通プロンプト lesson_generate.md


class ApplyPromptDiffRequest(BaseModel):
    prompt_file: str
    diff_instructions: list[dict]


class CreateCategoryPromptRequest(BaseModel):
    base_prompt_file: str = "lesson_generate.md"


@router.post("/api/lessons/analyze-learnings")
async def api_analyze_learnings(body: AnalyzeLearningsRequest):
    """カテゴリ別に注釈を収集→AIがパターン抽出→学習結果をファイル＆DBに保存"""
    category = body.category

    # カテゴリ情報取得
    cat_name = ""
    cat_desc = ""
    if category:
        cat = db.get_category_by_slug(category)
        if cat:
            cat_name = cat.get("name", "")
            cat_desc = cat.get("description", "")

    try:
        result = await analyze_learnings(
            category=category,
            category_name=cat_name,
            category_description=cat_desc,
        )
    except Exception as e:
        logger.exception("学習分析エラー")
        return {"ok": False, "error": f"学習分析中にエラーが発生しました: {e}"}

    if result.get("error"):
        return {"ok": False, "error": result["error"],
                "prompt": result.get("prompt"), "raw_output": result.get("raw_output")}

    # ファイルに書き出し
    save_learnings_to_files(
        category=category,
        category_learnings=result["category_learnings"],
        common_learnings=result["common_learnings"],
    )

    # DBに保存
    analysis_input = _json.dumps({
        "category": category,
        "section_count": result["section_count"],
    }, ensure_ascii=False)

    learning = db.save_learning(
        category=category,
        analysis_input=analysis_input,
        analysis_output=result["raw_output"],
        learnings_md=result["category_learnings"],
        section_count=result["section_count"],
    )

    logger.info("学習分析完了: category=%s, sections=%d", category or "(all)", result["section_count"])

    return {
        "ok": True,
        "category": category,
        "category_learnings": result["category_learnings"],
        "common_learnings": result["common_learnings"],
        "section_count": result["section_count"],
        "learning_id": learning["id"],
        "prompt": result["prompt"],
        "raw_output": result["raw_output"],
    }


@router.get("/api/lessons/learnings")
async def api_get_learnings(category: str | None = None):
    """カテゴリ別の学習結果・注釈統計を返す"""
    categories = db.get_categories()

    # カテゴリ別の統計を構築
    stats = []
    all_lessons = db.get_all_lessons()

    target_categories = [{"slug": c["slug"], "name": c["name"], "description": c.get("description", "")}
                         for c in categories]
    # 未分類も含める
    target_categories.append({"slug": "", "name": "未分類", "description": ""})

    for cat in target_categories:
        slug = cat["slug"]
        if category is not None and slug != category:
            continue

        # このカテゴリの授業
        cat_lessons = [l for l in all_lessons if l.get("category", "") == slug]
        if not cat_lessons:
            stats.append({
                "category": slug,
                "category_name": cat["name"],
                "lesson_count": 0,
                "annotation_counts": {"good": 0, "needs_improvement": 0, "redo": 0},
                "latest_learning": None,
                "learnings_md": "",
            })
            continue

        # 注釈カウント
        good_count = 0
        ni_count = 0
        redo_count = 0
        for lesson in cat_lessons:
            sections = db.get_lesson_sections(lesson["id"])
            for s in sections:
                r = s.get("annotation_rating", "")
                if r == "good":
                    good_count += 1
                elif r == "needs_improvement":
                    ni_count += 1
                elif r == "redo":
                    redo_count += 1

        # 最新の学習結果
        latest = db.get_latest_learning(slug)

        # ファイルから学習結果を読み込み
        learnings_md = load_learnings(slug)

        stats.append({
            "category": slug,
            "category_name": cat["name"],
            "lesson_count": len(cat_lessons),
            "annotation_counts": {
                "good": good_count,
                "needs_improvement": ni_count,
                "redo": redo_count,
            },
            "latest_learning": {
                "id": latest["id"],
                "created_at": latest["created_at"],
                "section_count": latest["section_count"],
            } if latest else None,
            "learnings_md": learnings_md,
        })

    return {"ok": True, "stats": stats}


@router.post("/api/lessons/improve-prompt")
async def api_improve_prompt(body: ImprovePromptRequest):
    """学習結果をもとに生成プロンプトの改善案をdiff生成"""
    category = body.category

    # カテゴリ情報
    cat_name = ""
    cat_desc = ""
    prompt_content = ""
    if category:
        cat = db.get_category_by_slug(category)
        if cat:
            cat_name = cat.get("name", "")
            cat_desc = cat.get("description", "")
            prompt_content = cat.get("prompt_content", "")

    try:
        result = await improve_prompt(
            category=category,
            category_name=cat_name,
            category_description=cat_desc,
            prompt_content=prompt_content,
        )
    except Exception as e:
        logger.exception("プロンプト改善エラー")
        return {"ok": False, "error": f"プロンプト改善中にエラーが発生しました: {e}"}

    if result.get("error"):
        return {"ok": False, "error": result["error"]}

    # prompt_diff をDBに保存
    diff_json = _json.dumps(result.get("diff_instructions", []), ensure_ascii=False)
    db.save_learning(
        category=category,
        analysis_input=_json.dumps({"action": "improve_prompt", "prompt_file": result.get("prompt_file", "")}, ensure_ascii=False),
        analysis_output=result.get("raw_output", ""),
        prompt_diff=diff_json,
    )

    logger.info("プロンプト改善提案: category=%s, file=%s, diffs=%d",
                category or "(common)", result.get("prompt_file", ""),
                len(result.get("diff_instructions", [])))

    return {
        "ok": True,
        "summary": result["summary"],
        "diff_instructions": result["diff_instructions"],
        "learnings_to_graduate": result["learnings_to_graduate"],
        "prompt_file": result["prompt_file"],
        "prompt": result["prompt"],
        "raw_output": result["raw_output"],
    }


@router.post("/api/lessons/apply-prompt-diff")
async def api_apply_prompt_diff(body: ApplyPromptDiffRequest):
    """プロンプト改善diffを適用する（ユーザー承認後に呼ばれる）"""
    result = apply_prompt_diff(body.prompt_file, body.diff_instructions)
    if result.get("error"):
        return {"ok": False, "error": result["error"]}
    logger.info("プロンプトdiff適用: %s, applied=%d", body.prompt_file, result["applied"])
    return {"ok": True, **result}


@router.post("/api/lesson-categories/{slug}/create-prompt")
async def api_create_category_prompt(slug: str, body: CreateCategoryPromptRequest):
    """カテゴリ専用プロンプトを生成する"""
    cat = db.get_category_by_slug(slug)
    if not cat:
        return {"ok": False, "error": f"カテゴリ '{slug}' が見つかりません"}

    try:
        result = await create_category_prompt(
            base_prompt_file=body.base_prompt_file,
            category_slug=slug,
            category_name=cat["name"],
            category_description=cat.get("description", ""),
        )
    except Exception as e:
        logger.exception("カテゴリ専用プロンプト作成エラー")
        return {"ok": False, "error": f"プロンプト作成中にエラーが発生しました: {e}"}

    if result.get("error"):
        return {"ok": False, "error": result["error"]}

    # カテゴリの prompt_content をDBに保存
    db.update_category(cat["id"], prompt_content=result["content"])

    logger.info("カテゴリ専用プロンプト作成: %s (DB保存)", slug)
    return {"ok": True, "content": result["content"]}


@router.get("/api/lessons/{lesson_id}")
async def get_lesson(lesson_id: int, version: int | None = None):
    """コンテンツ詳細（ソース＋セクション＋言語別プラン＋バージョン一覧付き）

    version パラメータ指定時はそのバージョンのセクションのみ返す。
    省略時は全セクション返す（後方互換）。
    """
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    sources = db.get_lesson_sources(lesson_id)
    sections = db.get_lesson_sections(
        lesson_id,
        version_number=version,
    )
    # バージョン一覧
    versions = db.get_lesson_versions(lesson_id)
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
            "sections_by_generator": sections_by_generator, "plans": plans,
            "versions": versions}


@router.put("/api/lessons/{lesson_id}")
async def update_lesson(lesson_id: int, body: LessonUpdate):
    """コンテンツ名更新"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.category is not None:
        updates["category"] = body.category
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
    lang: str = "ja", generator: str = "claude",
    version: int | None = None,
):
    """外部生成されたセクションをインポートする

    version パラメータ:
    - 指定あり → そのバージョンのセクションを置換
    - 省略（None） → 新バージョン（max+1）を自動作成してインポート
    """
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

    # バージョン決定
    if version is not None:
        # 指定バージョンのセクションを置換
        ver = db.get_lesson_version(lesson_id, lang, generator, version)
        if not ver:
            return {"ok": False, "error": f"バージョン {version} が見つかりません"}
        version_number = version
        db.delete_lesson_sections(lesson_id, lang=lang, generator=generator,
                                  version_number=version_number)
    else:
        # 新バージョンを自動作成
        ver = db.create_lesson_version(lesson_id, lang=lang, generator=generator,
                                       note="インポート")
        version_number = ver["version_number"]

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

        # display_properties: dictならJSON文字列に変換
        display_properties = s.get("display_properties", "")
        if isinstance(display_properties, dict):
            display_properties = _json.dumps(display_properties, ensure_ascii=False)

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
            version_number=version_number,
            display_properties=display_properties,
        )
        saved.append(sec)

    # plan_summary があればプランとして保存
    if body.plan_summary:
        db.upsert_lesson_plan(
            lesson_id, lang,
            knowledge=body.plan_summary,
            generator=generator,
            version_number=version_number,
        )

    logger.info("セクションインポート: lesson=%d, lang=%s, gen=%s, v=%d, sections=%d",
                lesson_id, lang, generator, version_number, len(saved))

    # TTS事前生成をバックグラウンドで開始
    _start_tts_pregeneration(lesson_id, lang, generator, version_number)

    return {"ok": True, "sections": saved, "count": len(saved),
            "version_number": version_number,
            "tts_pregeneration_started": True}


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

    # display_properties は dict → JSON文字列に変換
    if "display_properties" in updates:
        updates["display_properties"] = _json.dumps(updates["display_properties"], ensure_ascii=False)

    # tts_text または content が変更された場合、該当セクションのTTSキャッシュを削除
    if "tts_text" in updates or "content" in updates:
        # セクションの order_index, version_number を取得
        sections = db.get_lesson_sections(lesson_id)
        sec = next((s for s in sections if s["id"] == section_id), None)
        if sec:
            clear_tts_cache(lesson_id, order_index=sec["order_index"],
                            version_number=sec.get("version_number", 1))
            logger.info("TTSキャッシュ削除: lesson=%d, section order=%d, v%d",
                        lesson_id, sec["order_index"], sec.get("version_number", 1))

    db.update_lesson_section(section_id, **updates)
    return {"ok": True}


@router.delete("/api/lessons/{lesson_id}/sections/{section_id}")
async def delete_section(lesson_id: int, section_id: int):
    """セクション削除"""
    # TTSキャッシュ削除
    sections = db.get_lesson_sections(lesson_id)
    sec = next((s for s in sections if s["id"] == section_id), None)
    if sec:
        clear_tts_cache(lesson_id, order_index=sec["order_index"],
                        version_number=sec.get("version_number", 1))

    db.delete_lesson_section(section_id)
    return {"ok": True}


@router.post("/api/lessons/{lesson_id}/start")
async def start_lesson(lesson_id: int, lang: str = "ja", generator: str = "claude",
                       version: int | None = None):
    """授業を開始する

    version パラメータでバージョンを指定。省略時は最新バージョンを使用。
    """
    # バージョン解決: 省略時は最新
    if version is None:
        versions = db.get_lesson_versions(lesson_id, lang=lang, generator=generator)
        version = versions[-1]["version_number"] if versions else 1

    runner = _get_lesson_runner()
    # 授業再生中は配信言語も一時的に合わせる
    _with_lang(lang)
    try:
        await runner.start(lesson_id, lang=lang, generator=generator,
                           version_number=version)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "status": runner.get_status()}


# --- TTSキャッシュ ---


@router.get("/api/lessons/{lesson_id}/tts-cache")
async def get_tts_cache(lesson_id: int, lang: str = "ja", generator: str = "claude",
                        version: int | None = None):
    """TTSキャッシュ状況を取得する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    vn = version or 1
    sections = get_tts_cache_info(lesson_id, lang=lang, generator=generator, version_number=vn)
    return {"ok": True, "sections": sections}



@router.delete("/api/lessons/{lesson_id}/tts-cache")
async def delete_tts_cache(lesson_id: int, lang: str | None = None, generator: str | None = None,
                           version: int | None = None):
    """全TTSキャッシュを削除する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    clear_tts_cache(lesson_id, lang=lang, generator=generator, version_number=version)
    logger.info("TTSキャッシュ全削除: lesson=%d, lang=%s, generator=%s, version=%s", lesson_id, lang or "all", generator or "all", version or "all")
    return {"ok": True}


@router.delete("/api/lessons/{lesson_id}/tts-cache/{order_index}")
async def delete_tts_cache_section(lesson_id: int, order_index: int, lang: str = "ja",
                                   generator: str | None = None, version: int | None = None):
    """特定セクションのTTSキャッシュを削除する"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    clear_tts_cache(lesson_id, order_index=order_index, lang=lang, generator=generator, version_number=version)
    logger.info("TTSキャッシュ削除: lesson=%d, section=%d, lang=%s, generator=%s, version=%s", lesson_id, order_index, lang, generator or "all", version or "all")
    return {"ok": True}


# --- TTS事前生成 API ---


@router.get("/api/lessons/{lesson_id}/tts-pregen-status")
async def tts_pregen_status(lesson_id: int, lang: str = "ja", generator: str = "claude",
                            version: int | None = None):
    """TTS事前生成の進捗を返す"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    status = _get_tts_pregen_status(lesson_id, lang=lang, generator=generator,
                                     version_number=version)
    return {"ok": True, **status}


@router.post("/api/lessons/{lesson_id}/tts-pregen")
async def tts_pregen_trigger(lesson_id: int, lang: str = "ja", generator: str = "claude",
                              version: int | None = None):
    """TTS事前生成を手動トリガーする"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}
    vn = version or 1
    key = _start_tts_pregeneration(lesson_id, lang, generator, vn)
    return {"ok": True, "key": key, "tts_pregeneration_started": True}


@router.post("/api/lessons/{lesson_id}/tts-pregen-cancel")
async def tts_pregen_cancel(lesson_id: int, lang: str = "ja", generator: str = "claude",
                             version: int | None = None):
    """TTS事前生成をキャンセルする"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    if version is not None:
        key = _tts_pregen_key(lesson_id, lang, generator, version)
        entry = _tts_pregen_tasks.get(key)
        if entry and not entry["task"].done():
            entry["cancel_event"].set()
            return {"ok": True, "cancelled": True}
        return {"ok": True, "cancelled": False, "reason": "タスクが見つからないか既に完了"}

    # version未指定: 該当lesson_idの全タスクをキャンセル
    prefix = f"{lesson_id}_"
    cancelled = 0
    for k, v in _tts_pregen_tasks.items():
        if k.startswith(prefix) and not v["task"].done():
            v["cancel_event"].set()
            cancelled += 1
    return {"ok": True, "cancelled": cancelled > 0, "cancelled_count": cancelled}


# --- バージョン CRUD ---


class VersionCreate(BaseModel):
    lang: str = "ja"
    generator: str = "claude"
    note: str = ""
    copy_from: int | None = None  # コピー元バージョン番号


class VersionUpdate(BaseModel):
    note: str | None = None


class AnnotationUpdate(BaseModel):
    rating: str | None = None   # "good" | "needs_improvement" | "redo" | ""
    comment: str | None = None


VALID_RATINGS = {"good", "needs_improvement", "redo", ""}


@router.get("/api/lessons/{lesson_id}/versions")
async def list_versions(lesson_id: int, lang: str | None = None, generator: str | None = None):
    """バージョン一覧取得"""
    versions = db.get_lesson_versions(lesson_id, lang=lang, generator=generator)
    return {"ok": True, "versions": versions}


@router.post("/api/lessons/{lesson_id}/versions")
async def create_version(lesson_id: int, body: VersionCreate):
    """新バージョン作成（copy_from指定でセクション・プランをコピー）"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    ver = db.create_lesson_version(lesson_id, lang=body.lang, generator=body.generator,
                                   note=body.note)
    version_number = ver["version_number"]

    # copy_from でセクション・プランをコピー
    if body.copy_from is not None:
        src_ver = db.get_lesson_version(lesson_id, body.lang, body.generator, body.copy_from)
        if not src_ver:
            return {"ok": False, "error": f"コピー元バージョン {body.copy_from} が見つかりません"}
        # セクションコピー
        src_sections = db.get_lesson_sections(
            lesson_id, lang=body.lang, generator=body.generator,
            version_number=body.copy_from,
        )
        for s in src_sections:
            db.add_lesson_section(
                lesson_id, order_index=s["order_index"],
                section_type=s["section_type"], title=s.get("title", ""),
                content=s["content"], tts_text=s.get("tts_text", ""),
                display_text=s.get("display_text", ""),
                emotion=s.get("emotion", "neutral"),
                question=s.get("question", ""), answer=s.get("answer", ""),
                wait_seconds=s.get("wait_seconds", 8),
                lang=body.lang, dialogues=s.get("dialogues", ""),
                dialogue_directions=s.get("dialogue_directions", ""),
                generator=body.generator, version_number=version_number,
            )
        # プランコピー
        src_plan = db.get_lesson_plan(lesson_id, body.lang, generator=body.generator,
                                      version_number=body.copy_from)
        if src_plan:
            db.upsert_lesson_plan(
                lesson_id, body.lang,
                knowledge=src_plan.get("knowledge", ""),
                entertainment=src_plan.get("entertainment", ""),
                plan_json=src_plan.get("plan_json", ""),
                director_json=src_plan.get("director_json", ""),
                plan_generations=src_plan.get("plan_generations", ""),
                generator=body.generator, version_number=version_number,
            )

    logger.info("バージョン作成: lesson=%d, lang=%s, gen=%s, v=%d%s",
                lesson_id, body.lang, body.generator, version_number,
                f" (copy from v{body.copy_from})" if body.copy_from else "")
    return {"ok": True, "version": ver}


@router.put("/api/lessons/{lesson_id}/versions/{version_number}")
async def update_version(lesson_id: int, version_number: int, body: VersionUpdate,
                         lang: str = "ja", generator: str = "claude"):
    """バージョンメモ更新"""
    ver = db.get_lesson_version(lesson_id, lang, generator, version_number)
    if not ver:
        return {"ok": False, "error": "バージョンが見つかりません"}
    updates = {}
    if body.note is not None:
        updates["note"] = body.note
    if updates:
        db.update_lesson_version(ver["id"], **updates)
    return {"ok": True}


@router.delete("/api/lessons/{lesson_id}/versions/{version_number}")
async def delete_version(lesson_id: int, version_number: int,
                         lang: str = "ja", generator: str = "claude"):
    """バージョン削除（セクション・プランも削除）"""
    ver = db.get_lesson_version(lesson_id, lang, generator, version_number)
    if not ver:
        return {"ok": False, "error": "バージョンが見つかりません"}
    db.delete_lesson_version(lesson_id, lang, generator, version_number)
    logger.info("バージョン削除: lesson=%d, lang=%s, gen=%s, v=%d",
                lesson_id, lang, generator, version_number)
    return {"ok": True}


# --- セクション注釈 ---


@router.put("/api/lessons/{lesson_id}/sections/{section_id}/annotation")
async def update_annotation(lesson_id: int, section_id: int, body: AnnotationUpdate):
    """セクションの注釈（◎/△/✕ + コメント）を更新する。指定フィールドのみ更新。"""
    if body.rating is not None and body.rating not in VALID_RATINGS:
        return {"ok": False, "error": f"不正な rating: {body.rating}（good/needs_improvement/redo のいずれか）"}
    db.update_section_annotation(section_id, rating=body.rating, comment=body.comment)
    return {"ok": True}


# --- 検証 & 改善 ---


class VerifyRequest(BaseModel):
    lang: str = "ja"
    generator: str = "claude"
    version_number: int | None = None  # 省略時は最新バージョン


class ImproveRequest(BaseModel):
    source_version: int
    lang: str = "ja"
    generator: str = "claude"
    target_sections: list[int]  # order_index のリスト
    verify_result: dict | None = None
    user_instructions: str = ""


@router.post("/api/lessons/{lesson_id}/verify")
async def verify_content(lesson_id: int, body: VerifyRequest):
    """元教材との整合性チェック（coverage/contradictions）"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    # バージョン決定
    version_number = body.version_number
    if version_number is None:
        versions = db.get_lesson_versions(lesson_id, lang=body.lang, generator=body.generator)
        if not versions:
            return {"ok": False, "error": "バージョンが見つかりません"}
        version_number = versions[-1]["version_number"]

    ver = db.get_lesson_version(lesson_id, body.lang, body.generator, version_number)
    if not ver:
        return {"ok": False, "error": f"バージョン {version_number} が見つかりません"}

    sections = db.get_lesson_sections(
        lesson_id, lang=body.lang, generator=body.generator,
        version_number=version_number,
    )
    if not sections:
        return {"ok": False, "error": "セクションがありません"}

    # 元教材
    extracted_text = lesson.get("extracted_text", "")
    main_content_raw = lesson.get("main_content", "")
    main_content = []
    if main_content_raw:
        try:
            main_content = _json.loads(main_content_raw) if isinstance(main_content_raw, str) else main_content_raw
        except (_json.JSONDecodeError, TypeError):
            pass

    if not extracted_text and not main_content:
        return {"ok": False, "error": "元教材テキストがありません（extracted_text/main_content が空）"}

    en = body.lang == "en"

    try:
        result = await verify_lesson(
            extracted_text=extracted_text,
            main_content=main_content,
            sections=sections,
            en=en,
        )
    except Exception as e:
        logger.exception("検証エラー: lesson=%d", lesson_id)
        return {"ok": False, "error": f"検証中にエラーが発生しました: {e}"}

    # 結果をDBに保存
    verify_json = _json.dumps(result["result"], ensure_ascii=False)
    db.save_version_verify(ver["id"], verify_json)

    logger.info("検証完了: lesson=%d, v=%d, coverage=%d, contradictions=%d",
                lesson_id, version_number,
                len(result["result"].get("coverage", [])),
                len(result["result"].get("contradictions", [])))

    return {
        "ok": True,
        "version_number": version_number,
        "verify_result": result["result"],
        "prompt": result["prompt"],
        "raw_output": result["raw_output"],
    }


@router.post("/api/lessons/{lesson_id}/improve")
async def improve_content(lesson_id: int, body: ImproveRequest):
    """指定バージョンから部分改善 → 新バージョン作成"""
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return {"ok": False, "error": "コンテンツが見つかりません"}

    # ソースバージョン確認
    src_ver = db.get_lesson_version(lesson_id, body.lang, body.generator, body.source_version)
    if not src_ver:
        return {"ok": False, "error": f"ソースバージョン {body.source_version} が見つかりません"}

    src_sections = db.get_lesson_sections(
        lesson_id, lang=body.lang, generator=body.generator,
        version_number=body.source_version,
    )
    if not src_sections:
        return {"ok": False, "error": "ソースバージョンにセクションがありません"}

    # 元教材
    extracted_text = lesson.get("extracted_text", "")
    main_content_raw = lesson.get("main_content", "")
    main_content = []
    if main_content_raw:
        try:
            main_content = _json.loads(main_content_raw) if isinstance(main_content_raw, str) else main_content_raw
        except (_json.JSONDecodeError, TypeError):
            pass

    # キャラクター情報
    en = body.lang == "en"
    chars = get_lesson_characters()
    char_lines = []
    if chars.get("teacher"):
        char_lines.append(_format_character_for_prompt(chars["teacher"], "teacher", en))
    if chars.get("student"):
        char_lines.append(_format_character_for_prompt(chars["student"], "student", en))
    character_info = "\n\n".join(char_lines)

    # カテゴリ
    category = lesson.get("category", "")

    # 検証結果（リクエストから or DB保存分）
    verify_result = body.verify_result
    if verify_result is None and src_ver.get("verify_json"):
        try:
            verify_result = _json.loads(src_ver["verify_json"])
        except (_json.JSONDecodeError, TypeError):
            pass

    # --- 自動判定フロー: target_sections が空の場合 ---
    auto_detected = False
    evaluation = None
    if not body.target_sections:
        import asyncio
        logger.info("自動判定開始: lesson=%d, v=%d", lesson_id, body.source_version)

        # ① 元教材整合性（DB保存分がなければ実行）
        verify_for_eval = verify_result
        verify_prompt_info = None
        verify_raw = None
        if verify_for_eval is None:
            try:
                vr = await verify_lesson(
                    extracted_text=extracted_text,
                    main_content=main_content,
                    sections=src_sections,
                    en=en,
                )
                verify_for_eval = vr["result"]
                verify_prompt_info = vr["prompt"]
                verify_raw = vr["raw_output"]
                # DB保存
                verify_json_str = _json.dumps(verify_for_eval, ensure_ascii=False)
                db.save_version_verify(src_ver["id"], verify_json_str)
            except Exception as e:
                logger.warning("自動判定: verify失敗（続行）: %s", e)

        # ② 授業品質 + ③ カテゴリ適合性（並列実行）
        generation_prompt = _load_prompt("lesson_generate.md")

        eval_tasks = [
            evaluate_lesson_quality(
                sections=src_sections,
                generation_prompt=generation_prompt,
                en=en,
            )
        ]

        # カテゴリ専用プロンプトがある場合のみ③を実行
        category_row = db.get_category_by_slug(category) if category else None
        has_category_prompt = category_row and category_row.get("prompt_content")
        if has_category_prompt:
            eval_tasks.append(
                evaluate_category_fit(
                    sections=src_sections,
                    category_prompt=category_row["prompt_content"],
                    category_name=category_row["name"],
                    category_description=category_row.get("description", ""),
                    en=en,
                )
            )

        try:
            eval_results = await asyncio.gather(*eval_tasks)
        except Exception as e:
            logger.exception("自動判定: 評価エラー: lesson=%d", lesson_id)
            return {"ok": False, "error": f"AI自動判定中にエラーが発生しました: {e}"}

        quality_result_full = eval_results[0]
        category_result_full = eval_results[1] if has_category_prompt else None

        # 3軸統合
        auto_targets, auto_instructions = determine_targets(
            verify_for_eval,
            quality_result_full["result"],
            category_result_full["result"] if category_result_full else None,
            src_sections,
        )

        if not auto_targets:
            # 全軸で問題なし
            evaluation = {
                "verify_result": verify_for_eval,
                "quality_result": quality_result_full["result"],
                "category_result": category_result_full["result"] if category_result_full else None,
                "detection_summary": "問題なし — 改善対象セクションが見つかりませんでした",
            }
            return {
                "ok": True,
                "no_issues": True,
                "evaluation": evaluation,
                "quality_prompt": quality_result_full["prompt"],
                "quality_raw_output": quality_result_full["raw_output"],
                "category_prompt": category_result_full["prompt"] if category_result_full else None,
                "category_raw_output": category_result_full["raw_output"] if category_result_full else None,
                "verify_prompt": verify_prompt_info,
                "verify_raw_output": verify_raw,
            }

        # 自動判定の結果で target_sections と user_instructions を設定
        body.target_sections = auto_targets
        if auto_instructions:
            if body.user_instructions:
                body.user_instructions = f"{body.user_instructions}\n\n{auto_instructions}"
            else:
                body.user_instructions = auto_instructions
        # verify_result も更新
        verify_result = verify_for_eval
        auto_detected = True

        # 評価結果サマリ構築
        verify_weak = len([c for c in (verify_for_eval or {}).get("coverage", []) if c.get("status") == "weak"])
        verify_missing = len([c for c in (verify_for_eval or {}).get("coverage", []) if c.get("status") == "missing"])
        verify_contradictions = len((verify_for_eval or {}).get("contradictions", []))
        quality_major = len([q for q in quality_result_full["result"].get("quality_issues", []) if q.get("severity") == "major"])
        quality_minor = len([q for q in quality_result_full["result"].get("quality_issues", []) if q.get("severity") == "minor"])
        cat_major = 0
        cat_minor = 0
        if category_result_full:
            cat_major = len([c for c in category_result_full["result"].get("category_issues", []) if c.get("severity") == "major"])
            cat_minor = len([c for c in category_result_full["result"].get("category_issues", []) if c.get("severity") == "minor"])

        summary_parts = [
            f"教材整合性: weak {verify_weak} / missing {verify_missing} / 矛盾 {verify_contradictions}",
            f"授業品質: major {quality_major} / minor {quality_minor}",
        ]
        if category_result_full:
            summary_parts.append(f"カテゴリ: major {cat_major} / minor {cat_minor}")
        summary_parts.append(f"→ 改善対象: セクション {auto_targets}")

        evaluation = {
            "verify_result": verify_for_eval,
            "quality_result": quality_result_full["result"],
            "category_result": category_result_full["result"] if category_result_full else None,
            "detection_summary": " / ".join(summary_parts),
            "quality_prompt": quality_result_full["prompt"],
            "quality_raw_output": quality_result_full["raw_output"],
            "category_prompt": category_result_full["prompt"] if category_result_full else None,
            "category_raw_output": category_result_full["raw_output"] if category_result_full else None,
            "verify_prompt": verify_prompt_info,
            "verify_raw_output": verify_raw,
        }

        logger.info("自動判定完了: lesson=%d, targets=%s", lesson_id, auto_targets)

    # target_sections の検証
    existing_indices = {s["order_index"] for s in src_sections}
    invalid = [i for i in body.target_sections if i not in existing_indices]
    if invalid:
        return {"ok": False, "error": f"存在しない order_index: {invalid}"}

    try:
        result = await improve_sections(
            extracted_text=extracted_text,
            main_content=main_content,
            all_sections=src_sections,
            target_indices=body.target_sections,
            verify_result=verify_result,
            user_instructions=body.user_instructions,
            category=category,
            character_info=character_info,
            en=en,
        )
    except Exception as e:
        logger.exception("改善エラー: lesson=%d", lesson_id)
        return {"ok": False, "error": f"改善中にエラーが発生しました: {e}"}

    improved = result["sections"]
    if not improved:
        return {"ok": False, "error": "AIが改善セクションを生成できませんでした",
                "prompt": result["prompt"], "raw_output": result["raw_output"]}

    # 新バージョン作成
    improved_indices = [s.get("order_index", -1) for s in improved]
    new_ver = db.create_lesson_version(
        lesson_id, lang=body.lang, generator=body.generator,
        note=f"v{body.source_version}から改善",
        improve_source_version=body.source_version,
        improve_summary=body.user_instructions or "部分改善",
        improved_sections=_json.dumps(improved_indices),
    )
    new_version_number = new_ver["version_number"]

    # セクション保存: 改善対象は新セクション、それ以外はソースからコピー
    improved_by_index = {s.get("order_index", -1): s for s in improved}
    saved = []
    for src_sec in src_sections:
        idx = src_sec["order_index"]
        if idx in improved_by_index:
            s = improved_by_index[idx]
            dialogues = s.get("dialogues", "")
            if isinstance(dialogues, (list, dict)):
                dialogues = _json.dumps(dialogues, ensure_ascii=False)
            dialogue_directions = s.get("dialogue_directions", "")
            if isinstance(dialogue_directions, (list, dict)):
                dialogue_directions = _json.dumps(dialogue_directions, ensure_ascii=False)
            display_properties = s.get("display_properties", "")
            if isinstance(display_properties, dict):
                display_properties = _json.dumps(display_properties, ensure_ascii=False)
            sec = db.add_lesson_section(
                lesson_id, order_index=idx,
                section_type=s.get("section_type", src_sec["section_type"]),
                title=s.get("title", src_sec.get("title", "")),
                content=s.get("content", ""),
                tts_text=s.get("tts_text", ""),
                display_text=s.get("display_text", ""),
                emotion=s.get("emotion", "neutral"),
                question=s.get("question", ""),
                answer=s.get("answer", ""),
                wait_seconds=s.get("wait_seconds", 3),
                lang=body.lang,
                dialogues=dialogues,
                dialogue_directions=dialogue_directions,
                generator=body.generator,
                version_number=new_version_number,
                display_properties=display_properties,
            )
        else:
            # ソースからコピー
            sec = db.add_lesson_section(
                lesson_id, order_index=idx,
                section_type=src_sec["section_type"],
                title=src_sec.get("title", ""),
                content=src_sec["content"],
                tts_text=src_sec.get("tts_text", ""),
                display_text=src_sec.get("display_text", ""),
                emotion=src_sec.get("emotion", "neutral"),
                question=src_sec.get("question", ""),
                answer=src_sec.get("answer", ""),
                wait_seconds=src_sec.get("wait_seconds", 8),
                lang=body.lang,
                dialogues=src_sec.get("dialogues", ""),
                dialogue_directions=src_sec.get("dialogue_directions", ""),
                generator=body.generator,
                version_number=new_version_number,
                display_properties=src_sec.get("display_properties", ""),
            )
        saved.append(sec)

    # プランもコピー
    src_plan = db.get_lesson_plan(lesson_id, body.lang, generator=body.generator,
                                  version_number=body.source_version)
    if src_plan:
        db.upsert_lesson_plan(
            lesson_id, body.lang,
            knowledge=src_plan.get("knowledge", ""),
            entertainment=src_plan.get("entertainment", ""),
            plan_json=src_plan.get("plan_json", ""),
            director_json=src_plan.get("director_json", ""),
            plan_generations=src_plan.get("plan_generations", ""),
            generator=body.generator, version_number=new_version_number,
        )

    logger.info("改善完了: lesson=%d, v%d→v%d, improved=%s",
                lesson_id, body.source_version, new_version_number, improved_indices)

    # TTS事前生成をバックグラウンドで開始
    _start_tts_pregeneration(lesson_id, body.lang, body.generator, new_version_number)

    resp = {
        "ok": True,
        "version_number": new_version_number,
        "improved_sections": improved_indices,
        "sections": saved,
        "prompt": result["prompt"],
        "raw_output": result["raw_output"],
        "tts_pregeneration_started": True,
    }
    if auto_detected:
        resp["auto_detected"] = True
        resp["evaluation"] = evaluation
    return resp
