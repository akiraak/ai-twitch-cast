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
        test_db.upsert_broadcast_item("lay1", "todo", {"positionX": 1, "positionY": 2})
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


class TestChildPanelAPI:
    """子パネルCRUD APIのテスト"""

    def _ensure_parent(self, test_db):
        test_db.upsert_broadcast_item("avatar", "avatar", {
            "positionX": 46.5, "positionY": 24.3,
        })

    def test_create_child(self, api_client, test_db):
        self._ensure_parent(test_db)
        resp = api_client.post("/api/items/avatar/children", json={
            "type": "child_text",
            "label": "バージョン",
            "content": "v1.0",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "child:avatar:1"
        assert data["type"] == "child_text"
        assert data["label"] == "バージョン"
        assert data["parentId"] == "avatar"

    def test_create_child_nonexistent_parent(self, api_client):
        resp = api_client.post("/api/items/nonexistent/children", json={
            "type": "child_text", "label": "テスト",
        })
        data = resp.json()
        assert data.get("error") == "parent not found"

    def test_delete_child(self, api_client, test_db):
        self._ensure_parent(test_db)
        child = test_db.create_child_item("avatar", {"label": "削除対象"})
        resp = api_client.delete(f"/api/items/{child['id']}")
        assert resp.status_code == 200
        assert resp.json().get("ok") is True
        assert test_db.get_child_items("avatar") == []

    def test_update_child_layout(self, api_client, test_db):
        self._ensure_parent(test_db)
        child = test_db.create_child_item("avatar", {"label": "位置テスト"})
        resp = api_client.post(f"/api/items/{child['id']}/layout", json={
            "positionX": 20, "positionY": 30,
        })
        assert resp.status_code == 200
        updated = test_db.get_broadcast_item(child["id"])
        assert updated["positionX"] == 20
        assert updated["positionY"] == 30

    def test_get_items_with_children(self, api_client, test_db):
        self._ensure_parent(test_db)
        test_db.create_child_item("avatar", {"label": "子A"})
        test_db.create_child_item("avatar", {"label": "子B"})
        resp = api_client.get("/api/items")
        items = resp.json()
        avatar = next((i for i in items if i["id"] == "avatar"), None)
        assert avatar is not None
        assert "children" in avatar
        assert len(avatar["children"]) == 2

    def test_get_single_item_with_children(self, api_client, test_db):
        self._ensure_parent(test_db)
        test_db.create_child_item("avatar", {"label": "子テスト"})
        resp = api_client.get("/api/items/avatar")
        data = resp.json()
        assert len(data["children"]) == 1
        assert data["children"][0]["label"] == "子テスト"

    def test_children_not_in_root_list(self, api_client, test_db):
        """子パネルがルートの一覧に混ざらないこと"""
        self._ensure_parent(test_db)
        test_db.create_child_item("avatar", {"label": "子"})
        resp = api_client.get("/api/items")
        items = resp.json()
        child_in_root = [i for i in items if i["id"].startswith("child:")]
        assert len(child_in_root) == 0


class TestItemSchema:
    """設定スキーマAPIのテスト"""

    def test_get_common_schema(self, api_client):
        """パラメータなしで共通スキーマが返ること"""
        resp = api_client.get("/api/items/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data
        titles = [g["title"] for g in data["groups"]]
        assert "表示" in titles
        assert "配置" in titles
        assert "背景" in titles
        assert "文字" in titles
        # 共通スキーマにはitem_id/item_typeがない
        assert "item_id" not in data

    def test_get_schema_with_item_id(self, api_client):
        """item_id指定で固有プロパティ + 共通スキーマが返ること"""
        resp = api_client.get("/api/items/schema?item_id=subtitle")
        assert resp.status_code == 200
        data = resp.json()
        assert data["item_id"] == "subtitle"
        assert data["item_type"] == "subtitle"
        assert data["label"] == "字幕（メイン）"
        # 固有設定グループが先頭にある
        assert data["groups"][0]["title"] == "固有設定"
        specific_keys = [f["key"] for f in data["groups"][0]["fields"]]
        assert "bottom" in specific_keys
        assert "maxWidth" in specific_keys
        assert "fadeDuration" in specific_keys
        # 共通グループも含まれる
        titles = [g["title"] for g in data["groups"]]
        assert "配置" in titles

    def test_get_schema_avatar(self, api_client):
        """avatarの固有プロパティ（scale）が含まれること"""
        resp = api_client.get("/api/items/schema?item_id=avatar")
        data = resp.json()
        assert data["item_type"] == "avatar"
        specific_keys = [f["key"] for f in data["groups"][0]["fields"]]
        assert "scale" in specific_keys

    def test_get_schema_custom_text(self, api_client):
        """customtext:のIDでcustom_textスキーマが返ること"""
        resp = api_client.get("/api/items/schema?item_id=customtext:1")
        data = resp.json()
        assert data["item_type"] == "custom_text"
        specific_keys = [f["key"] for f in data["groups"][0]["fields"]]
        assert "label" in specific_keys
        assert "content" in specific_keys

    def test_get_schema_capture(self, api_client):
        """capture:のIDで共通スキーマのみ返ること（固有定義なし）"""
        resp = api_client.get("/api/items/schema?item_id=capture:1")
        data = resp.json()
        assert data["item_type"] == "capture"
        # 固有スキーマがないので全グループが共通
        assert data["groups"][0]["title"] == "表示"

    def test_get_schema_child(self, api_client):
        """child:のIDでchild_textスキーマが返ること"""
        resp = api_client.get("/api/items/schema?item_id=child:avatar:1")
        data = resp.json()
        assert data["item_type"] == "child_text"

    def test_schema_field_structure(self, api_client):
        """スキーマフィールドに必要な属性が含まれること"""
        resp = api_client.get("/api/items/schema")
        data = resp.json()
        # 配置グループのpositionXを検証
        layout_group = next(g for g in data["groups"] if g["title"] == "配置")
        pos_x = next(f for f in layout_group["fields"] if f["key"] == "positionX")
        assert pos_x["type"] == "slider"
        assert pos_x["min"] == 0
        assert pos_x["max"] == 100
        assert pos_x["step"] == 0.5
        assert "label" in pos_x

    def test_schema_select_has_options(self, api_client):
        """selectタイプにoptionsが含まれること"""
        resp = api_client.get("/api/items/schema")
        data = resp.json()
        text_group = next(g for g in data["groups"] if g["title"] == "文字")
        font = next(f for f in text_group["fields"] if f["key"] == "fontFamily")
        assert font["type"] == "select"
        assert isinstance(font["options"], list)
        assert len(font["options"]) >= 2
        # 各optionは[value, label]の形式
        assert len(font["options"][0]) == 2

    def test_schema_uses_db_label(self, api_client, test_db):
        """DBにアイテムが存在する場合そのlabelを使うこと"""
        test_db.upsert_broadcast_item("todo", "todo", {"positionX": 36})
        resp = api_client.get("/api/items/schema?item_id=todo")
        data = resp.json()
        assert data["label"] == "TODO"


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
