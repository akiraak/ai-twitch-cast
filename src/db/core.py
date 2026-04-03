"""データベースコア — 接続管理・マイグレーション・基本ドメイン関数"""

import json as _json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
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
            name TEXT NOT NULL UNIQUE,
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
        from .items import migrate_overlay_to_items
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
            title TEXT NOT NULL DEFAULT '',
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

    # Migration: lessons テーブルにプラン用カラム追加
    for col in ["plan_knowledge", "plan_entertainment", "plan_json"]:
        try:
            conn.execute(f"ALTER TABLE lessons ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Migration: lessons テーブルに main_content カラム追加
    try:
        conn.execute("ALTER TABLE lessons ADD COLUMN main_content TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: dev_repos テーブル削除（機能廃止）
    conn.execute("DROP TABLE IF EXISTS dev_repos")
    conn.commit()
    # Migration: topics/topic_scripts テーブル削除（トピック機能廃止）
    conn.execute("DROP TABLE IF EXISTS topic_scripts")
    conn.execute("DROP TABLE IF EXISTS topics")
    conn.execute("DELETE FROM broadcast_items WHERE id = 'topic'")
    conn.execute("DELETE FROM settings WHERE key LIKE 'overlay.topic.%'")
    conn.commit()
    # Migration: add title to lesson_sections（監督プランのタイトル保存用）
    try:
        conn.execute("ALTER TABLE lesson_sections ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: lesson_plans テーブル（言語別プラン保存）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lesson_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
            lang TEXT NOT NULL DEFAULT 'ja',
            knowledge TEXT NOT NULL DEFAULT '',
            entertainment TEXT NOT NULL DEFAULT '',
            plan_json TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(lesson_id, lang)
        )
    """)
    conn.commit()

    # Migration: lesson_sections に lang カラム追加
    try:
        conn.execute("ALTER TABLE lesson_sections ADD COLUMN lang TEXT NOT NULL DEFAULT 'ja'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: lesson_sections に dialogues カラム追加（対話形式スクリプト用）
    try:
        conn.execute("ALTER TABLE lesson_sections ADD COLUMN dialogues TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: lesson_plans に director_json, plan_generations カラム追加（v3監督主導）
    for col in ("director_json", "plan_generations"):
        try:
            conn.execute(f"ALTER TABLE lesson_plans ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Migration: lesson_sections に dialogue_directions カラム追加（v3監督の演出指示）
    try:
        conn.execute("ALTER TABLE lesson_sections ADD COLUMN dialogue_directions TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: 既存の lessons.plan_* データを lesson_plans に移行
    try:
        rows = conn.execute(
            "SELECT id, plan_knowledge, plan_entertainment, plan_json FROM lessons "
            "WHERE plan_knowledge != '' OR plan_entertainment != '' OR plan_json != ''"
        ).fetchall()
        now = _now()
        for row in rows:
            # 既にmigrated済みか確認
            existing = conn.execute(
                "SELECT id FROM lesson_plans WHERE lesson_id = ? AND lang = 'ja'",
                (row["id"],)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO lesson_plans (lesson_id, lang, knowledge, entertainment, plan_json, created_at, updated_at) "
                    "VALUES (?, 'ja', ?, ?, ?, ?, ?)",
                    (row["id"], row["plan_knowledge"], row["plan_entertainment"], row["plan_json"], now, now),
                )
        conn.commit()
    except Exception:
        pass

    # Migration: VRM設定を settings → characters.config.vrm に移行
    try:
        _migrate_vrm_to_character_config(conn)
    except Exception:
        pass

    # Migration: ライティング設定を settings → characters.config.lighting に移行
    try:
        _migrate_lighting_to_character_config(conn)
    except Exception:
        pass

    # Migration: lesson_sections に generator カラム追加
    try:
        conn.execute("ALTER TABLE lesson_sections ADD COLUMN generator TEXT NOT NULL DEFAULT 'gemini'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: lesson_plans に generator カラム追加 + UNIQUE制約変更
    # 既存テーブルは UNIQUE(lesson_id, lang) だが、generator追加後は UNIQUE(lesson_id, lang, generator) が必要。
    # SQLiteではテーブルレベルのUNIQUE制約をALTERで変更できないため、テーブル再作成で対応する。
    try:
        conn.execute("SELECT generator FROM lesson_plans LIMIT 1")
    except sqlite3.OperationalError:
        # generator カラムが存在しない → マイグレーション実行
        conn.execute("""CREATE TABLE lesson_plans_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
            lang TEXT NOT NULL DEFAULT 'ja',
            knowledge TEXT NOT NULL DEFAULT '',
            entertainment TEXT NOT NULL DEFAULT '',
            plan_json TEXT NOT NULL DEFAULT '',
            director_json TEXT NOT NULL DEFAULT '',
            plan_generations TEXT NOT NULL DEFAULT '',
            generator TEXT NOT NULL DEFAULT 'gemini',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(lesson_id, lang, generator)
        )""")
        conn.execute("""INSERT INTO lesson_plans_new
            (id, lesson_id, lang, knowledge, entertainment, plan_json,
             director_json, plan_generations, generator, created_at, updated_at)
            SELECT id, lesson_id, lang, knowledge, entertainment, plan_json,
                   director_json, plan_generations, 'gemini', created_at, updated_at
            FROM lesson_plans""")
        conn.execute("DROP TABLE lesson_plans")
        conn.execute("ALTER TABLE lesson_plans_new RENAME TO lesson_plans")
        conn.commit()

    # Migration: ライティングプリセットを settings → characters.config.lighting_presets に移行
    try:
        _migrate_lighting_presets_to_character_config(conn)
    except Exception:
        pass

    # Migration: characters.config に集約済みの旧 settings キーを削除
    try:
        _cleanup_old_character_settings(conn)
    except Exception:
        pass

    # Migration: characters.name を UNIQUE に（重複キャラを削除して制約追加）
    try:
        _migrate_characters_unique_name(conn)
    except Exception:
        pass

    # Migration: characters.config に tts_voice/tts_style がなければデフォルト値を補完
    try:
        _migrate_characters_tts_defaults(conn)
    except Exception:
        pass

    # Migration: avatar_comments に speaker カラム追加（マルチキャラクター応答分担）
    try:
        conn.execute("ALTER TABLE avatar_comments ADD COLUMN speaker TEXT DEFAULT NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: characters.config から "name" キーを除去（characters.name カラムがマスター）
    try:
        _migrate_remove_name_from_config(conn)
    except Exception:
        pass

    # --- バージョニング機能 (Step 1) ---

    # Migration: lesson_categories テーブル作成
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lesson_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            prompt_file TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()

    # Migration: lessons に category カラム追加
    try:
        conn.execute("ALTER TABLE lessons ADD COLUMN category TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: lesson_versions テーブル作成
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lesson_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            lang TEXT NOT NULL DEFAULT 'ja',
            generator TEXT NOT NULL DEFAULT 'gemini',
            version_number INTEGER NOT NULL DEFAULT 1,
            note TEXT DEFAULT '',
            verify_json TEXT DEFAULT '',
            improve_source_version INTEGER,
            improve_summary TEXT DEFAULT '',
            improved_sections TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
            UNIQUE(lesson_id, lang, generator, version_number)
        )
    """)
    conn.commit()

    # Migration: lesson_sections に version_number, annotation カラム追加
    for col, typedef in [
        ("version_number", "INTEGER NOT NULL DEFAULT 1"),
        ("annotation_rating", "TEXT DEFAULT ''"),
        ("annotation_comment", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE lesson_sections ADD COLUMN {col} {typedef}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Migration: lesson_sections に display_properties カラム追加（セクション別パネルサイズ制御）
    try:
        conn.execute("ALTER TABLE lesson_sections ADD COLUMN display_properties TEXT NOT NULL DEFAULT '{}'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: lesson_plans に version_number 追加 + UNIQUE制約変更
    # 既存は UNIQUE(lesson_id, lang, generator) → UNIQUE(lesson_id, lang, generator, version_number)
    try:
        conn.execute("SELECT version_number FROM lesson_plans LIMIT 1")
    except sqlite3.OperationalError:
        # version_number が存在しない → マイグレーション実行
        conn.execute("""CREATE TABLE lesson_plans_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
            lang TEXT NOT NULL DEFAULT 'ja',
            knowledge TEXT NOT NULL DEFAULT '',
            entertainment TEXT NOT NULL DEFAULT '',
            plan_json TEXT NOT NULL DEFAULT '',
            director_json TEXT NOT NULL DEFAULT '',
            plan_generations TEXT NOT NULL DEFAULT '',
            generator TEXT NOT NULL DEFAULT 'gemini',
            version_number INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(lesson_id, lang, generator, version_number)
        )""")
        conn.execute("""INSERT INTO lesson_plans_v2
            (id, lesson_id, lang, knowledge, entertainment, plan_json,
             director_json, plan_generations, generator, version_number, created_at, updated_at)
            SELECT id, lesson_id, lang, knowledge, entertainment, plan_json,
                   director_json, plan_generations, generator, 1, created_at, updated_at
            FROM lesson_plans""")
        conn.execute("DROP TABLE lesson_plans")
        conn.execute("ALTER TABLE lesson_plans_v2 RENAME TO lesson_plans")
        conn.commit()

    # Migration: lesson_learnings テーブル作成
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lesson_learnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL DEFAULT '',
            analysis_input TEXT DEFAULT '',
            analysis_output TEXT DEFAULT '',
            learnings_md TEXT DEFAULT '',
            prompt_diff TEXT DEFAULT '',
            section_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()

    # Migration: 既存データから lesson_versions v1 を自動生成
    try:
        _migrate_lesson_versions_v1(conn)
    except Exception:
        pass


def _migrate_lesson_versions_v1(conn):
    """既存の lesson_sections から lesson_versions v1 レコードを自動生成する（冪等）"""
    # 既にバージョンレコードがあればスキップ
    existing = conn.execute("SELECT COUNT(*) as cnt FROM lesson_versions").fetchone()
    if existing["cnt"] > 0:
        return
    # 各 (lesson_id, lang, generator) の組み合わせに v1 を作成
    rows = conn.execute(
        "SELECT DISTINCT lesson_id, lang, generator FROM lesson_sections"
    ).fetchall()
    now = _now()
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO lesson_versions "
            "(lesson_id, lang, generator, version_number, note, created_at) "
            "VALUES (?, ?, ?, 1, '初版（自動生成）', ?)",
            (row["lesson_id"], row["lang"], row["generator"], now),
        )
    conn.commit()


def _migrate_vrm_to_character_config(conn):
    """settings の files.active_avatar* を characters.config.vrm に移行（冪等）"""
    key_role_map = {
        "files.active_avatar": "teacher",
        "files.active_avatar2": "student",
    }
    for settings_key, role in key_role_map.items():
        val_row = conn.execute("SELECT value FROM settings WHERE key = ?", (settings_key,)).fetchone()
        if not val_row or not val_row["value"]:
            continue
        vrm_file = val_row["value"]
        # config に vrm が既にあるキャラは移行済み → スキップ
        rows = conn.execute("SELECT id, config FROM characters ORDER BY id").fetchall()
        for row in rows:
            config = _json.loads(row["config"])
            if config.get("role") == role:
                if not config.get("vrm"):
                    config["vrm"] = vrm_file
                    conn.execute(
                        "UPDATE characters SET config = ? WHERE id = ?",
                        (_json.dumps(config, ensure_ascii=False), row["id"]),
                    )
                break
    conn.commit()


def _migrate_lighting_to_character_config(conn):
    """settings の overlay.lighting_* を characters.config.lighting に移行（冪等）"""
    role_section_map = {
        "teacher": "overlay.lighting_teacher.",
        "student": "overlay.lighting_student.",
    }
    rows = conn.execute("SELECT id, config FROM characters ORDER BY id").fetchall()
    for row in rows:
        config = _json.loads(row["config"])
        role = config.get("role")
        if not role or role not in role_section_map:
            continue
        if config.get("lighting"):
            continue  # 既に移行済み
        prefix = role_section_map[role]
        settings_rows = conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE ?", (prefix + "%",)
        ).fetchall()
        if not settings_rows:
            continue
        lighting = {}
        for sr in settings_rows:
            prop = sr["key"][len(prefix):]
            try:
                lighting[prop] = float(sr["value"])
            except (ValueError, TypeError):
                lighting[prop] = sr["value"]
        config["lighting"] = lighting
        conn.execute(
            "UPDATE characters SET config = ? WHERE id = ?",
            (_json.dumps(config, ensure_ascii=False), row["id"]),
        )
    conn.commit()


def _migrate_lighting_presets_to_character_config(conn):
    """settings の lighting.presets を先生の characters.config.lighting_presets に移行（冪等）"""
    val_row = conn.execute("SELECT value FROM settings WHERE key = 'lighting.presets'").fetchone()
    if not val_row or not val_row["value"]:
        return
    try:
        presets = _json.loads(val_row["value"])
    except (ValueError, TypeError):
        return
    if not presets:
        return
    # 先生キャラの config.lighting_presets が空なら移行
    rows = conn.execute("SELECT id, config FROM characters ORDER BY id").fetchall()
    for row in rows:
        config = _json.loads(row["config"])
        if config.get("role") == "teacher":
            if not config.get("lighting_presets"):
                config["lighting_presets"] = presets
                conn.execute(
                    "UPDATE characters SET config = ? WHERE id = ?",
                    (_json.dumps(config, ensure_ascii=False), row["id"]),
                )
                conn.commit()
            break


def _cleanup_old_character_settings(conn):
    """characters.config に移行済みの旧 settings キーを削除（冪等）"""
    rows = conn.execute("SELECT config FROM characters ORDER BY id").fetchall()
    teacher_has_vrm = False
    for row in rows:
        config = _json.loads(row["config"])
        if config.get("role") == "teacher" and config.get("vrm"):
            teacher_has_vrm = True
            break
    if not teacher_has_vrm:
        return  # 未移行の場合は削除しない

    old_keys = [
        "files.active_avatar",
        "files.active_avatar2",
    ]
    for key in old_keys:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    conn.execute("DELETE FROM settings WHERE key LIKE 'overlay.lighting_teacher.%'")
    conn.execute("DELETE FROM settings WHERE key LIKE 'overlay.lighting_student.%'")
    conn.execute("DELETE FROM settings WHERE key = 'lighting.presets'")
    conn.commit()


def _migrate_characters_unique_name(conn):
    """characters.name に UNIQUE 制約を追加する（冪等）"""
    # 既に UNIQUE 制約があるかチェック
    index_info = conn.execute("PRAGMA index_list('characters')").fetchall()
    for idx in index_info:
        cols = conn.execute(f"PRAGMA index_info('{idx['name']}')").fetchall()
        if len(cols) == 1 and any(c["name"] == "name" for c in cols) and idx["unique"]:
            return  # 既に UNIQUE

    # 同名キャラの重複を解消: config が最も充実している（長い）1件を残す
    rows = conn.execute(
        "SELECT id, name, LENGTH(config) as config_len FROM characters ORDER BY name, config_len DESC"
    ).fetchall()
    seen_names = {}
    delete_ids = []
    for row in rows:
        if row["name"] in seen_names:
            delete_ids.append(row["id"])
        else:
            seen_names[row["name"]] = row["id"]

    if delete_ids:
        placeholders = ",".join("?" * len(delete_ids))
        conn.execute(f"DELETE FROM character_memory WHERE character_id IN ({placeholders})", delete_ids)
        conn.execute(f"DELETE FROM characters WHERE id IN ({placeholders})", delete_ids)
        conn.commit()

    # 使われなくなったチャンネルを削除
    orphan_channels = conn.execute(
        "SELECT c.id FROM channels c LEFT JOIN characters ch ON ch.channel_id = c.id "
        "WHERE ch.id IS NULL"
    ).fetchall()
    for ch in orphan_channels:
        conn.execute("DELETE FROM channels WHERE id = ?", (ch["id"],))
    conn.commit()

    # UNIQUE 制約を追加（テーブル再作成）
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_characters_name ON characters(name)")
    conn.commit()


def _migrate_characters_tts_defaults(conn):
    """characters.config に tts_voice/tts_style がなければデフォルト値を補完する（冪等）"""
    from src.character_manager import DEFAULT_CHARACTER, DEFAULT_STUDENT_CHARACTER

    defaults_by_role = {
        "teacher": {
            "tts_voice": DEFAULT_CHARACTER.get("tts_voice"),
            "tts_style": DEFAULT_CHARACTER.get("tts_style"),
        },
        "student": {
            "tts_voice": DEFAULT_STUDENT_CHARACTER.get("tts_voice"),
            "tts_style": DEFAULT_STUDENT_CHARACTER.get("tts_style"),
        },
    }

    rows = conn.execute("SELECT id, config FROM characters").fetchall()
    for row in rows:
        config = _json.loads(row["config"])
        role = config.get("role", "teacher")
        defaults = defaults_by_role.get(role, defaults_by_role["teacher"])
        updated = False
        for key, default_val in defaults.items():
            if not config.get(key) and default_val:
                config[key] = default_val
                updated = True
        if updated:
            conn.execute(
                "UPDATE characters SET config = ?, updated_at = ? WHERE id = ?",
                (_json.dumps(config, ensure_ascii=False), _now(), row["id"]),
            )
    conn.commit()


def _migrate_remove_name_from_config(conn):
    """characters.config JSON から "name" キーを除去する（冪等）"""
    rows = conn.execute("SELECT id, config FROM characters").fetchall()
    for row in rows:
        try:
            config = _json.loads(row["config"])
        except (ValueError, TypeError):
            continue
        if "name" not in config:
            continue
        config.pop("name")
        conn.execute(
            "UPDATE characters SET config = ? WHERE id = ?",
            (_json.dumps(config, ensure_ascii=False), row["id"]),
        )
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
            chars = conn.execute("SELECT name FROM characters").fetchall()
            for c in chars:
                if c["name"]:
                    char_names.add(c["name"])
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
    characters = conn.execute("SELECT id, name FROM characters").fetchall()
    if not characters:
        return
    now = _now()
    # グローバル persona を取得
    persona_row = conn.execute("SELECT value FROM settings WHERE key = 'persona'").fetchone()
    persona = persona_row["value"] if persona_row else ""
    for char in characters:
        char_id = char["id"]
        char_name = char["name"] or ""
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
    # name は UNIQUE — channel_id に関わらず名前で検索
    row = conn.execute(
        "SELECT * FROM characters WHERE name = ?",
        (name,),
    ).fetchone()
    if row:
        return dict(row)
    # config JSON から name を除去（characters.name カラムがマスター）
    try:
        cfg = _json.loads(config)
        cfg.pop("name", None)
        config = _json.dumps(cfg, ensure_ascii=False)
    except (ValueError, TypeError):
        pass
    conn.execute(
        "INSERT INTO characters (channel_id, name, config, created_at) VALUES (?, ?, ?, ?)",
        (channel_id, name, config, _now()),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM characters WHERE name = ?",
        (name,),
    ).fetchone())


