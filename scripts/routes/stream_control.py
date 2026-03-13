"""配信制御ルート - Electronパイプライン経由でTwitch配信"""

import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scripts import state
from src import db
from src.scene_config import load_config_value, save_config_value

logger = logging.getLogger(__name__)
router = APIRouter()

# 配信中フラグ
_is_streaming = False


async def _ensure_electron():
    """Electronアプリが起動していなければワンクリックプレビューで自動起動し、接続を待つ"""
    import asyncio
    from scripts.routes.capture import _ws_request, capture_preview_oneclick, capture_preview_oneclick_status

    try:
        await _ws_request("stream_status")
        return  # 既に接続済み
    except Exception:
        pass

    # ワンクリックプレビューを起動
    logger.info("Electronアプリ未起動 → ワンクリックプレビューを自動開始")
    await capture_preview_oneclick()

    # 完了を待つ（最大60秒）
    for _ in range(120):
        await asyncio.sleep(0.5)
        st = await capture_preview_oneclick_status()
        if st.get("status") == "done":
            break
        if st.get("status") == "error":
            raise RuntimeError(f"Electron自動起動失敗: {st.get('message', '不明なエラー')}")
    else:
        raise RuntimeError("Electron自動起動タイムアウト")

    # WebSocket接続を待つ（最大10秒）
    for _ in range(20):
        await asyncio.sleep(0.5)
        try:
            await _ws_request("stream_status")
            return
        except Exception:
            pass
    raise RuntimeError("Electron起動後のWebSocket接続に失敗しました")


async def _electron_stream_start():
    """Electron経由でTwitch配信を開始"""
    from scripts.routes.capture import _ws_request
    from src.wsl_path import get_windows_host_ip

    stream_key = os.environ.get("TWITCH_STREAM_KEY", "")
    if not stream_key:
        raise ValueError("TWITCH_STREAM_KEY が .env に設定されていません")

    # Electronアプリが起動していなければ自動起動
    await _ensure_electron()

    web_port = os.environ.get("WEB_PORT", "8080")
    try:
        host = get_windows_host_ip()
    except Exception:
        host = "localhost"
    server_url = f"http://{host}:{web_port}"

    result = await _ws_request(
        "start_stream",
        streamKey=stream_key,
        serverUrl=server_url,
    )
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Electron配信開始失敗"))


async def _electron_stream_stop():
    """Electron経由の配信を停止"""
    from scripts.routes.capture import _ws_request
    try:
        await _ws_request("stop_stream")
    except Exception as e:
        logger.warning("Electron配信停止エラー（無視）: %s", e)


async def _electron_stream_status() -> dict:
    """Electron配信の状態を取得"""
    from scripts.routes.capture import _ws_request
    try:
        return await _ws_request("stream_status")
    except Exception:
        return {"streaming": False}


# =====================================================
# 配信制御
# =====================================================


@router.post("/api/broadcast/go-live")
async def broadcast_go_live():
    """Electron経由で配信開始"""
    global _is_streaming
    try:
        electron_st = await _electron_stream_status()
        if not electron_st.get("streaming"):
            await _electron_stream_start()
        _is_streaming = True
        await state.ensure_reader()
        await state.git_watcher.start()
        return {"ok": True}
    except Exception as e:
        logger.error("Go Live失敗: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/broadcast/start")
async def broadcast_start():
    """Electron経由で配信開始"""
    global _is_streaming
    try:
        await _electron_stream_start()
        _is_streaming = True
        await state.ensure_reader()
        await state.git_watcher.start()
        return {"ok": True}
    except Exception as e:
        logger.error("配信開始失敗: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/broadcast/stop")
async def broadcast_stop():
    """配信を停止"""
    global _is_streaming

    await state.git_watcher.stop()
    if state.reader.is_running:
        await state.reader.stop()
    if state.current_episode:
        db.end_episode(state.current_episode["id"])
        state.current_episode = None

    await _electron_stream_stop()
    _is_streaming = False
    return {"ok": True}


# =====================================================
# シーン
# =====================================================


class SceneRequest(BaseModel):
    name: str


@router.post("/api/broadcast/scene")
async def broadcast_scene(body: SceneRequest):
    """シーンを切り替える"""
    valid_scenes = ["main", "start", "end"]
    if body.name not in valid_scenes:
        raise HTTPException(status_code=400, detail=f"不明なシーン: {body.name} (有効: {valid_scenes})")
    await state.broadcast_to_broadcast({"type": "scene", "name": body.name})
    logger.info("シーン切替: %s", body.name)
    return {"ok": True, "scene": body.name}


