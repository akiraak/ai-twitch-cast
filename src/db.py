"""データベース管理モジュール（SQLite）"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = _PROJECT_DIR / "data" / "comments.db"

_conn = None


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    """DB接続を取得する（シングルトン）"""
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _create_tables(_conn)
    return _conn


def _create_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL REFERENCES channels(id),
            name TEXT NOT NULL,
            config TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS shows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL REFERENCES channels(id),
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id INTEGER NOT NULL REFERENCES shows(id),
            character_id INTEGER NOT NULL REFERENCES characters(id),
            title TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            ended_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            first_seen TEXT NOT NULL,
            comment_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id INTEGER NOT NULL REFERENCES episodes(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            message TEXT NOT NULL,
            response TEXT NOT NULL DEFAULT '',
            emotion TEXT NOT NULL DEFAULT 'neutral',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id INTEGER NOT NULL REFERENCES episodes(id),
            type TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    # Migration: add updated_at to characters
    try:
        conn.execute("ALTER TABLE characters ADD COLUMN updated_at TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass


# --- channels ---

def get_or_create_channel(name):
    conn = get_connection()
    row = conn.execute("SELECT * FROM channels WHERE name = ?", (name,)).fetchone()
    if row:
        return dict(row)
    conn.execute("INSERT INTO channels (name, created_at) VALUES (?, ?)", (name, _now()))
    conn.commit()
    return dict(conn.execute("SELECT * FROM channels WHERE name = ?", (name,)).fetchone())


# --- characters ---

def get_or_create_character(channel_id, name, config="{}"):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM characters WHERE channel_id = ? AND name = ?",
        (channel_id, name),
    ).fetchone()
    if row:
        return dict(row)
    conn.execute(
        "INSERT INTO characters (channel_id, name, config, created_at) VALUES (?, ?, ?, ?)",
        (channel_id, name, config, _now()),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM characters WHERE channel_id = ? AND name = ?",
        (channel_id, name),
    ).fetchone())


def get_character_by_channel(channel_id):
    """チャンネルのキャラクター設定を取得する"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM characters WHERE channel_id = ? ORDER BY id LIMIT 1",
        (channel_id,),
    ).fetchone()
    return dict(row) if row else None


def update_character(character_id, name=None, config=None):
    """キャラクター設定を更新する"""
    conn = get_connection()
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if config is not None:
        updates.append("config = ?")
        params.append(config)
    if not updates:
        return
    updates.append("updated_at = ?")
    params.append(_now())
    params.append(character_id)
    conn.execute(
        f"UPDATE characters SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()


# --- shows ---

def get_or_create_show(channel_id, name, description=""):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM shows WHERE channel_id = ? AND name = ?",
        (channel_id, name),
    ).fetchone()
    if row:
        return dict(row)
    conn.execute(
        "INSERT INTO shows (channel_id, name, description, created_at) VALUES (?, ?, ?, ?)",
        (channel_id, name, description, _now()),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM shows WHERE channel_id = ? AND name = ?",
        (channel_id, name),
    ).fetchone())


# --- episodes ---

def start_episode(show_id, character_id, title=""):
    conn = get_connection()
    now = _now()
    cur = conn.execute(
        "INSERT INTO episodes (show_id, character_id, title, started_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (show_id, character_id, title, now, now),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM episodes WHERE id = ?", (cur.lastrowid,)).fetchone())


def end_episode(episode_id):
    conn = get_connection()
    conn.execute("UPDATE episodes SET ended_at = ? WHERE id = ?", (_now(), episode_id))
    conn.commit()


# --- users ---

def get_or_create_user(name):
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
    if row:
        return dict(row)
    now = _now()
    conn.execute(
        "INSERT INTO users (name, first_seen, comment_count) VALUES (?, ?, 0)",
        (name, now),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone())


def increment_comment_count(user_id):
    conn = get_connection()
    conn.execute("UPDATE users SET comment_count = comment_count + 1 WHERE id = ?", (user_id,))
    conn.commit()


# --- comments ---

def save_comment(episode_id, user_id, message, response="", emotion="neutral"):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO comments (episode_id, user_id, message, response, emotion, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (episode_id, user_id, message, response, emotion, _now()),
    )
    conn.commit()
    return cur.lastrowid


# --- actions ---

def save_action(episode_id, action_type, detail=""):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO actions (episode_id, type, detail, created_at) VALUES (?, ?, ?, ?)",
        (episode_id, action_type, detail, _now()),
    )
    conn.commit()
    return cur.lastrowid


# --- queries ---

def get_user_comment_count(user_name):
    """ユーザーのコメント数を取得する"""
    conn = get_connection()
    row = conn.execute("SELECT comment_count FROM users WHERE name = ?", (user_name,)).fetchone()
    return row["comment_count"] if row else 0