def get_character_by_channel(channel_id):
    """チャンネルのキャラクター設定を取得する（先頭1件）"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM characters WHERE channel_id = ? ORDER BY id LIMIT 1",
        (channel_id,),
    ).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM characters ORDER BY id LIMIT 1").fetchone()
    return dict(row) if row else None


def get_characters_by_channel(channel_id):
    """チャンネルの全キャラクター一覧を返す"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM characters WHERE channel_id = ? ORDER BY id",
        (channel_id,),
    ).fetchall()
    if not rows:
        rows = conn.execute("SELECT * FROM characters ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_character_by_id(character_id):
    """IDでキャラクターを取得する"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM characters WHERE id = ?",
        (character_id,),
    ).fetchone()
    return dict(row) if row else None


def get_character_by_role(channel_id, role):
    """チャンネル内の指定roleのキャラクターを取得する"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM characters WHERE channel_id = ? ORDER BY id",
        (channel_id,),
    ).fetchall()
    for row in rows:
        config = _json.loads(row["config"])
        if config.get("role") == role:
            return dict(row)
    return None


def update_character(character_id, name=None, config=None):
    """キャラクター設定を更新する"""
    conn = get_connection()
    fields = {}
    if name is not None:
        fields["name"] = name
    if config is not None:
        try:
            cfg = _json.loads(config)
            cfg.pop("name", None)
            config = _json.dumps(cfg, ensure_ascii=False)
        except (ValueError, TypeError):
            pass
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


