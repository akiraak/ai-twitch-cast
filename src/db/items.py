"""ブロードキャストアイテム・カスタムテキスト・キャプチャウィンドウ CRUD"""

import json as _json

from .core import get_connection, _now, get_setting


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
    "lesson_text": {"maxHeight", "lineHeight"},
    "lesson_progress": {"titleFontSize", "itemFontSize"},
}

_ITEM_LABELS = {
    "avatar1": "アバター（メイン）",
    "avatar2": "アバター（サブ）",
    "subtitle": "字幕（メイン）",
    "subtitle2": "字幕（サブ）",
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


# --- migration functions ---

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


def _migrate_avatar_to_avatar1():
    """broadcast_items: avatar → avatar1 にリネーム"""
    conn = get_connection()
    old = conn.execute("SELECT id FROM broadcast_items WHERE id = 'avatar'").fetchone()
    if not old:
        return
    already = conn.execute("SELECT id FROM broadcast_items WHERE id = 'avatar1'").fetchone()
    if already:
        # avatar1 が既にあれば旧 avatar を削除するだけ
        conn.execute("DELETE FROM broadcast_items WHERE id = 'avatar'")
    else:
        conn.execute("UPDATE broadcast_items SET id = 'avatar1' WHERE id = 'avatar'")
    conn.commit()


def migrate_overlay_to_items():
    """overlay.* settings → broadcast_items に移行（初回起動時に自動実行）"""
    conn = get_connection()
    # avatar → avatar1 リネーム
    _migrate_avatar_to_avatar1()
    existing = conn.execute(
        "SELECT id FROM broadcast_items WHERE id = 'avatar1'"
    ).fetchone()
    if existing:
        # 固定アイテム移行済み、動的アイテムの移行もチェック
        _migrate_custom_texts_to_items()
        _migrate_capture_windows_to_items()
        return

    from scripts.routes.overlay import _OVERLAY_DEFAULTS, _COMMON_DEFAULTS

    now = _now()
    fixed_items = ["avatar1", "avatar2", "subtitle", "todo"]
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
