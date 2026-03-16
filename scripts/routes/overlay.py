"""オーバーレイルート（WebSocket + 設定 + TODO表示）"""

import asyncio
import json as _json_mod
import logging
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse

from scripts import state
from src import db
from src.scene_config import load_config_value, load_config_json

router = APIRouter()
logger = logging.getLogger(__name__)

# broadcast.htmlアクセス用トークン（配信アプリ+プレビュー用）
BROADCAST_TOKEN = secrets.token_urlsafe(16)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_DIR / "static"
TODO_PATH = PROJECT_DIR / "TODO.md"

# TODO.mdファイル監視用
_todo_last_mtime: float = 0.0
_todo_watch_task: asyncio.Task | None = None


async def broadcast_todo():
    """TODO.mdを読み込み、todo_updateイベントをブロードキャストする"""
    todo_data = await get_todo()
    await state.broadcast_overlay({"type": "todo_update", "items": todo_data["items"]})


async def _watch_todo_file():
    """TODO.mdのmtimeを監視し、変更があればブロードキャストする"""
    global _todo_last_mtime
    if TODO_PATH.exists():
        _todo_last_mtime = TODO_PATH.stat().st_mtime
    while True:
        await asyncio.sleep(2)
        try:
            if not TODO_PATH.exists():
                continue
            mtime = TODO_PATH.stat().st_mtime
            if mtime != _todo_last_mtime:
                _todo_last_mtime = mtime
                await broadcast_todo()
        except Exception:
            pass


def start_todo_watcher():
    """TODO.mdファイル監視タスクを開始する"""
    global _todo_watch_task
    if _todo_watch_task is None or _todo_watch_task.done():
        _todo_watch_task = asyncio.create_task(_watch_todo_file())
        logger.info("TODO.mdファイル監視を開始")


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
    # 音量設定を送信（DB優先 → scenes.json → デフォルト）
    try:
        for source, fallback in [("master", 0.8), ("tts", 0.8), ("bgm", 1.0)]:
            val = db.get_setting(f"volume.{source}")
            if val is not None:
                vol = float(val)
            else:
                cfg_val = load_config_value(f"audio_volumes.{source}")
                vol = float(cfg_val) if cfg_val is not None else fallback
            await websocket.send_json({
                "type": "volume",
                "source": source,
                "volume": vol,
            })
    except Exception:
        pass
    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = _json_mod.loads(text)
                if msg.get("type") == "save_volume":
                    source = msg.get("source", "")
                    volume = msg.get("volume", 0)
                    if source in ("master", "tts", "bgm"):
                        db.set_setting(f"volume.{source}", volume)
                        logger.debug("音量保存(WS): %s = %.2f", source, volume)
            except Exception:
                pass
    except WebSocketDisconnect:
        state.broadcast_clients.discard(websocket)


@router.get("/broadcast")
async def broadcast_page(request: Request):
    """broadcast.htmlを返す（トークン認証必須、配信アプリレンダリング用）"""
    token = request.query_params.get("token")
    if token != BROADCAST_TOKEN:
        return PlainTextResponse(
            "配信合成ページは配信アプリで表示されます。Web UIからプレビューや編集を行ってください。",
            status_code=403,
        )
    return HTMLResponse((STATIC_DIR / "broadcast.html").read_text(encoding="utf-8"))


@router.get("/preview")
async def preview_page(request: Request):
    """preview.htmlを返す（トークン認証必須、プレビュー用）"""
    token = request.query_params.get("token")
    if token != BROADCAST_TOKEN:
        return PlainTextResponse("認証エラー", status_code=403)
    return HTMLResponse((STATIC_DIR / "preview.html").read_text(encoding="utf-8"))


@router.get("/api/broadcast/token")
async def broadcast_token():
    """broadcast.htmlアクセス用トークンを返す（レイアウト編集用）"""
    return {"token": BROADCAST_TOKEN}



