"""SE（効果音）ルート — 一覧・再生テスト・トラック管理・アップロード"""

import logging
import wave
from pathlib import Path

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from scripts import state
from src import db

router = APIRouter()
logger = logging.getLogger(__name__)

SE_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "audio" / "se"


def _get_wav_duration(filepath: Path) -> float:
    """WAVファイルの長さ（秒）を取得する"""
    try:
        with wave.open(str(filepath), "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 1.0


def scan_and_register_se():
    """SE_DIR内のファイルをスキャンしてDBに未登録のものを登録する"""
    SE_DIR.mkdir(parents=True, exist_ok=True)
    existing = db.get_all_se_tracks()
    for f in SE_DIR.iterdir():
        if f.suffix.lower() in (".wav", ".mp3", ".ogg", ".m4a"):
            if f.name not in existing:
                duration = _get_wav_duration(f)
                category = f.stem  # ファイル名をカテゴリとして使う
                db.upsert_se_track(f.name, category=category,
                                   description="", volume=1.0, duration=duration)
                logger.info("SE自動登録: %s (category=%s, duration=%.2fs)", f.name, category, duration)


@router.get("/api/se/list")
async def se_list():
    """SE一覧を返す（カテゴリ・音量・説明付き）"""
    SE_DIR.mkdir(parents=True, exist_ok=True)
    all_tracks = db.get_all_se_tracks()
    tracks = []
    for f in sorted(SE_DIR.iterdir()):
        if f.suffix.lower() in (".wav", ".mp3", ".ogg", ".m4a"):
            info = all_tracks.get(f.name, {})
            tracks.append({
                "file": f.name,
                "name": f.stem,
                "category": info.get("category", f.stem),
                "description": info.get("description", ""),
                "volume": info.get("volume", 1.0),
                "duration": info.get("duration", 1.0),
            })
    return {"tracks": tracks}


class SEPlay(BaseModel):
    file: str


@router.post("/api/se/play")
async def se_play(body: SEPlay):
    """SE再生テスト（C#アプリに送信）"""
    file_path = SE_DIR / body.file
    if not file_path.exists():
        return {"ok": False, "error": "ファイルが見つかりません"}

    all_tracks = db.get_all_se_tracks()
    info = all_tracks.get(body.file, {})
    track_volume = info.get("volume", 1.0)

    await state.broadcast_se({
        "type": "se_play",
        "url": f"/se/{body.file}",
        "volume": track_volume,
    })
    return {"ok": True}


class SETrackUpdate(BaseModel):
    file: str
    category: str = ""
    description: str = ""
    volume: float = 1.0


@router.post("/api/se/track")
async def se_track_update(body: SETrackUpdate):
    """SEトラック情報を更新する"""
    file_path = SE_DIR / body.file
    if not file_path.exists():
        return {"ok": False, "error": "ファイルが見つかりません"}
    duration = _get_wav_duration(file_path)
    db.upsert_se_track(body.file, category=body.category,
                       description=body.description, volume=body.volume,
                       duration=duration)
    return {"ok": True}


@router.delete("/api/se/track")
async def se_track_delete(file: str):
    """SEトラックを削除する"""
    file_path = SE_DIR / file
    if not file_path.exists():
        return {"ok": False, "error": "ファイルが見つかりません"}
    file_path.unlink()
    db.delete_se_track(file)
    logger.info("SEトラック削除: %s", file)
    return {"ok": True}


@router.post("/api/se/upload")
async def se_upload(file: UploadFile):
    """SEファイルをアップロードする"""
    if not file.filename:
        return {"ok": False, "error": "ファイル名がありません"}

    SE_DIR.mkdir(parents=True, exist_ok=True)
    dest = SE_DIR / file.filename
    content = await file.read()
    dest.write_bytes(content)

    duration = _get_wav_duration(dest)
    category = dest.stem
    db.upsert_se_track(dest.name, category=category, description="",
                       volume=1.0, duration=duration)
    logger.info("SEアップロード: %s (%.2fs)", dest.name, duration)
    return {"ok": True, "file": dest.name, "duration": duration}
