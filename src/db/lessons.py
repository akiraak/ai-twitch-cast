"""レッスン（教師モード）CRUD"""

from .core import get_connection, _now


# --- lessons ---

def create_lesson(name, category=""):
    """授業コンテンツを作成する"""
    conn = get_connection()
    now = _now()
    cur = conn.execute(
        "INSERT INTO lessons (name, extracted_text, category, created_at, updated_at) VALUES (?, '', ?, ?, ?)",
        (name, category, now, now),
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
    allowed = {"name", "extracted_text", "main_content", "category", "plan_knowledge", "plan_entertainment", "plan_json"}
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
    conn.execute("DELETE FROM lesson_versions WHERE lesson_id = ?", (lesson_id,))
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
                       dialogue_directions="", generator="gemini", version_number=1,
                       display_properties=""):
    """授業セクションを追加する"""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO lesson_sections "
        "(lesson_id, order_index, section_type, title, content, tts_text, display_text, "
        "emotion, question, answer, wait_seconds, lang, dialogues, dialogue_directions, "
        "generator, version_number, display_properties, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (lesson_id, order_index, section_type, title, content, tts_text,
         display_text, emotion, question, answer, wait_seconds, lang, dialogues,
         dialogue_directions, generator, version_number,
         display_properties or "{}", _now()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM lesson_sections WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_lesson_sections(lesson_id, lang=None, generator=None, version_number=None):
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
    if version_number is not None:
        where += " AND version_number = ?"
        params.append(version_number)
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
               "dialogues", "dialogue_directions", "display_properties"}
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


def delete_lesson_sections(lesson_id, lang=None, generator=None, version_number=None):
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
    if version_number is not None:
        where += " AND version_number = ?"
        params.append(version_number)
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

def get_lesson_plan(lesson_id, lang, generator=None, version_number=None):
    """指定言語のプランを取得する"""
    conn = get_connection()
    where = "WHERE lesson_id = ? AND lang = ?"
    params = [lesson_id, lang]
    if generator:
        where += " AND generator = ?"
        params.append(generator)
    if version_number is not None:
        where += " AND version_number = ?"
        params.append(version_number)
    row = conn.execute(f"SELECT * FROM lesson_plans {where}", params).fetchone()
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
                       director_json="", plan_generations="", generator="gemini",
                       version_number=1):
    """プランを保存する（INSERT or UPDATE）"""
    conn = get_connection()
    now = _now()
    existing = conn.execute(
        "SELECT id FROM lesson_plans WHERE lesson_id = ? AND lang = ? AND generator = ? AND version_number = ?",
        (lesson_id, lang, generator, version_number),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE lesson_plans SET knowledge = ?, entertainment = ?, plan_json = ?, "
            "director_json = ?, plan_generations = ?, updated_at = ? "
            "WHERE lesson_id = ? AND lang = ? AND generator = ? AND version_number = ?",
            (knowledge, entertainment, plan_json, director_json, plan_generations, now,
             lesson_id, lang, generator, version_number),
        )
    else:
        conn.execute(
            "INSERT INTO lesson_plans (lesson_id, lang, knowledge, entertainment, plan_json, "
            "director_json, plan_generations, generator, version_number, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lesson_id, lang, knowledge, entertainment, plan_json, director_json,
             plan_generations, generator, version_number, now, now),
        )
    conn.commit()


def delete_lesson_plans(lesson_id, lang=None, generator=None, version_number=None):
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
    if version_number is not None:
        where += " AND version_number = ?"
        params.append(version_number)
    conn.execute(f"DELETE FROM lesson_plans {where}", params)
    conn.commit()


# --- lesson_categories ---

def get_categories():
    """カテゴリ一覧を取得する"""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM lesson_categories ORDER BY slug").fetchall()
    return [dict(r) for r in rows]


