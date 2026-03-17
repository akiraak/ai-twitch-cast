"""ウィンドウキャプチャルート - Windows配信アプリ経由のウィンドウキャプチャ"""

import base64
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from scripts import state
from scripts.services.capture_client import (
    capture_base_url,
    proxy_request,
    ws_request,
)
from src import db

logger = logging.getLogger(__name__)
router = APIRouter()


# =====================================================
# サーバー管理
# =====================================================


@router.get("/api/capture/status")
async def capture_status():
    """キャプチャサーバーの状態を返す"""
    try:
        data = await proxy_request("GET", "/status")
        return {"running": True, **data}
    except Exception:
        return {"running": False}


# =====================================================
# ウィンドウ操作
# =====================================================


@router.get("/api/capture/windows")
async def capture_windows():
    """Windows側のウィンドウ一覧を取得"""
    try:
        return await proxy_request("GET", "/windows")
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"キャプチャサーバーに接続できません: {e}"
        )


# =====================================================
# キャプチャ操作
# =====================================================


class CaptureStartRequest(BaseModel):
    sourceId: str
    id: str | None = None
    label: str | None = None
    fps: int | None = None
    quality: float | None = None


# =====================================================
# 保存済みキャプチャ設定API
# NOTE: /api/capture/{capture_id} より前に定義する必要がある（パス競合防止）
# =====================================================


@router.get("/api/capture/saved")
async def capture_saved_list():
    """保存済みキャプチャウィンドウ一覧"""
    rows = db.get_capture_windows()
    return [_row_to_config(r) for r in rows]


@router.delete("/api/capture/saved")
async def capture_saved_delete(request: Request):
    """保存済みキャプチャウィンドウを削除"""
    body = await request.json()
    window_name = body.get("window_name", "")
    if window_name:
        db.delete_capture_window(window_name)
    return {"ok": True}


@router.post("/api/capture/restore")
async def capture_restore():
    """保存済み設定からウィンドウ名マッチングでキャプチャを復元"""
    saved = db.get_capture_windows()
    if not saved:
        return {"ok": True, "restored": 0, "message": "保存済み設定なし"}

    try:
        windows = await proxy_request("GET", "/windows")
    except Exception as e:
        return {"ok": False, "error": f"配信アプリに接続できません: {e}"}

    # 現在アクティブなキャプチャのウィンドウ名を取得
    try:
        active = await proxy_request("GET", "/captures")
        active_names = {c.get("name", "") for c in active}
    except Exception:
        active_names = set()

    restored = 0
    for row in saved:
        wname = row["window_name"]
        if wname in active_names:
            continue

        # ウィンドウ名マッチング（完全一致 → 部分一致）
        match = None
        for w in windows:
            if w["name"] == wname:
                match = w
                break
        if not match:
            for w in windows:
                if wname in w["name"] or w["name"] in wname:
                    match = w
                    break

        if not match:
            continue

        try:
            data = await proxy_request("POST", "/capture", {"sourceId": match.get("sourceId") or match["id"]})
            if data.get("ok"):
                cid = data["id"]
                layout = _row_to_layout(row)
                label = row.get("label", wname)
                _save_capture_layout(cid, layout, label, window_name=match["name"])
                # 名前が変わっていたら保存済み設定も更新
                if match["name"] != wname:
                    db.upsert_capture_window(match["name"], label, layout)
                await state.broadcast_to_broadcast({
                    "type": "capture_add",
                    "id": cid,
                    "stream_url": f"{capture_base_url()}/stream/{cid}",
                    "label": label,
                    "layout": layout,
                })
                restored += 1
        except Exception as e:
            logger.warning("キャプチャ復元失敗 %s: %s", wname, e)

    return {"ok": True, "restored": restored}


# =====================================================
# スクリーンショット（デバッグ用）
# NOTE: /api/capture/{capture_id} より前に定義する必要がある（パス競合防止）
# =====================================================

SCREENSHOT_DIR = Path("/tmp/screenshots")


