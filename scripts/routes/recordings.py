"""録画ファイル管理ルート

C#ネイティブ配信アプリから `POST /api/recordings/upload` でMP4を受信し、
`<repo>/videos/` に保存する。管理画面から一覧・ダウンロード・削除ができる。
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter()
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
VIDEOS_DIR = PROJECT_DIR / "videos"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

FILENAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+\.mp4$")
CHUNK_SIZE = 1024 * 1024  # 1MB


def cleanup_partials():
    """前回アップロード中断で残った .part ファイルを削除する（起動時に呼ぶ）。"""
    for part in VIDEOS_DIR.glob(".*.part"):
        try:
            part.unlink()
            logger.info("部分アップロードファイル削除: %s", part.name)
        except OSError as e:
            logger.warning("部分ファイル削除失敗 %s: %s", part.name, e)


# モジュール読み込み時に一度だけ実行（web.py lifespan経由でも可だがここで十分）
cleanup_partials()


def _safe_filename(name: str) -> str:
    """ファイル名を検証する。パストラバーサルと非MP4を拒否。"""
    if not name or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, f"invalid filename: {name!r}")
    if not FILENAME_RE.match(name):
        raise HTTPException(400, f"filename must match {FILENAME_RE.pattern}")
    return name


@router.post("/api/recordings/upload")
async def upload_recording(
    request: Request,
    x_filename: str = Header(..., alias="X-Filename"),
):
    """MP4をストリーミング受信して `videos/` に保存する。

    - リクエストボディは MP4 の生バイト列（`application/octet-stream`）
    - 受信中は `.{filename}.part` に書き、成功したらrename
    - ファイル名検証でパストラバーサル等は400
    """
    filename = _safe_filename(x_filename)
    dest = VIDEOS_DIR / filename
    part = VIDEOS_DIR / f".{filename}.part"

    total = 0
    try:
        with open(part, "wb") as f:
            async for chunk in request.stream():
                if not chunk:
                    continue
                f.write(chunk)
                total += len(chunk)
        part.replace(dest)
    except Exception as e:
        logger.error("録画アップロード失敗: %s (%d bytes 書き込み済み) err=%s",
                     filename, total, e)
        if part.exists():
            try:
                part.unlink()
            except Exception:
                pass
        raise HTTPException(500, f"upload failed: {e}")

    logger.info("録画アップロード完了: %s (%d bytes)", filename, total)
    return {
        "ok": True,
        "filename": filename,
        "size": total,
        "saved_path": str(dest),
    }


@router.get("/api/recordings")
async def list_recordings():
    """`videos/` の MP4 一覧をmtime降順で返す。"""
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(VIDEOS_DIR.glob("*.mp4"),
                    key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            st = p.stat()
            items.append({
                "filename": p.name,
                "size_bytes": st.st_size,
                "created_at": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(
                    timespec="seconds"),
                # 長さは v1 ではスキップ（MP4メタ解析は将来拡張）
                "duration_sec": None,
            })
        except FileNotFoundError:
            continue
    return {"recordings": items}


@router.get("/api/recordings/{filename}/download")
async def download_recording(filename: str):
    """ダウンロード用エンドポイント（Content-Disposition: attachment 付き）。"""
    filename = _safe_filename(filename)
    path = VIDEOS_DIR / filename
    if not path.exists():
        raise HTTPException(404, "not found")
    return FileResponse(
        path=str(path),
        media_type="video/mp4",
        filename=filename,
    )


@router.delete("/api/recordings/{filename}")
async def delete_recording(filename: str):
    """録画ファイルを削除する。"""
    filename = _safe_filename(filename)
    path = VIDEOS_DIR / filename
    if not path.exists():
        raise HTTPException(404, "not found")
    path.unlink()
    logger.info("録画削除: %s", filename)
    return {"ok": True, "filename": filename}
