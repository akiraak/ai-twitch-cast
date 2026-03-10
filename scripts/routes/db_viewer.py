"""DB閲覧ルート"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from src import db
from src.ai_responder import generate_user_notes

logger = logging.getLogger(__name__)

router = APIRouter()

# 閲覧可能テーブルとカラム定義
TABLES = {
    "comments": {
        "query": """
            SELECT c.id, u.name as user, c.message, c.response, c.emotion, c.created_at
            FROM comments c JOIN users u ON c.user_id = u.id
            ORDER BY c.id DESC LIMIT ? OFFSET ?
        """,
        "count": "SELECT COUNT(*) as cnt FROM comments",
    },
    "users": {
        "query": "SELECT id, name, note, comment_count, first_seen, last_seen FROM users ORDER BY comment_count DESC LIMIT ? OFFSET ?",
        "count": "SELECT COUNT(*) as cnt FROM users",
    },
    "episodes": {
        "query": "SELECT id, show_id, character_id, title, started_at, ended_at FROM episodes ORDER BY id DESC LIMIT ? OFFSET ?",
        "count": "SELECT COUNT(*) as cnt FROM episodes",
    },
    "topics": {
        "query": "SELECT id, title, description, status, created_at FROM topics ORDER BY id DESC LIMIT ? OFFSET ?",
        "count": "SELECT COUNT(*) as cnt FROM topics",
    },
    "topic_scripts": {
        "query": "SELECT ts.id, t.title as topic, ts.content, ts.emotion, ts.spoken_at FROM topic_scripts ts JOIN topics t ON ts.topic_id = t.id ORDER BY ts.id DESC LIMIT ? OFFSET ?",
        "count": "SELECT COUNT(*) as cnt FROM topic_scripts",
    },
    "bgm_tracks": {
        "query": "SELECT id, filename, volume FROM bgm_tracks ORDER BY id LIMIT ? OFFSET ?",
        "count": "SELECT COUNT(*) as cnt FROM bgm_tracks",
    },
}


@router.get("/api/db/tables")
async def list_tables():
    """テーブル一覧を返す"""
    conn = db.get_connection()
    result = []
    for name in TABLES:
        row = conn.execute(TABLES[name]["count"]).fetchone()
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
    return {"ok": True, "updated": updated, "notes": notes}


@router.get("/api/db/{table}")
async def get_table(table: str, limit: int = 50, offset: int = 0):
    """テーブルデータを返す"""
    if table not in TABLES:
        return {"error": f"テーブル '{table}' は閲覧できません"}
    conn = db.get_connection()
    count_row = conn.execute(TABLES[table]["count"]).fetchone()
    rows = conn.execute(TABLES[table]["query"], (limit, offset)).fetchall()
    return {
        "table": table,
        "total": count_row["cnt"],
        "offset": offset,
        "limit": limit,
        "columns": list(rows[0].keys()) if rows else [],
        "rows": [dict(r) for r in rows],
    }
