"""データベース管理モジュール（SQLite）"""

import json as _json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = _PROJECT_DIR / "data" / "app.db"

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

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bgm_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            volume REAL NOT NULL DEFAULT 1.0,
            source_url TEXT
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
        CREATE TABLE IF NOT EXISTS dev_repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            local_path TEXT NOT NULL,
            branch TEXT DEFAULT 'main',
            last_commit_hash TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS custom_texts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            x REAL NOT NULL DEFAULT 5,
            y REAL NOT NULL DEFAULT 5,
            width REAL NOT NULL DEFAULT 20,
            height REAL NOT NULL DEFAULT 15,
            font_size REAL NOT NULL DEFAULT 1.2,
            bg_opacity REAL NOT NULL DEFAULT 0.85,
            z_index INTEGER NOT NULL DEFAULT 15,
            visible INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS capture_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            window_name TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            x REAL NOT NULL DEFAULT 5,
            y REAL NOT NULL DEFAULT 10,
            width REAL NOT NULL DEFAULT 40,
            height REAL NOT NULL DEFAULT 50,
            z_index INTEGER NOT NULL DEFAULT 10,
            visible INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS broadcast_items (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            x REAL NOT NULL DEFAULT 0,
            y REAL NOT NULL DEFAULT 0,
            width REAL NOT NULL DEFAULT 50,
            height REAL NOT NULL DEFAULT 50,
            z_index INTEGER NOT NULL DEFAULT 10,
            visible INTEGER NOT NULL DEFAULT 1,
            bg_color TEXT NOT NULL DEFAULT 'rgba(20,20,35,1)',
            bg_opacity REAL NOT NULL DEFAULT 0.85,
            border_radius REAL NOT NULL DEFAULT 8,
            border_enabled INTEGER NOT NULL DEFAULT 0,
            border_color TEXT NOT NULL DEFAULT 'rgba(255,255,255,0.5)',
            border_size REAL NOT NULL DEFAULT 1,
            border_opacity REAL NOT NULL DEFAULT 1.0,
            text_color TEXT NOT NULL DEFAULT '#e0e0e0',
            font_size REAL NOT NULL DEFAULT 1.0,
            text_stroke_color TEXT NOT NULL DEFAULT 'rgba(0,0,0,0.8)',
            text_stroke_size REAL NOT NULL DEFAULT 0,
            text_stroke_opacity REAL NOT NULL DEFAULT 0.8,
            padding REAL NOT NULL DEFAULT 8,
            properties TEXT NOT NULL DEFAULT '{}',
            created_at TEXT,
            updated_at TEXT
        );
    """)
    conn.commit()
    # Migration: add updated_at to characters
    try:
        conn.execute("ALTER TABLE characters ADD COLUMN updated_at TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    # Migration: add source_url to bgm_tracks
    try:
        conn.execute("ALTER TABLE bgm_tracks ADD COLUMN source_url TEXT")
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
    # Migration: overlay.* settings → broadcast_items
    try:
        migrate_overlay_to_items()
    except Exception:
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


def count_user_comments_in_episode(episode_id, user_id):
    """このエピソード（配信）でのユーザーのコメント数を返す"""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM comments WHERE episode_id = ? AND user_id = ?",
        (episode_id, user_id),
    ).fetchone()
    return row["cnt"]


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


def get_all_bgm_tracks():
    """全BGMトラック情報を返す（filename → {volume, source_url}）"""
    conn = get_connection()
    rows = conn.execute("SELECT filename, volume, source_url FROM bgm_tracks").fetchall()
    return {row["filename"]: {"volume": row["volume"], "source_url": row["source_url"]} for row in rows}


def set_bgm_track_volume(filename, volume):
    """BGMトラックの個別ボリュームを保存する"""
    conn = get_connection()
    conn.execute(
        "INSERT INTO bgm_tracks (filename, volume) VALUES (?, ?) "
        "ON CONFLICT(filename) DO UPDATE SET volume = excluded.volume",
        (filename, volume),
    )
    conn.commit()


def set_bgm_track_source_url(filename, source_url):
    """BGMトラックのソースURLを保存する"""
    conn = get_connection()
    conn.execute(
        "INSERT INTO bgm_tracks (filename, volume, source_url) VALUES (?, 1.0, ?) "
        "ON CONFLICT(filename) DO UPDATE SET source_url = excluded.source_url",
        (filename, source_url),
    )
    conn.commit()


def delete_bgm_track_volume(filename):
    """BGMトラックのボリュームレコードを削除する"""
    conn = get_connection()
    conn.execute("DELETE FROM bgm_tracks WHERE filename = ?", (filename,))
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


# --- settings ---

def get_setting(key, default=None):
    """設定値を取得する"""
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    """設定値を保存する"""
    conn = get_connection()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()


def get_settings_by_prefix(prefix):
    """プレフィックスに一致する設定をdict{key: value}で返す"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key LIKE ?", (prefix + "%",)
    ).fetchall()
    return {row["key"]: row["value"] for row in rows}


