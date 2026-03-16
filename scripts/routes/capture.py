"""ウィンドウキャプチャルート - Windows配信アプリ経由のウィンドウキャプチャ"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from scripts import state
from src import db
from src.wsl_path import get_windows_host_ip

logger = logging.getLogger(__name__)
router = APIRouter()

CAPTURE_PORT = 9090


def _capture_base_url():
    """キャプチャサーバーのベースURLを返す"""
    try:
        host = get_windows_host_ip()
    except Exception:
        host = "localhost"
    return f"http://{host}:{CAPTURE_PORT}"


def _capture_ws_url():
    """キャプチャサーバーの制御WebSocket URLを返す"""
    try:
        host = get_windows_host_ip()
    except Exception:
        host = "localhost"
    return f"ws://{host}:{CAPTURE_PORT}/ws/control"


# WebSocketクライアント（配信アプリ制御用）
_capture_ws = None
_capture_ws_lock = asyncio.Lock()
_pending_requests: dict[str, asyncio.Future] = {}
_ws_reader_task = None


async def _ensure_capture_ws():
    """配信アプリへの制御WebSocket接続を確保する"""
    global _capture_ws, _ws_reader_task
    import websockets

    if _capture_ws is not None:
        try:
            await _capture_ws.ping()
            return _capture_ws
        except Exception:
            _capture_ws = None

    url = _capture_ws_url()
    _capture_ws = await websockets.connect(url, close_timeout=2)
    _ws_reader_task = asyncio.create_task(_read_capture_ws())
    logger.info("配信アプリ制御WebSocket接続: %s", url)

    # C#アプリ接続時にBGM状態を復元
    asyncio.create_task(_restore_bgm_to_app())

    return _capture_ws


async def _restore_bgm_to_app():
    """C#アプリ接続時に保存済みBGMを送信する"""
    await asyncio.sleep(1)  # WebSocket接続安定待ち
    try:
        from scripts.routes.bgm import load_bgm_settings
        bgm = load_bgm_settings()
        track = bgm.get("track", "")
        if track:
            result = await _ws_request("bgm_play", url=f"/bgm/{track}")
            logger.info("C#アプリにBGM復元: %s result=%s", track, result)
        else:
            logger.info("BGM復元: トラック未設定")
    except Exception as e:
        logger.warning("BGM復元失敗: %s", e)


async def _read_capture_ws():
    """WebSocketからのレスポンスを読み取り、pendingリクエストを解決する"""
    global _capture_ws
    try:
        async for msg in _capture_ws:
            data = json.loads(msg)
            rid = data.get("requestId")
            if rid and rid in _pending_requests:
                _pending_requests[rid].set_result(data)
    except Exception:
        pass
    finally:
        _capture_ws = None
        for fut in _pending_requests.values():
            if not fut.done():
                fut.set_exception(ConnectionError("WebSocket closed"))
        _pending_requests.clear()


async def _ws_request(action, timeout=5.0, **params):
    """WebSocket経由で配信アプリにコマンドを送信し、レスポンスを待つ"""
    async with _capture_ws_lock:
        ws = await _ensure_capture_ws()
    rid = hashlib.md5(f"{action}{time.time()}".encode()).hexdigest()[:8]
    fut = asyncio.get_event_loop().create_future()
    _pending_requests[rid] = fut
    try:
        await ws.send(json.dumps({"requestId": rid, "action": action, **params}))
        result = await asyncio.wait_for(fut, timeout=timeout)
        # 配列レスポンスは data フィールドに入る
        return result.get("data", result)
    finally:
        _pending_requests.pop(rid, None)


# HTTP method+path → WebSocket action マッピング
_PATH_TO_ACTION = {
    ("GET", "/status"): ("status", {}),
    ("GET", "/windows"): ("windows", {}),
    ("GET", "/captures"): ("captures", {}),
    ("GET", "/preview/status"): ("preview_status", {}),
    ("POST", "/preview/close"): ("preview_close", {}),
    ("POST", "/quit"): ("quit", {}),
    ("POST", "/stream/stop"): ("stop_stream", {}),
    ("GET", "/stream/status"): ("stream_status", {}),
    ("POST", "/broadcast/close"): ("broadcast_close", {}),
    ("GET", "/broadcast/status"): ("broadcast_status", {}),
}


async def _proxy_request(method, path, body=None):
    """キャプチャサーバーへリクエスト（WebSocket優先→HTTPフォールバック）"""
    # WebSocket経由を試行
    try:
        key = (method, path)
        if key in _PATH_TO_ACTION:
            action, _ = _PATH_TO_ACTION[key]
            return await _ws_request(action, **(body or {}))
        elif method == "POST" and path == "/capture":
            return await _ws_request("start_capture", **(body or {}))
        elif method == "DELETE" and path.startswith("/capture/"):
            cap_id = path.split("/capture/")[1]
            return await _ws_request("stop_capture", id=cap_id)
        elif method == "POST" and path == "/preview/open":
            return await _ws_request("preview_open", **(body or {}))
    except Exception as e:
        logger.debug("WebSocket制御失敗、HTTPフォールバック: %s", e)

    # HTTPフォールバック
    import httpx

    url = f"{_capture_base_url()}{path}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        if method == "GET":
            resp = await client.get(url)
        elif method == "POST":
            resp = await client.post(url, json=body)
        elif method == "DELETE":
            resp = await client.delete(url)
        else:
            raise ValueError(f"Unknown method: {method}")
        return resp.json()


