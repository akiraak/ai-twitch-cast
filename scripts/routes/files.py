"""素材ファイル管理ルート（アバター・背景画像のアップロード・選択・削除）"""

import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from scripts import state
from src.scene_config import load_config_value, save_config_value

router = APIRouter()
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
RESOURCES_DIR = PROJECT_DIR / "resources"

# 素材カテゴリごとのディレクトリとファイル拡張子
CATEGORIES = {
    "avatar": {
        "dir": RESOURCES_DIR / "vrm",
        "extensions": {".vrm"},
        "config_key": "files.active_avatar",
    },
    "background": {
        "dir": RESOURCES_DIR / "images" / "backgrounds",
        "extensions": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
        "config_key": "files.active_background",
    },
}


def _sanitize_filename(name: str) -> str:
    """ファイル名に使えない文字を除去する"""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.strip(". ")
    if not name:
        name = "untitled"
    return name[:200]


@router.get("/api/files/{category}/list")
async def files_list(category: str):
    """カテゴリ内のファイル一覧を返す"""
    cat = CATEGORIES.get(category)
    if not cat:
        return {"ok": False, "error": f"不明なカテゴリ: {category}"}

    cat["dir"].mkdir(parents=True, exist_ok=True)
    active = load_config_value(cat["config_key"], "")

    files = []
    for f in sorted(cat["dir"].iterdir()):
        if f.suffix.lower() in cat["extensions"]:
            files.append({
                "name": f.stem,
                "file": f.name,
                "active": f.name == active,
                "size": f.stat().st_size,
            })
    return {"ok": True, "files": files, "active": active}


@router.post("/api/files/{category}/upload")
async def files_upload(category: str, file: UploadFile = File(...)):
    """ファイルをアップロードする"""
    cat = CATEGORIES.get(category)
    if not cat:
        return {"ok": False, "error": f"不明なカテゴリ: {category}"}

    if not file.filename:
        return {"ok": False, "error": "ファイル名がありません"}

    # 拡張子チェック
    ext = Path(file.filename).suffix.lower()
    if ext not in cat["extensions"]:
        allowed = ", ".join(cat["extensions"])
        return {"ok": False, "error": f"対応していないファイル形式です（対応: {allowed}）"}

    cat["dir"].mkdir(parents=True, exist_ok=True)

    safe_name = _sanitize_filename(Path(file.filename).stem) + ext
    dest = cat["dir"] / safe_name

    # 同名ファイルがある場合は番号付与
    counter = 1
    while dest.exists():
        dest = cat["dir"] / f"{_sanitize_filename(Path(file.filename).stem)}_{counter}{ext}"
        counter += 1

    content = await file.read()
    dest.write_bytes(content)
    logger.info("ファイルアップロード: %s → %s", file.filename, dest.name)

    return {"ok": True, "file": dest.name, "size": len(content)}


class FileSelect(BaseModel):
    file: str


@router.post("/api/files/{category}/select")
async def files_select(category: str, body: FileSelect):
    """アクティブなファイルを選択する"""
    cat = CATEGORIES.get(category)
    if not cat:
        return {"ok": False, "error": f"不明なカテゴリ: {category}"}

    file_path = cat["dir"] / body.file
    if not file_path.exists():
        return {"ok": False, "error": "ファイルが見つかりません"}

    save_config_value(cat["config_key"], body.file)
    logger.info("素材選択: %s → %s", category, body.file)

    # broadcast.htmlに通知
    if category == "avatar":
        await state.broadcast_to_broadcast({
            "type": "avatar_vrm_change",
            "url": f"/resources/vrm/{body.file}",
        })
    elif category == "background":
        await state.broadcast_to_broadcast({
            "type": "background_change",
            "url": f"/resources/images/backgrounds/{body.file}",
        })

    return {"ok": True}


@router.delete("/api/files/{category}")
async def files_delete(category: str, file: str):
    """ファイルを削除する"""
    cat = CATEGORIES.get(category)
    if not cat:
        return {"ok": False, "error": f"不明なカテゴリ: {category}"}

    file_path = cat["dir"] / file
    if not file_path.exists():
        return {"ok": False, "error": "ファイルが見つかりません"}

    # アクティブなファイルを削除する場合は解除
    active = load_config_value(cat["config_key"], "")
    if active == file:
        save_config_value(cat["config_key"], "")

    file_path.unlink()
    logger.info("ファイル削除: %s/%s", category, file)
    return {"ok": True}
