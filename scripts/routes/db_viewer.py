"""DB閲覧ルート"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from src import db
from src.ai_responder import generate_self_note, generate_user_notes, get_character

logger = logging.getLogger(__name__)

router = APIRouter()

# カスタムクエリ（JOINなど特別な表示が必要なテーブル）
CUSTOM_QUERIES = {
    "comments": {
        "query": """
            SELECT c.id, u.name as user, c.message, c.response, c.emotion, c.created_at
            FROM comments c JOIN users u ON c.user_id = u.id
            ORDER BY c.id DESC LIMIT ? OFFSET ?
        """,
    },
    "topic_scripts": {
        "query": """
            SELECT ts.id, t.title as topic, ts.content, ts.emotion, ts.spoken_at
            FROM topic_scripts ts JOIN topics t ON ts.topic_id = t.id
            ORDER BY ts.id DESC LIMIT ? OFFSET ?
        """,
    },
}


def _get_all_tables(conn):
    """DBから全テーブル名を取得（sqlite内部テーブルを除外）"""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


@router.get("/api/db/tables")
async def list_tables():
    """テーブル一覧を返す"""
    conn = db.get_connection()
    result = []
    for name in _get_all_tables(conn):
        row = conn.execute(f"SELECT COUNT(*) as cnt FROM [{name}]").fetchone()
        result.append({"name": name, "count": row["cnt"]})
    return {"tables": result}


@router.post("/api/db/update-notes")
async def update_notes():
    """ユーザーメモを手動で即時更新する"""
    since = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    users = await asyncio.to_thread(db.get_users_commented_since, since)
    if not users:
        return {"ok": True, "updated": 0, "message": "対象ユーザーなし"}

    users_data = []
    for u in users:
        comments = await asyncio.to_thread(db.get_user_recent_comments, u["name"], 10, 2)
        if comments:
            users_data.append({
                "name": u["name"],
                "note": u.get("note", ""),
                "comments": comments,
            })
    if not users_data:
        return {"ok": True, "updated": 0, "message": "コメントなし"}

    logger.info("[note] 手動メモ更新中... (%d人)", len(users_data))
    notes = await asyncio.to_thread(generate_user_notes, users_data)
    updated = 0
    for u in users:
        if u["name"] in notes and notes[u["name"]]:
            await asyncio.to_thread(db.update_user_note, u["id"], notes[u["name"]])
            updated += 1

    logger.info("[note] 手動メモ更新完了: %s", notes)

    # アバター自身のメモも更新
    try:
        char_name = get_character().get("name", "ちょビ")
        avatar_user = await asyncio.to_thread(db.get_or_create_user, char_name)
        recent = await asyncio.to_thread(db.get_recent_comments, 20, 2)
        if recent:
            current_note = avatar_user.get("note", "")
            new_note = await asyncio.to_thread(generate_self_note, recent, current_note)
            if new_note and new_note != current_note:
                await asyncio.to_thread(db.update_user_note, avatar_user["id"], new_note)
                updated += 1
                notes[char_name] = new_note
                logger.info("[note] アバターメモ更新: %s", new_note)
    except Exception as e:
        logger.warning("[note] アバターメモ更新失敗: %s", e)

    return {"ok": True, "updated": updated, "notes": notes}


@router.get("/api/db/{table}")
async def get_table(table: str, limit: int = 50, offset: int = 0):
    """テーブルデータを返す"""
    conn = db.get_connection()
    if table not in _get_all_tables(conn):
        return {"error": f"テーブル '{table}' は閲覧できません"}
    count_row = conn.execute(f"SELECT COUNT(*) as cnt FROM [{table}]").fetchone()
    if table in CUSTOM_QUERIES:
        rows = conn.execute(CUSTOM_QUERIES[table]["query"], (limit, offset)).fetchall()
    else:
        rows = conn.execute(f"SELECT * FROM [{table}] LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return {
        "table": table,
        "total": count_row["cnt"],
        "offset": offset,
        "limit": limit,
        "columns": list(rows[0].keys()) if rows else [],
        "rows": [dict(r) for r in rows],
    }