# --- capture_windows ---

def get_capture_windows():
    """保存済みキャプチャウィンドウ一覧を返す"""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM capture_windows ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def upsert_capture_window(window_name, label="", layout=None):
    """キャプチャウィンドウを追加/更新（window_nameで一意）"""
    if not window_name:
        return
    conn = get_connection()
    layout = layout or {}
    conn.execute(
        """INSERT INTO capture_windows (window_name, label, x, y, width, height, z_index, visible, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(window_name) DO UPDATE SET
             label = excluded.label,
             x = excluded.x, y = excluded.y,
             width = excluded.width, height = excluded.height,
             z_index = excluded.z_index, visible = excluded.visible""",
        (
            window_name,
            label or window_name,
            layout.get("x", 5),
            layout.get("y", 10),
            layout.get("width", 40),
            layout.get("height", 50),
            layout.get("zIndex", 10),
            1 if layout.get("visible", True) else 0,
            _now(),
        ),
    )
    conn.commit()


def update_capture_window_layout(window_name, layout_update):
    """キャプチャウィンドウのレイアウトを部分更新"""
    if not window_name:
        return
    conn = get_connection()
    col_map = {"x": "x", "y": "y", "width": "width", "height": "height", "zIndex": "z_index", "visible": "visible"}
    sets = []
    vals = []
    for key, val in layout_update.items():
        col = col_map.get(key)
        if col:
            if key == "visible":
                val = 1 if val else 0
            sets.append(f"{col} = ?")
            vals.append(val)
    if not sets:
        return
    vals.append(window_name)
    conn.execute(f"UPDATE capture_windows SET {', '.join(sets)} WHERE window_name = ?", vals)
    conn.commit()


def delete_capture_window(window_name):
    """キャプチャウィンドウを削除"""
    conn = get_connection()
    conn.execute("DELETE FROM capture_windows WHERE window_name = ?", (window_name,))
    conn.commit()


def get_capture_window_by_name(window_name):
    """ウィンドウ名でキャプチャウィンドウを取得"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM capture_windows WHERE window_name = ?", (window_name,)).fetchone()
    return dict(row) if row else None


# --- dev_repos ---

def add_dev_repo(name, url, local_path, branch="main"):
    """開発配信用リポジトリを追加する"""
    conn = get_connection()
    now = _now()
    cur = conn.execute(
        "INSERT INTO dev_repos (name, url, local_path, branch, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, url, local_path, branch, now, now),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM dev_repos WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_dev_repos():
    """全リポジトリ一覧を返す"""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM dev_repos ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_active_dev_repos():
    """監視中（active=1）のリポジトリ一覧を返す"""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM dev_repos WHERE active = 1 ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_dev_repo(repo_id):
    """IDでリポジトリを取得する"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM dev_repos WHERE id = ?", (repo_id,)).fetchone()
    return dict(row) if row else None


def update_dev_repo_commit(repo_id, commit_hash):
    """最後に処理したコミットハッシュを更新する"""
    conn = get_connection()
    conn.execute(
        "UPDATE dev_repos SET last_commit_hash = ?, updated_at = ? WHERE id = ?",
        (commit_hash, _now(), repo_id),
    )
    conn.commit()


def toggle_dev_repo(repo_id, active):
    """リポジトリの監視ON/OFFを切り替える"""
    conn = get_connection()
    conn.execute(
        "UPDATE dev_repos SET active = ?, updated_at = ? WHERE id = ?",
        (1 if active else 0, _now(), repo_id),
    )
    conn.commit()


