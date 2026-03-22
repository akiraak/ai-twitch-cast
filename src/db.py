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
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS avatar_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id INTEGER NOT NULL REFERENCES episodes(id),
            trigger_type TEXT NOT NULL,
            trigger_text TEXT NOT NULL,
            text TEXT NOT NULL,
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

        CREATE TABLE IF NOT EXISTS se_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            volume REAL NOT NULL DEFAULT 1.0,
            duration REAL NOT NULL DEFAULT 1.0
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
            border_color TEXT NOT NULL DEFAULT 'rgba(255,255,255,0.5)',
            border_size REAL NOT NULL DEFAULT 1,
            border_opacity REAL NOT NULL DEFAULT 1.0,
            backdrop_blur REAL NOT NULL DEFAULT 6,
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
    # Migration: add backdrop_blur to broadcast_items
    try:
        conn.execute("ALTER TABLE broadcast_items ADD COLUMN backdrop_blur REAL NOT NULL DEFAULT 6")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    # Migration: add text_align, vertical_align to broadcast_items
    for col, default in [("text_align", "'left'"), ("vertical_align", "'top'")]:
        try:
            conn.execute(f"ALTER TABLE broadcast_items ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    # Migration: add font_family to broadcast_items
    try:
        conn.execute("ALTER TABLE broadcast_items ADD COLUMN font_family TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    # Migration: add parent_id to broadcast_items (子パネル対応)
    try:
        conn.execute("ALTER TABLE broadcast_items ADD COLUMN parent_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    # Migration: overlay.* settings → broadcast_items
    try:
        migrate_overlay_to_items()
    except Exception:
        pass
    # Migration: character_memory テーブル（ペルソナ・セルフメモのキャラクター紐付け）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS character_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL UNIQUE REFERENCES characters(id),
            persona TEXT NOT NULL DEFAULT '',
            self_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    try:
        _migrate_character_memory(conn)
    except Exception:
        pass
    # Migration: comments → comments + avatar_comments 分離
    try:
        _migrate_comments_split(conn)
    except Exception:
        pass
    # Migration: 旧lessonsテーブル（title/status/image_files構造）を削除して再作成
    try:
        conn.execute("SELECT title FROM lessons LIMIT 1")
        # 旧スキーマが存在する → 関連テーブルごと全削除
        conn.execute("DROP TABLE IF EXISTS lesson_sections")
        conn.execute("DROP TABLE IF EXISTS lesson_sources")
        conn.execute("DROP TABLE IF EXISTS lessons")
        conn.commit()
    except Exception:
        pass

    # lessons テーブル（教師モード）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            extracted_text TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lesson_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL REFERENCES lessons(id),
            source_type TEXT NOT NULL,
            file_path TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            original_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lesson_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL REFERENCES lessons(id),
            order_index INTEGER NOT NULL DEFAULT 0,
            section_type TEXT NOT NULL DEFAULT 'explanation',
            content TEXT NOT NULL DEFAULT '',
            tts_text TEXT NOT NULL DEFAULT '',
            display_text TEXT NOT NULL DEFAULT '',
            emotion TEXT NOT NULL DEFAULT 'neutral',
            question TEXT NOT NULL DEFAULT '',
            answer TEXT NOT NULL DEFAULT '',
            wait_seconds INTEGER NOT NULL DEFAULT 8,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()

    # Migration: dev_repos テーブル削除（機能廃止）
    conn.execute("DROP TABLE IF EXISTS dev_repos")
    conn.commit()
    # Migration: topics/topic_scripts テーブル削除（トピック機能廃止）
    conn.execute("DROP TABLE IF EXISTS topic_scripts")
    conn.execute("DROP TABLE IF EXISTS topics")
    conn.execute("DELETE FROM broadcast_items WHERE id = 'topic'")
    conn.execute("DELETE FROM settings WHERE key LIKE 'overlay.topic.%'")
    conn.commit()


def _migrate_comments_split(conn):
    """commentsテーブルからavatar_commentsを分離するマイグレーション（冪等）"""
    # messageカラムが存在する＝未マイグレーション
    try:
        conn.execute("SELECT message FROM comments LIMIT 1")
    except sqlite3.OperationalError:
        return  # 既にマイグレーション済み

    # avatar_commentsテーブルが空なら既存データをコピー
    existing = conn.execute("SELECT COUNT(*) as cnt FROM avatar_comments").fetchone()
    if existing["cnt"] == 0:
        # キャラクター名を取得
        char_names = set()
        try:
            chars = conn.execute("SELECT config FROM characters").fetchall()
            for c in chars:
                try:
                    name = _json.loads(c["config"]).get("name", "")
                    if name:
                        char_names.add(name)
                except (ValueError, TypeError):
                    pass
        except Exception:
            pass

        rows = conn.execute(
            """SELECT c.episode_id, c.message, c.response, c.emotion, c.created_at,
                      u.name as user_name
               FROM comments c JOIN users u ON c.user_id = u.id
               WHERE c.response != ''"""
        ).fetchall()
        for r in rows:
            user_name = r["user_name"]
            if user_name in char_names:
                trigger_type = "topic"
            elif user_name == "システム":
                trigger_type = "event"
            else:
                trigger_type = "comment"
            conn.execute(
                "INSERT INTO avatar_comments (episode_id, trigger_type, trigger_text, text, emotion, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (r["episode_id"], trigger_type, r["message"], r["response"],
                 r["emotion"], r["created_at"]),
            )
        conn.commit()

    # カラムリネーム・削除
    conn.execute("ALTER TABLE comments RENAME COLUMN message TO text")
    conn.execute("ALTER TABLE comments DROP COLUMN response")
    conn.execute("ALTER TABLE comments DROP COLUMN emotion")
    conn.commit()


def _migrate_character_memory(conn):
    """既存データを character_memory テーブルに移行する（冪等）"""
    # 既にデータがあればスキップ
    existing = conn.execute("SELECT COUNT(*) as cnt FROM character_memory").fetchone()
    if existing["cnt"] > 0:
        return
    # 全キャラクターに対して移行
    characters = conn.execute("SELECT id, config FROM characters").fetchall()
    if not characters:
        return
    now = _now()
    # グローバル persona を取得
    persona_row = conn.execute("SELECT value FROM settings WHERE key = 'persona'").fetchone()
    persona = persona_row["value"] if persona_row else ""
    for char in characters:
        char_id = char["id"]
        # キャラ名を config JSON から取得
        try:
            config = _json.loads(char["config"])
            char_name = config.get("name", "")
        except (ValueError, TypeError):
            char_name = ""
        # users テーブルからセルフメモを取得
        self_note = ""
        if char_name:
            user_row = conn.execute(
                "SELECT id, note FROM users WHERE name = ?", (char_name,)
            ).fetchone()
            if user_row:
                self_note = user_row["note"] or ""
                # users テーブルのキャラ行の note をクリア
                if self_note:
                    conn.execute("UPDATE users SET note = '' WHERE id = ?", (user_row["id"],))
        conn.execute(
            "INSERT INTO character_memory (character_id, persona, self_note, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (char_id, persona, self_note, now, now),
        )
    conn.commit()


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
    """指定ユーザーの直近コメントを取得する

    Returns:
        list[dict]: [{text, created_at}, ...]
    """
    conn = get_connection()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """SELECT c.text, c.created_at
           FROM comments c JOIN users u ON c.user_id = u.id
           WHERE u.name = ? AND c.created_at > ?
           ORDER BY c.created_at DESC LIMIT ?""",
        (user_name, since, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


# --- comments ---

def save_comment(episode_id, user_id, text):
    """視聴者のコメントを保存する"""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO comments (episode_id, user_id, text, created_at) VALUES (?, ?, ?, ?)",
        (episode_id, user_id, text, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_recent_comments(limit=20, hours=2):
    """直近N時間以内の視聴者コメントを取得する

    Returns:
        list[dict]: [{user_name, text, created_at}, ...]
    """
    conn = get_connection()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """SELECT u.name as user_name, c.text, c.created_at
           FROM comments c JOIN users u ON c.user_id = u.id
           WHERE c.created_at > ?
           ORDER BY c.created_at DESC LIMIT ?""",
        (since, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


# --- avatar_comments ---

def save_avatar_comment(episode_id, trigger_type, trigger_text, text, emotion="neutral"):
    """アバターのコメントを保存する"""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO avatar_comments (episode_id, trigger_type, trigger_text, text, emotion, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (episode_id, trigger_type, trigger_text, text, emotion, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_recent_avatar_comments(limit=20, hours=2, trigger_type=None):
    """直近N時間以内のアバターコメントを取得する

    Args:
        limit: 最大件数
        hours: 遡る時間
        trigger_type: フィルタ（'comment', 'topic', 'event'）。Noneなら全件

    Returns:
        list[dict]: [{trigger_type, trigger_text, text, emotion, created_at}, ...]
    """
    conn = get_connection()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    if trigger_type:
        rows = conn.execute(
            """SELECT trigger_type, trigger_text, text, emotion, created_at
               FROM avatar_comments
               WHERE created_at > ? AND trigger_type = ?
               ORDER BY created_at DESC LIMIT ?""",
            (since, trigger_type, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT trigger_type, trigger_text, text, emotion, created_at
               FROM avatar_comments
               WHERE created_at > ?
               ORDER BY created_at DESC LIMIT ?""",
            (since, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_recent_timeline(limit=20, hours=2):
    """直近N時間以内のコメント+アバター発話を時系列で取得する

    Returns:
        list[dict]: [{type, user_name, text, trigger_type, trigger_text, emotion, created_at}, ...]
    """
    conn = get_connection()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """SELECT * FROM (
               SELECT 'comment' as type, u.name as user_name, c.text,
                      NULL as trigger_type, NULL as trigger_text, NULL as emotion,
                      c.created_at
               FROM comments c JOIN users u ON c.user_id = u.id
               WHERE c.created_at > ?
               UNION ALL
               SELECT 'avatar_comment' as type, NULL as user_name, ac.text,
                      ac.trigger_type, ac.trigger_text, ac.emotion,
                      ac.created_at
               FROM avatar_comments ac
               WHERE ac.created_at > ?
           ) ORDER BY created_at DESC LIMIT ?""",
        (since, since, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


# --- comments 削除 ---

def clear_comments():
    """commentsテーブルの全レコードを削除する"""
    conn = get_connection()
    conn.execute("DELETE FROM comments")
    conn.commit()


def clear_avatar_comments():
    """avatar_commentsテーブルの全レコードを削除する"""
    conn = get_connection()
    conn.execute("DELETE FROM avatar_comments")
    conn.commit()


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


# --- SE tracks ---

def get_all_se_tracks():
    """全SEトラック情報を返す（filename → {category, description, volume, duration}）"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT filename, category, description, volume, duration FROM se_tracks"
    ).fetchall()
    return {row["filename"]: {
        "category": row["category"],
        "description": row["description"],
        "volume": row["volume"],
        "duration": row["duration"],
    } for row in rows}


def get_se_tracks_by_category(category):
    """カテゴリでSEトラックを検索する"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT filename, category, description, volume, duration FROM se_tracks WHERE category = ?",
        (category,),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_se_track(filename, category="", description="", volume=1.0, duration=1.0):
    """SEトラックを追加/更新する"""
    conn = get_connection()
    conn.execute(
        "INSERT INTO se_tracks (filename, category, description, volume, duration) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(filename) DO UPDATE SET "
        "category = excluded.category, description = excluded.description, "
        "volume = excluded.volume, duration = excluded.duration",
        (filename, category, description, volume, duration),
    )
    conn.commit()


def delete_se_track(filename):
    """SEトラックを削除する"""
    conn = get_connection()
    conn.execute("DELETE FROM se_tracks WHERE filename = ?", (filename,))
    conn.commit()


# --- lessons (教師モード) ---

def create_lesson(name):
    """授業コンテンツを作成する"""
    conn = get_connection()
    now = _now()
    cur = conn.execute(
        "INSERT INTO lessons (name, extracted_text, created_at, updated_at) VALUES (?, '', ?, ?)",
        (name, now, now),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM lessons WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_lesson(lesson_id):
    """授業コンテンツを取得する"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    return dict(row) if row else None


def get_all_lessons():
    """全授業コンテンツを取得する"""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM lessons ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def update_lesson(lesson_id, **fields):
    """授業コンテンツを更新する"""
    conn = get_connection()
    allowed = {"name", "extracted_text"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [lesson_id]
    conn.execute(f"UPDATE lessons SET {set_clause} WHERE id = ?", params)
    conn.commit()


def delete_lesson(lesson_id):
    """授業コンテンツと関連データを削除する"""
    conn = get_connection()
    conn.execute("DELETE FROM lesson_sections WHERE lesson_id = ?", (lesson_id,))
    conn.execute("DELETE FROM lesson_sources WHERE lesson_id = ?", (lesson_id,))
    conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    conn.commit()


# --- lesson_sources ---

def add_lesson_source(lesson_id, source_type, file_path="", url="", original_name=""):
    """教材ソースを追加する"""
    conn = get_connection()
    now = _now()
    cur = conn.execute(
        "INSERT INTO lesson_sources (lesson_id, source_type, file_path, url, original_name, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (lesson_id, source_type, file_path, url, original_name, now),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM lesson_sources WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_lesson_sources(lesson_id):
    """教材ソース一覧を取得する"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM lesson_sources WHERE lesson_id = ? ORDER BY id",
        (lesson_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_lesson_source(source_id):
    """教材ソースを削除する"""
    conn = get_connection()
    conn.execute("DELETE FROM lesson_sources WHERE id = ?", (source_id,))
    conn.commit()


# --- lesson_sections ---

def add_lesson_section(lesson_id, order_index, section_type, content, tts_text="",
                       display_text="", emotion="neutral", question="", answer="", wait_seconds=8):
    """授業セクションを追加する"""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO lesson_sections "
        "(lesson_id, order_index, section_type, content, tts_text, display_text, "
        "emotion, question, answer, wait_seconds, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (lesson_id, order_index, section_type, content, tts_text,
         display_text, emotion, question, answer, wait_seconds, _now()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM lesson_sections WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_lesson_sections(lesson_id):
    """授業セクション一覧を取得する（order_index順）"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM lesson_sections WHERE lesson_id = ? ORDER BY order_index",
        (lesson_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_lesson_section(section_id, **fields):
    """授業セクションを更新する"""
    conn = get_connection()
    allowed = {"order_index", "section_type", "content", "tts_text",
               "display_text", "emotion", "question", "answer", "wait_seconds"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [section_id]
    conn.execute(f"UPDATE lesson_sections SET {set_clause} WHERE id = ?", params)
    conn.commit()


def delete_lesson_section(section_id):
    """授業セクションを削除する"""
    conn = get_connection()
    conn.execute("DELETE FROM lesson_sections WHERE id = ?", (section_id,))
    conn.commit()


def delete_lesson_sections(lesson_id):
    """授業の全セクションを削除する（再生成用）"""
    conn = get_connection()
    conn.execute("DELETE FROM lesson_sections WHERE lesson_id = ?", (lesson_id,))
    conn.commit()


def reorder_lesson_sections(lesson_id, section_ids):
    """セクションの並び順を更新する（section_idsの順番に従う）"""
    conn = get_connection()
    for i, sid in enumerate(section_ids):
        conn.execute(
            "UPDATE lesson_sections SET order_index = ? WHERE id = ? AND lesson_id = ?",
            (i, sid, lesson_id),
        )
    conn.commit()


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


# --- character_memory ---

def get_character_memory(character_id):
    """キャラクターのメモリ（ペルソナ・セルフメモ）を取得する"""
    conn = get_connection()
    row = conn.execute(
        "SELECT persona, self_note, updated_at FROM character_memory WHERE character_id = ?",
        (character_id,),
    ).fetchone()
    if row:
        return dict(row)
    # 行がなければ空で作成
    now = _now()
    conn.execute(
        "INSERT INTO character_memory (character_id, persona, self_note, created_at, updated_at) "
        "VALUES (?, '', '', ?, ?)",
        (character_id, now, now),
    )
    conn.commit()
    return {"persona": "", "self_note": "", "updated_at": now}


def update_character_persona(character_id, persona):
    """キャラクターのペルソナを更新する"""
    conn = get_connection()
    now = _now()
    conn.execute(
        "INSERT INTO character_memory (character_id, persona, self_note, created_at, updated_at) "
        "VALUES (?, ?, '', ?, ?) "
        "ON CONFLICT(character_id) DO UPDATE SET persona = excluded.persona, updated_at = excluded.updated_at",
        (character_id, persona, now, now),
    )
    conn.commit()


def update_character_self_note(character_id, self_note):
    """キャラクターのセルフメモを更新する"""
    conn = get_connection()
    now = _now()
    conn.execute(
        "INSERT INTO character_memory (character_id, self_note, persona, created_at, updated_at) "
        "VALUES (?, ?, '', ?, ?) "
        "ON CONFLICT(character_id) DO UPDATE SET self_note = excluded.self_note, updated_at = excluded.updated_at",
        (character_id, self_note, now, now),
    )
    conn.commit()


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
    "borderRadius": "border_radius",
    "borderColor": "border_color", "borderSize": "border_size",
    "borderOpacity": "border_opacity",
    "backdropBlur": "backdrop_blur",
    "textColor": "text_color", "fontSize": "font_size",
    "textStrokeColor": "text_stroke_color", "textStrokeSize": "text_stroke_size",
    "textStrokeOpacity": "text_stroke_opacity", "padding": "padding",
    "textAlign": "text_align", "verticalAlign": "vertical_align",
    "fontFamily": "font_family",
}

# 逆マッピング（DB列名→APIキー名）
_ITEM_COL_TO_KEY = {v: k for k, v in _ITEM_COMMON_COLS.items()}

# アイテム固有プロパティのキー一覧（共通カラムに含まれないもの）
_ITEM_SPECIFIC_KEYS = {
    "subtitle": {"bottom", "maxWidth", "fadeDuration"},
    "todo": {"titleFontSize"},
}

_ITEM_LABELS = {
    "avatar": "アバター",
    "subtitle": "字幕",
    "todo": "TODO",
}


def _item_row_to_dict(row):
    """broadcast_items行をAPI用dictに変換"""
    d = dict(row)
    # DB列名→APIキー名に変換
    result = {"id": d["id"], "type": d["type"], "label": d["label"]}
    if d.get("parent_id"):
        result["parentId"] = d["parent_id"]
    for col, key in _ITEM_COL_TO_KEY.items():
        if col in d:
            result[key] = d[col]
    # properties JSONをマージ
    props = _json.loads(d.get("properties", "{}"))
    result.update(props)
    return result


def get_broadcast_items():
    """全broadcast_itemsを返す（ルートのみ、子は含まない）"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM broadcast_items WHERE parent_id IS NULL ORDER BY z_index"
    ).fetchall()
    return [_item_row_to_dict(r) for r in rows]


def get_all_broadcast_items():
    """全broadcast_itemsを返す（子も含む）"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM broadcast_items ORDER BY z_index"
    ).fetchall()
    return [_item_row_to_dict(r) for r in rows]


def get_child_items(parent_id):
    """指定親IDの子アイテム一覧を返す"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM broadcast_items WHERE parent_id = ? ORDER BY z_index",
        (parent_id,)
    ).fetchall()
    return [_item_row_to_dict(r) for r in rows]


def create_child_item(parent_id, data):
    """親パネルに子パネルを作成する"""
    conn = get_connection()
    # 親パネルの存在確認
    parent = conn.execute(
        "SELECT id FROM broadcast_items WHERE id = ?", (parent_id,)
    ).fetchone()
    if not parent:
        return None

    # 次のIDを算出
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, LENGTH(?) + 2) AS INTEGER)) as max_id "
        "FROM broadcast_items WHERE parent_id = ?",
        (f"child:{parent_id}", parent_id)
    ).fetchone()
    next_id = (row["max_id"] or 0) + 1 if row and row["max_id"] else 1
    item_id = f"child:{parent_id}:{next_id}"

    child_type = data.get("type", "child_text")
    label = data.get("label", "テキスト")
    content = data.get("content", "")

    now = _now()
    item_data = {
        "positionX": data.get("positionX", 5),
        "positionY": data.get("positionY", 75),
        "width": data.get("width", 90),
        "height": data.get("height", 20),
        "zIndex": data.get("zIndex", 10),
        "visible": 1 if data.get("visible", True) else 0,
        "bgColor": data.get("bgColor", "rgba(0,0,0,0.5)"),
        "bgOpacity": data.get("bgOpacity", 0.5),
        "borderRadius": data.get("borderRadius", 4),
        "borderSize": data.get("borderSize", 0),
        "fontSize": data.get("fontSize", 0.8),
        "textColor": data.get("textColor", "#ffffff"),
        "padding": data.get("padding", 4),
        "content": content,
    }

    # 共通カラムとpropertiesに分離
    common = {}
    props = {}
    for key, val in item_data.items():
        if key in _ITEM_COMMON_COLS:
            common[_ITEM_COMMON_COLS[key]] = val
        else:
            props[key] = val

    cols = ["id", "type", "label", "parent_id", "properties", "created_at", "updated_at"]
    vals = [item_id, child_type, label, parent_id,
            _json.dumps(props, ensure_ascii=False), now, now]
    for col, val in common.items():
        cols.append(col)
        vals.append(val)

    placeholders = ", ".join(["?"] * len(vals))
    col_names = ", ".join(cols)
    conn.execute(
        f"INSERT INTO broadcast_items ({col_names}) VALUES ({placeholders})",
        vals,
    )
    conn.commit()
    return get_broadcast_item(item_id)


def delete_child_item(item_id):
    """子パネルを削除する"""
    conn = get_connection()
    conn.execute("DELETE FROM broadcast_items WHERE id = ?", (item_id,))
    conn.commit()


def delete_broadcast_item_cascade(item_id):
    """パネルとその子パネルをすべて削除する"""
    conn = get_connection()
    conn.execute("DELETE FROM broadcast_items WHERE parent_id = ?", (item_id,))
    conn.execute("DELETE FROM broadcast_items WHERE id = ?", (item_id,))
    conn.commit()


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

    # labelはdata指定 → 既存値 → デフォルト の優先順
    if "label" in data:
        label = data["label"]
    elif existing:
        existing_row = conn.execute(
            "SELECT label FROM broadcast_items WHERE id = ?", (item_id,)
        ).fetchone()
        label = existing_row["label"] if existing_row else _ITEM_LABELS.get(item_type, item_id)
    else:
        label = _ITEM_LABELS.get(item_type, item_id)
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
    fixed_items = ["avatar", "subtitle", "todo"]
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
