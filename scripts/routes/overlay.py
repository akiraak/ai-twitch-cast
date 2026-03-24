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


def _get_todo_active():
    """現在のアクティブTODO IDを返す ("project" or UUID)"""
    return db.get_setting("todo.active", "project")


def _get_todo_files():
    """DB保存済みTODOファイル一覧を返す [{id, name, path}]"""
    raw = db.get_setting("todo.files", "[]")
    try:
        return _json_mod.loads(raw)
    except (ValueError, TypeError):
        return []


def _set_todo_files(files: list):
    db.set_setting("todo.files", _json_mod.dumps(files, ensure_ascii=False))


def _get_in_progress(file_id: str) -> list[str]:
    raw = db.get_setting(f"todo.ip.{file_id}", "[]")
    try:
        return _json_mod.loads(raw)
    except (ValueError, TypeError):
        return []


def _set_in_progress(file_id: str, items: list[str]):
    db.set_setting(f"todo.ip.{file_id}", _json_mod.dumps(items, ensure_ascii=False))


def _parse_todo_text(text: str, in_progress_override: list[str] | None = None):
    """TODOテキストをパースしてアイテムリストを返す"""
    items = []
    current_section = ""
    for line in text.splitlines():
        m_section = re.match(r"\s*##\s+(.*)", line)
        if m_section:
            current_section = m_section.group(1).strip()
            continue
        m = re.match(r"\s*-\s*\[\s*\]\s*(.*)", line)
        if m:
            task_text = m.group(1).strip()
            status = "in_progress" if in_progress_override is not None and task_text in in_progress_override else "todo"
            items.append({"text": task_text, "status": status, "section": current_section})
            continue
        m = re.match(r"\s*-\s*\[>\]\s*(.*)", line)
        if m:
            items.append({"text": m.group(1).strip(), "status": "in_progress", "section": current_section})
    # 作業中タスクを「作業中」セクションとして先頭に表示
    in_progress = [{"text": i["text"], "status": i["status"], "section": "作業中"} for i in items if i["status"] == "in_progress"]
    others = [i for i in items if i["status"] != "in_progress"]
    return in_progress + others


async def broadcast_todo():
    """TODOを読み込み、todo_updateイベントをブロードキャストする"""
    todo_data = await get_todo()
    event = {"type": "todo_update", "items": todo_data["items"]}
    await state.broadcast_overlay(event)


async def _watch_todo_file():
    """TODO.mdのmtimeを監視し、変更があればブロードキャストする（projectソースのみ）"""
    global _todo_last_mtime
    todo_path = TODO_PATH
    if todo_path.exists():
        _todo_last_mtime = todo_path.stat().st_mtime
    while True:
        await asyncio.sleep(2)
        try:
            if _get_todo_active() != "project":
                continue
            todo_path = TODO_PATH
            if not todo_path.exists():
                continue
            mtime = todo_path.stat().st_mtime
            if mtime != _todo_last_mtime:
                _todo_last_mtime = mtime
                await broadcast_todo()
        except Exception as e:
            logger.debug("TODO監視エラー: %s", e)


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
    except Exception as e:
        logger.debug("WS初期BGM送信失敗: %s", e)
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
    except Exception as e:
        logger.debug("WS初期音量送信失敗: %s", e)
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
                    elif source.startswith("overlay."):
                        db.set_setting(source, volume)
                        logger.debug("設定保存(WS): %s = %s", source, volume)
                elif msg.get("type") == "save_track_volume":
                    file = msg.get("file", "")
                    volume = msg.get("volume", 1.0)
                    if file:
                        db.set_bgm_track_volume(file, volume)
                        logger.debug("曲別音量保存(WS): %s = %.2f", file, volume)
            except (ValueError, KeyError) as e:
                logger.debug("WSメッセージ処理失敗: %s", e)
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



@router.get("/api/broadcast/token")
async def broadcast_token():
    """broadcast.htmlアクセス用トークンを返す（レイアウト編集用）"""
    return {"token": BROADCAST_TOKEN}



@router.post("/api/debug/subtitle")
async def debug_subtitle():
    """デバッグ用：字幕を仮表示する"""
    await state.broadcast_overlay({
        "type": "comment",
        "trigger_text": "こんにちは！テスト表示です",
        "speech": "これはデバッグ用の字幕サンプルです。位置やサイズを調整してください！",
        "translation": "This is a debug subtitle sample.",
    })
    return {"ok": True}


@router.post("/api/debug/subtitle/hide")
async def debug_subtitle_hide():
    """デバッグ用：字幕をフェードアウトする"""
    await state.broadcast_overlay({"type": "speaking_end"})
    return {"ok": True}


