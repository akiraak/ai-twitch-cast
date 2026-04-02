"""TranscriptParser テスト"""

import json
import os
import tempfile

import pytest

from src.claude_watcher import TranscriptParser, TranscriptSummary


# ── ヘルパー ────────────────────────────────────────


def _write_jsonl(path: str, entries: list[dict]):
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _user_entry(content: str, is_meta: bool = False) -> dict:
    """ユーザー指示エントリ"""
    entry = {
        "type": "user",
        "message": {"role": "user", "content": content},
    }
    if is_meta:
        entry["isMeta"] = True
    return entry


def _user_tool_result() -> dict:
    """ツール結果エントリ（content=list）"""
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "123", "content": "ok"}],
        },
    }


def _assistant_text(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
    }


def _assistant_tool(name: str, tool_input: dict) -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": name, "input": tool_input}],
        },
    }


def _assistant_thinking() -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "考え中..."}],
        },
    }


def _file_history_snapshot() -> dict:
    return {"type": "file-history-snapshot", "messageId": "abc", "snapshot": {}}


def _system_entry(subtype: str = "") -> dict:
    entry: dict = {"type": "system", "content": "info", "level": "info"}
    if subtype:
        entry["subtype"] = subtype
    return entry


# ── テスト ─────────────────────────────────────────


class TestTranscriptParserBasic:
    """基本的な解析"""

    def test_normal_session(self, tmp_path):
        """通常のセッション: ユーザー指示 → ツール使用 → テキスト応答"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _file_history_snapshot(),
                _user_entry("TODOを更新して"),
                _assistant_text("TODOファイルを確認します。"),
                _assistant_tool("Read", {"file_path": "/home/ubuntu/TODO.md"}),
                _user_tool_result(),
                _assistant_tool("Edit", {"file_path": "/home/ubuntu/TODO.md"}),
                _user_tool_result(),
                _assistant_text("TODOファイルを更新しました。"),
            ],
        )

        parser = TranscriptParser()
        summary = parser.parse(path)

        assert summary is not None
        assert summary.user_prompt == "TODOを更新して"
        assert any("ファイル読み取り" in a for a in summary.actions)
        assert any("ファイル編集" in a for a in summary.actions)
        assert len(summary.assistant_texts) == 2
        assert summary.line_count == 8

    def test_multiple_user_prompts_returns_last(self, tmp_path):
        """複数のユーザー指示がある場合、最後のものを返す"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _user_entry("最初の指示"),
                _assistant_text("了解しました。"),
                _user_entry("次の指示"),
                _assistant_text("はい、次の指示を実行します。"),
            ],
        )

        parser = TranscriptParser()
        summary = parser.parse(path)

        assert summary is not None
        assert summary.user_prompt == "次の指示"

    def test_all_tool_types(self, tmp_path):
        """全ツールタイプが正しく説明に変換される"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _user_entry("テスト"),
                _assistant_tool("Bash", {"command": "python3 -m pytest tests/ -q"}),
                _assistant_tool("Edit", {"file_path": "/home/ubuntu/src/app.py"}),
                _assistant_tool("Write", {"file_path": "/home/ubuntu/src/new.py"}),
                _assistant_tool("Read", {"file_path": "/home/ubuntu/README.md"}),
                _assistant_tool("Grep", {"pattern": "def main"}),
                _assistant_tool("Glob", {"pattern": "**/*.py"}),
                _assistant_tool("Agent", {"description": "search for files"}),
                _assistant_tool("TaskCreate", {"description": "task"}),
            ],
        )

        parser = TranscriptParser()
        summary = parser.parse(path)

        assert summary is not None
        actions = summary.actions
        assert len(actions) == 8
        assert "コマンド実行: python3 -m pytest tests/ -q" in actions[0]
        assert "ファイル編集: app.py" in actions[1]
        assert "ファイル作成: new.py" in actions[2]
        assert "ファイル読み取り: README.md" in actions[3]
        assert "コード検索: def main" in actions[4]
        assert "コード検索: **/*.py" in actions[5]
        assert "サブエージェント: search for files" in actions[6]
        assert "TaskCreateを使用" in actions[7]


class TestTranscriptParserDiff:
    """差分解析（前回位置の記憶）"""

    def test_incremental_parse(self, tmp_path):
        """2回目の解析は新しい行のみ処理する"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _user_entry("最初の指示"),
                _assistant_text("最初の応答です。"),
            ],
        )

        parser = TranscriptParser()
        s1 = parser.parse(path)
        assert s1 is not None
        assert s1.user_prompt == "最初の指示"
        assert s1.line_count == 2

        # 追記
        with open(path, "a") as f:
            f.write(json.dumps(_user_entry("2番目の指示"), ensure_ascii=False) + "\n")
            f.write(
                json.dumps(
                    _assistant_tool("Bash", {"command": "ls"}), ensure_ascii=False
                )
                + "\n"
            )

        s2 = parser.parse(path)
        assert s2 is not None
        assert s2.user_prompt == "2番目の指示"
        assert len(s2.actions) == 1
        assert s2.line_count == 2

    def test_no_change_returns_none(self, tmp_path):
        """変化がなければNoneを返す"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(path, [_user_entry("テスト")])

        parser = TranscriptParser()
        parser.parse(path)

        assert parser.parse(path) is None

    def test_reset(self, tmp_path):
        """reset()で位置をリセットし、全行を再解析する"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [_user_entry("指示"), _assistant_text("これはテスト応答です。")],
        )

        parser = TranscriptParser()
        parser.parse(path)
        assert parser.parse(path) is None

        parser.reset()
        s = parser.parse(path)
        assert s is not None
        assert s.user_prompt == "指示"