def create_category(slug, name, description="", prompt_file="", prompt_content=""):
    """カテゴリを作成する"""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO lesson_categories (slug, name, description, prompt_file, prompt_content, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (slug, name, description, prompt_file, prompt_content, _now()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM lesson_categories WHERE id = ?", (cur.lastrowid,)).fetchone())


def update_category(category_id, **fields):
    """カテゴリを更新する"""
    conn = get_connection()
    allowed = {"name", "description", "prompt_file", "prompt_content"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [category_id]
    conn.execute(f"UPDATE lesson_categories SET {set_clause} WHERE id = ?", params)
    conn.commit()


def get_category_by_slug(slug):
    """slugでカテゴリを取得する"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM lesson_categories WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def delete_category(category_id):
    """カテゴリを削除する（授業の category は空文字にリセット）"""
    conn = get_connection()
    row = conn.execute("SELECT slug FROM lesson_categories WHERE id = ?", (category_id,)).fetchone()
    if row:
        conn.execute("UPDATE lessons SET category = '' WHERE category = ?", (row["slug"],))
    conn.execute("DELETE FROM lesson_categories WHERE id = ?", (category_id,))
    conn.commit()


# --- lesson_versions ---

def get_lesson_versions(lesson_id, lang=None, generator=None):
    """バージョン一覧を取得する"""
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
        f"SELECT * FROM lesson_versions {where} ORDER BY version_number",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def get_lesson_version(lesson_id, lang, generator, version_number):
    """特定バージョンを取得する"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM lesson_versions WHERE lesson_id = ? AND lang = ? AND generator = ? AND version_number = ?",
        (lesson_id, lang, generator, version_number),
    ).fetchone()
    return dict(row) if row else None


def create_lesson_version(lesson_id, lang="ja", generator="gemini", version_number=None,
                          note="", improve_source_version=None, improve_summary="",
                          improved_sections=""):
    """バージョンを作成する。version_number省略時は自動採番（max+1）"""
    conn = get_connection()
    if version_number is None:
        row = conn.execute(
            "SELECT MAX(version_number) as max_v FROM lesson_versions "
            "WHERE lesson_id = ? AND lang = ? AND generator = ?",
            (lesson_id, lang, generator),
        ).fetchone()
        version_number = (row["max_v"] or 0) + 1
    cur = conn.execute(
        "INSERT INTO lesson_versions "
        "(lesson_id, lang, generator, version_number, note, "
        "improve_source_version, improve_summary, improved_sections, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (lesson_id, lang, generator, version_number, note,
         improve_source_version, improve_summary, improved_sections, _now()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM lesson_versions WHERE id = ?", (cur.lastrowid,)).fetchone())


def update_lesson_version(version_id, **fields):
    """バージョンのメタ情報を更新する"""
    conn = get_connection()
    allowed = {"note", "verify_json", "improve_source_version", "improve_summary", "improved_sections"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [version_id]
    conn.execute(f"UPDATE lesson_versions SET {set_clause} WHERE id = ?", params)
    conn.commit()


def delete_lesson_version(lesson_id, lang, generator, version_number):
    """バージョンとそのセクション・プランを削除する"""
    conn = get_connection()
    conn.execute(
        "DELETE FROM lesson_sections WHERE lesson_id = ? AND lang = ? AND generator = ? AND version_number = ?",
        (lesson_id, lang, generator, version_number),
    )
    conn.execute(
        "DELETE FROM lesson_plans WHERE lesson_id = ? AND lang = ? AND generator = ? AND version_number = ?",
        (lesson_id, lang, generator, version_number),
    )
    conn.execute(
        "DELETE FROM lesson_versions WHERE lesson_id = ? AND lang = ? AND generator = ? AND version_number = ?",
        (lesson_id, lang, generator, version_number),
    )
    conn.commit()


def save_version_verify(version_id, verify_json):
    """バージョンの整合性チェック結果を保存する"""
    conn = get_connection()
    conn.execute(
        "UPDATE lesson_versions SET verify_json = ? WHERE id = ?",
        (verify_json, version_id),
    )
    conn.commit()


# --- section annotations ---

def update_section_annotation(section_id, rating=None, comment=None):
    """セクションの注釈（◎/△/✕ + コメント）を更新する。Noneのフィールドは既存値を維持。"""
    conn = get_connection()
    if rating is not None and comment is not None:
        conn.execute(
            "UPDATE lesson_sections SET annotation_rating = ?, annotation_comment = ? WHERE id = ?",
            (rating, comment, section_id),
        )
    elif rating is not None:
        conn.execute(
            "UPDATE lesson_sections SET annotation_rating = ? WHERE id = ?",
            (rating, section_id),
        )
    elif comment is not None:
        conn.execute(
            "UPDATE lesson_sections SET annotation_comment = ? WHERE id = ?",
            (comment, section_id),
        )
    conn.commit()


# --- lesson_learnings ---

def save_learning(category, analysis_input="", analysis_output="", learnings_md="",
                  prompt_diff="", section_count=0):
    """学習分析結果を保存する"""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO lesson_learnings "
        "(category, analysis_input, analysis_output, learnings_md, prompt_diff, section_count, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (category, analysis_input, analysis_output, learnings_md, prompt_diff, section_count, _now()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM lesson_learnings WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_latest_learning(category):
    """カテゴリの最新の学習結果を取得する"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM lesson_learnings WHERE category = ? ORDER BY created_at DESC LIMIT 1",
        (category,),
    ).fetchone()
    return dict(row) if row else None


def get_learnings(category=None):
    """学習結果一覧を取得する"""
    conn = get_connection()
    if category is not None:
        rows = conn.execute(
            "SELECT * FROM lesson_learnings WHERE category = ? ORDER BY created_at DESC",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM lesson_learnings ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]