def delete_dev_repo(repo_id):
    """リポジトリをDBから削除する"""
    conn = get_connection()
    conn.execute("DELETE FROM dev_repos WHERE id = ?", (repo_id,))
    conn.commit()


# --- custom_texts (broadcast_items経由) ---

def _item_to_custom_text_dict(item):
    """broadcast_itemをcustom_text API形式に変換"""
    item_id = item["id"]
    num_id = int(item_id.split(":")[1]) if ":" in str(item_id) else item_id
    return {
        "id": num_id,
        "label": item.get("label", ""),
        "content": item.get("content", ""),
        "layout": {
            "x": item.get("positionX", 5),
            "y": item.get("positionY", 5),
            "width": item.get("width", 20),
            "height": item.get("height", 15),
            "fontSize": item.get("fontSize", 1.2),
            "bgOpacity": item.get("bgOpacity", 0.85),
            "zIndex": item.get("zIndex", 15),
            "visible": bool(item.get("visible", 1)),
        },
    }


def get_custom_texts():
    """全カスタムテキストアイテムを返す"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM broadcast_items WHERE type = 'custom_text' ORDER BY id"
    ).fetchall()
    return [_item_to_custom_text_dict(_item_row_to_dict(r)) for r in rows]


def create_custom_text(label="", content="", layout=None):
    """カスタムテキストを作成し、作成されたレコードを返す"""
    conn = get_connection()
    layout = layout or {}
    # 次のIDを算出
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 12) AS INTEGER)) as max_id "
        "FROM broadcast_items WHERE type = 'custom_text'"
    ).fetchone()
    next_id = (row["max_id"] or 0) + 1 if row and row["max_id"] else 1
    item_id = f"customtext:{next_id}"

    data = {
        "positionX": layout.get("x", 5),
        "positionY": layout.get("y", 5),
        "width": layout.get("width", 20),
        "height": layout.get("height", 15),
        "fontSize": layout.get("fontSize", 1.2),
        "bgOpacity": layout.get("bgOpacity", 0.85),
        "zIndex": layout.get("zIndex", 15),
        "visible": 1 if layout.get("visible", True) else 0,
        "content": content,
    }
    upsert_broadcast_item(item_id, "custom_text", data)
    # label を直接更新
    conn.execute(
        "UPDATE broadcast_items SET label = ? WHERE id = ?", (label, item_id)
    )
    conn.commit()
    item = get_broadcast_item(item_id)
    return _item_to_custom_text_dict(item)


def update_custom_text(text_id, **kwargs):
    """カスタムテキストを部分更新（label, content, layout properties）"""
    item_id = f"customtext:{text_id}"
    data = {}
    key_map = {
        "x": "positionX", "y": "positionY",
        "width": "width", "height": "height",
        "fontSize": "fontSize", "bgOpacity": "bgOpacity",
        "zIndex": "zIndex", "visible": "visible",
    }
    for key, val in kwargs.items():
        if key in key_map:
            data[key_map[key]] = val
        elif key in ("label", "content"):
            data[key] = val
    if data:
        upsert_broadcast_item(item_id, "custom_text", data)
        # label は直接カラムなので個別更新
        if "label" in data:
            conn = get_connection()
            conn.execute(
                "UPDATE broadcast_items SET label = ? WHERE id = ?",
                (data["label"], item_id),
            )
            conn.commit()


def update_custom_text_layout(text_id, layout_update):
    """レイアウトのみ部分更新（broadcast.htmlドラッグ保存用）"""
    item_id = f"customtext:{text_id}"
    data = {}
    key_map = {"x": "positionX", "y": "positionY", "width": "width",
               "height": "height", "zIndex": "zIndex", "visible": "visible"}
    for key, val in layout_update.items():
        if key in key_map:
            data[key_map[key]] = val
    if data:
        update_broadcast_item_layout(item_id, data)


def delete_custom_text(text_id):
    """カスタムテキストを削除"""
    conn = get_connection()
    item_id = f"customtext:{text_id}"
    conn.execute("DELETE FROM broadcast_items WHERE id = ?", (item_id,))
    conn.commit()


# --- broadcast_items ---

# 共通カラムとDB列名のマッピング
_ITEM_COMMON_COLS = {
    "positionX": "x", "positionY": "y", "width": "width", "height": "height",
    "zIndex": "z_index", "visible": "visible",
    "bgColor": "bg_color", "bgOpacity": "bg_opacity",
    "borderRadius": "border_radius", "borderEnabled": "border_enabled",
    "borderColor": "border_color", "borderSize": "border_size",
    "borderOpacity": "border_opacity",
    "textColor": "text_color", "fontSize": "font_size",
    "textStrokeColor": "text_stroke_color", "textStrokeSize": "text_stroke_size",
    "textStrokeOpacity": "text_stroke_opacity", "padding": "padding",
}

# 逆マッピング（DB列名→APIキー名）
_ITEM_COL_TO_KEY = {v: k for k, v in _ITEM_COMMON_COLS.items()}

# アイテム固有プロパティのキー一覧（共通カラムに含まれないもの）
_ITEM_SPECIFIC_KEYS = {
    "subtitle": {"bottom", "maxWidth", "fadeDuration"},
    "todo": {"titleFontSize"},
    "topic": {"maxWidth", "titleFontSize"},
    "version": {"format", "strokeSize", "strokeOpacity"},
}

_ITEM_LABELS = {
    "avatar": "アバター",
    "subtitle": "字幕",
    "todo": "TODOパネル",
    "topic": "トピックパネル",
    "version": "バージョン表示",
    "dev_activity": "開発アクティビティ",
}


def _item_row_to_dict(row):
    """broadcast_items行をAPI用dictに変換"""
    d = dict(row)
    # DB列名→APIキー名に変換
    result = {"id": d["id"], "type": d["type"], "label": d["label"]}
    for col, key in _ITEM_COL_TO_KEY.items():
        if col in d:
            result[key] = d[col]
    # properties JSONをマージ
    props = _json.loads(d.get("properties", "{}"))
    result.update(props)
    return result


def get_broadcast_items():
    """全broadcast_itemsを返す"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM broadcast_items ORDER BY z_index"
    ).fetchall()
    return [_item_row_to_dict(r) for r in rows]