class TestTranscriptParserEdgeCases:
    """エッジケース・エラー耐性"""

    def test_file_not_exists(self):
        """存在しないファイル → None"""
        parser = TranscriptParser()
        assert parser.parse("/nonexistent/path.jsonl") is None

    def test_empty_path(self):
        """空パス → None"""
        parser = TranscriptParser()
        assert parser.parse("") is None

    def test_empty_file(self, tmp_path):
        """空ファイル → None"""
        path = str(tmp_path / "t.jsonl")
        with open(path, "w"):
            pass

        parser = TranscriptParser()
        assert parser.parse(path) is None

    def test_invalid_json_lines_skipped(self, tmp_path):
        """不正なJSON行は個別にスキップされ、残りは正常に処理される"""
        path = str(tmp_path / "t.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps(_user_entry("有効な指示"), ensure_ascii=False) + "\n")
            f.write("THIS IS NOT JSON\n")
            f.write(json.dumps(_assistant_text("有効な応答テキストです。"), ensure_ascii=False) + "\n")

        parser = TranscriptParser()
        summary = parser.parse(path)

        assert summary is not None
        assert summary.user_prompt == "有効な指示"
        assert len(summary.assistant_texts) == 1

    def test_low_parse_rate_returns_none(self, tmp_path):
        """パース成功率50%未満 → None（警告あり）"""
        path = str(tmp_path / "t.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps(_user_entry("指示"), ensure_ascii=False) + "\n")
            for _ in range(5):
                f.write("BROKEN JSON LINE\n")

        parser = TranscriptParser()
        summary = parser.parse(path)
        # 1/6 ≈ 16.7% < 50%
        assert summary is None

    def test_unknown_type_skipped(self, tmp_path):
        """未知のtypeはスキップされる"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                {"type": "unknown_new_type", "data": "something"},
                _user_entry("指示テスト"),
                {"type": "another_unknown", "data": "x"},
            ],
        )

        parser = TranscriptParser()
        summary = parser.parse(path)
        assert summary is not None
        assert summary.user_prompt == "指示テスト"

    def test_is_meta_skipped(self, tmp_path):
        """isMeta=trueのuserエントリはスキップ"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _user_entry("system caveat text", is_meta=True),
                _user_entry("実際の指示"),
            ],
        )

        parser = TranscriptParser()
        summary = parser.parse(path)
        assert summary is not None
        assert summary.user_prompt == "実際の指示"

    def test_command_entries_skipped(self, tmp_path):
        """<command-name>で始まるuserエントリはスキップ"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _user_entry("<command-name>/clear</command-name>"),
                _user_entry("本当の指示"),
            ],
        )

        parser = TranscriptParser()
        summary = parser.parse(path)
        assert summary is not None
        assert summary.user_prompt == "本当の指示"

    def test_tool_result_entries_skipped(self, tmp_path):
        """content=list形式のuserエントリ（tool_result）はユーザー指示として扱わない"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _user_entry("指示テスト"),
                _user_tool_result(),
                _assistant_text("これはテスト応答です。"),
            ],
        )

        parser = TranscriptParser()
        summary = parser.parse(path)
        assert summary is not None
        assert summary.user_prompt == "指示テスト"

    def test_thinking_entries_no_text(self, tmp_path):
        """thinkingエントリはassistant_textsに含まれない"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _user_entry("テスト"),
                _assistant_thinking(),
                _assistant_text("実際の応答テキストです。"),
            ],
        )

        parser = TranscriptParser()
        summary = parser.parse(path)
        assert summary is not None
        assert len(summary.assistant_texts) == 1
        assert "実際の応答テキスト" in summary.assistant_texts[0]

    def test_short_text_filtered(self, tmp_path):
        """10文字以下のassistantテキストは除外"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _user_entry("テスト"),
                _assistant_text("OK"),  # 10文字以下 → 除外
                _assistant_text("これは十分に長いテキストです。"),
            ],
        )

        parser = TranscriptParser()
        summary = parser.parse(path)
        assert summary is not None
        assert len(summary.assistant_texts) == 1

    def test_file_history_and_system_ignored(self, tmp_path):
        """file-history-snapshotとsystemはスキップされる"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _file_history_snapshot(),
                _system_entry("stop_hook_summary"),
                _system_entry("turn_duration"),
                _user_entry("唯一の指示"),
            ],
        )

        parser = TranscriptParser()
        summary = parser.parse(path)
        assert summary is not None
        assert summary.user_prompt == "唯一の指示"
        assert len(summary.actions) == 0

    def test_only_system_entries_returns_none(self, tmp_path):
        """system/file-history-snapshotのみ → 意味のある内容なし → None"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _file_history_snapshot(),
                _system_entry("stop_hook_summary"),
            ],
        )

        parser = TranscriptParser()
        assert parser.parse(path) is None