# =====================================================
# サーバー管理
# =====================================================


@router.get("/api/capture/status")
async def capture_status():
    """キャプチャサーバーの状態を返す"""
    try:
        data = await _proxy_request("GET", "/status")
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
        return await _proxy_request("GET", "/windows")
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
    """保存済みキャプチャ設定一覧"""
    return _load_saved_configs()


@router.delete("/api/capture/saved")
async def capture_saved_delete(request: Request):
    """保存済みキャプチャ設定を削除"""
    body = await request.json()
    window_name = body.get("window_name", "")
    if window_name:
        _remove_saved_config(window_name)
    return {"ok": True}


@router.post("/api/capture/restore")
async def capture_restore():
    """保存済み設定からウィンドウ名マッチングでキャプチャを復元"""
    saved = _load_saved_configs()
    if not saved:
        return {"ok": True, "restored": 0, "message": "保存済み設定なし"}

    try:
        windows = await _proxy_request("GET", "/windows")
    except Exception as e:
        return {"ok": False, "error": f"配信アプリに接続できません: {e}"}

    # 現在アクティブなキャプチャのウィンドウ名を取得
    try:
        active = await _proxy_request("GET", "/captures")
        active_names = {c.get("name", "") for c in active}
    except Exception:
        active_names = set()

    restored = 0
    for config in saved:
        wname = config["window_name"]
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
            data = await _proxy_request("POST", "/capture", {"sourceId": match["sourceId"]})
            if data.get("ok"):
                cid = data["id"]
                layout = config.get("layout", {"x": 5, "y": 10, "width": 40, "height": 50, "zIndex": 10, "visible": True})
                label = config.get("label", wname)
                _save_capture_layout(cid, layout, label, window_name=match["name"])
                # 名前が変わっていたら保存済み設定も更新
                if match["name"] != wname:
                    _upsert_saved_config(match["name"], label, layout)
                await state.broadcast_to_broadcast({
                    "type": "capture_add",
                    "id": cid,
                    "stream_url": f"{_capture_base_url()}/stream/{cid}",
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
        result = await _ws_request("screenshot", timeout=10.0)
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
        data = await _proxy_request("POST", "/capture", req_body)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not data.get("ok"):
        raise HTTPException(status_code=400, detail=data.get("error", "unknown"))

    cid = data["id"]
    window_name = data.get("name", "")
    stream_url = f"{_capture_base_url()}/stream/{cid}"

    # 保存済み設定があればレイアウトを復元、なければデフォルト
    label = body.label or window_name
    layout = {"x": 5, "y": 10, "width": 40, "height": 50, "zIndex": 10, "visible": True}
    for c in _load_saved_configs():
        if c["window_name"] == window_name:
            layout = c.get("layout", layout)
            label = c.get("label", label)
            break

    # DBにレイアウト保存（アクティブ + 永続）
    _save_capture_layout(cid, layout, label, window_name=window_name)
    _upsert_saved_config(window_name, label, layout)

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
        await _proxy_request("DELETE", f"/capture/{capture_id}")
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
        captures = await _proxy_request("GET", "/captures")
    except Exception:
        captures = []

    # DB保存のレイアウト情報をマージ
    saved = {s["id"]: s for s in _load_capture_sources()}

    result = []
    for c in captures:
        cid = c["id"]
        info = saved.get(cid, {})
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
        result.append(
            {
                **c,
                "label": info.get("label", c.get("name", cid)),
                "stream_url": f"{_capture_base_url()}/stream/{cid}",
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
    # 保存済み設定のレイアウトも同期更新
    if window_name:
        configs = _load_saved_configs()
        for c in configs:
            if c["window_name"] == window_name:
                c.setdefault("layout", {}).update(layout_update)
                _save_saved_configs(configs)
                break


def _remove_capture_layout(capture_id):
    sources = _load_capture_sources()
    sources = [s for s in sources if s["id"] != capture_id]
    _save_capture_sources(sources)


# =====================================================
# DB管理（保存済みキャプチャ設定 - 永続化）
# =====================================================


def _load_saved_configs():
    raw = db.get_setting("capture.saved_configs")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return []


def _save_saved_configs(configs):
    db.set_setting("capture.saved_configs", json.dumps(configs, ensure_ascii=False))


def _upsert_saved_config(window_name, label, layout):
    """window_nameで保存済み設定を追加/更新"""
    if not window_name:
        return
    configs = _load_saved_configs()
    for c in configs:
        if c["window_name"] == window_name:
            c["label"] = label
            c["layout"] = layout
            _save_saved_configs(configs)
            return
    configs.append({"window_name": window_name, "label": label, "layout": layout})
    _save_saved_configs(configs)


def _remove_saved_config(window_name):
    configs = _load_saved_configs()
    configs = [c for c in configs if c["window_name"] != window_name]
    _save_saved_configs(configs)


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
        result = await _ws_request(
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
        result = await _ws_request("stop_stream")
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/capture/stream/status")
async def capture_stream_status():
    """配信の状態を取得"""
    try:
        return await _ws_request("stream_status")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
