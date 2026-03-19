"""broadcast_items統合APIルート"""

from fastapi import APIRouter, Request

from scripts import state
from src import db

router = APIRouter()


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
    prefix = item_id if item_id in ("avatar", "subtitle", "todo", "topic", "version", "dev_activity") else item["type"]
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
