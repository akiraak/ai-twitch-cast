"""ウィンドウキャプチャルート - Windows側Electronアプリの管理"""

import asyncio
import json
import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scripts import state
from src import db
from src.wsl_path import get_windows_host_ip, to_windows_path, is_wsl

logger = logging.getLogger(__name__)
router = APIRouter()

CAPTURE_PORT = 9090
_capture_proc = None

# Electronアプリのパス
_APP_DIR = Path(__file__).resolve().parent.parent.parent / "win-capture-app"
_EXE_PATH = _APP_DIR / "dist" / "win-unpacked" / "win-capture-app.exe"


def _capture_base_url():
    """キャプチャサーバーのベースURLを返す"""
    try:
        host = get_windows_host_ip()
    except Exception:
        host = "localhost"
    return f"http://{host}:{CAPTURE_PORT}"


async def _proxy_request(method, path, body=None):
    """キャプチャサーバーへHTTPリクエストをプロキシする"""
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


@router.post("/api/capture/launch")
async def capture_launch():
    """Electronキャプチャアプリを起動する"""
    global _capture_proc

    # 既に起動中か確認
    st = await capture_status()
    if st.get("running"):
        return {"ok": True, "message": "既に起動中"}

    if not _EXE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"ビルド済みexeが見つかりません: {_EXE_PATH}。win-capture-app/build.sh を実行してください。",
        )

    try:
        if is_wsl():
            win_path = to_windows_path(str(_EXE_PATH))
            _capture_proc = subprocess.Popen(
                ["cmd.exe", "/C", "start", "", win_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            _capture_proc = subprocess.Popen(
                [str(_EXE_PATH)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # 起動待ち
        for _ in range(10):
            await asyncio.sleep(0.5)
            st = await capture_status()
            if st.get("running"):
                logger.info("キャプチャサーバー起動成功")
                return {"ok": True}

        return {"ok": False, "error": "起動タイムアウト"}
    except Exception as e:
        logger.error("キャプチャサーバー起動失敗: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/capture/shutdown")
async def capture_shutdown():
    """キャプチャサーバーを停止する"""
    global _capture_proc
    if _capture_proc:
        try:
            _capture_proc.terminate()
        except Exception:
            pass
        _capture_proc = None
    return {"ok": True}


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
    stream_url = f"{_capture_base_url()}/stream/{cid}"
    layout = {
        "x": 5,
        "y": 10,
        "width": 40,
        "height": 50,
        "zIndex": 10,
        "visible": True,
    }

    label = body.label or data.get("name", "")

    # DBにレイアウト保存
    _save_capture_layout(cid, layout, label)

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


def _save_capture_layout(capture_id, layout, label=""):
    sources = _load_capture_sources()
    for s in sources:
        if s["id"] == capture_id:
            s["layout"] = layout
            s["label"] = label
            _save_capture_sources(sources)
            return
    sources.append({"id": capture_id, "label": label, "layout": layout})
    _save_capture_sources(sources)


def _update_capture_layout(capture_id, layout_update):
    sources = _load_capture_sources()
    for s in sources:
        if s["id"] == capture_id:
            s.setdefault("layout", {}).update(layout_update)
            _save_capture_sources(sources)
            return


def _remove_capture_layout(capture_id):
    sources = _load_capture_sources()
    sources = [s for s in sources if s["id"] != capture_id]
    _save_capture_sources(sources)