@router.post("/api/debug/lesson-text")
async def debug_lesson_text():
    """デバッグ用：授業テキストを仮表示する"""
    await state.broadcast_overlay({
        "type": "lesson_text_show",
        "text": "授業テキストのプレビュー\n\nここに教材の内容が表示されます。\n背景・文字・位置を調整してください。",
    })
    return {"ok": True}


@router.post("/api/debug/lesson-text/hide")
async def debug_lesson_text_hide():
    """デバッグ用：授業テキストを非表示にする"""
    await state.broadcast_overlay({"type": "lesson_text_hide"})
    return {"ok": True}


@router.post("/api/debug/expression/{name}")
async def debug_expression(name: str, value: float = 1.0):
    """デバッグ用：表情テスト（blendshapeイベント直送）"""
    event = {"type": "blendshape", "shapes": {name: value}}
    await state.broadcast_overlay(event)
    return {"ok": True, "sent": event}


@router.post("/api/debug/expression-reset")
async def debug_expression_reset():
    """デバッグ用：全表情リセット"""
    shapes = {n: 0.0 for n in ["happy", "angry", "sad", "relaxed", "surprised"]}
    event = {"type": "blendshape", "shapes": shapes}
    await state.broadcast_overlay(event)
    return {"ok": True, "sent": event}


@router.post("/api/debug/jslog")
async def debug_jslog(request: Request):
    """ブラウザのconsole.logをファイルに保存"""
    import aiofiles
    body = await request.json()
    lines = body.get("lines", [])
    async with aiofiles.open("jslog.txt", "a") as f:
        for line in lines:
            await f.write(line + "\n")
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


# 全アイテム共通デフォルト
_COMMON_DEFAULTS = {
    "visible": 1,
    "positionX": 0,
    "positionY": 0,
    "width": 50,
    "height": 50,
    "zIndex": 10,
    "bgColor": "rgba(20,20,35,1)",
    "bgOpacity": 0.85,
    "borderRadius": 8,
    "borderColor": "rgba(255,255,255,0.5)",
    "borderSize": 1,
    "borderOpacity": 1.0,
    "backdropBlur": 6,
    "textColor": "#e0e0e0",
    "fontSize": 1.0,
    "textStrokeColor": "rgba(0,0,0,0.8)",
    "textStrokeSize": 0,
    "textStrokeOpacity": 0.8,
    "padding": 8,
}


def _make_item_defaults(overrides):
    """共通デフォルトにアイテム固有のオーバーライドをマージ"""
    return {**_COMMON_DEFAULTS, **overrides}


_OVERLAY_DEFAULTS = {
    "avatar1": _make_item_defaults({
        "positionX": 46.5, "positionY": 24.3, "width": 53.5, "height": 75.7,
        "zIndex": 5, "bgOpacity": 0, "borderRadius": 0, "padding": 0,
    }),
    "avatar2": _make_item_defaults({
        "positionX": 0, "positionY": 30, "width": 40, "height": 70,
        "zIndex": 4, "bgOpacity": 0, "borderRadius": 0, "borderSize": 0,
        "padding": 0, "backdropBlur": 0,
    }),
    "lighting": {
        "brightness": 1.0, "contrast": 1.0, "temperature": 0.1, "saturation": 1.0,
        "ambient": 0.75, "directional": 1.0, "lightX": 0.5, "lightY": 1.5, "lightZ": 2.0,
    },
    "lighting_teacher": {
        "brightness": 1.0, "contrast": 1.0, "temperature": 0.1, "saturation": 1.0,
        "ambient": 0.75, "directional": 1.0, "lightX": 0.5, "lightY": 1.5, "lightZ": 2.0,
    },
    "lighting_student": {
        "brightness": 1.0, "contrast": 1.0, "temperature": 0.1, "saturation": 1.0,
        "ambient": 0.75, "directional": 1.0, "lightX": 0.5, "lightY": 1.5, "lightZ": 2.0,
    },
    "subtitle": _make_item_defaults({
        "bottom": 7.4, "fontSize": 1.875, "maxWidth": 62, "fadeDuration": 3,
        "bgOpacity": 0.85, "zIndex": 20, "borderRadius": 12, "padding": 16,
    }),
    "todo": _make_item_defaults({
        "positionX": 36, "positionY": 2, "width": 28, "height": 70,
        "fontSize": 1.25, "titleFontSize": 1.46, "bgOpacity": 0.95, "zIndex": 20,
    }),
    "lesson_text": _make_item_defaults({
        "bgOpacity": 0.65, "backdropBlur": 12,
        "fontSize": 1.4, "lineHeight": 1.7, "maxHeight": 70,
        "bgColor": "#0a0a1e", "borderColor": "#7c4dff", "borderOpacity": 0.3,
        "textColor": "#ffffff",
    }),
    "lesson_progress": _make_item_defaults({
        "bgOpacity": 0.6, "backdropBlur": 10,
        "titleFontSize": 1.1, "itemFontSize": 0.95,
        "bgColor": "#0a0a1e", "borderColor": "#7c4dff", "borderOpacity": 0.3,
        "textColor": "#ffffff",
    }),
    "sync": {"lipsyncDelay": 100},
}


