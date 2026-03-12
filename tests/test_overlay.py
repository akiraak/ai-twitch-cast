"""overlay.py のテスト（TODOパース・ブロードキャスト）"""

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
