"""broadcast_items統合APIルート"""

from fastapi import APIRouter, Request

from scripts import state
from src import db

router = APIRouter()

# ---------------------------------------------------------------------------
# 設定スキーマ定義（全クライアント共通: Web UI / broadcast.html / C#アプリ）
# ---------------------------------------------------------------------------

_COMMON_SCHEMA_GROUPS = [
    {
        "title": "表示",
        "fields": [
            {"key": "visible", "label": "表示", "type": "toggle", "default": 1},
        ],
    },
    {
        "title": "配置",
        "fields": [
            {"key": "positionX", "label": "X位置 (%)", "type": "slider", "min": 0, "max": 100, "step": 0.5, "default": 0},
            {"key": "positionY", "label": "Y位置 (%)", "type": "slider", "min": 0, "max": 100, "step": 0.5, "default": 0},
            {"key": "width", "label": "幅 (%)", "type": "slider", "min": 5, "max": 100, "step": 0.5, "default": 30},
            {"key": "height", "label": "高さ (%)", "type": "slider", "min": 5, "max": 100, "step": 0.5, "default": 30},
            {"key": "zIndex", "label": "Z順序", "type": "slider", "min": 0, "max": 100, "step": 1, "default": 10},
        ],
    },
    {
        "title": "背景",
        "fields": [
            {"key": "bgColor", "label": "色", "type": "color", "default": "#141428"},
            {"key": "bgOpacity", "label": "透明度", "type": "slider", "min": 0, "max": 1, "step": 0.05, "default": 0.85},
            {"key": "backdropBlur", "label": "ぼかし (px)", "type": "slider", "min": 0, "max": 30, "step": 1, "default": 6},
            {"key": "borderRadius", "label": "角丸 (px)", "type": "slider", "min": 0, "max": 30, "step": 1, "default": 8},
            {"key": "borderSize", "label": "枠サイズ", "type": "slider", "min": 0, "max": 10, "step": 0.5, "default": 1},
            {"key": "borderColor", "label": "枠色", "type": "color", "default": "#7c4dff"},
            {"key": "borderOpacity", "label": "枠透明度", "type": "slider", "min": 0, "max": 1, "step": 0.05, "default": 0.3},
        ],
    },
    {
        "title": "文字",
        "fields": [
            {"key": "fontFamily", "label": "フォント", "type": "select", "default": "", "options": [
                ["", "デフォルト"], ["Noto Sans JP", "Noto Sans JP"],
                ["Yu Gothic UI", "Yu Gothic UI"], ["Meiryo", "メイリオ"],
                ["Yu Mincho", "游明朝"], ["BIZ UDPGothic", "BIZ UDPゴシック"],
                ["M PLUS Rounded 1c", "M PLUS Rounded 1c"],
                ["Kosugi Maru", "小杉丸ゴシック"], ["monospace", "等幅"],
            ]},
            {"key": "fontSize", "label": "サイズ (vw)", "type": "slider", "min": 0.3, "max": 5, "step": 0.05, "default": 1.2},
            {"key": "textColor", "label": "色", "type": "color", "default": "#ffffff"},
            {"key": "textAlign", "label": "水平揃え", "type": "select", "default": "left", "options": [
                ["left", "左"], ["center", "中央"], ["right", "右"],
            ]},
            {"key": "verticalAlign", "label": "垂直揃え", "type": "select", "default": "top", "options": [
                ["top", "上"], ["center", "中央"], ["bottom", "下"],
            ]},
            {"key": "textStrokeSize", "label": "縁取りサイズ", "type": "slider", "min": 0, "max": 10, "step": 0.5, "default": 0},
            {"key": "textStrokeColor", "label": "縁取り色", "type": "color", "default": "#000000"},
            {"key": "textStrokeOpacity", "label": "縁取り透明度", "type": "slider", "min": 0, "max": 1, "step": 0.05, "default": 0.8},
            {"key": "padding", "label": "内余白 (px)", "type": "slider", "min": 0, "max": 30, "step": 1, "default": 10},
        ],
    },
]