@router.get("/api/overlay/settings")
async def get_overlay_settings():
    """レイアウト設定を返す（broadcast_items優先→overlay.* settings→デフォルト）"""
    file_defaults = _get_overlay_defaults()
    result = {}

    # broadcast_itemsテーブルからの読み込みを試行
    items_map = {}
    try:
        items = db.get_broadcast_items()
        for item in items:
            items_map[item["id"]] = item
    except Exception:
        pass

    for section, props in _OVERLAY_DEFAULTS.items():
        result[section] = {}
        file_section = file_defaults.get(section, {})
        bi = items_map.get(section)

        for prop, fallback in props.items():
            # 1. broadcast_itemsテーブルから取得
            if bi and prop in bi:
                result[section][prop] = bi[prop]
                continue
            # 2. overlay.* settings（旧形式フォールバック）
            val = db.get_setting(f"overlay.{section}.{prop}")
            if val is not None:
                try:
                    result[section][prop] = float(val)
                except (ValueError, TypeError):
                    result[section][prop] = val
            else:
                result[section][prop] = file_section.get(prop, fallback)
    return result


@router.get("/api/todo")
async def get_todo():
    """TODOから未完了タスクを返す（プロジェクトファイル or DB保存ファイル）"""
    active = _get_todo_active()
    if active != "project":
        content = db.get_setting(f"todo.file.{active}.content", "")
        if not content:
            return {"items": []}
        ip_list = _get_in_progress(active)
        return {"items": _parse_todo_text(content, in_progress_override=ip_list)}
    # project source
    todo_path = TODO_PATH
    if not todo_path.exists():
        return {"items": []}
    text = todo_path.read_text(encoding="utf-8")
    return {"items": _parse_todo_text(text)}


@router.post("/api/todo/start")
async def start_todo(request: Request):
    """TODOを作業中にマークし、アバターに読み上げさせる"""
    body = await request.json()
    task_text = body.get("text", "").strip()
    if not task_text:
        return {"ok": False, "error": "タスクが見つかりません"}

    active = _get_todo_active()
    if active != "project":
        # DB管理: リストに追加
        ip_list = _get_in_progress(active)
        if task_text not in ip_list:
            ip_list.append(task_text)
        _set_in_progress(active, ip_list)
    else:
        # ファイル書き戻し
        todo_path = TODO_PATH
        if not todo_path.exists():
            return {"ok": False, "error": "タスクが見つかりません"}
        text = todo_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        found = False
        new_lines = []
        for line in lines:
            m_todo = re.match(r"(\s*-\s*)\[\s*\](\s*)(.*)", line)
            if m_todo and m_todo.group(3).strip() == task_text:
                new_lines.append(f"{m_todo.group(1)}[>]{m_todo.group(2)}{m_todo.group(3)}")
                found = True
                continue
            new_lines.append(line)
        if not found:
            return {"ok": False, "error": "タスクが見つかりません"}
        todo_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    await state.broadcast_overlay({"type": "current_task", "task": task_text})
    await broadcast_todo()

    if state.reader:
        asyncio.create_task(state.reader.speak_event("作業開始", task_text))

    return {"ok": True}


@router.post("/api/todo/stop")
async def stop_todo(request: Request):
    """作業中のTODOを未着手に戻す"""
    body = await request.json()
    task_text = body.get("text", "").strip()
    if not task_text:
        return {"ok": False, "error": "タスクが見つかりません"}

    active = _get_todo_active()
    if active != "project":
        ip_list = _get_in_progress(active)
        if task_text not in ip_list:
            return {"ok": False, "error": "タスクが見つかりません"}
        _set_in_progress(active, [t for t in ip_list if t != task_text])
    else:
        todo_path = TODO_PATH
        if not todo_path.exists():
            return {"ok": False, "error": "タスクが見つかりません"}
        text = todo_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        found = False
        new_lines = []
        for line in lines:
            m = re.match(r"(\s*-\s*)\[>\](\s*)(.*)", line)
            if m and m.group(3).strip() == task_text:
                new_lines.append(f"{m.group(1)}[ ]{m.group(2)}{m.group(3)}")
                found = True
                continue
            new_lines.append(line)
        if not found:
            return {"ok": False, "error": "タスクが見つかりません"}
        todo_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    await broadcast_todo()
    return {"ok": True}