@router.get("/api/broadcast/scenes")
async def broadcast_scenes():
    """利用可能なシーン一覧を返す"""
    return {
        "scenes": [
            {"name": "main", "label": "メイン"},
            {"name": "start", "label": "開始画面"},
            {"name": "end", "label": "終了画面"},
        ],
    }


# =====================================================
# 音量
# =====================================================


class VolumeRequest(BaseModel):
    source: str
    volume: float


def _get_volume(source):
    """音量を取得（DB volume.* → scenes.json audio_volumes.* → デフォルト）"""
    val = db.get_setting(f"volume.{source}")
    if val is not None:
        return float(val)
    val = load_config_value(f"audio_volumes.{source}")
    if val is not None:
        return float(val)
    return {"master": 0.8, "tts": 0.8, "bgm": 1.0}.get(source, 1.0)


@router.get("/api/broadcast/volume")
async def broadcast_get_volumes():
    """音量設定を取得"""
    return {
        "master": _get_volume("master"),
        "tts": _get_volume("tts"),
        "bgm": _get_volume("bgm"),
    }


@router.post("/api/broadcast/volume")
async def broadcast_set_volume(body: VolumeRequest):
    """音量を設定してDBに保存し、broadcast.htmlに反映する"""
    if body.source not in ("master", "tts", "bgm"):
        raise HTTPException(status_code=400, detail=f"不明なソース: {body.source}")

    db.set_setting(f"volume.{body.source}", body.volume)

    await state.broadcast_to_broadcast({"type": "volume", "source": body.source, "volume": body.volume})
    logger.info("音量変更: %s = %.2f", body.source, body.volume)

    return {"ok": True}


# =====================================================
# アバターキャプチャ
# =====================================================


class AvatarStreamRequest(BaseModel):
    url: str


def _load_avatar_capture_url():
    """avatar_capture_urlを読み込む（DB優先 → scenes.json）"""
    return load_config_value("avatar_capture_url", "")


def _save_avatar_capture_url(url: str):
    """avatar_capture_urlをDBに保存する"""
    save_config_value("avatar_capture_url", url)


@router.get("/api/broadcast/avatar")
async def broadcast_get_avatar():
    """アバターキャプチャURLを取得"""
    url = _load_avatar_capture_url()
    return {"url": url}


@router.post("/api/broadcast/avatar")
async def broadcast_set_avatar(body: AvatarStreamRequest):
    """アバターキャプチャURLを設定し、broadcast.htmlに送信"""
    _save_avatar_capture_url(body.url)
    await state.broadcast_to_broadcast({
        "type": "avatar_stream",
        "url": body.url,
    })
    logger.info("アバターストリーム設定: %s", body.url)
    return {"ok": True}


@router.post("/api/broadcast/avatar/stop")
async def broadcast_stop_avatar():
    """アバターストリームを停止"""
    _save_avatar_capture_url("")
    await state.broadcast_to_broadcast({"type": "avatar_stop"})
    logger.info("アバターストリーム停止")
    return {"ok": True}


# =====================================================
# ステータス・診断
# =====================================================


@router.get("/api/broadcast/status")
async def broadcast_status():
    """配信状態を返す"""
    electron_st = await _electron_stream_status()
    streaming = electron_st.get("streaming", False)

    result = {
        "streaming": streaming,
        "uptime_seconds": electron_st.get("uptime_seconds"),
        "frames_sent": electron_st.get("frames_sent"),
        "frames_dropped": electron_st.get("frames_dropped"),
        "resolution": (electron_st.get("config") or {}).get("resolution", "1920x1080"),
        "framerate": (electron_st.get("config") or {}).get("framerate", 30),
        "audio_pipe_connected": electron_st.get("audio_pipe_connected", False),
        "electron": electron_st,
    }
    return result


@router.get("/api/broadcast/diag")
async def broadcast_diag():
    """Electronアプリのヘルスチェック"""
    errors = []
    electron_st = await _electron_stream_status()

    if _is_streaming and not electron_st.get("streaming"):
        errors.append("Electron配信が停止しています")

    if not electron_st.get("streaming") and electron_st == {"streaming": False}:
        errors.append("Electronアプリに接続できません")

    return {
        "streaming": electron_st.get("streaming", False),
        "electron": electron_st,
        "errors": errors,
        "healthy": len(errors) == 0,
    }
