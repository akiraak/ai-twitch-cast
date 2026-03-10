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
from src.scene_config import CONFIG_PATH

router = APIRouter()
logger = logging.getLogger(__name__)

BGM_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "audio" / "bgm"


def _load_bgm_volume() -> float:
    """scenes.jsonからBGM音量を読み込む"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        return config.get("bgm", {}).get("volume", 0.3)
    except Exception:
        return 0.3


def _save_bgm_volume(volume: float):
    """scenes.jsonにBGM音量を保存する"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    if "bgm" not in config:
        config["bgm"] = {}
    config["bgm"]["volume"] = volume
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


@router.get("/api/bgm/list")
async def bgm_list():
    """BGMトラック一覧を返す"""
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    tracks = []
    for f in sorted(BGM_DIR.iterdir()):
        if f.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a"):
            tracks.append({"name": f.stem, "file": f.name})
    return {"tracks": tracks, "volume": _load_bgm_volume()}


class BGMControl(BaseModel):
    action: str  # play, stop, volume
    track: str = ""
    volume: float = 0.3


@router.post("/api/bgm")
async def bgm_control(body: BGMControl):
    """BGM制御（overlay経由で再生）"""
    if body.action == "play":
        _save_bgm_volume(body.volume)
        await state.broadcast_overlay({
            "type": "bgm_play",
            "url": f"/bgm/{body.track}",
            "volume": body.volume,
        })
        return {"ok": True}
    elif body.action == "stop":
        await state.broadcast_overlay({"type": "bgm_stop"})
        return {"ok": True}
    elif body.action == "volume":
        _save_bgm_volume(body.volume)
        await state.broadcast_overlay({
            "type": "bgm_volume",
            "volume": body.volume,
        })
        return {"ok": True}
    return {"ok": False, "error": f"不明なアクション: {body.action}"}


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
