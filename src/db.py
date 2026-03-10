"""データベース管理モジュール（SQLite）"""

import sqlite3
from datetime import datetime, timedelta, timezone
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

        CREATE TABLE IF NOT EXISTS bgm_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            volume REAL NOT NULL DEFAULT 1.0
        );

        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS topic_scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL REFERENCES topics(id),
            content TEXT NOT NULL,
            emotion TEXT NOT NULL DEFAULT 'neutral',
            sort_order INTEGER NOT NULL DEFAULT 0,
            spoken_at TEXT,
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
    # Migration: add display_name, note, last_seen to users
    for col, typedef in [
        ("display_name", "TEXT NOT NULL DEFAULT ''"),
        ("note", "TEXT NOT NULL DEFAULT ''"),
        ("last_seen", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef}")
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
    fields = {}
    if name is not None:
        fields["name"] = name
    if config is not None:
        fields["config"] = config
    if not fields:
        return
    fields["updated_at"] = _now()
    allowed = {"name", "config", "updated_at"}
    set_clause = ", ".join(f"{k} = ?" for k in fields if k in allowed)
    params = [v for k, v in fields.items() if k in allowed]
    params.append(character_id)
    conn.execute(
        f"UPDATE characters SET {set_clause} WHERE id = ?",
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


def update_user_last_seen(user_id):
    """ユーザーの最終コメント日時を更新する"""
    conn = get_connection()
    conn.execute("UPDATE users SET last_seen = ? WHERE id = ?", (_now(), user_id))
    conn.commit()


def update_user_note(user_id, note):
    """ユーザーメモを更新する"""
    conn = get_connection()
    conn.execute("UPDATE users SET note = ? WHERE id = ?", (note, user_id))
    conn.commit()


def get_users_commented_since(since_iso):
    """指定時刻以降にコメントしたユーザー一覧を返す（アバター自身を除く）"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT DISTINCT u.id, u.name, u.note, u.comment_count, u.first_seen
           FROM comments c JOIN users u ON c.user_id = u.id
           WHERE c.created_at > ? AND u.name NOT IN (
               SELECT json_extract(config, '$.name') FROM characters
           )
           ORDER BY u.name""",
        (since_iso,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_user_recent_comments(user_name, limit=10, hours=2):
    """指定ユーザーの直近コメントを取得する"""
    conn = get_connection()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """SELECT c.message, c.response, c.created_at
           FROM comments c JOIN users u ON c.user_id = u.id
           WHERE u.name = ? AND c.created_at > ?
           ORDER BY c.created_at DESC LIMIT ?""",
        (user_name, since, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


# --- comments ---

def save_comment(episode_id, user_id, message, response="", emotion="neutral"):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO comments (episode_id, user_id, message, response, emotion, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (episode_id, user_id, message, response, emotion, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_recent_comments(limit=20, hours=2):
    """直近N時間以内のコメントを取得する（配信またぎ対応）

    Returns:
        list[dict]: [{user_name, message, response, emotion, created_at}, ...]
    """
    conn = get_connection()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """SELECT u.name as user_name, c.message, c.response, c.emotion, c.created_at
           FROM comments c JOIN users u ON c.user_id = u.id
           WHERE c.created_at > ?
           ORDER BY c.created_at DESC LIMIT ?""",
        (since, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


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


# --- BGM tracks ---

def get_bgm_track_volume(filename):
    """BGMトラックの個別ボリュームを取得する（デフォルト1.0）"""
    conn = get_connection()
    row = conn.execute("SELECT volume FROM bgm_tracks WHERE filename = ?", (filename,)).fetchone()
    return row["volume"] if row else 1.0


def get_all_bgm_track_volumes():
    """全BGMトラックのボリュームをdict{filename: volume}で返す"""
    conn = get_connection()
    rows = conn.execute("SELECT filename, volume FROM bgm_tracks").fetchall()
    return {row["filename"]: row["volume"] for row in rows}


def set_bgm_track_volume(filename, volume):
    """BGMトラックの個別ボリュームを保存する"""
    conn = get_connection()
    conn.execute(
        "INSERT INTO bgm_tracks (filename, volume) VALUES (?, ?) "
        "ON CONFLICT(filename) DO UPDATE SET volume = excluded.volume",
        (filename, volume),
    )
    conn.commit()


# --- topics ---

def create_topic(title, description=""):
    """トピックを作成する"""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO topics (title, description, status, created_at) VALUES (?, ?, 'active', ?)",
        (title, description, _now()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM topics WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_active_topic():
    """アクティブなトピックを取得する"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM topics WHERE status = 'active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def deactivate_topic(topic_id):
    """トピックを完了にする"""
    conn = get_connection()
    conn.execute("UPDATE topics SET status = 'completed' WHERE id = ?", (topic_id,))
    conn.commit()


def deactivate_all_topics():
    """全アクティブトピックを完了にする"""
    conn = get_connection()
    conn.execute("UPDATE topics SET status = 'completed' WHERE status = 'active'")
    conn.commit()


# --- topic_scripts ---

def add_topic_scripts(topic_id, scripts):
    """トピックにスクリプトを一括追加する

    Args:
        topic_id: トピックID
        scripts: list of {"content": str, "emotion": str, "sort_order": int}
    """
    conn = get_connection()
    now = _now()
    for s in scripts:
        conn.execute(
            "INSERT INTO topic_scripts (topic_id, content, emotion, sort_order, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (topic_id, s["content"], s.get("emotion", "neutral"), s.get("sort_order", 0), now),
        )
    conn.commit()


def get_next_unspoken_script(topic_id):
    """未発話のスクリプトを1件取得する"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM topic_scripts WHERE topic_id = ? AND spoken_at IS NULL "
        "ORDER BY sort_order, id LIMIT 1",
        (topic_id,),
    ).fetchone()
    return dict(row) if row else None


def mark_script_spoken(script_id):
    """スクリプトを発話済みにする"""
    conn = get_connection()
    conn.execute(
        "UPDATE topic_scripts SET spoken_at = ? WHERE id = ?",
        (_now(), script_id),
    )
    conn.commit()


def count_unspoken_scripts(topic_id):
    """未発話スクリプトの件数を返す"""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM topic_scripts WHERE topic_id = ? AND spoken_at IS NULL",
        (topic_id,),
    ).fetchone()
    return row["cnt"]


def get_spoken_scripts(topic_id):
    """発話済みスクリプトを取得する"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM topic_scripts WHERE topic_id = ? AND spoken_at IS NOT NULL "
        "ORDER BY spoken_at",
        (topic_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_scripts(topic_id):
    """トピックの全スクリプトを取得する"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM topic_scripts WHERE topic_id = ? ORDER BY sort_order, id",
        (topic_id,),
    ).fetchall()
    return [dict(r) for r in rows]
