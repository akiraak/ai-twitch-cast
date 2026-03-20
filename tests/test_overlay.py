"""overlay.py のテスト（TODOパース・ブロードキャスト・共通プロパティ）"""

import json
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


class TestTodoUploadedSource:
    """DB保存TODOソースのテスト"""

    async def test_get_todo_from_db(self, test_db):
        """DBファイルのコンテンツをパースする"""
        from src import db
        file_id = "test1"
        db.set_setting("todo.active", file_id)
        db.set_setting("todo.files", json.dumps([{"id": file_id, "name": "test.md"}]))
        db.set_setting(f"todo.file.{file_id}.content", "## 機能\n- [ ] タスクX\n- [ ] タスクY\n")
        from scripts.routes.overlay import get_todo
        result = await get_todo()
        assert len(result["items"]) == 2
        assert result["items"][0]["text"] == "タスクX"
        assert result["items"][0]["status"] == "todo"

    async def test_get_todo_with_in_progress(self, test_db):
        """DB管理のin_progressが反映される"""
        from src import db
        file_id = "test2"
        db.set_setting("todo.active", file_id)
        db.set_setting("todo.files", json.dumps([{"id": file_id, "name": "test.md"}]))
        db.set_setting(f"todo.file.{file_id}.content", "## 機能\n- [ ] タスクX\n- [ ] タスクY\n")
        db.set_setting(f"todo.ip.{file_id}", json.dumps(["タスクX"]))
        from scripts.routes.overlay import get_todo
        result = await get_todo()
        assert result["items"][0]["status"] == "in_progress"
        assert result["items"][0]["section"] == "作業中"

    async def test_get_todo_empty_content(self, test_db):
        """コンテンツが空なら空リスト"""
        from src import db
        file_id = "test3"
        db.set_setting("todo.active", file_id)
        db.set_setting("todo.files", json.dumps([{"id": file_id, "name": "test.md"}]))
        db.set_setting(f"todo.file.{file_id}.content", "")
        from scripts.routes.overlay import get_todo
        result = await get_todo()
        assert result["items"] == []