@router.get("/api/todo/files")
async def list_todo_files():
    """保存済みTODOファイル一覧+アクティブIDを返す"""
    files = _get_todo_files()
    active = _get_todo_active()
    return {"files": files, "active": active, "project_dir": str(PROJECT_DIR)}


@router.post("/api/todo/upload")
async def upload_todo(request: Request):
    """外部TODO.mdをアップロードしてDBに保存し、アクティブにする"""
    body = await request.json()
    content = body.get("content", "")
    name = body.get("name", "TODO.md")

    # 同名ファイルがあれば更新、なければ新規追加
    files = _get_todo_files()
    file_id = None
    for f in files:
        if f["name"] == name:
            file_id = f["id"]
            break
    if file_id is None:
        file_id = secrets.token_hex(6)
        files.append({"id": file_id, "name": name})

    _set_todo_files(files)
    db.set_setting(f"todo.file.{file_id}.content", content)
    db.set_setting("todo.active", file_id)
    await broadcast_todo()
    return {"ok": True, "id": file_id}


@router.post("/api/todo/switch")
async def switch_todo(request: Request):
    """アクティブTODOファイルを切り替える"""
    body = await request.json()
    file_id = body.get("id", "project")
    if file_id != "project":
        files = _get_todo_files()
        if not any(f["id"] == file_id for f in files):
            return {"ok": False, "error": "ファイルが見つかりません"}
    db.set_setting("todo.active", file_id)
    await broadcast_todo()
    return {"ok": True}


@router.delete("/api/todo/files/{file_id}")
async def delete_todo_file(file_id: str):
    """保存済みTODOファイルを削除する"""
    files = _get_todo_files()
    new_files = [f for f in files if f["id"] != file_id]
    if len(new_files) == len(files):
        return {"ok": False, "error": "ファイルが見つかりません"}
    _set_todo_files(new_files)
    # コンテンツとin_progressも削除
    db.set_setting(f"todo.file.{file_id}.content", "")
    db.set_setting(f"todo.ip.{file_id}", "[]")
    # アクティブだったらprojectに戻す
    if _get_todo_active() == file_id:
        db.set_setting("todo.active", "project")
    await broadcast_todo()
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
    logger.info("[overlay] save_settings: %s", {k: v for k, v in body.items() if k != "type"})
    fixed_items = {"avatar", "avatar1", "avatar2", "subtitle", "todo", "lesson_text", "lesson_progress"}
    for section, props in body.items():
        if not isinstance(props, dict):
            continue
        if section in fixed_items:
            # broadcast_itemsテーブルに保存
            db.upsert_broadcast_item(section, section, props)
        else:
            # lighting/sync等はsettingsテーブルに保存（従来通り）
            for prop, val in props.items():
                db.set_setting(f"overlay.{section}.{prop}", val)
    # 変更されたプロパティのみブロードキャスト（他のプロパティでドラッグ位置を上書きしない）
    await state.broadcast_overlay({"type": "settings_update", **body})
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


# --- カスタムテキスト ---

@router.get("/api/overlay/custom-texts")
async def get_custom_texts():
    """カスタムテキストアイテム一覧を返す"""
    return db.get_custom_texts()


@router.post("/api/overlay/custom-texts")
async def create_custom_text(request: Request):
    """カスタムテキストを新規作成"""
    body = await request.json()
    item = db.create_custom_text(
        label=body.get("label", ""),
        content=body.get("content", ""),
        layout=body.get("layout"),
    )
    await state.broadcast_overlay({
        "type": "custom_text_add", **item,
    })
    return item


@router.put("/api/overlay/custom-texts/{text_id}")
async def update_custom_text(text_id: int, request: Request):
    """カスタムテキストを更新（label, content, layout properties）"""
    body = await request.json()
    db.update_custom_text(text_id, **body)
    await state.broadcast_overlay({
        "type": "custom_text_update", "id": text_id, **body,
    })
    return {"ok": True}


@router.post("/api/overlay/custom-texts/{text_id}/layout")
async def update_custom_text_layout(text_id: int, request: Request):
    """カスタムテキストのレイアウトのみ更新（broadcast.htmlドラッグ保存用）"""
    body = await request.json()
    db.update_custom_text_layout(text_id, body)
    return {"ok": True}


@router.delete("/api/overlay/custom-texts/{text_id}")
async def delete_custom_text(text_id: int):
    """カスタムテキストを削除"""
    db.delete_custom_text(text_id)
    await state.broadcast_overlay({
        "type": "custom_text_remove", "id": text_id,
    })
    return {"ok": True}
