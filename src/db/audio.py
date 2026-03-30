"""BGM・SE トラック CRUD"""

from .core import get_connection


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
