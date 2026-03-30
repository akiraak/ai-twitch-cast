"""ドキュメント閲覧ルート（plans/ docs/ のMarkdownファイル）"""

import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ALLOWED_DIRS = {"plans", "docs"}


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
