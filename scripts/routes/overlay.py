"""オーバーレイルート（WebSocket + 設定 + TODO表示）"""

import json
import logging
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse

from scripts import state
from src import db
from src.scene_config import CONFIG_PATH

router = APIRouter()
logger = logging.getLogger(__name__)

# broadcast.htmlアクセス用トークン（xvfb Chromiumのみ許可）
BROADCAST_TOKEN = secrets.token_urlsafe(16)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_DIR / "static"
TODO_PATH = PROJECT_DIR / "TODO.md"


@router.websocket("/ws/broadcast")
async def broadcast_ws(websocket: WebSocket):
    """broadcast.html用WebSocket（overlay+tts+bgm統合）"""
    await websocket.accept()
    state.broadcast_clients.add(websocket)
    # 保存済みBGMがあれば自動再生
    try:
        from scripts.routes.bgm import load_bgm_settings
        bgm = load_bgm_settings()
        track = bgm.get("track", "")
        if track:
            await websocket.send_json({
                "type": "bgm_play",
                "url": f"/bgm/{track}",
            })
    except Exception:
        pass
    # 音量設定を送信（DB優先、なければscenes.jsonのデフォルト）
    try:
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                defaults = json.load(f).get("audio_volumes", {})
        except Exception:
            defaults = {}
        for source, fallback in [("master", 0.8), ("tts", 0.8), ("bgm", 1.0)]:
            val = db.get_setting(f"volume.{source}")
            vol = float(val) if val is not None else defaults.get(source, fallback)
            await websocket.send_json({
                "type": "volume",
                "source": source,
                "volume": vol,
            })
    except Exception:
        pass
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.broadcast_clients.discard(websocket)


@router.get("/broadcast")
async def broadcast_page(request: Request):
    """broadcast.htmlを返す（トークン認証必須、xvfb Chromium用）"""
    token = request.query_params.get("token")
    if token != BROADCAST_TOKEN:
        return PlainTextResponse(
            "配信合成ページはxvfb内のChromiumで表示されます。Web UIからプレビューや編集を行ってください。",
            status_code=403,
        )
    return HTMLResponse((STATIC_DIR / "broadcast.html").read_text(encoding="utf-8"))


@router.get("/api/broadcast/token")
async def broadcast_token():
    """broadcast.htmlアクセス用トークンを返す（レイアウト編集用）"""
    return {"token": BROADCAST_TOKEN}



@router.get("/api/broadcast/volumes")
async def get_broadcast_volumes():
    """broadcast.html用の音量設定を返す（DB優先、なければscenes.jsonのデフォルト）"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        defaults = config.get("audio_volumes", {})
    except Exception:
        defaults = {}
    result = {}
    for key, fallback in [("master", 0.8), ("tts", 0.8), ("bgm", 1.0)]:
        val = db.get_setting(f"volume.{key}")
        result[key] = float(val) if val is not None else defaults.get(key, fallback)
    return result


def _get_overlay_defaults():
    """scenes.jsonからオーバーレイのデフォルト値を読み込む"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        return config.get("overlay", {})
    except Exception:
        return {}


_OVERLAY_DEFAULTS = {
    "avatar": {"positionX": 73.25, "positionY": 62.15, "scale": 1.0},
    "lighting": {"brightness": 1.0, "contrast": 1.0, "temperature": 0, "saturation": 1.0},
    "subtitle": {"bottom": 7.4, "fontSize": 1.875, "maxWidth": 62, "fadeDuration": 3, "bgOpacity": 0.85},
    "todo": {"positionX": 50, "positionY": 50, "width": 28, "height": 70, "fontSize": 1.25, "titleFontSize": 1.46, "bgOpacity": 0.95},
    "topic": {"positionX": 1.04, "positionY": 1.85, "maxWidth": 31, "titleFontSize": 1.25, "bgOpacity": 0.95},
}


@router.get("/api/overlay/settings")
async def get_overlay_settings():
    """レイアウト設定を返す（DB優先→scenes.json→ハードコードデフォルト）"""
    file_defaults = _get_overlay_defaults()
    result = {}
    for section, props in _OVERLAY_DEFAULTS.items():
        result[section] = {}
        file_section = file_defaults.get(section, {})
        for prop, fallback in props.items():
            val = db.get_setting(f"overlay.{section}.{prop}")
            if val is not None:
                result[section][prop] = float(val)
            else:
                result[section][prop] = file_section.get(prop, fallback)
    return result


