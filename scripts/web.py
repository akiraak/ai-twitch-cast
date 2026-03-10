"""Web インターフェース（console.py相当）"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

from scripts import state
from scripts.routes.avatar import router as avatar_router
from scripts.routes.bgm import router as bgm_router
from scripts.routes.character import router as character_router
from scripts.routes.obs import router as obs_router
from scripts.routes.overlay import router as overlay_router
from scripts.routes.stream import router as stream_router
from scripts.routes.twitch import router as twitch_router
from src.ai_responder import load_character
from src import scene_config
from src.scene_config import AVATAR_APP

app = FastAPI()

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_DIR / "static"
STATE_FILE = PROJECT_DIR / ".server_state"
BGM_DIR = PROJECT_DIR / "resources" / "audio" / "bgm"
BGM_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/bgm", StaticFiles(directory=str(BGM_DIR)), name="bgm")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ルーターを登録
app.include_router(obs_router)
app.include_router(stream_router)
app.include_router(avatar_router)
app.include_router(bgm_router)
app.include_router(character_router)
app.include_router(overlay_router)
app.include_router(twitch_router)


# --- 環境設定 ---

ENV_KEYS = [
    ("OBS_WS_HOST", "OBS WebSocket ホスト"),
    ("OBS_WS_PORT", "OBS WebSocket ポート"),
    ("OBS_WS_PASSWORD", "OBS WebSocket パスワード"),
    ("AVATAR_APP", "アバターアプリ (vts/vsf)"),
    ("VTS_HOST", "VTube Studio ホスト"),
    ("VTS_PORT", "VTube Studio ポート"),
    ("VSF_OSC_HOST", "VSeeFace OSC ホスト"),
    ("VSF_OSC_PORT", "VSeeFace OSC ポート"),
    ("TWITCH_TOKEN", "Twitch トークン"),
    ("TWITCH_CLIENT_ID", "Twitch Client ID"),
    ("TWITCH_CHANNEL", "Twitch チャンネル"),
    ("GEMINI_API_KEY", "Gemini API キー"),
    ("TTS_VOICE", "TTS 音声"),
]

MASK_KEYS = {"OBS_WS_PASSWORD", "TWITCH_TOKEN", "GEMINI_API_KEY"}


@app.get("/api/env")
async def get_env():
    result = []
    for key, label in ENV_KEYS:
        value = os.environ.get(key, "")
        if key in MASK_KEYS and value:
            value = "***"
        result.append({"key": key, "label": label, "value": value})
    return result


# --- ページ ---

@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# --- ステータス ---

@app.get("/api/status")
async def get_status():
    return {
        "avatar_app": AVATAR_APP,
        "obs": {
            "connected": state.obs_connected,
            "stream": state.obs.get_stream_status() if state.obs_connected else None,
        },
        "vts": {"connected": state.vts_connected},
        "vsf": {
            "connected": state.vsf_connected,
            "idle": state.vsf.is_idle_running if state.vsf_connected else False,
        },
        "reader": {
            "running": state.reader.is_running,
            "queue": state.reader.queue_size,
        },
    }


# --- セットアップ & 配信開始 ---

@app.post("/api/start")
async def start():
    state.obs.connect()
    state.obs_connected = True
    if AVATAR_APP == "vsf":
        state.vsf.connect()
        state.vsf_connected = True
        state.vsf.apply_default_pose()
        defaults = state.load_vsf_defaults()
        if defaults.get("blendshapes"):
            state.vsf.set_blendshapes(defaults["blendshapes"])
        state.vsf.start_idle(defaults.get("idle_scale", 1.0))
    else:
        await state.vts.connect()
        state.vts_connected = True
    scene_config.reload()
    setup_result = state.obs.setup_scenes(scene_config.SCENES, scene_config.MAIN_SCENE)
    # ブラウザソースの音声をOBSミキサーに出力 & モニタリング有効化 & キャッシュクリア
    overlay_name = f"{scene_config.PREFIX}オーバーレイ"
    try:
        state.obs.set_input_settings(overlay_name, {"reroute_audio": True})
        state.obs._client.set_input_audio_monitor_type(overlay_name, "OBS_MONITORING_TYPE_NONE")
        state.obs.refresh_browser_source(overlay_name)
    except Exception as e:
        setup_result.setdefault("errors", []).append(f"オーバーレイ音声設定: {e}")
    await state.ensure_reader()
    await state.git_watcher.start()

    # 状態ファイルを作成（再起動時の自動復旧用）
    STATE_FILE.touch()

    return {"ok": True, **setup_result}


@app.on_event("startup")
async def startup():
    """起動時にキャラクターをDBにシード＆前回の接続状態を自動復旧する"""
    try:
        load_character()
    except Exception:
        pass

    # Setup済みの状態ファイルがなければ復旧しない
    if not STATE_FILE.exists():
        return

    logger.info("前回のセッションを自動復旧中...")
    try:
        state.obs.connect()
        state.obs_connected = True
        # 音声モニタリングをオフに設定（配信出力のみ）
        overlay_name = f"{scene_config.PREFIX}オーバーレイ"
        try:
            state.obs.set_input_settings(overlay_name, {"reroute_audio": True})
            state.obs._client.set_input_audio_monitor_type(overlay_name, "OBS_MONITORING_TYPE_NONE")
        except Exception:
            pass
        logger.info("OBS接続復旧OK")
    except Exception as e:
        logger.warning("OBS接続復旧失敗: %s", e)

    try:
        if AVATAR_APP == "vsf":
            state.vsf.connect()
            state.vsf_connected = True
            state.vsf.apply_default_pose()
            defaults = state.load_vsf_defaults()
            if defaults.get("blendshapes"):
                state.vsf.set_blendshapes(defaults["blendshapes"])
            state.vsf.start_idle(defaults.get("idle_scale", 1.0))
            logger.info("アバター復旧OK")
        else:
            await state.vts.connect()
            state.vts_connected = True
            logger.info("VTS接続復旧OK")
    except Exception as e:
        logger.warning("アバター復旧失敗: %s", e)

    try:
        await state.ensure_reader()
        logger.info("Reader復旧OK")
    except Exception as e:
        logger.warning("Reader復旧失敗: %s", e)

    try:
        await state.git_watcher.start()
        logger.info("Git監視復旧OK")
    except Exception as e:
        logger.warning("Git監視復旧失敗: %s", e)

    logger.info("自動復旧完了")

    # 保留コミットの読み上げ
    pending_file = PROJECT_DIR / ".pending_commit"
    if pending_file.exists():
        try:
            text = pending_file.read_text(encoding="utf-8").strip()
            pending_file.unlink()
            if text and state.reader:
                commits = []
                for line in text.splitlines():
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        commits.append((parts[0], parts[1]))
                if commits:
                    if len(commits) == 1:
                        detail = f"{commits[0][0]}: {commits[0][1]}"
                    else:
                        lines = [f"- {h}: {m}" for h, m in commits]
                        detail = f"{len(commits)}件のコミット\n" + "\n".join(lines)
                    logger.info("保留コミット読み上げ: %d件", len(commits))
                    asyncio.ensure_future(
                        state.reader.speak_event("コミット", detail)
                    )
        except Exception as e:
            logger.warning("保留コミット読み上げ失敗: %s", e)


@app.on_event("shutdown")
async def shutdown():
    """終了時にリソースを解放する"""
    state.vsf.stop_idle()
    try:
        await state.reader.stop()
    except Exception:
        pass
    try:
        await state.git_watcher.stop()
    except Exception:
        pass
    logger.info("シャットダウン完了")


if __name__ == "__main__":
    import uvicorn

    from src.scene_config import WEB_PORT
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)
