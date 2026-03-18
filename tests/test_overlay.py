"""overlay.py のテスト（TODOパース・ブロードキャスト・共通プロパティ）"""

from unittest.mock import AsyncMock, patch

import pytest


class TestGetTodo:
    """TODO.mdパースのテスト"""

    async def test_missing_file_returns_empty(self, tmp_path):
        with patch("scripts.routes.overlay.TODO_PATH", tmp_path / "nonexistent.md"):
            from scripts.routes.overlay import get_todo
            result = await get_todo()
            assert result == {"items": []}

    async def test_parse_todo_items(self, tmp_path):
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("# TODO\n\n## 機能\n- [ ] タスクA\n- [ ] タスクB\n", encoding="utf-8")
        with patch("scripts.routes.overlay.TODO_PATH", todo_file):
            from scripts.routes.overlay import get_todo
            result = await get_todo()
            assert len(result["items"]) == 2
            assert result["items"][0]["text"] == "タスクA"
            assert result["items"][0]["status"] == "todo"
            assert result["items"][0]["section"] == "機能"

    async def test_in_progress_comes_first(self, tmp_path):
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("## セクション1\n- [>] 作業中タスク\n- [ ] 未着手タスク\n", encoding="utf-8")
        with patch("scripts.routes.overlay.TODO_PATH", todo_file):
            from scripts.routes.overlay import get_todo
            result = await get_todo()
            assert len(result["items"]) == 2
            assert result["items"][0]["status"] == "in_progress"
            assert result["items"][0]["section"] == "作業中"
            assert result["items"][1]["status"] == "todo"

    async def test_multiple_sections(self, tmp_path):
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("## A\n- [ ] タスク1\n## B\n- [ ] タスク2\n", encoding="utf-8")
        with patch("scripts.routes.overlay.TODO_PATH", todo_file):
            from scripts.routes.overlay import get_todo
            result = await get_todo()
            assert result["items"][0]["section"] == "A"
            assert result["items"][1]["section"] == "B"

    async def test_completed_tasks_ignored(self, tmp_path):
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("# TODO\nただのテキスト\n- [x] 完了タスク\n", encoding="utf-8")
        with patch("scripts.routes.overlay.TODO_PATH", todo_file):
            from scripts.routes.overlay import get_todo
            result = await get_todo()
            assert result["items"] == []

    async def test_nested_indent(self, tmp_path):
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("## 機能\n- [ ] 親タスク\n  - [ ] 子タスク\n", encoding="utf-8")
        with patch("scripts.routes.overlay.TODO_PATH", todo_file):
            from scripts.routes.overlay import get_todo
            result = await get_todo()
            assert len(result["items"]) == 2


class TestBroadcastTodo:
    """broadcast_todoのテスト"""

    async def test_broadcasts_todo_update_event(self, tmp_path):
        todo_file = tmp_path / "TODO.md"
        todo_file.write_text("## テスト\n- [ ] アイテム\n", encoding="utf-8")
        with patch("scripts.routes.overlay.TODO_PATH", todo_file), \
             patch("scripts.routes.overlay.state") as mock_state:
            mock_state.broadcast_overlay = AsyncMock()
            from scripts.routes.overlay import broadcast_todo
            await broadcast_todo()
            mock_state.broadcast_overlay.assert_called_once()
            event = mock_state.broadcast_overlay.call_args[0][0]
            assert event["type"] == "todo_update"
            assert len(event["items"]) == 1
            assert event["items"][0]["text"] == "アイテム"


class TestTodoSource:
    """TODOソース切り替えのテスト"""

    async def test_default_source_is_self(self):
        import scripts.routes.overlay as ov
        original = ov._todo_source
        ov._todo_source = "self"
        try:
            assert ov._get_todo_path() == ov.TODO_PATH
            assert ov._get_todo_source_label() is None
        finally:
            ov._todo_source = original

    async def test_dev_source_returns_repo_path(self, test_db, tmp_path):
        import scripts.routes.overlay as ov
        local_path = tmp_path / "repo"
        local_path.mkdir()
        (local_path / "TODO.md").write_text("- [ ] task\n")
        repo = test_db.add_dev_repo("o/r", "https://o.git", str(local_path))
        original = ov._todo_source
        ov._todo_source = f"dev:{repo['id']}"
        try:
            assert ov._get_todo_path() == local_path / "TODO.md"
            assert ov._get_todo_source_label() == "o/r"
        finally:
            ov._todo_source = original

    async def test_invalid_dev_source_falls_back(self):
        import scripts.routes.overlay as ov
        original = ov._todo_source
        ov._todo_source = "dev:999"
        try:
            assert ov._get_todo_path() == ov.TODO_PATH
        finally:
            ov._todo_source = original

    def test_get_todo_source_api(self, api_client):
        resp = api_client.get("/api/todo/source")
        assert resp.status_code == 200
        assert resp.json()["source"] == "self"

    def test_set_todo_source_self(self, api_client):
        resp = api_client.post("/api/todo/source", json={"source": "self"})
        assert resp.json()["ok"] is True

    def test_set_todo_source_dev(self, api_client, test_db):
        repo = test_db.add_dev_repo("o/r", "https://o.git", "repos/r")
        resp = api_client.post("/api/todo/source", json={"source": "dev", "repo_id": repo["id"]})
        assert resp.json()["ok"] is True
        assert resp.json()["label"] == "o/r"
        # クリーンアップ
        api_client.post("/api/todo/source", json={"source": "self"})

    def test_set_todo_source_invalid_repo(self, api_client):
        resp = api_client.post("/api/todo/source", json={"source": "dev", "repo_id": 999})
        assert resp.json()["ok"] is False


