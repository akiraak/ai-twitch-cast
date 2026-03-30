"""TODO操作ロジック（パース・取得・start/stop・ファイル管理）"""

import json as _json_mod
import logging
import re
import secrets
from pathlib import Path

from src import db

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
TODO_PATH = PROJECT_DIR / "TODO.md"


def get_active_source() -> str:
    """現在のアクティブTODOソースIDを返す ("project" or UUID)"""
    return db.get_setting("todo.active", "project")


def get_files() -> list[dict]:
    """DB保存済みTODOファイル一覧を返す [{id, name, path}]"""
    raw = db.get_setting("todo.files", "[]")
    try:
        return _json_mod.loads(raw)
    except (ValueError, TypeError):
        return []


def _set_files(files: list):
    db.set_setting("todo.files", _json_mod.dumps(files, ensure_ascii=False))


def get_in_progress(file_id: str) -> list[str]:
    raw = db.get_setting(f"todo.ip.{file_id}", "[]")
    try:
        return _json_mod.loads(raw)
    except (ValueError, TypeError):
        return []


def set_in_progress(file_id: str, items: list[str]):
    db.set_setting(f"todo.ip.{file_id}", _json_mod.dumps(items, ensure_ascii=False))


def parse_todo_text(text: str, in_progress_override: list[str] | None = None) -> list[dict]:
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


def get_items() -> dict:
    """TODOアイテムを返す（プロジェクトファイル or DB保存ファイル）"""
    active = get_active_source()
    if active != "project":
        content = db.get_setting(f"todo.file.{active}.content", "")
        if not content:
            return {"items": []}
        ip_list = get_in_progress(active)
        return {"items": parse_todo_text(content, in_progress_override=ip_list)}
    # project source
    todo_path = TODO_PATH
    if not todo_path.exists():
        return {"items": []}
    text = todo_path.read_text(encoding="utf-8")
    return {"items": parse_todo_text(text)}


def _modify_project_file_start(task_text: str) -> bool:
    """TODO.mdの [ ] → [>] に変更"""
    todo_path = TODO_PATH
    if not todo_path.exists():
        return False
    text = todo_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    found = False
    new_lines = []
    for line in lines:
        m = re.match(r"(\s*-\s*)\[\s*\](\s*)(.*)", line)
        if m and m.group(3).strip() == task_text:
            new_lines.append(f"{m.group(1)}[>]{m.group(2)}{m.group(3)}")
            found = True
            continue
        new_lines.append(line)
    if not found:
        return False
    todo_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


def _modify_project_file_stop(task_text: str) -> bool:
    """TODO.mdの [>] → [ ] に変更"""
    todo_path = TODO_PATH
    if not todo_path.exists():
        return False
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
        return False
    todo_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


def start_task(task_text: str) -> tuple[bool, str]:
    """タスクを作業中にマークする。(成功, エラーメッセージ)を返す。"""
    active = get_active_source()
    if active != "project":
        ip_list = get_in_progress(active)
        if task_text not in ip_list:
            ip_list.append(task_text)
        set_in_progress(active, ip_list)
    else:
        if not _modify_project_file_start(task_text):
            return False, "タスクが見つかりません"
    return True, ""


def stop_task(task_text: str) -> tuple[bool, str]:
    """作業中タスクを未着手に戻す。(成功, エラーメッセージ)を返す。"""
    active = get_active_source()
    if active != "project":
        ip_list = get_in_progress(active)
        if task_text not in ip_list:
            return False, "タスクが見つかりません"
        set_in_progress(active, [t for t in ip_list if t != task_text])
    else:
        if not _modify_project_file_stop(task_text):
            return False, "タスクが見つかりません"
    return True, ""


def upload_file(content: str, name: str) -> str:
    """外部TODO.mdをDBに保存し、アクティブにする。file_idを返す。"""
    files = get_files()
    file_id = None
    for f in files:
        if f["name"] == name:
            file_id = f["id"]
            break
    if file_id is None:
        file_id = secrets.token_hex(6)
        files.append({"id": file_id, "name": name})

    _set_files(files)
    db.set_setting(f"todo.file.{file_id}.content", content)
    db.set_setting("todo.active", file_id)
    return file_id


def switch_source(file_id: str) -> tuple[bool, str]:
    """アクティブTODOソースを切り替える。(成功, エラーメッセージ)を返す。"""
    if file_id != "project":
        files = get_files()
        if not any(f["id"] == file_id for f in files):
            return False, "ファイルが見つかりません"
    db.set_setting("todo.active", file_id)
    return True, ""


def delete_file(file_id: str) -> tuple[bool, str]:
    """保存済みTODOファイルを削除する。(成功, エラーメッセージ)を返す。"""
    files = get_files()
    new_files = [f for f in files if f["id"] != file_id]
    if len(new_files) == len(files):
        return False, "ファイルが見つかりません"
    _set_files(new_files)
    db.set_setting(f"todo.file.{file_id}.content", "")
    db.set_setting(f"todo.ip.{file_id}", "[]")
    if get_active_source() == file_id:
        db.set_setting("todo.active", "project")
    return True, ""
