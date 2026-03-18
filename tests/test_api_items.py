"""broadcast_items統合APIのテスト"""

import pytest
from src import db


class TestBroadcastItemsDB:
    """broadcast_itemsテーブルのCRUDテスト"""

    def test_table_exists(self, test_db):
        """broadcast_itemsテーブルが作成されること"""
        conn = test_db.get_connection()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='broadcast_items'"
        ).fetchone()
        assert row is not None

    def test_upsert_and_get(self, test_db):
        result = test_db.upsert_broadcast_item("test1", "avatar", {
            "positionX": 10, "positionY": 20, "zIndex": 5,
        })
        assert result["id"] == "test1"
        assert result["positionX"] == 10
        assert result["positionY"] == 20
        assert result["zIndex"] == 5

        fetched = test_db.get_broadcast_item("test1")
        assert fetched["positionX"] == 10

    def test_upsert_updates_existing(self, test_db):
        test_db.upsert_broadcast_item("test2", "todo", {"positionX": 5})
        test_db.upsert_broadcast_item("test2", "todo", {"positionX": 15, "bgOpacity": 0.5})
        item = test_db.get_broadcast_item("test2")
        assert item["positionX"] == 15
        assert item["bgOpacity"] == 0.5

    def test_specific_props_in_properties_json(self, test_db):
        """アイテム固有プロパティがproperties JSONに格納されること"""
        test_db.upsert_broadcast_item("sub1", "subtitle", {
            "positionX": 50, "bottom": 7.4, "fadeDuration": 3,
        })
        item = test_db.get_broadcast_item("sub1")
        assert item["positionX"] == 50
        assert item["bottom"] == 7.4
        assert item["fadeDuration"] == 3

    def test_get_all(self, test_db):
        test_db.upsert_broadcast_item("a1", "avatar", {"zIndex": 5})
        test_db.upsert_broadcast_item("t1", "todo", {"zIndex": 20})
        items = test_db.get_broadcast_items()
        ids = [i["id"] for i in items]
        assert "a1" in ids
        assert "t1" in ids

    def test_update_layout(self, test_db):
        test_db.upsert_broadcast_item("lay1", "topic", {"positionX": 1, "positionY": 2})
        test_db.update_broadcast_item_layout("lay1", {
            "positionX": 10, "positionY": 20, "zIndex": 30,
        })
        item = test_db.get_broadcast_item("lay1")
        assert item["positionX"] == 10
        assert item["positionY"] == 20
        assert item["zIndex"] == 30

    def test_get_nonexistent_returns_none(self, test_db):
        assert test_db.get_broadcast_item("nonexistent") is None

    def test_properties_merge_on_update(self, test_db):
        """properties JSONが更新時にマージされること"""
        test_db.upsert_broadcast_item("ver1", "version", {
            "format": "v{version}", "strokeSize": 2,
        })
        test_db.upsert_broadcast_item("ver1", "version", {
            "strokeOpacity": 0.5,
        })
        item = test_db.get_broadcast_item("ver1")
        assert item["format"] == "v{version}"
        assert item["strokeSize"] == 2
        assert item["strokeOpacity"] == 0.5


