"""BGMルート（トラック一覧・再生制御・YouTube取得）"""

import asyncio
import logging
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from scripts import state
from src import db
from src.scene_config import load_config_value, save_config_value

router = APIRouter()
logger = logging.getLogger(__name__)

BGM_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "audio" / "bgm"




def load_bgm_settings() -> dict:
    """BGM設定を読み込む（DB優先 → scenes.json）"""
    track = load_config_value("bgm.track", "")
    return {"track": track}


def _save_bgm(track: str | None = None):
    """BGM再生状態をDBに保存する"""
    if track is not None:
        save_config_value("bgm.track", track)



@router.get("/api/bgm/list")
async def bgm_list():
    """BGMトラック一覧を返す（曲別音量・ソースURL付き）"""
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    all_tracks = db.get_all_bgm_tracks()
    tracks = []
    for f in sorted(BGM_DIR.iterdir()):
        if f.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a"):
            info = all_tracks.get(f.name, {})
            tracks.append({
                "name": f.stem,
                "file": f.name,
                "volume": info.get("volume", 1.0),
                "source_url": info.get("source_url"),
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
    return {"ok": True}


@router.delete("/api/bgm/track")
async def bgm_track_delete(file: str):
    """BGMトラックを削除する（再生中なら停止してから削除）"""
    file_path = BGM_DIR / file
    if not file_path.exists():
        return {"ok": False, "error": "ファイルが見つかりません"}

    # 再生中なら停止
    settings = load_bgm_settings()
    if settings.get("track") == file:
        _save_bgm(track="")
        await state.broadcast_bgm({"type": "bgm_stop"})

    # ファイル削除
    file_path.unlink()
    # DB音量レコードも削除
    db.delete_bgm_track_volume(file)
    logger.info("BGMトラック削除: %s", file)
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
            # URLが未保存なら保存する（既存トラックへの補完）
            db.set_bgm_track_source_url(output_path.name, url)
            return {"ok": True, "file": output_path.name, "title": title, "message": "既にダウンロード済み"}

        # ダウンロード
        await asyncio.to_thread(_download_youtube_audio, url, str(output_path))

        if not output_path.exists():
            return {"ok": False, "error": "ダウンロードに失敗しました"}

        # ソースURLをDBに保存
        db.set_bgm_track_source_url(output_path.name, url)

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