@router.post("/api/capture/screenshot")
async def capture_screenshot():
    """broadcast画面のスクリーンショットを撮影して/tmp/screenshots/に保存"""
    try:
        result = await ws_request("screenshot", timeout=10.0)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"配信アプリに接続できません: {e}")

    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "スクリーンショット失敗"))

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{timestamp}.png"
    filepath = SCREENSHOT_DIR / filename

    png_data = base64.b64decode(result["png_base64"])
    filepath.write_bytes(png_data)
    logger.info("スクリーンショット保存: %s (%d bytes)", filepath, len(png_data))

    return {"ok": True, "file": filename, "path": str(filepath), "size": len(png_data)}


@router.get("/api/capture/screenshots")
async def capture_screenshots_list():
    """保存済みスクリーンショットの一覧を返す"""
    if not SCREENSHOT_DIR.exists():
        return {"files": []}

    files = []
    for f in sorted(SCREENSHOT_DIR.glob("screenshot_*.png"), reverse=True):
        stat = f.stat()
        files.append({
            "name": f.name,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return {"files": files}


@router.get("/api/capture/screenshots/{filename}")
async def capture_screenshot_file(filename: str):
    """スクリーンショット画像を返す"""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="不正なファイル名")
    filepath = SCREENSHOT_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")
    return FileResponse(filepath, media_type="image/png")


@router.delete("/api/capture/screenshots/{filename}")
async def capture_screenshot_delete(filename: str):
    """スクリーンショットを削除"""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="不正なファイル名")
    filepath = SCREENSHOT_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")
    filepath.unlink()
    return {"ok": True}


# =====================================================
# キャプチャ操作
# =====================================================


@router.post("/api/capture/start")
async def capture_start(body: CaptureStartRequest):
    """ウィンドウキャプチャを開始"""
    try:
        req_body = {"sourceId": body.sourceId}
        if body.id:
            req_body["id"] = body.id
        if body.fps:
            req_body["fps"] = body.fps
        if body.quality:
            req_body["quality"] = body.quality
        data = await proxy_request("POST", "/capture", req_body)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not data.get("ok"):
        raise HTTPException(status_code=400, detail=data.get("error", "unknown"))

    cid = data["id"]
    window_name = data.get("name", "")
    # C#旧バージョン対応: nameがなければcaptures一覧から取得
    if not window_name:
        try:
            captures = await proxy_request("GET", "/captures")
            for c in captures:
                if c.get("id") == cid:
                    window_name = c.get("name", "")
                    break
        except Exception:
            pass
    stream_url = f"{capture_base_url()}/stream/{cid}"

    # 保存済み設定があればレイアウトを復元、なければデフォルト
    label = body.label or window_name
    layout = {"x": 5, "y": 10, "width": 40, "height": 50, "zIndex": 10, "visible": True}
    saved_row = db.get_capture_window_by_name(window_name) if window_name else None
    if saved_row:
        layout = _row_to_layout(saved_row)
        label = saved_row.get("label", label)

    # DBにレイアウト保存（アクティブ + 永続）
    _save_capture_layout(cid, layout, label, window_name=window_name)
    db.upsert_capture_window(window_name, label, layout)

    # broadcast.htmlに通知
    await state.broadcast_to_broadcast(
        {
            "type": "capture_add",
            "id": cid,
            "stream_url": stream_url,
            "label": label,
            "layout": layout,
        }
    )

    return {"ok": True, "id": cid, "stream_url": stream_url}


@router.delete("/api/capture/{capture_id}")
async def capture_stop(capture_id: str):
    """キャプチャを停止"""
    try:
        await proxy_request("DELETE", f"/capture/{capture_id}")
    except Exception:
        pass

    _remove_capture_layout(capture_id)

    await state.broadcast_to_broadcast(
        {"type": "capture_remove", "id": capture_id}
    )
    return {"ok": True}


@router.get("/api/capture/sources")
async def capture_sources():
    """アクティブなキャプチャソース一覧（レイアウト情報付き）"""
    try:
        captures = await proxy_request("GET", "/captures")
    except Exception:
        captures = []

    # DB保存のレイアウト情報をマージ
    saved = {s["id"]: s for s in _load_capture_sources()}

    result = []
    for c in captures:
        cid = c["id"]
        info = saved.get(cid, {})
        window_name = c.get("name", "")
        layout = info.get(
            "layout",
            {
                "x": 5,
                "y": 10,
                "width": 40,
                "height": 50,
                "zIndex": 10,
                "visible": True,
            },
        )
        label = info.get("label", window_name or cid)

        result.append(
            {
                **c,
                "label": label,
                "stream_url": f"{capture_base_url()}/stream/{cid}",
                "layout": layout,
            }
        )
    return result