def update_character_config_field(character_id, field, value):
    """キャラクターの config JSON 内の特定フィールドを更新する"""
    conn = get_connection()
    row = conn.execute("SELECT config FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not row:
        return
    config = _json.loads(row["config"])
    config[field] = value
    conn.execute(
        "UPDATE characters SET config = ?, updated_at = ? WHERE id = ?",
        (_json.dumps(config, ensure_ascii=False), _now(), character_id),
    )
    conn.commit()


def get_character_config_field(character_id, field, default=None):
    """キャラクターの config JSON 内の特定フィールドを取得する"""
    conn = get_connection()
    row = conn.execute("SELECT config FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not row:
        return default
    config = _json.loads(row["config"])
    return config.get(field, default)


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
    """直近N時間以内の視聴者コメントを取得する"""
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

def save_avatar_comment(episode_id, trigger_type, trigger_text, text, emotion="neutral", speaker=None):
    """アバターのコメントを保存する"""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO avatar_comments (episode_id, trigger_type, trigger_text, text, emotion, speaker, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (episode_id, trigger_type, trigger_text, text, emotion, speaker, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_recent_avatar_comments(limit=20, hours=2, trigger_type=None, speaker=None):
    """直近N時間以内のアバターコメントを取得する"""
    conn = get_connection()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conditions = ["created_at > ?"]
    params = [since]
    if trigger_type:
        conditions.append("trigger_type = ?")
        params.append(trigger_type)
    if speaker:
        conditions.append("speaker = ?")
        params.append(speaker)
    where = " AND ".join(conditions)
    params.append(limit)
    rows = conn.execute(
        f"""SELECT trigger_type, trigger_text, text, emotion, speaker, created_at
           FROM avatar_comments
           WHERE {where}
           ORDER BY created_at DESC LIMIT ?""",
        params,
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_recent_timeline(limit=20, hours=2):
    """直近N時間以内のコメント+アバター発話を時系列で取得する"""
    conn = get_connection()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """SELECT * FROM (
               SELECT 'comment' as type, u.name as user_name, c.text,
                      NULL as trigger_type, NULL as trigger_text, NULL as emotion,
                      NULL as speaker, c.created_at
               FROM comments c JOIN users u ON c.user_id = u.id
               WHERE c.created_at > ?
               UNION ALL
               SELECT 'avatar_comment' as type, NULL as user_name, ac.text,
                      ac.trigger_type, ac.trigger_text, ac.emotion,
                      ac.speaker, ac.created_at
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
