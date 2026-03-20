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
            {"key": "visible", "label": "表示", "type": "toggle"},
        ],
    },
    {
        "title": "配置",
        "fields": [
            {"key": "positionX", "label": "X位置 (%)", "type": "slider", "min": 0, "max": 100, "step": 0.5},
            {"key": "positionY", "label": "Y位置 (%)", "type": "slider", "min": 0, "max": 100, "step": 0.5},
            {"key": "width", "label": "幅 (%)", "type": "slider", "min": 5, "max": 100, "step": 0.5},
            {"key": "height", "label": "高さ (%)", "type": "slider", "min": 5, "max": 100, "step": 0.5},
            {"key": "zIndex", "label": "Z順序", "type": "slider", "min": 0, "max": 100, "step": 1},
        ],
    },
    {
        "title": "背景",
        "fields": [
            {"key": "bgColor", "label": "色", "type": "color"},
            {"key": "bgOpacity", "label": "透明度", "type": "slider", "min": 0, "max": 1, "step": 0.05},
            {"key": "backdropBlur", "label": "ぼかし (px)", "type": "slider", "min": 0, "max": 30, "step": 1},
            {"key": "borderRadius", "label": "角丸 (px)", "type": "slider", "min": 0, "max": 30, "step": 1},
            {"key": "borderSize", "label": "枠サイズ", "type": "slider", "min": 0, "max": 10, "step": 0.5},
            {"key": "borderColor", "label": "枠色", "type": "color"},
            {"key": "borderOpacity", "label": "枠透明度", "type": "slider", "min": 0, "max": 1, "step": 0.05},
        ],
    },
    {
        "title": "文字",
        "fields": [
            {"key": "fontFamily", "label": "フォント", "type": "select", "options": [
                ["", "デフォルト"], ["Noto Sans JP", "Noto Sans JP"],
                ["Yu Gothic UI", "Yu Gothic UI"], ["Meiryo", "メイリオ"],
                ["Yu Mincho", "游明朝"], ["BIZ UDPGothic", "BIZ UDPゴシック"],
                ["M PLUS Rounded 1c", "M PLUS Rounded 1c"],
                ["Kosugi Maru", "小杉丸ゴシック"], ["monospace", "等幅"],
            ]},
            {"key": "fontSize", "label": "サイズ (vw)", "type": "slider", "min": 0.3, "max": 5, "step": 0.05},
            {"key": "textColor", "label": "色", "type": "color"},
            {"key": "textAlign", "label": "水平揃え", "type": "select", "options": [
                ["left", "左"], ["center", "中央"], ["right", "右"],
            ]},
            {"key": "verticalAlign", "label": "垂直揃え", "type": "select", "options": [
                ["top", "上"], ["center", "中央"], ["bottom", "下"],
            ]},
            {"key": "textStrokeSize", "label": "縁取りサイズ", "type": "slider", "min": 0, "max": 10, "step": 0.5},
            {"key": "textStrokeColor", "label": "縁取り色", "type": "color"},
            {"key": "textStrokeOpacity", "label": "縁取り透明度", "type": "slider", "min": 0, "max": 1, "step": 0.05},
            {"key": "padding", "label": "内余白 (px)", "type": "slider", "min": 0, "max": 30, "step": 1},
        ],
    },
]

_ITEM_SPECIFIC_SCHEMA = {
    "avatar": [
        {"title": "固有設定", "fields": [
            {"key": "scale", "label": "スケール", "type": "slider", "min": 0.1, "max": 3, "step": 0.05},
        ]},
    ],
    "subtitle": [
        {"title": "固有設定", "fields": [
            {"key": "bottom", "label": "下からの距離 (%)", "type": "slider", "min": 0, "max": 30, "step": 0.1},
            {"key": "maxWidth", "label": "最大幅 (%)", "type": "slider", "min": 20, "max": 90, "step": 1},
            {"key": "fadeDuration", "label": "フェード (秒)", "type": "slider", "min": 1, "max": 10, "step": 0.5},
        ]},
    ],
    "todo": [
        {"title": "固有設定", "fields": [
            {"key": "titleFontSize", "label": "タイトルサイズ (vw)", "type": "slider", "min": 0.5, "max": 3, "step": 0.05},
        ]},
    ],
    "topic": [
        {"title": "固有設定", "fields": [
            {"key": "maxWidth", "label": "最大幅 (%)", "type": "slider", "min": 10, "max": 60, "step": 1},
            {"key": "titleFontSize", "label": "タイトルサイズ (vw)", "type": "slider", "min": 0.5, "max": 3, "step": 0.05},
        ]},
    ],
    "custom_text": [
        {"title": "コンテンツ", "fields": [
            {"key": "label", "label": "ラベル", "type": "text"},
            {"key": "content", "label": "テキスト", "type": "text"},
        ]},
    ],
}

_SCHEMA_ITEM_LABELS = {
    "avatar": "アバター",
    "subtitle": "字幕",
    "todo": "TODO",
    "topic": "トピック",
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
    return item_id  # avatar, subtitle, todo, topic


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
        return {"error": "not found"}, 404
    # 子パネルも含める
    children = db.get_child_items(item_id)
    if children:
        item["children"] = children
    return item


@router.put("/api/items/{item_id}")
async def update_item(item_id: str, request: Request):
    """broadcast_itemを更新（共通プロパティ + properties）"""
    body = await request.json()
    item = db.get_broadcast_item(item_id)
    if not item:
        return {"error": "not found"}
    result = db.upsert_broadcast_item(item_id, item["type"], body)
    await state.broadcast_overlay({"type": "settings_update", item_id: body})
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
    prefix = item_id if item_id in ("avatar", "subtitle", "todo", "topic", "version") else item["type"]
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