def get_broadcast_item(item_id):
    """指定IDのbroadcast_itemを返す"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM broadcast_items WHERE id = ?", (item_id,)
    ).fetchone()
    return _item_row_to_dict(row) if row else None


def upsert_broadcast_item(item_id, item_type, data):
    """broadcast_itemを挿入または更新する"""
    conn = get_connection()
    now = _now()
    # 共通カラムとpropertiesを分離
    common = {}
    props = {}
    specific_keys = _ITEM_SPECIFIC_KEYS.get(item_type, set())
    for key, val in data.items():
        if key in ("id", "type", "label", "created_at", "updated_at"):
            continue
        if key in _ITEM_COMMON_COLS:
            common[_ITEM_COMMON_COLS[key]] = val
        elif key in specific_keys or key not in _ITEM_COMMON_COLS:
            props[key] = val

    # 既存のpropertiesをマージ
    existing = conn.execute(
        "SELECT properties FROM broadcast_items WHERE id = ?", (item_id,)
    ).fetchone()
    if existing:
        old_props = _json.loads(existing["properties"])
        old_props.update(props)
        props = old_props

    label = data.get("label", _ITEM_LABELS.get(item_type, item_id))
    cols = ["id", "type", "label", "properties", "updated_at"]
    vals = [item_id, item_type, label, _json.dumps(props, ensure_ascii=False), now]
    for col, val in common.items():
        cols.append(col)
        vals.append(val)

    placeholders = ", ".join(["?"] * len(vals))
    col_names = ", ".join(cols)
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "id")
    conn.execute(
        f"INSERT INTO broadcast_items ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}",
        vals,
    )
    conn.commit()
    return get_broadcast_item(item_id)


def update_broadcast_item_layout(item_id, layout):
    """broadcast_itemのレイアウトのみ更新"""
    conn = get_connection()
    sets = []
    vals = []
    for key, val in layout.items():
        col = _ITEM_COMMON_COLS.get(key)
        if col and col in ("x", "y", "width", "height", "z_index", "visible"):
            sets.append(f"{col} = ?")
            vals.append(val)
    if not sets:
        return
    sets.append("updated_at = ?")
    vals.append(_now())
    vals.append(item_id)
    conn.execute(
        f"UPDATE broadcast_items SET {', '.join(sets)} WHERE id = ?", vals
    )
    conn.commit()


def _migrate_custom_texts_to_items():
    """custom_textsテーブル → broadcast_items に移行"""
    conn = get_connection()
    # 既に移行済みなら何もしない
    existing = conn.execute(
        "SELECT id FROM broadcast_items WHERE type = 'custom_text' LIMIT 1"
    ).fetchone()
    if existing:
        return
    try:
        rows = conn.execute("SELECT * FROM custom_texts").fetchall()
    except Exception:
        return
    now = _now()
    for row in rows:
        d = dict(row)
        item_id = f"customtext:{d['id']}"
        props = _json.dumps({"content": d.get("content", "")}, ensure_ascii=False)
        conn.execute(
            """INSERT OR IGNORE INTO broadcast_items
               (id, type, label, x, y, width, height, z_index, visible,
                font_size, bg_opacity, properties, created_at, updated_at)
               VALUES (?, 'custom_text', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item_id, d.get("label", ""), d.get("x", 5), d.get("y", 5),
             d.get("width", 20), d.get("height", 15), d.get("z_index", 15),
             d.get("visible", 1), d.get("font_size", 1.2), d.get("bg_opacity", 0.85),
             props, d.get("created_at", now), now),
        )
    conn.commit()


