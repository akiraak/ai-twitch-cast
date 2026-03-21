"""配信制御ルート - Windows配信アプリ経由でTwitch配信"""

import logging
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scripts import state
from src import db
from src.scene_config import load_config_value, save_config_value

logger = logging.getLogger(__name__)
router = APIRouter()

# 配信中フラグ
_is_streaming = False

# プロジェクトルート
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


async def _ensure_capture_app():
    """配信アプリが起動していなければ自動起動し、接続を待つ"""
    import asyncio
    import httpx
    from scripts.services.capture_client import capture_base_url, ws_request

    # HTTPサーバーが起動しているか確認
    app_http_ok = False
    try:
        resp = httpx.get(f"{capture_base_url()}/status", timeout=2.0)
        app_http_ok = resp.status_code == 200
    except Exception:
        pass

    if app_http_ok:
        # HTTPは応答あり → WebSocket接続を確立（最大10秒）
        logger.info("配信アプリHTTP応答あり → WebSocket再接続を試行")
        for i in range(20):
            await asyncio.sleep(0.5)
            try:
                await ws_request("stream_status")
                return
            except Exception:
                pass
        raise RuntimeError("配信アプリのWebSocket接続に失敗しました。アプリを再起動してください。")

    # アプリが起動していない → 自動起動
    await _launch_native_app()


async def _launch_native_app():
    """配信アプリをstream.sh経由で自動起動"""
    import asyncio
    from scripts.services.capture_client import ws_request

    logger.info("配信アプリ未起動 → stream.sh で自動起動")
    stream_sh = _PROJECT_ROOT / "stream.sh"
    if not stream_sh.exists():
        raise RuntimeError(f"stream.sh が見つかりません: {stream_sh}")

    # stream.shをバックグラウンドで実行
    subprocess.Popen(
        ["bash", str(stream_sh)],
        cwd=str(_PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # WebSocket接続を待つ（最大90秒 - ビルド時間を考慮）
    for i in range(180):
        await asyncio.sleep(0.5)
        try:
            await ws_request("stream_status")
            logger.info("配信アプリ起動完了（%d秒）", (i + 1) // 2)
            return
        except Exception:
            pass
    raise RuntimeError("配信アプリの起動がタイムアウトしました（90秒）")


async def _capture_stream_start():
    """配信アプリ経由でTwitch配信を開始"""
    from scripts.services.capture_client import ws_request
    from src.wsl_path import get_wsl_ip

    stream_key = os.environ.get("TWITCH_STREAM_KEY", "")
    if not stream_key:
        raise ValueError("TWITCH_STREAM_KEY が .env に設定されていません")

    # アプリが起動していなければ自動起動
    await _ensure_capture_app()

    web_port = os.environ.get("WEB_PORT", "8080")
    try:
        host = get_wsl_ip()
    except Exception:
        host = "localhost"
    server_url = f"http://{host}:{web_port}"

    result = await ws_request(
        "start_stream",
        timeout=120.0,
        streamKey=stream_key,
        serverUrl=server_url,
    )
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "配信開始失敗"))


async def _capture_stream_stop():
    """配信を停止"""
    from scripts.services.capture_client import ws_request
    try:
        await ws_request("stop_stream")
    except Exception as e:
        logger.warning("配信停止エラー（無視）: %s", e)


async def _capture_stream_status() -> dict:
    """配信の状態を取得"""
    from scripts.services.capture_client import ws_request
    try:
        return await ws_request("stream_status")
    except Exception:
        return {"streaming": False}


# =====================================================
# 配信制御
# =====================================================


@router.post("/api/broadcast/go-live")
async def broadcast_go_live():
    """配信開始"""
    global _is_streaming
    try:
        # 前回配信のコメントをクリア
        db.clear_comments()
        db.clear_avatar_comments()

        st = await _capture_stream_status()
        if not st.get("streaming"):
            await _capture_stream_start()
        _is_streaming = True
        # broadcast.htmlに配信状態を通知（TTSミュート切替用）
        await state.broadcast_to_broadcast({"type": "stream_status", "streaming": True})
        await state.ensure_reader()
        await state.git_watcher.start()
        return {"ok": True}
    except Exception as e:
        logger.error("Go Live失敗: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/broadcast/start")
async def broadcast_start():
    """配信開始"""
    global _is_streaming
    try:
        await _capture_stream_start()
        _is_streaming = True
        await state.broadcast_to_broadcast({"type": "stream_status", "streaming": True})
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

    await _capture_stream_stop()
    _is_streaming = False
    # broadcast.htmlに配信停止を通知（TTSミュート解除）
    await state.broadcast_to_broadcast({"type": "stream_status", "streaming": False})
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
    return {"master": 0.8, "tts": 0.8, "bgm": 1.0, "se": 0.8}.get(source, 1.0)


@router.get("/api/broadcast/volume")
async def broadcast_get_volumes():
    """音量設定を取得"""
    return {
        "master": _get_volume("master"),
        "tts": _get_volume("tts"),
        "bgm": _get_volume("bgm"),
        "se": _get_volume("se"),
    }


@router.post("/api/broadcast/volume")
async def broadcast_set_volume(body: VolumeRequest):
    """音量を設定してDBに保存し、broadcast.htmlに反映する"""
    if body.source not in ("master", "tts", "bgm", "se"):
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
    app_st = await _capture_stream_status()
    streaming = app_st.get("streaming", False)

    result = {
        "streaming": streaming,
        "uptime_seconds": app_st.get("uptime_seconds"),
        "frames_sent": app_st.get("frames_sent"),
        "frames_dropped": app_st.get("frames_dropped"),
        "resolution": (app_st.get("config") or {}).get("resolution", "1920x1080"),
        "framerate": (app_st.get("config") or {}).get("framerate", 30),
        "audio_stream_connected": app_st.get("audio_stream_connected", False),
        "audio_receiving_pcm": app_st.get("audio_receiving_pcm", False),
        "app": app_st,
    }
    return result


@router.get("/api/broadcast/diag")
async def broadcast_diag():
    """配信アプリのヘルスチェック"""
    errors = []
    app_st = await _capture_stream_status()

    if _is_streaming and not app_st.get("streaming"):
        errors.append("配信が停止しています")

    if not app_st.get("streaming") and app_st == {"streaming": False}:
        errors.append("配信アプリに接続できません")

    if app_st.get("ffmpeg_exists") is False:
        errors.append(f"FFmpegが見つかりません: {app_st.get('ffmpeg_path', '不明')}")

    return {
        "streaming": app_st.get("streaming", False),
        "app": app_st,
        "ffmpeg_log": app_st.get("ffmpeg_log", []),
        "errors": errors,
        "healthy": len(errors) == 0,
    }


@router.get("/api/broadcast/audio-log")
async def broadcast_audio_log():
    """配信アプリの音声診断ログを取得"""
    import httpx
    from scripts.services.capture_client import capture_base_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{capture_base_url()}/audio/log")
            return resp.json()
    except Exception as e:
        return {"error": str(e), "log": []}
