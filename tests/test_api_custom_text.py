"""カスタムテキストAPIのテスト"""


class TestCustomTextAPI:

    def test_list_empty(self, api_client):
        resp = api_client.get("/api/overlay/custom-texts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create(self, api_client):
        resp = api_client.post(
            "/api/overlay/custom-texts",
            json={"label": "test", "content": "hello"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] is not None
        assert data["label"] == "test"
        assert data["content"] == "hello"
        assert "layout" in data

    def test_create_and_list(self, api_client):
        api_client.post(
            "/api/overlay/custom-texts",
            json={"label": "a", "content": "text a"},
        )
        resp = api_client.get("/api/overlay/custom-texts")
        items = resp.json()
        assert len(items) == 1
        assert items[0]["label"] == "a"

    def test_update(self, api_client):
        r1 = api_client.post(
            "/api/overlay/custom-texts",
            json={"label": "old"},
        )
        item_id = r1.json()["id"]
        resp = api_client.put(
            f"/api/overlay/custom-texts/{item_id}",
            json={"content": "updated", "label": "new"},
        )
        assert resp.json()["ok"] is True

    def test_update_layout(self, api_client):
        r1 = api_client.post(
            "/api/overlay/custom-texts",
            json={"label": "a"},
        )
        item_id = r1.json()["id"]
        resp = api_client.post(
            f"/api/overlay/custom-texts/{item_id}/layout",
            json={"x": 50, "y": 60},
        )
        assert resp.json()["ok"] is True
        # 値が保存されたことを確認
        items = api_client.get("/api/overlay/custom-texts").json()
        assert items[0]["layout"]["x"] == 50
        assert items[0]["layout"]["y"] == 60

    def test_delete(self, api_client):
        r1 = api_client.post(
            "/api/overlay/custom-texts",
            json={"label": "del"},
        )
        item_id = r1.json()["id"]
        resp = api_client.delete(f"/api/overlay/custom-texts/{item_id}")
        assert resp.json()["ok"] is True
        assert api_client.get("/api/overlay/custom-texts").json() == []
