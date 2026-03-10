"""BGMルート（トラック一覧・再生制御・YouTube取得）"""

import asyncio
import json
import logging
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from scripts import state
from src import db
from src.scene_config import CONFIG_PATH

router = APIRouter()
logger = logging.getLogger(__name__)

BGM_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "audio" / "bgm"


def load_bgm_settings() -> dict:
    """scenes.jsonからBGM設定を読み込む"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        return config.get("bgm", {})
    except Exception:
        return {}


def _save_bgm(track: str | None = None):
    """scenes.jsonにBGM再生状態を保存する"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    if "bgm" not in config:
        config["bgm"] = {}
    if track is not None:
        config["bgm"]["track"] = track  # "" で停止状態
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _apply_bgm_volume():
    """BGMの実効音量をOBSに反映する（曲音量含む）"""
    from scripts.routes.obs import _apply_effective_volume
    try:
        _apply_effective_volume("bgm")
    except Exception as e:
        logger.warning("BGM音量適用失敗: %s", e)


@router.get("/api/bgm/list")
async def bgm_list():
    """BGMトラック一覧を返す（曲別音量付き）"""
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    volumes = db.get_all_bgm_track_volumes()
    tracks = []
    for f in sorted(BGM_DIR.iterdir()):
        if f.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a"):
            tracks.append({
                "name": f.stem,
                "file": f.name,
                "volume": volumes.get(f.name, 1.0),
            })
    settings = load_bgm_settings()
    return {"tracks": tracks, "track": settings.get("track", "")}


class BGMControl(BaseModel):
    action: str  # play, stop
    track: str = ""


@router.post("/api/bgm")
async def bgm_control(body: BGMControl):
    """BGM制御（専用ブラウザソース経由で再生、音量はOBSミキサーで制御）"""
    if body.action == "play":
        _save_bgm(track=body.track)
        await state.broadcast_bgm({
            "type": "bgm_play",
            "url": f"/bgm/{body.track}",
        })
        # 曲音量を含めた実効音量をOBSに反映
        _apply_bgm_volume()
        return {"ok": True}
    elif body.action == "stop":
        _save_bgm(track="")
        await state.broadcast_bgm({"type": "bgm_stop"})
        return {"ok": True}
    return {"ok": False, "error": f"不明なアクション: {body.action}"}


class BGMTrackVolume(BaseModel):
    file: str
    volume: float  # 0.0 - 1.0


@router.post("/api/bgm/track-volume")
async def bgm_track_volume(body: BGMTrackVolume):
    """曲別音量を設定する（DBに保存、再生中ならOBSに即反映）"""
    db.set_bgm_track_volume(body.file, body.volume)
    # 再生中の曲なら実効音量を再計算してOBSに反映
    settings = load_bgm_settings()
    if settings.get("track") == body.file:
        _apply_bgm_volume()
    return {"ok": True}


class BGMTrackDelete(BaseModel):
    file: str


@router.delete("/api/bgm/track")
async def bgm_track_delete(body: BGMTrackDelete):
    """BGMトラックを削除する（再生中なら停止してから削除）"""
    file_path = BGM_DIR / body.file
    if not file_path.exists():
        return {"ok": False, "error": "ファイルが見つかりません"}

    # 再生中なら停止
    settings = load_bgm_settings()
    if settings.get("track") == body.file:
        _save_bgm(track="")
        await state.broadcast_bgm({"type": "bgm_stop"})

    # ファイル削除
    file_path.unlink()
    # DB音量レコードも削除
    db.delete_bgm_track_volume(body.file)
    logger.info("BGMトラック削除: %s", body.file)
    return {"ok": True}


class YouTubeDownload(BaseModel):
    url: str


@router.post("/api/bgm/youtube")
async def bgm_youtube(body: YouTubeDownload):
    """YouTube URLから音声をダウンロードしてBGMに追加する"""
    url = body.url.strip()
    if not url:
        return {"ok": False, "error": "URLが空です"}

    BGM_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # まずタイトルを取得
        title = await asyncio.to_thread(_get_youtube_title, url)
        # 安全なファイル名に変換
        safe_name = _sanitize_filename(title)
        output_path = BGM_DIR / f"{safe_name}.mp3"

        if output_path.exists():
            return {"ok": True, "file": output_path.name, "title": title, "message": "既にダウンロード済み"}

        # ダウンロード
        await asyncio.to_thread(_download_youtube_audio, url, str(output_path))

        if not output_path.exists():
            return {"ok": False, "error": "ダウンロードに失敗しました"}

        logger.info("YouTube BGMダウンロード完了: %s → %s", title, output_path.name)
        return {"ok": True, "file": output_path.name, "title": title}

    except Exception as e:
        logger.error("YouTubeダウンロード失敗: %s", e)
        return {"ok": False, "error": str(e)}


def _get_youtube_title(url):
    """YouTubeの動画タイトルを取得する"""
    result = subprocess.run(
        ["yt-dlp", "--get-title", "--no-warnings", url],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"タイトル取得失敗: {result.stderr.strip()}")
    return result.stdout.strip()


def _download_youtube_audio(url, output_path):
    """YouTube動画の音声をMP3でダウンロードする"""
    result = subprocess.run(
        [
            "yt-dlp",
            "-x", "--audio-format", "mp3",
            "--audio-quality", "192K",
            "--no-warnings",
            "--no-playlist",
            "-o", output_path,
            url,
        ],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ダウンロード失敗: {result.stderr.strip()}")


def _sanitize_filename(name):
    """ファイル名に使えない文字を除去する"""
    name = re.sub(r'[\\/*?:"<>|]', '', name)
    name = name.strip('. ')
    if not name:
        name = "untitled"
    return name[:100]
