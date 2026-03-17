"""CaptureAppClient - Windows配信アプリ（C#）へのWebSocket/HTTP通信クライアント"""

import asyncio
import hashlib
import json
import logging
import time

from src.wsl_path import get_windows_host_ip

logger = logging.getLogger(__name__)

CAPTURE_PORT = 9090

# HTTP method+path → WebSocket action マッピング
PATH_TO_ACTION = {
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


def capture_base_url():
    """キャプチャサーバーのベースURLを返す"""
    try:
        host = get_windows_host_ip()
    except Exception:
        host = "localhost"
    return f"http://{host}:{CAPTURE_PORT}"


def capture_ws_url():
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


async def ensure_capture_ws():
    """配信アプリへの制御WebSocket接続を確保する"""
    global _capture_ws, _ws_reader_task
    import websockets

    if _capture_ws is not None:
        try:
            await _capture_ws.ping()
            return _capture_ws
        except Exception:
            _capture_ws = None

    url = capture_ws_url()
    _capture_ws = await websockets.connect(url, close_timeout=2)
    _ws_reader_task = asyncio.create_task(_read_capture_ws())
    logger.info("配信アプリ制御WebSocket接続: %s", url)

    # C#アプリ接続時に状態を復元
    asyncio.create_task(restore_bgm_to_app())
    asyncio.create_task(restore_captures_to_app())

    return _capture_ws


async def restore_bgm_to_app():
    """C#アプリ接続時に保存済みBGMを送信する"""
    await asyncio.sleep(1)  # WebSocket接続安定待ち
    try:
        from scripts.routes.bgm import load_bgm_settings
        bgm = load_bgm_settings()
        track = bgm.get("track", "")
        if track:
            result = await ws_request("bgm_play", url=f"/bgm/{track}")
            logger.info("C#アプリにBGM復元: %s result=%s", track, result)
        else:
            logger.info("BGM復元: トラック未設定")
    except Exception as e:
        logger.warning("BGM復元失敗: %s", e)


async def restore_captures_to_app():
    """C#アプリ接続時に保存済みキャプチャを復元する"""
    await asyncio.sleep(2)  # WebSocket接続安定待ち
    try:
        from scripts.routes.capture import capture_restore
        result = await capture_restore()
        restored = result.get("restored", 0)
        if restored:
            logger.info("キャプチャ復元OK: %d件", restored)
        else:
            logger.info("キャプチャ復元: 対象なし (%s)", result.get("message", ""))
    except Exception as e:
        logger.warning("キャプチャ復元失敗: %s", e)


async def _handle_capture_changed(data):
    """C#アプリからのキャプチャ変更通知を処理する"""
    from src import db
    action = data.get("action")
    name = data.get("name", "")
    if action == "add" and name:
        if not db.get_capture_window_by_name(name):
            layout = {"x": 5, "y": 10, "width": 40, "height": 50, "zIndex": 10, "visible": True}
            db.upsert_capture_window(name, name, layout)
            logger.info("キャプチャ保存: %s", name)
    elif action == "remove":
        logger.info("キャプチャ停止通知: id=%s", data.get("id"))


async def _read_capture_ws():
    """WebSocketからのレスポンスを読み取り、pendingリクエストを解決する"""
    global _capture_ws
    try:
        async for msg in _capture_ws:
            data = json.loads(msg)
            # Push通知（requestIdなし）の処理
            if data.get("type") == "capture_changed":
                asyncio.create_task(_handle_capture_changed(data))
                continue
            rid = data.get("requestId")
            if rid and rid in _pending_requests:
                _pending_requests[rid].set_result(data)
    except Exception as e:
        if str(e):  # 正常切断時はメッセージなし
            logger.debug("WebSocket読み取り終了: %s", e)
    finally:
        _capture_ws = None
        for fut in _pending_requests.values():
            if not fut.done():
                fut.set_exception(ConnectionError("WebSocket closed"))
        _pending_requests.clear()


async def ws_request(action, timeout=5.0, **params):
    """WebSocket経由で配信アプリにコマンドを送信し、レスポンスを待つ"""
    async with _capture_ws_lock:
        ws = await ensure_capture_ws()
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


async def proxy_request(method, path, body=None):
    """キャプチャサーバーへリクエスト（WebSocket優先→HTTPフォールバック）"""
    # WebSocket経由を試行
    try:
        key = (method, path)
        if key in PATH_TO_ACTION:
            action, _ = PATH_TO_ACTION[key]
            return await ws_request(action, **(body or {}))
        elif method == "POST" and path == "/capture":
            return await ws_request("start_capture", **(body or {}))
        elif method == "DELETE" and path.startswith("/capture/"):
            cap_id = path.split("/capture/")[1]
            return await ws_request("stop_capture", id=cap_id)
        elif method == "POST" and path == "/preview/open":
            return await ws_request("preview_open", **(body or {}))
    except Exception as e:
        logger.debug("WebSocket制御失敗、HTTPフォールバック: %s", e)

    # HTTPフォールバック
    import httpx

    url = f"{capture_base_url()}{path}"
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
