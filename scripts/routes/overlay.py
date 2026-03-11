"""オーバーレイルート（WebSocket + 設定 + TODO表示）"""

import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from scripts import state
from src import db
from src.scene_config import CONFIG_PATH

router = APIRouter()
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_DIR / "static"
TODO_PATH = PROJECT_DIR / "TODO.md"


@router.websocket("/ws/overlay")
async def overlay_ws(websocket: WebSocket):
    await websocket.accept()
    state.overlay_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.overlay_clients.discard(websocket)


@router.websocket("/ws/tts")
async def tts_ws(websocket: WebSocket):
    await websocket.accept()
    state.tts_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.tts_clients.discard(websocket)


@router.websocket("/ws/bgm")
async def bgm_ws(websocket: WebSocket):
    await websocket.accept()
    state.bgm_clients.add(websocket)
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
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.bgm_clients.discard(websocket)


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


@router.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page():
    return (STATIC_DIR / "broadcast.html").read_text(encoding="utf-8")


@router.get("/broadcast-ui", response_class=HTMLResponse)
async def broadcast_ui_page():
    return (STATIC_DIR / "broadcast-ui.html").read_text(encoding="utf-8")


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


@router.get("/overlay", response_class=HTMLResponse)
async def overlay_page():
    return (STATIC_DIR / "overlay.html").read_text(encoding="utf-8")


@router.get("/audio/tts", response_class=HTMLResponse)
async def audio_tts_page():
    return (STATIC_DIR / "audio-tts.html").read_text(encoding="utf-8")


@router.get("/audio/bgm", response_class=HTMLResponse)
async def audio_bgm_page():
    return (STATIC_DIR / "audio-bgm.html").read_text(encoding="utf-8")


@router.get("/design-proposal", response_class=HTMLResponse)
async def design_proposal_page():
    return (STATIC_DIR / "design-proposal.html").read_text(encoding="utf-8")


@router.get("/api/overlay/settings")
async def get_overlay_settings():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return config.get("overlay", {
        "subtitle": {"bottom": 80, "fontSize": 28, "fadeDuration": 3},
        "todo": {"width": 460, "fontSize": 15, "titleFontSize": 18},
    })


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
    """設定をファイルに保存せずオーバーレイにリアルタイム反映する"""
    body = await request.json()
    await state.broadcast_overlay({"type": "settings_update", **body})
    return {"ok": True}


@router.post("/api/overlay/settings")
async def save_overlay_settings(request: Request):
    body = await request.json()
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    # 既存設定にマージ（部分更新対応）
    existing = config.get("overlay", {})
    for key, val in body.items():
        if isinstance(val, dict) and isinstance(existing.get(key), dict):
            existing[key].update(val)
        else:
            existing[key] = val
    config["overlay"] = existing
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")
    await state.broadcast_overlay({"type": "settings_update", **existing})
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