@router.get("/api/todo")
async def get_todo():
    """TODO.mdから未完了タスクを返す（セクション・作業中マーク対応）"""
    if not TODO_PATH.exists():
        return {"items": []}
    text = TODO_PATH.read_text(encoding="utf-8")
    items = []
    current_section = ""
    for line in text.splitlines():
        # セクション見出し: ## セクション名
        m_section = re.match(r"\s*##\s+(.*)", line)
        if m_section:
            current_section = m_section.group(1).strip()
            continue
        # 未着手: - [ ] タスク
        m = re.match(r"\s*-\s*\[\s*\]\s*(.*)", line)
        if m:
            items.append({"text": m.group(1).strip(), "status": "todo", "section": current_section})
            continue
        # 作業中: - [>] タスク
        m = re.match(r"\s*-\s*\[>\]\s*(.*)", line)
        if m:
            items.append({"text": m.group(1).strip(), "status": "in_progress", "section": current_section})
    # 作業中タスクを「作業中」セクションとして先頭に表示
    in_progress = [{"text": i["text"], "status": i["status"], "section": "作業中"} for i in items if i["status"] == "in_progress"]
    others = [i for i in items if i["status"] != "in_progress"]
    return {"items": in_progress + others}


@router.post("/api/todo/start")
async def start_todo(request: Request):
    """TODOを作業中にマークし、アバターに読み上げさせる"""
    import asyncio
    body = await request.json()
    task_text = body.get("text", "").strip()
    if not task_text or not TODO_PATH.exists():
        return {"ok": False, "error": "タスクが見つかりません"}

    # TODO.mdの該当行を [ ] → [>] に変更（他の作業中は [ ] に戻す）
    text = TODO_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    found = False
    new_lines = []
    for line in lines:
        # 既存の作業中マークを未着手に戻す
        m_prog = re.match(r"(\s*-\s*)\[>\](\s*.*)", line)
        if m_prog:
            new_lines.append(f"{m_prog.group(1)}[ ]{m_prog.group(2)}")
            continue
        # 対象タスクを作業中にする
        m_todo = re.match(r"(\s*-\s*)\[\s*\](\s*)(.*)", line)
        if m_todo and m_todo.group(3).strip() == task_text:
            new_lines.append(f"{m_todo.group(1)}[>]{m_todo.group(2)}{m_todo.group(3)}")
            found = True
            continue
        new_lines.append(line)

    if not found:
        return {"ok": False, "error": "タスクが見つかりません"}

    TODO_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # オーバーレイに現在の作業を通知
    await state.broadcast_overlay({
        "type": "current_task",
        "task": task_text,
    })

    # アバターに読み上げさせる
    if state.reader:
        asyncio.ensure_future(state.reader.speak_event("作業開始", task_text))

    return {"ok": True}


@router.post("/api/overlay/preview")
async def preview_overlay_settings(request: Request):
    """設定をオーバーレイにリアルタイム反映する（保存なし）"""
    body = await request.json()
    await state.broadcast_overlay({"type": "settings_update", **body})
    return {"ok": True}


@router.post("/api/overlay/settings")
async def save_overlay_settings(request: Request):
    """レイアウト設定をDBに保存し、オーバーレイに反映する"""
    body = await request.json()
    for section, props in body.items():
        if not isinstance(props, dict):
            continue
        for prop, val in props.items():
            db.set_setting(f"overlay.{section}.{prop}", val)
    # 全設定を読み直してブロードキャスト
    full = await get_overlay_settings()
    await state.broadcast_overlay({"type": "settings_update", **full})
    return {"ok": True}


@router.post("/api/overlay/info")
async def overlay_info(request: Request):
    """情報パネルにメッセージを追加する（汎用）"""
    body = await request.json()
    await state.broadcast_overlay({
        "type": "info",
        "icon": body.get("icon", "📋"),
        "text": body.get("text", ""),
        "label": body.get("label", ""),
    })
    return {"ok": True}