class TestCommonDefaults:
    """_COMMON_DEFAULTS と _make_item_defaults のテスト"""

    def test_common_defaults_has_all_keys(self):
        from scripts.routes.overlay import _COMMON_DEFAULTS
        expected_keys = {
            "visible", "positionX", "positionY", "width", "height", "zIndex",
            "bgColor", "bgOpacity", "borderRadius",
            "borderEnabled", "borderColor", "borderSize", "borderOpacity",
            "textColor", "fontSize",
            "textStrokeColor", "textStrokeSize", "textStrokeOpacity",
            "padding",
        }
        assert set(_COMMON_DEFAULTS.keys()) == expected_keys

    def test_make_item_defaults_merges(self):
        from scripts.routes.overlay import _COMMON_DEFAULTS, _make_item_defaults
        result = _make_item_defaults({"positionX": 10, "extra": "val"})
        # 共通デフォルトがベース
        assert result["visible"] == _COMMON_DEFAULTS["visible"]
        assert result["bgColor"] == _COMMON_DEFAULTS["bgColor"]
        # オーバーライドが優先
        assert result["positionX"] == 10
        # 追加プロパティも含まれる
        assert result["extra"] == "val"

    def test_all_visual_items_have_common_properties(self):
        from scripts.routes.overlay import _OVERLAY_DEFAULTS, _COMMON_DEFAULTS
        visual_items = ["avatar", "subtitle", "todo", "topic", "version", "dev_activity"]
        for item in visual_items:
            assert item in _OVERLAY_DEFAULTS, f"{item} が _OVERLAY_DEFAULTS にない"
            for key in _COMMON_DEFAULTS:
                assert key in _OVERLAY_DEFAULTS[item], f"{item} に共通プロパティ {key} がない"

    def test_non_visual_items_unchanged(self):
        """lighting・syncは共通プロパティを持たない"""
        from scripts.routes.overlay import _OVERLAY_DEFAULTS, _COMMON_DEFAULTS
        for item in ["lighting", "sync"]:
            for key in _COMMON_DEFAULTS:
                if key not in _OVERLAY_DEFAULTS[item]:
                    break
            else:
                pytest.fail(f"{item} が不要な共通プロパティを持っている")

    def test_dev_activity_in_overlay_defaults(self):
        from scripts.routes.overlay import _OVERLAY_DEFAULTS
        da = _OVERLAY_DEFAULTS["dev_activity"]
        assert da["visible"] == 0
        assert da["positionX"] == 1
        assert da["positionY"] == 75
        assert da["zIndex"] == 15
        assert da["bgOpacity"] == 0.9
        assert da["fontSize"] == 0.65


class TestOverlaySettingsAPI:
    """GET/POST /api/overlay/settings のテスト"""

    def test_get_returns_common_properties(self, api_client):
        resp = api_client.get("/api/overlay/settings")
        assert resp.status_code == 200
        data = resp.json()
        # 全ビジュアルアイテムの共通プロパティが返る
        for item in ["avatar", "subtitle", "todo", "topic", "version", "dev_activity"]:
            assert item in data, f"{item} がレスポンスにない"
            assert "bgColor" in data[item], f"{item} に bgColor がない"
            assert "borderRadius" in data[item], f"{item} に borderRadius がない"
            assert "textColor" in data[item], f"{item} に textColor がない"
            assert "padding" in data[item], f"{item} に padding がない"

    def test_get_returns_item_specific_properties(self, api_client):
        resp = api_client.get("/api/overlay/settings")
        data = resp.json()
        # アイテム固有のプロパティも返る
        assert "bottom" in data["subtitle"]
        assert "titleFontSize" in data["todo"]
        assert "format" in data["version"]
        assert "lipsyncDelay" in data["sync"]

    def test_post_saves_common_property(self, api_client):
        # bgColorを変更して保存
        resp = api_client.post("/api/overlay/settings", json={
            "todo": {"bgColor": "rgba(255,0,0,1)"},
        })
        assert resp.status_code == 200
        # GETで確認
        resp = api_client.get("/api/overlay/settings")
        assert resp.json()["todo"]["bgColor"] == "rgba(255,0,0,1)"

    def test_post_saves_dev_activity(self, api_client):
        resp = api_client.post("/api/overlay/settings", json={
            "dev_activity": {"positionX": 5, "positionY": 80, "fontSize": 0.8},
        })
        assert resp.status_code == 200
        resp = api_client.get("/api/overlay/settings")
        assert resp.json()["dev_activity"]["positionX"] == 5
        assert resp.json()["dev_activity"]["positionY"] == 80
        assert resp.json()["dev_activity"]["fontSize"] == 0.8

    def test_default_values_when_no_db(self, api_client):
        """DB未保存のプロパティはデフォルト値が返る（scenes.jsonの値で上書きされることもある）"""
        resp = api_client.get("/api/overlay/settings")
        data = resp.json()
        # 共通プロパティが型としてちゃんと返る
        assert isinstance(data["avatar"]["positionX"], (int, float))
        assert isinstance(data["avatar"]["bgOpacity"], (int, float))
        # dev_activityの新プロパティが返る
        assert "visible" in data["dev_activity"]
        assert "bgColor" in data["dev_activity"]