def _migrate_capture_windows_to_items():
    """capture_windowsテーブル → broadcast_items に移行"""
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM broadcast_items WHERE type = 'capture' LIMIT 1"
    ).fetchone()
    if existing:
        return
    try:
        rows = conn.execute("SELECT * FROM capture_windows").fetchall()
    except Exception:
        return
    now = _now()
    for row in rows:
        d = dict(row)
        item_id = f"capture:{d['id']}"
        props = _json.dumps({"window_name": d.get("window_name", "")}, ensure_ascii=False)
        conn.execute(
            """INSERT OR IGNORE INTO broadcast_items
               (id, type, label, x, y, width, height, z_index, visible,
                properties, created_at, updated_at)
               VALUES (?, 'capture', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item_id, d.get("label", ""), d.get("x", 5), d.get("y", 10),
             d.get("width", 40), d.get("height", 50), d.get("z_index", 10),
             d.get("visible", 1), props, d.get("created_at", now), now),
        )
    conn.commit()


def migrate_overlay_to_items():
    """overlay.* settings → broadcast_items に移行（初回起動時に自動実行）"""
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM broadcast_items WHERE id = 'avatar'"
    ).fetchone()
    if existing:
        # 固定アイテム移行済み、動的アイテムの移行もチェック
        _migrate_custom_texts_to_items()
        _migrate_capture_windows_to_items()
        return

    from scripts.routes.overlay import _OVERLAY_DEFAULTS, _COMMON_DEFAULTS

    now = _now()
    fixed_items = ["avatar", "subtitle", "todo", "topic", "version", "dev_activity"]
    for item_type in fixed_items:
        defaults = _OVERLAY_DEFAULTS.get(item_type, {})
        # overlay.* settingsからDB値を読み込み
        saved = {}
        for prop in defaults:
            val = get_setting(f"overlay.{item_type}.{prop}")
            if val is not None:
                try:
                    saved[prop] = float(val)
                except (ValueError, TypeError):
                    saved[prop] = val

        merged = {**defaults, **saved}

        # 共通カラムとpropertiesに分離
        common = {}
        props = {}
        specific_keys = _ITEM_SPECIFIC_KEYS.get(item_type, set())
        for key, val in merged.items():
            if key in _ITEM_COMMON_COLS:
                common[_ITEM_COMMON_COLS[key]] = val
            elif key in specific_keys:
                props[key] = val

        label = _ITEM_LABELS.get(item_type, item_type)
        cols = ["id", "type", "label", "properties", "created_at", "updated_at"]
        vals = [item_type, item_type, label, _json.dumps(props, ensure_ascii=False), now, now]
        for col, val in common.items():
            cols.append(col)
            vals.append(val)

        placeholders = ", ".join(["?"] * len(vals))
        col_names = ", ".join(cols)
        conn.execute(
            f"INSERT OR IGNORE INTO broadcast_items ({col_names}) VALUES ({placeholders})",
            vals,
        )
    conn.commit()
    # 動的アイテムも移行
    _migrate_custom_texts_to_items()
    _migrate_capture_windows_to_items()
