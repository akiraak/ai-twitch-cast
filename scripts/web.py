"""Web インターフェース"""

import asyncio
import logging
import os
import sys
import time
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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

from scripts import state
from scripts.routes.avatar import router as avatar_router
from scripts.routes.capture import router as capture_router
from scripts.routes.bgm import router as bgm_router
from scripts.routes.character import router as character_router
from scripts.routes.db_viewer import router as db_viewer_router
from scripts.routes.overlay import router as overlay_router
from scripts.routes.stream_control import router as stream_control_router
from scripts.routes.topic import router as topic_router
from scripts.routes.files import router as files_router
from scripts.routes.items import router as items_router
from scripts.routes.twitch import router as twitch_router
from src.ai_responder import load_character
from src import scene_config

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SERVER_STARTED_AT = time.time()

PROJECT_DIR = Path(__file__).resolve().parent.parent

# バージョン情報
APP_VERSION = (PROJECT_DIR / "VERSION").read_text(encoding="utf-8").strip() if (PROJECT_DIR / "VERSION").exists() else "0.0.0"
try:
    import subprocess as _sp
    APP_UPDATED_AT = _sp.run(
        ["git", "log", "-1", "--format=%cI"], cwd=str(PROJECT_DIR),
        capture_output=True, text=True, timeout=5,
    ).stdout.strip() or None
except Exception:
    APP_UPDATED_AT = None
STATIC_DIR = PROJECT_DIR / "static"
STATE_FILE = PROJECT_DIR / ".server_state"
BGM_DIR = PROJECT_DIR / "resources" / "audio" / "bgm"
BGM_DIR.mkdir(parents=True, exist_ok=True)
RESOURCES_DIR = PROJECT_DIR / "resources"
app.mount("/bgm", StaticFiles(directory=str(BGM_DIR)), name="bgm")
app.mount("/resources", StaticFiles(directory=str(RESOURCES_DIR)), name="resources")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response

# ルーターを登録
app.include_router(stream_control_router)
app.include_router(capture_router)
app.include_router(avatar_router)
app.include_router(bgm_router)
app.include_router(character_router)
app.include_router(db_viewer_router)
app.include_router(files_router)
app.include_router(items_router)
app.include_router(overlay_router)
app.include_router(topic_router)
app.include_router(twitch_router)


# --- 環境設定 ---

ENV_KEYS = [
    ("TWITCH_TOKEN", "Twitch トークン"),
    ("TWITCH_CLIENT_ID", "Twitch Client ID"),
    ("TWITCH_CHANNEL", "Twitch チャンネル"),
    ("GEMINI_API_KEY", "Gemini API キー"),
    ("TTS_VOICE", "TTS 音声"),
    ("WEB_PORT", "Webサーバー ポート"),
]

MASK_KEYS = {"TWITCH_TOKEN", "GEMINI_API_KEY"}


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
        "version": APP_VERSION,
        "updated_at": APP_UPDATED_AT,
        "server_started_at": SERVER_STARTED_AT,
        "reader": {
            "running": state.reader.is_running,
            "queue": state.reader.queue_size,
        },
    }


# --- セットアップ & 配信開始 ---

@app.post("/api/start")
async def start():
    await state.ensure_reader()
    await state.git_watcher.start()

    # 状態ファイルを作成（再起動時の自動復旧用）
    STATE_FILE.touch()

    return {"ok": True}


@app.on_event("startup")
async def startup():
    """起動時にキャラクターをDBにシード＆前回の接続状態を自動復旧する"""
    try:
        load_character()
    except Exception:
        pass

    # 言語モードを復元
    try:
        lang = scene_config.load_config_value("language_mode")
        if lang:
            from src.prompt_builder import set_language_mode
            set_language_mode(lang)
            logger.info("言語モード復元: %s", lang)
    except Exception:
        pass

    # TODO.mdファイル監視を開始
    from scripts.routes.overlay import start_todo_watcher
    start_todo_watcher()

    # Setup済みの状態ファイルがなければ復旧しない
    if not STATE_FILE.exists():
        return

    # 復旧処理はバックグラウンドで実行（サーバーを即座に応答可能にする）
    asyncio.create_task(_restore_session())

    # WebSocketクライアントにサーバー再起動を通知（ポーリング不要化）
    asyncio.create_task(_notify_server_restart())


async def _notify_server_restart():
    """WebSocketクライアントにサーバー再起動を通知する（クライアント接続を少し待つ）"""
    await asyncio.sleep(2)
    await state.broadcast_overlay({
        "type": "server_restart",
        "server_started_at": SERVER_STARTED_AT,
    })


async def _restore_session():
    """前回のセッションをバックグラウンドで自動復旧する"""
    logger.info("前回のセッションを自動復旧中...")

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

    # C#アプリの配信状態確認（タイムアウト3秒 — アプリ未起動時にブロックしない）
    try:
        import scripts.routes.stream_control as sc
        from scripts.services.capture_client import ws_request
        st = await asyncio.wait_for(ws_request("stream_status", timeout=2.0), timeout=3.0)
        if st.get("streaming"):
            sc._is_streaming = True
            logger.info("配信状態復旧OK（C#アプリ配信中）")
    except Exception as e:
        logger.info("配信状態確認スキップ（C#アプリ未起動）: %s", type(e).__name__)

    logger.info("自動復旧完了")

    # 保留コミットの読み上げ（TTSクライアント接続を待ってから）
    pending_file = PROJECT_DIR / ".pending_commit"
    if pending_file.exists():
        await _speak_pending_commits(pending_file)


async def _speak_pending_commits(pending_file):
    """broadcast.htmlの接続を待ってからコミットを読み上げる"""
    try:
        text = pending_file.read_text(encoding="utf-8").strip()
        if not text or not state.reader:
            pending_file.unlink(missing_ok=True)
            return

        commits = []
        for line in text.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                commits.append((parts[0], parts[1]))
        if not commits:
            pending_file.unlink(missing_ok=True)
            return

        # broadcast クライアントの接続を待つ（最大30秒）
        for i in range(60):
            if state.broadcast_clients:
                break
            await asyncio.sleep(0.5)
        else:
            logger.warning("broadcastクライアント未接続のためコミット読み上げを保留")
            return  # ファイルを残して次回再トライ

        # 少し待ってから発話（接続直後の安定化）
        await asyncio.sleep(1.0)

        if len(commits) == 1:
            detail = f"{commits[0][0]}: {commits[0][1]}"
        else:
            lines = [f"- {h}: {m}" for h, m in commits]
            detail = f"{len(commits)}件のコミット\n" + "\n".join(lines)

        logger.info("保留コミット読み上げ: %d件", len(commits))
        await state.reader.speak_event("コミット", detail)
        pending_file.unlink(missing_ok=True)
        logger.info("保留コミット読み上げ完了・ファイル削除")
    except Exception as e:
        logger.warning("保留コミット読み上げ失敗: %s", e)


@app.on_event("shutdown")
async def shutdown():
    """終了時にリソースを解放する"""
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
