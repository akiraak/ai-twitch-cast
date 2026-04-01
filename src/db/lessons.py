"""レッスン（教師モード）CRUD"""

from .core import get_connection, _now


# --- lessons ---

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
    allowed = {"name", "extracted_text", "main_content", "plan_knowledge", "plan_entertainment", "plan_json"}
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
    conn.execute("DELETE FROM lesson_plans WHERE lesson_id = ?", (lesson_id,))
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
                       display_text="", emotion="neutral", question="", answer="",
                       wait_seconds=8, title="", lang="ja", dialogues="",
                       dialogue_directions="", generator="gemini"):
    """授業セクションを追加する"""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO lesson_sections "
        "(lesson_id, order_index, section_type, title, content, tts_text, display_text, "
        "emotion, question, answer, wait_seconds, lang, dialogues, dialogue_directions, "
        "generator, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (lesson_id, order_index, section_type, title, content, tts_text,
         display_text, emotion, question, answer, wait_seconds, lang, dialogues,
         dialogue_directions, generator, _now()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM lesson_sections WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_lesson_sections(lesson_id, lang=None, generator=None):
    """授業セクション一覧を取得する（order_index順）"""
    conn = get_connection()
    where = "WHERE lesson_id = ?"
    params = [lesson_id]
    if lang:
        where += " AND lang = ?"
        params.append(lang)
    if generator:
        where += " AND generator = ?"
        params.append(generator)
    rows = conn.execute(
        f"SELECT * FROM lesson_sections {where} ORDER BY order_index",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def update_lesson_section(section_id, **fields):
    """授業セクションを更新する"""
    conn = get_connection()
    allowed = {"order_index", "section_type", "title", "content", "tts_text",
               "display_text", "emotion", "question", "answer", "wait_seconds",
               "dialogues", "dialogue_directions"}
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


def delete_lesson_sections(lesson_id, lang=None, generator=None):
    """授業の全セクションを削除する（再生成用）"""
    conn = get_connection()
    where = "WHERE lesson_id = ?"
    params = [lesson_id]
    if lang:
        where += " AND lang = ?"
        params.append(lang)
    if generator:
        where += " AND generator = ?"
        params.append(generator)
    conn.execute(f"DELETE FROM lesson_sections {where}", params)
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


# --- lesson_plans (言語別) ---

def get_lesson_plan(lesson_id, lang, generator=None):
    """指定言語のプランを取得する"""
    conn = get_connection()
    if generator:
        row = conn.execute(
            "SELECT * FROM lesson_plans WHERE lesson_id = ? AND lang = ? AND generator = ?",
            (lesson_id, lang, generator),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM lesson_plans WHERE lesson_id = ? AND lang = ?",
            (lesson_id, lang),
        ).fetchone()
    return dict(row) if row else None


def get_lesson_plans(lesson_id):
    """全言語のプランを取得する"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM lesson_plans WHERE lesson_id = ? ORDER BY lang",
        (lesson_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_lesson_plan(lesson_id, lang, knowledge="", entertainment="", plan_json="",
                       director_json="", plan_generations="", generator="gemini"):
    """プランを保存する（INSERT or UPDATE）"""
    conn = get_connection()
    now = _now()
    existing = conn.execute(
        "SELECT id FROM lesson_plans WHERE lesson_id = ? AND lang = ? AND generator = ?",
        (lesson_id, lang, generator),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE lesson_plans SET knowledge = ?, entertainment = ?, plan_json = ?, "
            "director_json = ?, plan_generations = ?, updated_at = ? "
            "WHERE lesson_id = ? AND lang = ? AND generator = ?",
            (knowledge, entertainment, plan_json, director_json, plan_generations, now, lesson_id, lang, generator),
        )
    else:
        conn.execute(
            "INSERT INTO lesson_plans (lesson_id, lang, knowledge, entertainment, plan_json, "
            "director_json, plan_generations, generator, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lesson_id, lang, knowledge, entertainment, plan_json, director_json, plan_generations, generator, now, now),
        )
    conn.commit()


def delete_lesson_plans(lesson_id, lang=None, generator=None):
    """プランを削除する"""
    conn = get_connection()
    where = "WHERE lesson_id = ?"
    params = [lesson_id]
    if lang:
        where += " AND lang = ?"
        params.append(lang)
    if generator:
        where += " AND generator = ?"
        params.append(generator)
    conn.execute(f"DELETE FROM lesson_plans {where}", params)
    conn.commit()