@router.post("/api/debug/subtitle")
async def debug_subtitle():
    """デバッグ用：字幕を仮表示する"""
    await state.broadcast_overlay({
        "type": "comment",
        "message": "こんにちは！テスト表示です",
        "response": "これはデバッグ用の字幕サンプルです。位置やサイズを調整してください！",
        "english": "This is a debug subtitle sample.",
    })
    return {"ok": True}


@router.post("/api/debug/subtitle/hide")
async def debug_subtitle_hide():
    """デバッグ用：字幕をフェードアウトする"""
    await state.broadcast_overlay({"type": "speaking_end"})
    return {"ok": True}


@router.get("/api/broadcast/volumes")
async def get_broadcast_volumes():
    """broadcast.html用の音量設定を返す（DB優先 → scenes.json → デフォルト）"""
    result = {}
    for key, fallback in [("master", 0.8), ("tts", 0.8), ("bgm", 1.0)]:
        val = db.get_setting(f"volume.{key}")
        if val is not None:
            result[key] = float(val)
        else:
            cfg_val = load_config_value(f"audio_volumes.{key}")
            result[key] = float(cfg_val) if cfg_val is not None else fallback
    return result


def _get_overlay_defaults():
    """オーバーレイのデフォルト値を読み込む（DB優先 → scenes.json）"""
    return load_config_json("overlay", {})


_OVERLAY_DEFAULTS = {
    "avatar": {"positionX": 46.5, "positionY": 24.3, "width": 53.5, "height": 75.7, "zIndex": 5},
    "lighting": {"brightness": 1.0, "contrast": 1.0, "temperature": 0.1, "saturation": 1.0, "ambient": 0.75, "directional": 1.0, "lightX": 0.5, "lightY": 1.5, "lightZ": 2.0},
    "subtitle": {"bottom": 7.4, "fontSize": 1.875, "maxWidth": 62, "fadeDuration": 3, "bgOpacity": 0.85, "zIndex": 20},
    "todo": {"positionX": 36, "positionY": 2, "width": 28, "height": 70, "fontSize": 1.25, "titleFontSize": 1.46, "bgOpacity": 0.95, "zIndex": 20},
    "topic": {"positionX": 1.04, "positionY": 1.85, "maxWidth": 31, "titleFontSize": 1.25, "bgOpacity": 0.95, "zIndex": 20},
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

    # TODOリストを即座にブロードキャスト
    await broadcast_todo()

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


@router.get("/api/lighting/presets")
async def get_lighting_presets():
    """保存済みライティングプリセット一覧を返す"""
    import json as _json
    raw = db.get_setting("lighting.presets", "[]")
    try:
        presets = _json.loads(raw)
    except Exception:
        presets = []
    return {"presets": presets}


@router.post("/api/lighting/presets")
async def save_lighting_preset(request: Request):
    """ライティングプリセットを保存する"""
    import json as _json
    body = await request.json()
    name = body.get("name", "").strip()
    values = body.get("values", {})
    if not name:
        return {"ok": False, "error": "name is required"}
    raw = db.get_setting("lighting.presets", "[]")
    try:
        presets = _json.loads(raw)
    except Exception:
        presets = []
    # 同名があれば上書き
    presets = [p for p in presets if p.get("name") != name]
    presets.append({"name": name, "values": values})
    db.set_setting("lighting.presets", _json.dumps(presets, ensure_ascii=False))
    return {"ok": True}


@router.delete("/api/lighting/presets")
async def delete_lighting_preset(request: Request):
    """ライティングプリセットを削除する"""
    import json as _json
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return {"ok": False, "error": "name is required"}
    raw = db.get_setting("lighting.presets", "[]")
    try:
        presets = _json.loads(raw)
    except Exception:
        presets = []
    presets = [p for p in presets if p.get("name") != name]
    db.set_setting("lighting.presets", _json.dumps(presets, ensure_ascii=False))
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