_ITEM_SPECIFIC_SCHEMA = {
    "avatar": [
        {"title": "固有設定", "fields": [
            {"key": "scale", "label": "スケール", "type": "slider", "min": 0.1, "max": 3, "step": 0.05, "default": 1.0},
            {"key": "bodyAngle", "label": "体の向き (°)", "type": "slider", "min": -45, "max": 45, "step": 1, "default": 0},
        ]},
        {"title": "待機モーション", "fields": [
            {"key": "idleScale", "label": "動きの大きさ", "type": "slider", "min": 0, "max": 2, "step": 0.05, "default": 1.0},
            {"key": "breathScale", "label": "呼吸の大きさ", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
            {"key": "swayScale", "label": "体の揺れ", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
            {"key": "headScale", "label": "頭の動き", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
            {"key": "gazeRange", "label": "見回し範囲", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
            {"key": "armAngle", "label": "腕の角度 (°)", "type": "slider", "min": 30, "max": 90, "step": 1, "default": 70},
            {"key": "armScale", "label": "腕の揺れ", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
            {"key": "earFreq", "label": "耳ぴくぴく頻度", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
        ]},
    ],
    "subtitle": [
        {"title": "固有設定", "fields": [
            {"key": "bottom", "label": "下からの距離 (%)", "type": "slider", "min": 0, "max": 30, "step": 0.1, "default": 7.4},
            {"key": "maxWidth", "label": "最大幅 (%)", "type": "slider", "min": 20, "max": 90, "step": 1, "default": 60},
            {"key": "fadeDuration", "label": "フェード (秒)", "type": "slider", "min": 1, "max": 10, "step": 0.5, "default": 3},
        ]},
    ],
    "subtitle2": [
        {"title": "固有設定", "fields": [
            {"key": "bottom", "label": "下からの距離 (%)", "type": "slider", "min": 0, "max": 30, "step": 0.1, "default": 7.4},
            {"key": "maxWidth", "label": "最大幅 (%)", "type": "slider", "min": 20, "max": 90, "step": 1, "default": 60},
            {"key": "fadeDuration", "label": "フェード (秒)", "type": "slider", "min": 1, "max": 10, "step": 0.5, "default": 3},
        ]},
    ],
    "todo": [
        {"title": "固有設定", "fields": [
            {"key": "titleFontSize", "label": "タイトルサイズ (vw)", "type": "slider", "min": 0.5, "max": 3, "step": 0.05, "default": 1.0},
        ]},
    ],
    "custom_text": [
        {"title": "コンテンツ", "fields": [
            {"key": "label", "label": "ラベル", "type": "text"},
            {"key": "content", "label": "テキスト", "type": "text"},
        ]},
    ],
    "lesson_title": [],
    "lesson_text": [
        {"title": "固有設定", "fields": [
            {"key": "maxHeight", "label": "最大高さ (%)", "type": "slider", "min": 20, "max": 90, "step": 1, "default": 70},
            {"key": "lineHeight", "label": "行間", "type": "slider", "min": 1.0, "max": 3.0, "step": 0.1, "default": 1.7},
        ]},
    ],
    "lesson_progress": [
        {"title": "固有設定", "fields": [
            {"key": "maxHeight", "label": "最大高さ (%)", "type": "slider", "min": 20, "max": 90, "step": 1, "default": 80},
            {"key": "itemFontSize", "label": "項目文字 (vw)", "type": "slider", "min": 0.8, "max": 2, "step": 0.05, "default": 0.95},
        ]},
        {"title": "タイトル文字", "fields": [
            {"key": "titleFontSize", "label": "サイズ (vw)", "type": "slider", "min": 0.5, "max": 3, "step": 0.05, "default": 1.1},
            {"key": "titleColor", "label": "色", "type": "color", "default": "#7c4dff"},
            {"key": "titleStrokeSize", "label": "縁取りサイズ", "type": "slider", "min": 0, "max": 10, "step": 0.5, "default": 0},
            {"key": "titleStrokeColor", "label": "縁取り色", "type": "color", "default": "#000000"},
            {"key": "titleStrokeOpacity", "label": "縁取り透明度", "type": "slider", "min": 0, "max": 1, "step": 0.05, "default": 0.8},
        ]},
        {"title": "カウント文字", "fields": [
            {"key": "countFontSize", "label": "サイズ (vw)", "type": "slider", "min": 0.5, "max": 2, "step": 0.05, "default": 0.85},
            {"key": "countColor", "label": "色", "type": "color", "default": "#c8b4ff"},
            {"key": "countStrokeSize", "label": "縁取りサイズ", "type": "slider", "min": 0, "max": 10, "step": 0.5, "default": 0},
            {"key": "countStrokeColor", "label": "縁取り色", "type": "color", "default": "#000000"},
            {"key": "countStrokeOpacity", "label": "縁取り透明度", "type": "slider", "min": 0, "max": 1, "step": 0.05, "default": 0.8},
        ]},
    ],
}

_SCHEMA_ITEM_LABELS = {
    "avatar1": "アバター（メイン）",
    "avatar2": "アバター（サブ）",
    "subtitle": "字幕（メイン）",
    "subtitle2": "字幕（サブ）",
    "todo": "TODO",
    "lesson_title": "授業タイトル",
    "lesson_text": "授業テキスト",
    "lesson_progress": "授業進捗",
    "custom_text": "カスタムテキスト",
    "capture": "キャプチャ",
    "child_text": "子テキスト",
}


def _get_item_type(item_id: str) -> str:
    """アイテムIDからタイプを推定"""
    if item_id.startswith("customtext:"):
        return "custom_text"
    if item_id.startswith("capture:"):
        return "capture"
    if item_id.startswith("child:"):
        return "child_text"
    if item_id.startswith("avatar"):
        return "avatar"
    return item_id  # subtitle, todo


@router.get("/api/items/schema")
async def get_item_schema(item_id: str | None = None):
    """設定スキーマを返す。item_id指定で固有プロパティも含む"""
    if item_id:
        item_type = _get_item_type(item_id)
        specific = _ITEM_SPECIFIC_SCHEMA.get(item_type, [])
        item = db.get_broadcast_item(item_id)
        label = (item or {}).get("label") or _SCHEMA_ITEM_LABELS.get(item_type, item_id)
        return {
            "item_id": item_id,
            "item_type": item_type,
            "label": label,
            "groups": specific + _COMMON_SCHEMA_GROUPS,
        }
    return {"groups": _COMMON_SCHEMA_GROUPS}


@router.get("/api/items")
async def get_items():
    """全broadcast_items一覧を返す（子パネルはchildren配列としてネスト）"""
    items = db.get_broadcast_items()
    # 各アイテムにchildren配列を追加
    for item in items:
        children = db.get_child_items(item["id"])
        if children:
            item["children"] = children
    return items


@router.get("/api/items/{item_id}")
async def get_item(item_id: str):
    """指定IDのbroadcast_itemを返す"""
    item = db.get_broadcast_item(item_id)
    if not item:
        return {"error": "not found"}
    # 子パネルも含める
    children = db.get_child_items(item_id)
    if children:
        item["children"] = children
    return item


@router.put("/api/items/{item_id}")
async def update_item(item_id: str, request: Request):
    """broadcast_itemを更新（存在しなければ自動作成）"""
    body = await request.json()
    item = db.get_broadcast_item(item_id)
    item_type = item["type"] if item else _get_item_type(item_id)
    result = db.upsert_broadcast_item(item_id, item_type, body)
    await state.broadcast_overlay({"type": "settings_update", **{item_id: body}})
    return result


@router.post("/api/items/{item_id}/layout")
async def update_item_layout(item_id: str, request: Request):
    """broadcast_itemのレイアウトのみ更新（ドラッグ保存用）"""
    body = await request.json()
    db.update_broadcast_item_layout(item_id, body)
    return {"ok": True}


@router.post("/api/items/{item_id}/visibility")
async def update_item_visibility(item_id: str, request: Request):
    """broadcast_itemの表示ON/OFF切替"""
    body = await request.json()
    visible = body.get("visible", 1)
    item = db.get_broadcast_item(item_id)
    if not item:
        return {"error": "not found"}
    db.upsert_broadcast_item(item_id, item["type"], {"visible": visible})
    prefix = item_id if item_id in ("avatar", "subtitle", "todo", "version") else item["type"]
    await state.broadcast_overlay({"type": "settings_update", prefix: {"visible": visible}})
    return {"ok": True}


@router.post("/api/items/{parent_id}/children")
async def create_child_item(parent_id: str, request: Request):
    """親パネルに子パネルを追加"""
    body = await request.json()
    item = db.create_child_item(parent_id, body)
    if not item:
        return {"error": "parent not found"}
    await state.broadcast_overlay({
        "type": "child_panel_add",
        "parentId": parent_id,
        **item,
    })
    return item


@router.delete("/api/items/{item_id}")
async def delete_item(item_id: str):
    """broadcast_itemを削除（子パネル含む）"""
    item = db.get_broadcast_item(item_id)
    if not item:
        return {"error": "not found"}
    parent_id = item.get("parentId")
    db.delete_broadcast_item_cascade(item_id)
    if parent_id:
        # 子パネル削除
        await state.broadcast_overlay({
            "type": "child_panel_remove",
            "id": item_id,
            "parentId": parent_id,
        })
    return {"ok": True}
