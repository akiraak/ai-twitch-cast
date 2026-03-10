"""DB閲覧ルート"""

from fastapi import APIRouter

from src import db

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
        "query": "SELECT id, name, comment_count, first_seen FROM users ORDER BY comment_count DESC LIMIT ? OFFSET ?",
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