class TestItemsAPI:
    """統合APIエンドポイントのテスト"""

    def test_get_items(self, api_client):
        resp = api_client.get("/api/items")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_put_item(self, api_client, test_db):
        # まずアイテムを作成
        test_db.upsert_broadcast_item("avatar", "avatar", {"positionX": 46.5})
        resp = api_client.put("/api/items/avatar", json={"positionX": 50, "bgOpacity": 0.5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["positionX"] == 50
        assert data["bgOpacity"] == 0.5

    def test_post_item_layout(self, api_client, test_db):
        test_db.upsert_broadcast_item("todo", "todo", {"positionX": 36})
        resp = api_client.post("/api/items/todo/layout", json={
            "positionX": 40, "positionY": 5, "zIndex": 25,
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        item = test_db.get_broadcast_item("todo")
        assert item["positionX"] == 40

    def test_post_item_visibility(self, api_client, test_db):
        test_db.upsert_broadcast_item("version", "version", {"visible": 0})
        resp = api_client.post("/api/items/version/visibility", json={"visible": 1})
        assert resp.status_code == 200
        item = test_db.get_broadcast_item("version")
        assert item["visible"] == 1


class TestCustomTextViaBroadcastItems:
    """custom_textsがbroadcast_items経由で動作すること"""

    def test_create_custom_text(self, test_db):
        item = test_db.create_custom_text(label="テスト", content="Hello")
        assert item["id"] == 1
        assert item["label"] == "テスト"
        assert item["content"] == "Hello"
        assert "layout" in item
        assert item["layout"]["x"] == 5

    def test_get_custom_texts(self, test_db):
        test_db.create_custom_text(label="A", content="aaa")
        test_db.create_custom_text(label="B", content="bbb")
        items = test_db.get_custom_texts()
        assert len(items) >= 2
        labels = [i["label"] for i in items]
        assert "A" in labels
        assert "B" in labels

    def test_update_custom_text(self, test_db):
        item = test_db.create_custom_text(label="Original", content="text")
        test_db.update_custom_text(item["id"], label="Updated", content="new text")
        items = test_db.get_custom_texts()
        updated = [i for i in items if i["id"] == item["id"]][0]
        assert updated["label"] == "Updated"
        assert updated["content"] == "new text"

    def test_update_custom_text_layout(self, test_db):
        item = test_db.create_custom_text(label="L", content="t")
        test_db.update_custom_text_layout(item["id"], {
            "x": 10, "y": 20, "zIndex": 30,
        })
        items = test_db.get_custom_texts()
        updated = [i for i in items if i["id"] == item["id"]][0]
        assert updated["layout"]["x"] == 10
        assert updated["layout"]["y"] == 20
        assert updated["layout"]["zIndex"] == 30

    def test_delete_custom_text(self, test_db):
        item = test_db.create_custom_text(label="Del", content="x")
        test_db.delete_custom_text(item["id"])
        items = test_db.get_custom_texts()
        assert all(i["id"] != item["id"] for i in items)

    def test_update_without_label_preserves_label(self, test_db):
        """labelなしの更新で既存labelが上書きされないこと"""
        item = test_db.create_custom_text(label="元ラベル", content="text")
        test_db.update_custom_text(item["id"], content="新内容")
        items = test_db.get_custom_texts()
        updated = [i for i in items if i["id"] == item["id"]][0]
        assert updated["label"] == "元ラベル"
        assert updated["content"] == "新内容"

    def test_stored_in_broadcast_items(self, test_db):
        """custom_textがbroadcast_itemsテーブルに格納されていること"""
        item = test_db.create_custom_text(label="Check", content="data")
        bi = test_db.get_broadcast_item(f"customtext:{item['id']}")
        assert bi is not None
        assert bi["type"] == "custom_text"
        assert bi["content"] == "data"

    def test_api_create(self, api_client):
        resp = api_client.post("/api/overlay/custom-texts", json={
            "label": "APIテスト", "content": "テキスト内容",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "APIテスト"
        assert data["content"] == "テキスト内容"

    def test_api_get_list(self, api_client):
        api_client.post("/api/overlay/custom-texts", json={
            "label": "List", "content": "c",
        })
        resp = api_client.get("/api/overlay/custom-texts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestMigration:
    """マイグレーションのテスト"""

    def test_migrate_custom_texts(self, test_db):
        """custom_textsテーブルからbroadcast_itemsへの移行"""
        conn = test_db.get_connection()
        # 旧テーブルにデータを直接挿入
        conn.execute(
            "INSERT INTO custom_texts (label, content, x, y, width, height, font_size, bg_opacity, z_index, visible, created_at) "
            "VALUES ('old', 'old content', 1, 2, 30, 40, 1.5, 0.9, 20, 1, '2024-01-01')"
        )
        conn.commit()
        # 移行実行
        from src.db import _migrate_custom_texts_to_items
        _migrate_custom_texts_to_items()
        # broadcast_itemsに移行されたか確認
        bi = test_db.get_broadcast_item("customtext:1")
        assert bi is not None
        assert bi["type"] == "custom_text"
        assert bi["content"] == "old content"

    def test_migrate_capture_windows(self, test_db):
        """capture_windowsテーブルからbroadcast_itemsへの移行"""
        conn = test_db.get_connection()
        conn.execute(
            "INSERT INTO capture_windows (window_name, label, x, y, width, height, z_index, visible, created_at) "
            "VALUES ('Terminal', 'Term', 5, 10, 40, 50, 10, 1, '2024-01-01')"
        )
        conn.commit()
        from src.db import _migrate_capture_windows_to_items
        _migrate_capture_windows_to_items()
        bi = test_db.get_broadcast_item("capture:1")
        assert bi is not None
        assert bi["type"] == "capture"


class TestOverlaySettingsCompat:
    """旧API /api/overlay/settings の互換性テスト"""

    def test_get_reads_from_broadcast_items(self, api_client, test_db):
        """GET時にbroadcast_itemsのデータが返ること"""
        test_db.upsert_broadcast_item("todo", "todo", {
            "positionX": 99, "bgOpacity": 0.5,
        })
        resp = api_client.get("/api/overlay/settings")
        data = resp.json()
        assert data["todo"]["positionX"] == 99
        assert data["todo"]["bgOpacity"] == 0.5

    def test_post_writes_to_broadcast_items(self, api_client, test_db):
        """POST時にbroadcast_itemsに書き込まれること"""
        resp = api_client.post("/api/overlay/settings", json={
            "avatar": {"positionX": 55, "positionY": 30},
        })
        assert resp.status_code == 200
        item = test_db.get_broadcast_item("avatar")
        assert item is not None
        assert item["positionX"] == 55

    def test_post_non_item_sections_use_settings(self, api_client, test_db):
        """lighting/syncはsettingsテーブルに保存されること"""
        resp = api_client.post("/api/overlay/settings", json={
            "sync": {"lipsyncDelay": 200},
        })
        assert resp.status_code == 200
        val = test_db.get_setting("overlay.sync.lipsyncDelay")
        assert val == "200"
