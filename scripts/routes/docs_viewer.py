"""ドキュメント閲覧ルート（plans/ docs/ のMarkdownファイル）"""

import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

logger = logging.getLogger(__name__)

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ALLOWED_DIRS = {"plans", "docs", "prompts"}


@router.get("/api/docs/files")
async def list_doc_files(dir: str = "plans"):
    """指定ディレクトリのMarkdownファイル一覧を返す"""
    if dir not in ALLOWED_DIRS:
        return {"ok": False, "error": f"許可されていないディレクトリです: {dir}"}

    target = PROJECT_ROOT / dir
    if not target.is_dir():
        return {"ok": True, "files": []}

    files = []
    for p in target.rglob("*.md"):
        rel = p.relative_to(target)
        stat = p.stat()
        title = ""
        try:
            with p.open("r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("# "):
                    title = first_line[2:].strip()
        except Exception:
            pass
        files.append({
            "name": str(rel),
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "title": title,
        })

    return {"ok": True, "files": files}


@router.get("/api/docs/file")
async def get_doc_file(dir: str = "plans", name: str = ""):
    """指定Markdownファイルの内容を返す"""
    if dir not in ALLOWED_DIRS:
        return PlainTextResponse("許可されていないディレクトリです", status_code=400)

    if not name or ".." in name or not name.endswith(".md"):
        return PlainTextResponse("不正なファイル名です", status_code=400)

    target = (PROJECT_ROOT / dir / name).resolve()
    allowed_root = (PROJECT_ROOT / dir).resolve()
    if not str(target).startswith(str(allowed_root)):
        return PlainTextResponse("不正なファイルパスです", status_code=400)

    if not target.is_file():
        return PlainTextResponse("ファイルが見つかりません", status_code=404)

    return PlainTextResponse(target.read_text(encoding="utf-8"))


@router.post("/api/docs/archive-plan")
async def archive_plan(name: str = ""):
    """plans/<name> を plans/archive/<name> に移動する

    <name> は plans/ 直下の .md ファイル または サブディレクトリ（例: teacher-mode-v2/）。
    サブディレクトリ内のファイル単体やパストラバーサルは拒否。
    archive 自身の移動も拒否。同名が archive に既にある場合は上書きせずエラーにする。
    """
    if not name or "/" in name or "\\" in name or ".." in name:
        return JSONResponse({"ok": False, "error": "不正な名前です"}, status_code=400)

    plans_root = (PROJECT_ROOT / "plans").resolve()
    archive_root = plans_root / "archive"
    src = (plans_root / name).resolve()
    dst = (archive_root / name).resolve()

    # plans/ 配下から出ていないか確認（シンボリックリンク等の脱出対策）
    try:
        src.relative_to(plans_root)
        dst.relative_to(archive_root)
    except ValueError:
        return JSONResponse({"ok": False, "error": "不正なファイルパスです"}, status_code=400)

    # plans/ 直下以外、または archive 自身は拒否
    if src.parent != plans_root or src == archive_root:
        return JSONResponse({"ok": False, "error": "plans/ 直下のファイル/ディレクトリのみアーカイブできます"}, status_code=400)

    if not src.exists():
        return JSONResponse({"ok": False, "error": "ファイル/ディレクトリが見つかりません"}, status_code=404)

    # ファイルは .md のみ対応、ディレクトリはそのまま
    if src.is_file() and not name.endswith(".md"):
        return JSONResponse({"ok": False, "error": "ファイルは .md のみアーカイブできます"}, status_code=400)

    if not src.is_file() and not src.is_dir():
        return JSONResponse({"ok": False, "error": "通常ファイルまたはディレクトリではありません"}, status_code=400)

    if dst.exists():
        return JSONResponse({"ok": False, "error": f"archive に同名が既にあります: {name}"}, status_code=409)

    archive_root.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    logger.info("plan をアーカイブ: %s → %s", src, dst)
    return {"ok": True, "moved_to": f"archive/{name}"}