class CaptureLayoutRequest(BaseModel):
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    zIndex: int | None = None
    visible: bool | None = None


@router.post("/api/capture/{capture_id}/layout")
async def capture_update_layout(capture_id: str, body: CaptureLayoutRequest):
    """キャプチャのレイアウトを更新"""
    layout_update = {k: v for k, v in body.model_dump().items() if v is not None}

    _update_capture_layout(capture_id, layout_update)

    await state.broadcast_to_broadcast(
        {"type": "capture_layout", "id": capture_id, "layout": layout_update}
    )
    return {"ok": True}


# =====================================================
# DB管理（キャプチャレイアウト）
# =====================================================


def _load_capture_sources():
    raw = db.get_setting("capture.sources")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return []


def _save_capture_sources(sources):
    db.set_setting("capture.sources", json.dumps(sources, ensure_ascii=False))


def _save_capture_layout(capture_id, layout, label="", window_name=""):
    sources = _load_capture_sources()
    for s in sources:
        if s["id"] == capture_id:
            s["layout"] = layout
            s["label"] = label
            if window_name:
                s["window_name"] = window_name
            _save_capture_sources(sources)
            return
    entry = {"id": capture_id, "label": label, "layout": layout}
    if window_name:
        entry["window_name"] = window_name
    sources.append(entry)
    _save_capture_sources(sources)


def _update_capture_layout(capture_id, layout_update):
    sources = _load_capture_sources()
    window_name = ""
    for s in sources:
        if s["id"] == capture_id:
            s.setdefault("layout", {}).update(layout_update)
            window_name = s.get("window_name", "")
            _save_capture_sources(sources)
            break
    # 保存済みテーブルも同期更新
    if window_name:
        db.update_capture_window_layout(window_name, layout_update)


def _remove_capture_layout(capture_id):
    sources = _load_capture_sources()
    sources = [s for s in sources if s["id"] != capture_id]
    _save_capture_sources(sources)


# =====================================================
# ヘルパー（capture_windowsテーブル → API形式変換）
# =====================================================


def _row_to_layout(row):
    """capture_windowsテーブルの行からlayout dictを生成"""
    return {
        "x": row["x"],
        "y": row["y"],
        "width": row["width"],
        "height": row["height"],
        "zIndex": row["z_index"],
        "visible": bool(row["visible"]),
    }


def _row_to_config(row):
    """capture_windowsテーブルの行からAPI応答形式に変換"""
    return {
        "window_name": row["window_name"],
        "label": row["label"],
        "layout": _row_to_layout(row),
    }


# =====================================================
# 配信ストリーミング制御
# =====================================================


class StreamStartRequest(BaseModel):
    stream_key: str | None = None
    resolution: str = "1920x1080"
    framerate: int = 30
    video_bitrate: str = "3500k"
    audio_bitrate: str = "128k"
    preset: str = "ultrafast"


@router.post("/api/capture/stream/start")
async def capture_stream_start(body: StreamStartRequest):
    """配信アプリ経由でTwitch配信を開始"""
    stream_key = body.stream_key or os.environ.get("TWITCH_STREAM_KEY", "")
    if not stream_key:
        raise HTTPException(
            status_code=400,
            detail="TWITCH_STREAM_KEY が設定されていません",
        )

    web_port = os.environ.get("WEB_PORT", "8080")
    server_url = f"http://{get_windows_host_ip()}:{web_port}"

    try:
        result = await ws_request(
            "start_stream",
            streamKey=stream_key,
            serverUrl=server_url,
            resolution=body.resolution,
            framerate=body.framerate,
            videoBitrate=body.video_bitrate,
            audioBitrate=body.audio_bitrate,
            preset=body.preset,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/capture/stream/stop")
async def capture_stream_stop():
    """配信を停止"""
    try:
        result = await ws_request("stop_stream")
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/capture/stream/status")
async def capture_stream_status():
    """配信の状態を取得"""
    try:
        return await ws_request("stream_status")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