class TestTodoFilesAPI:
    """TODO files管理APIのテスト"""

    def test_list_files_default(self, api_client):
        resp = api_client.get("/api/todo/files")
        data = resp.json()
        assert data["active"] == "project"
        assert data["files"] == []

    def test_upload_and_list(self, api_client):
        resp = api_client.post("/api/todo/upload", json={
            "content": "## テスト\n- [ ] アップロードタスク\n",
            "name": "cooking-basket",
        })
        assert resp.json()["ok"] is True
        file_id = resp.json()["id"]
        # ファイル一覧を確認
        resp = api_client.get("/api/todo/files")
        data = resp.json()
        assert data["active"] == file_id
        assert len(data["files"]) == 1
        assert data["files"][0]["name"] == "cooking-basket"
        # TODOリストを確認
        resp = api_client.get("/api/todo")
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["text"] == "アップロードタスク"

    def test_switch_to_project(self, api_client):
        api_client.post("/api/todo/upload", json={"content": "- [ ] X\n", "name": "x.md"})
        resp = api_client.post("/api/todo/switch", json={"id": "project"})
        assert resp.json()["ok"] is True
        resp = api_client.get("/api/todo/files")
        assert resp.json()["active"] == "project"

    def test_switch_between_files(self, api_client):
        r1 = api_client.post("/api/todo/upload", json={"content": "- [ ] A\n", "name": "a.md"})
        id_a = r1.json()["id"]
        r2 = api_client.post("/api/todo/upload", json={"content": "- [ ] B\n", "name": "b.md"})
        id_b = r2.json()["id"]
        # bがアクティブ
        resp = api_client.get("/api/todo")
        assert resp.json()["items"][0]["text"] == "B"
        # aに切り替え
        api_client.post("/api/todo/switch", json={"id": id_a})
        resp = api_client.get("/api/todo")
        assert resp.json()["items"][0]["text"] == "A"

    def test_delete_file(self, api_client):
        r = api_client.post("/api/todo/upload", json={"content": "- [ ] X\n", "name": "x.md"})
        file_id = r.json()["id"]
        resp = api_client.delete(f"/api/todo/files/{file_id}")
        assert resp.json()["ok"] is True
        # projectに戻る
        resp = api_client.get("/api/todo/files")
        assert resp.json()["active"] == "project"
        assert resp.json()["files"] == []

    def test_upload_same_name_updates(self, api_client):
        """同名ファイルはIDを維持して内容を更新"""
        r1 = api_client.post("/api/todo/upload", json={"content": "- [ ] old\n", "name": "todo.md"})
        id1 = r1.json()["id"]
        r2 = api_client.post("/api/todo/upload", json={"content": "- [ ] new\n", "name": "todo.md"})
        id2 = r2.json()["id"]
        assert id1 == id2
        resp = api_client.get("/api/todo")
        assert resp.json()["items"][0]["text"] == "new"
        resp = api_client.get("/api/todo/files")
        assert len(resp.json()["files"]) == 1

    def test_start_todo_db_file(self, api_client, monkeypatch):
        """DBファイルでstart_todoがDB管理で動作する"""
        import scripts.state as st
        mock_reader = type("R", (), {"speak_event": AsyncMock()})()
        monkeypatch.setattr(st, "reader", mock_reader)
        api_client.post("/api/todo/upload", json={
            "content": "- [ ] タスクA\n- [ ] タスクB\n",
            "name": "test.md",
        })
        resp = api_client.post("/api/todo/start", json={"text": "タスクA"})
        assert resp.json()["ok"] is True
        resp = api_client.get("/api/todo")
        items = resp.json()["items"]
        in_progress = [i for i in items if i["status"] == "in_progress"]
        assert len(in_progress) == 1
        assert in_progress[0]["text"] == "タスクA"

    def test_stop_todo_db_file(self, api_client, monkeypatch):
        """DBファイルでstop_todoがDB管理で動作する"""
        import scripts.state as st
        mock_reader = type("R", (), {"speak_event": AsyncMock()})()
        monkeypatch.setattr(st, "reader", mock_reader)
        api_client.post("/api/todo/upload", json={
            "content": "- [ ] タスクA\n",
            "name": "test.md",
        })
        api_client.post("/api/todo/start", json={"text": "タスクA"})
        resp = api_client.post("/api/todo/stop", json={"text": "タスクA"})
        assert resp.json()["ok"] is True
        resp = api_client.get("/api/todo")
        items = resp.json()["items"]
        assert all(i["status"] == "todo" for i in items)


class TestCommonDefaults:
    """_COMMON_DEFAULTS と _make_item_defaults のテスト"""

    def test_common_defaults_has_all_keys(self):
        from scripts.routes.overlay import _COMMON_DEFAULTS
        expected_keys = {
            "visible", "positionX", "positionY", "width", "height", "zIndex",
            "bgColor", "bgOpacity", "borderRadius",
            "borderColor", "borderSize", "borderOpacity", "backdropBlur",
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
        visual_items = ["avatar", "subtitle", "todo", "topic"]
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



class TestOverlaySettingsAPI:
    """GET/POST /api/overlay/settings のテスト"""

    def test_get_returns_common_properties(self, api_client):
        resp = api_client.get("/api/overlay/settings")
        assert resp.status_code == 200
        data = resp.json()
        # 全ビジュアルアイテムの共通プロパティが返る
        for item in ["avatar", "subtitle", "todo", "topic"]:
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

    def test_default_values_when_no_db(self, api_client):
        """DB未保存のプロパティはデフォルト値が返る（scenes.jsonの値で上書きされることもある）"""
        resp = api_client.get("/api/overlay/settings")
        data = resp.json()
        # 共通プロパティが型としてちゃんと返る
        assert isinstance(data["avatar"]["positionX"], (int, float))
        assert isinstance(data["avatar"]["bgOpacity"], (int, float))
