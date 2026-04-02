"""TranscriptParser / ClaudeWatcher テスト"""

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.claude_watcher import ClaudeWatcher, TranscriptParser, TranscriptSummary


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


# ── ClaudeWatcher テスト ──────────────────────────────

import time
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_speech():
    """SpeechPipelineモック"""
    speech = MagicMock()
    speech.apply_emotion = MagicMock()
    speech.speak = AsyncMock()
    speech.notify_overlay_end = AsyncMock()
    return speech


@pytest.fixture
def mock_comment_reader():
    """CommentReaderモック（queue_sizeプロパティ付き）"""
    reader = MagicMock()
    reader.queue_size = 0
    return reader


class TestClaudeWatcherLifecycle:
    """ClaudeWatcher の起動・停止・フラグ管理"""

    @pytest.mark.asyncio
    async def test_start_creates_active_flag(self, mock_speech):
        """start()でACTIVE_FLAGが作成される"""
        watcher = ClaudeWatcher(speech=mock_speech)
        try:
            await watcher.start()
            assert os.path.exists(ClaudeWatcher.ACTIVE_FLAG)
            assert watcher._running is True
        finally:
            await watcher.stop()

    @pytest.mark.asyncio
    async def test_stop_removes_active_flag(self, mock_speech):
        """stop()でACTIVE_FLAGが削除される"""
        watcher = ClaudeWatcher(speech=mock_speech)
        await watcher.start()
        assert os.path.exists(ClaudeWatcher.ACTIVE_FLAG)
        await watcher.stop()
        assert not os.path.exists(ClaudeWatcher.ACTIVE_FLAG)
        assert watcher._running is False

    @pytest.mark.asyncio
    async def test_stop_without_start(self, mock_speech):
        """start()せずにstop()しても安全"""
        watcher = ClaudeWatcher(speech=mock_speech)
        await watcher.stop()  # エラーなし
        assert watcher._running is False

    @pytest.mark.asyncio
    async def test_double_start(self, mock_speech):
        """二重start()は無視される"""
        watcher = ClaudeWatcher(speech=mock_speech)
        try:
            await watcher.start()
            task1 = watcher._task
            await watcher.start()  # 2回目
            assert watcher._task is task1  # 同じタスク
        finally:
            await watcher.stop()

    @pytest.mark.asyncio
    async def test_stop_resets_state(self, mock_speech):
        """stop()でパーサーと状態がリセットされる"""
        watcher = ClaudeWatcher(speech=mock_speech)
        watcher._transcript_path = "/tmp/test.jsonl"
        watcher._start_time = 1000.0
        watcher._last_conversation = ["hello"]
        await watcher.stop()
        assert watcher._transcript_path is None
        assert watcher._start_time is None


class TestClaudeWatcherMarkerDetection:
    """マーカーファイル検出"""

    @pytest.mark.asyncio
    async def test_marker_file_detected(self, mock_speech, tmp_path):
        """マーカーファイルが存在すればtranscript_pathを取得する"""
        marker_file = str(tmp_path / "claude_working")
        transcript_path = str(tmp_path / "test.jsonl")
        with open(transcript_path, "w") as f:
            f.write("")

        with open(marker_file, "w") as f:
            json.dump({"start_time": 1000.0, "transcript_path": transcript_path}, f)

        watcher = ClaudeWatcher(speech=mock_speech)
        watcher.MARKER_FILE = marker_file
        watcher.POLL_INTERVAL = 0.01
        watcher.INTERVAL = 9999  # 会話生成しない

        try:
            await watcher.start()
            await asyncio.sleep(0.05)
            assert watcher._transcript_path == transcript_path
            assert watcher._start_time == 1000.0
        finally:
            await watcher.stop()

    @pytest.mark.asyncio
    async def test_marker_file_removed_resets_session(self, mock_speech, tmp_path):
        """マーカーファイルが消えるとセッションリセット"""
        marker_file = str(tmp_path / "claude_working")
        with open(marker_file, "w") as f:
            json.dump({"start_time": 1000.0, "transcript_path": "/tmp/t.jsonl"}, f)

        watcher = ClaudeWatcher(speech=mock_speech)
        watcher.MARKER_FILE = marker_file
        watcher.POLL_INTERVAL = 0.01
        watcher.INTERVAL = 9999

        try:
            await watcher.start()
            await asyncio.sleep(0.05)
            assert watcher._transcript_path is not None

            # マーカーファイルを削除
            os.remove(marker_file)
            await asyncio.sleep(0.05)
            assert watcher._transcript_path is None
        finally:
            await watcher.stop()

    @pytest.mark.asyncio
    async def test_session_change_resets_parser(self, mock_speech, tmp_path):
        """transcript_pathが変わるとパーサーがリセットされる"""
        marker_file = str(tmp_path / "claude_working")
        with open(marker_file, "w") as f:
            json.dump({"start_time": 1000.0, "transcript_path": "/tmp/a.jsonl"}, f)

        watcher = ClaudeWatcher(speech=mock_speech)
        watcher.MARKER_FILE = marker_file
        watcher.POLL_INTERVAL = 0.01
        watcher.INTERVAL = 9999
        watcher._last_conversation = ["old"]

        try:
            await watcher.start()
            await asyncio.sleep(0.05)
            assert watcher._transcript_path == "/tmp/a.jsonl"

            # パスを変更
            with open(marker_file, "w") as f:
                json.dump({"start_time": 2000.0, "transcript_path": "/tmp/b.jsonl"}, f)
            await asyncio.sleep(0.05)
            assert watcher._transcript_path == "/tmp/b.jsonl"
            assert watcher._last_conversation == []
        finally:
            await watcher.stop()


class TestClaudeWatcherCheckAndConverse:
    """_check_and_converse の動作"""

    @pytest.mark.asyncio
    async def test_no_change_skips(self, mock_speech, tmp_path):
        """transcript変化なし → 会話生成スキップ"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(path, [_user_entry("テスト")])

        watcher = ClaudeWatcher(speech=mock_speech)
        watcher._transcript_path = path
        watcher._start_time = 1000.0

        # 1回目で差分消費
        watcher._parser.parse(path)
        # 2回目は変化なし
        await watcher._check_and_converse()
        mock_speech.speak.assert_not_called()

    @pytest.mark.asyncio
    async def test_insufficient_actions_skips(self, mock_speech, tmp_path):
        """アクション数がMIN_ACTIONS未満 → スキップ"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _user_entry("テスト"),
                _assistant_tool("Read", {"file_path": "/tmp/a.py"}),
                _assistant_tool("Read", {"file_path": "/tmp/b.py"}),
            ],
        )

        watcher = ClaudeWatcher(speech=mock_speech)
        watcher._transcript_path = path
        watcher._start_time = 1000.0
        watcher.MIN_ACTIONS = 3

        await watcher._check_and_converse()
        mock_speech.speak.assert_not_called()

    @pytest.mark.asyncio
    async def test_sufficient_actions_calls_generate(self, mock_speech, tmp_path):
        """アクション数がMIN_ACTIONS以上 → _generate_conversation呼び出し"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _user_entry("テスト指示"),
                _assistant_tool("Read", {"file_path": "/tmp/a.py"}),
                _assistant_tool("Edit", {"file_path": "/tmp/b.py"}),
                _assistant_tool("Bash", {"command": "pytest"}),
            ],
        )

        watcher = ClaudeWatcher(speech=mock_speech)
        watcher._transcript_path = path
        watcher._start_time = 1000.0
        watcher.MIN_ACTIONS = 3

        # _generate_conversation をモック化（Step 3 未実装のため）
        watcher._generate_conversation = AsyncMock(return_value=None)
        await watcher._check_and_converse()

        watcher._generate_conversation.assert_called_once()
        args = watcher._generate_conversation.call_args
        summary = args[0][0]
        assert isinstance(summary, TranscriptSummary)
        assert len(summary.actions) >= 3

    @pytest.mark.asyncio
    async def test_generate_returns_dialogues_plays(self, mock_speech, tmp_path):
        """_generate_conversationが会話を返す → _play_conversation実行"""
        path = str(tmp_path / "t.jsonl")
        _write_jsonl(
            path,
            [
                _user_entry("テスト"),
                _assistant_tool("Read", {"file_path": "/tmp/a.py"}),
                _assistant_tool("Edit", {"file_path": "/tmp/b.py"}),
                _assistant_tool("Bash", {"command": "pytest"}),
            ],
        )

        watcher = ClaudeWatcher(speech=mock_speech)
        watcher._transcript_path = path
        watcher._start_time = 1000.0
        watcher.MIN_ACTIONS = 3

        fake_dialogues = [
            {"speaker": "teacher", "speech": "テスト中だよ", "emotion": "neutral"},
        ]
        watcher._generate_conversation = AsyncMock(return_value=fake_dialogues)
        watcher._play_conversation = AsyncMock()

        await watcher._check_and_converse()

        watcher._play_conversation.assert_called_once_with(fake_dialogues)
        assert watcher._last_conversation == ["テスト中だよ"]


class TestClaudeWatcherPlayConversation:
    """_play_conversation の再生・割り込みテスト"""

    @pytest.mark.asyncio
    async def test_play_all_utterances(self, mock_speech):
        """全発話が順次再生される"""
        dialogues = [
            {"speaker": "teacher", "speech": "テストを実行中だよ", "emotion": "neutral"},
            {"speaker": "student", "speech": "どんなテスト？", "emotion": "joy"},
        ]

        watcher = ClaudeWatcher(speech=mock_speech)
        with patch("src.ai_responder.get_chat_characters", return_value={
            "teacher": {"name": "ちょビ", "tts_voice": "Despina", "tts_style": "にこにこ"},
            "student": {"name": "なるこ", "tts_voice": "Kore", "tts_style": ""},
        }):
            await watcher._play_conversation(dialogues)

        assert mock_speech.speak.call_count == 2
        assert mock_speech.apply_emotion.call_count == 4  # emotion + neutral × 2
        assert mock_speech.notify_overlay_end.call_count == 2

    @pytest.mark.asyncio
    async def test_comment_interrupt_skips_remaining(self, mock_speech, mock_comment_reader):
        """コメント到着で残り発話をスキップする"""
        dialogues = [
            {"speaker": "teacher", "speech": "1番目", "emotion": "neutral"},
            {"speaker": "student", "speech": "2番目", "emotion": "joy"},
            {"speaker": "teacher", "speech": "3番目", "emotion": "neutral"},
        ]

        # 2番目の発話前にコメント到着
        call_count = 0

        def queue_size_side_effect():
            nonlocal call_count
            call_count += 1
            # 1回目(1番目の前): 0, 2回目(2番目の前): 1
            return 0 if call_count <= 1 else 1

        type(mock_comment_reader).queue_size = property(lambda self: queue_size_side_effect())

        watcher = ClaudeWatcher(speech=mock_speech, comment_reader=mock_comment_reader)
        with patch("src.ai_responder.get_chat_characters", return_value={
            "teacher": {"name": "ちょビ"},
            "student": {"name": "なるこ"},
        }):
            await watcher._play_conversation(dialogues)

        # 1番目だけ再生（2番目の前にコメント到着でスキップ）
        assert mock_speech.speak.call_count == 1

    @pytest.mark.asyncio
    async def test_play_stores_to_db(self, mock_speech):
        """発話がDB保存される"""
        dialogues = [
            {"speaker": "teacher", "speech": "テスト発話", "emotion": "joy"},
        ]

        watcher = ClaudeWatcher(speech=mock_speech)
        with patch("src.ai_responder.get_chat_characters", return_value={
            "teacher": {"name": "ちょビ"},
        }), patch.object(watcher, "_save_avatar_comment", new_callable=AsyncMock) as mock_save:
            await watcher._play_conversation(dialogues)

        mock_save.assert_called_once_with(
            "claude_work", "[Claude Code実況]", "テスト発話", "joy", speaker="teacher",
        )

    @pytest.mark.asyncio
    async def test_play_with_no_comment_reader(self, mock_speech):
        """comment_reader=Noneでも正常動作"""
        dialogues = [
            {"speaker": "teacher", "speech": "テスト", "emotion": "neutral"},
        ]

        watcher = ClaudeWatcher(speech=mock_speech, comment_reader=None)
        with patch("src.ai_responder.get_chat_characters", return_value={
            "teacher": {"name": "ちょビ"},
        }):
            await watcher._play_conversation(dialogues)

        assert mock_speech.speak.call_count == 1

    @pytest.mark.asyncio
    async def test_speak_error_breaks_loop(self, mock_speech):
        """発話エラーでループが中断される"""
        dialogues = [
            {"speaker": "teacher", "speech": "1番目", "emotion": "neutral"},
            {"speaker": "student", "speech": "2番目", "emotion": "joy"},
        ]
        mock_speech.speak.side_effect = RuntimeError("TTS error")

        watcher = ClaudeWatcher(speech=mock_speech)
        with patch("src.ai_responder.get_chat_characters", return_value={
            "teacher": {"name": "ちょビ"},
            "student": {"name": "なるこ"},
        }):
            await watcher._play_conversation(dialogues)

        # 1番目でエラー → 2番目は試行されない
        assert mock_speech.speak.call_count == 1


class TestClaudeWatcherStatus:
    """statusプロパティ"""

    def test_status_idle(self, mock_speech):
        """アイドル時のステータス"""
        watcher = ClaudeWatcher(speech=mock_speech)
        status = watcher.status
        assert status["running"] is False
        assert status["active"] is False
        assert status["transcript_path"] is None
        assert status["elapsed_seconds"] is None

    def test_status_active(self, mock_speech):
        """監視中のステータス"""
        watcher = ClaudeWatcher(speech=mock_speech)
        watcher._running = True
        watcher._transcript_path = "/tmp/test.jsonl"
        watcher._start_time = time.time() - 300
        watcher._last_conversation = ["hello", "world"]

        status = watcher.status
        assert status["running"] is True
        assert status["active"] is True
        assert status["transcript_path"] == "/tmp/test.jsonl"
        assert 298 <= status["elapsed_seconds"] <= 302
        assert status["last_conversation"] == ["hello", "world"]

    def test_is_active_requires_both(self, mock_speech):
        """is_activeはrunning AND transcript_path両方必要"""
        watcher = ClaudeWatcher(speech=mock_speech)
        assert watcher.is_active is False

        watcher._running = True
        assert watcher.is_active is False

        watcher._transcript_path = "/tmp/test.jsonl"
        assert watcher.is_active is True


# ── CommentReader統合テスト ──────────────────────────────


class TestCommentReaderIntegration:
    """CommentReaderとClaudeWatcherの統合テスト"""

    @pytest.mark.asyncio
    async def test_comment_reader_has_claude_watcher(self):
        """CommentReaderがClaudeWatcherインスタンスを持つ"""
        with patch("src.comment_reader.TwitchChat"):
            reader = __import__("src.comment_reader", fromlist=["CommentReader"]).CommentReader()
            assert hasattr(reader, "_claude_watcher")
            assert isinstance(reader._claude_watcher, ClaudeWatcher)
            assert reader.claude_watcher is reader._claude_watcher

    @pytest.mark.asyncio
    async def test_claude_watcher_receives_comment_reader_ref(self):
        """ClaudeWatcherがCommentReaderへの参照を受け取る"""
        with patch("src.comment_reader.TwitchChat"):
            reader = __import__("src.comment_reader", fromlist=["CommentReader"]).CommentReader()
            assert reader._claude_watcher._comment_reader is reader

    @pytest.mark.asyncio
    async def test_claude_watcher_receives_speech_pipeline(self):
        """ClaudeWatcherがSpeechPipelineを共有する"""
        with patch("src.comment_reader.TwitchChat"):
            reader = __import__("src.comment_reader", fromlist=["CommentReader"]).CommentReader()
            assert reader._claude_watcher._speech is reader._speech

    @pytest.mark.asyncio
    async def test_start_launches_watcher(self):
        """CommentReader.start()でClaudeWatcherが起動する"""
        with patch("src.comment_reader.TwitchChat") as mock_twitch:
            mock_twitch_instance = MagicMock()
            mock_twitch_instance.start = AsyncMock()
            mock_twitch_instance.stop = AsyncMock()
            mock_twitch.return_value = mock_twitch_instance

            reader = __import__("src.comment_reader", fromlist=["CommentReader"]).CommentReader()
            start_called = False

            async def tracked_start():
                nonlocal start_called
                start_called = True

            reader._claude_watcher.start = tracked_start
            reader._claude_watcher.stop = AsyncMock()

            with patch("src.comment_reader.get_chat_characters", return_value={"teacher": {"name": "test"}}):
                await reader.start()

            assert reader._watcher_task is not None
            await asyncio.sleep(0)
            assert start_called

            await reader.stop()

    @pytest.mark.asyncio
    async def test_stop_stops_watcher(self):
        """CommentReader.stop()でClaudeWatcherが停止する"""
        with patch("src.comment_reader.TwitchChat") as mock_twitch:
            mock_twitch_instance = MagicMock()
            mock_twitch_instance.start = AsyncMock()
            mock_twitch_instance.stop = AsyncMock()
            mock_twitch.return_value = mock_twitch_instance

            reader = __import__("src.comment_reader", fromlist=["CommentReader"]).CommentReader()
            reader._claude_watcher.start = AsyncMock()
            reader._claude_watcher.stop = AsyncMock()

            with patch("src.comment_reader.get_chat_characters", return_value={"teacher": {"name": "test"}}):
                await reader.start()
            await reader.stop()

            reader._claude_watcher.stop.assert_called_once()
            assert reader._watcher_task is None

    @pytest.mark.asyncio
    async def test_queue_size_visible_to_watcher(self):
        """ClaudeWatcherがCommentReaderのqueue_sizeを参照できる"""
        with patch("src.comment_reader.TwitchChat"):
            reader = __import__("src.comment_reader", fromlist=["CommentReader"]).CommentReader()
            assert reader._claude_watcher._comment_reader.queue_size == 0

            # キューにメッセージを追加
            reader._queue.append(("user", "hello"))
            assert reader._claude_watcher._comment_reader.queue_size == 1


# ── 会話生成テスト ──────────────────────────────


_CHARACTERS = {
    "teacher": {
        "name": "ちょビ",
        "system_prompt": "あなたは配信者のちょビです。",
        "emotions": {"neutral": "通常", "joy": "嬉しい"},
        "tts_voice": "Despina",
        "tts_style": "にこにこ",
    },
    "student": {
        "name": "なるこ",
        "system_prompt": "あなたは生徒のなるこです。",
        "emotions": {"neutral": "通常", "surprise": "驚き"},
        "tts_voice": "Kore",
        "tts_style": "",
    },
}

_VALID_LLM_RESPONSE = json.dumps([
    {"speaker": "teacher", "speech": "テストを実行してるよ", "tts_text": "テストを実行してるよ", "emotion": "neutral"},
    {"speaker": "student", "speech": "どんなテスト？", "tts_text": "どんなテスト？", "emotion": "surprise"},
    {"speaker": "teacher", "speech": "ユニットテストだよ", "tts_text": "ユニットテストだよ", "emotion": "joy"},
], ensure_ascii=False)


class TestGenerateClaudeWorkConversation:
    """generate_claude_work_conversation のテスト"""

    def _make_summary(self, **overrides):
        base = {
            "user_prompt": "テストを実行して",
            "actions": ["コマンド実行: pytest", "ファイル編集: app.py", "ファイル読み取り: test.py"],
            "assistant_texts": ["テストを実行します。"],
            "elapsed_min": 5,
        }
        base.update(overrides)
        return base

    def test_returns_validated_dialogues(self, monkeypatch):
        """LLMのJSON応答がパース・検証されて返る"""
        client = MagicMock()
        client.models.generate_content.return_value.text = _VALID_LLM_RESPONSE
        monkeypatch.setattr("src.ai_responder.get_client", lambda: client)

        from src.ai_responder import generate_claude_work_conversation
        result = generate_claude_work_conversation(
            self._make_summary(), _CHARACTERS,
        )

        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["speaker"] == "teacher"
        assert result[1]["speaker"] == "student"
        assert result[2]["speaker"] == "teacher"
        # _validate_multi_response が translation を付与
        assert "translation" in result[0]

    def test_no_student_returns_empty(self, monkeypatch):
        """生徒キャラなし → 空リスト"""
        from src.ai_responder import generate_claude_work_conversation
        result = generate_claude_work_conversation(
            self._make_summary(), {"teacher": _CHARACTERS["teacher"]},
        )
        assert result == []

    def test_invalid_json_returns_empty(self, monkeypatch):
        """LLMが不正JSONを返した場合 → 空リスト"""
        client = MagicMock()
        client.models.generate_content.return_value.text = "NOT JSON"
        monkeypatch.setattr("src.ai_responder.get_client", lambda: client)

        from src.ai_responder import generate_claude_work_conversation
        result = generate_claude_work_conversation(
            self._make_summary(), _CHARACTERS,
        )
        assert result == []

    def test_single_dict_wrapped_in_list(self, monkeypatch):
        """LLMが配列でなく辞書を返した場合 → リストに包まれる"""
        single = json.dumps(
            {"speaker": "teacher", "speech": "テスト", "tts_text": "テスト", "emotion": "neutral"},
            ensure_ascii=False,
        )
        client = MagicMock()
        client.models.generate_content.return_value.text = single
        monkeypatch.setattr("src.ai_responder.get_client", lambda: client)

        from src.ai_responder import generate_claude_work_conversation
        result = generate_claude_work_conversation(
            self._make_summary(), _CHARACTERS,
        )
        assert isinstance(result, list)
        assert len(result) == 1

    def test_max_utterances_truncation(self, monkeypatch):
        """4発話を超える応答は切り詰められる"""
        long_response = json.dumps([
            {"speaker": "teacher", "speech": f"発話{i}", "tts_text": f"発話{i}", "emotion": "neutral"}
            for i in range(6)
        ], ensure_ascii=False)
        client = MagicMock()
        client.models.generate_content.return_value.text = long_response
        monkeypatch.setattr("src.ai_responder.get_client", lambda: client)

        from src.ai_responder import generate_claude_work_conversation
        result = generate_claude_work_conversation(
            self._make_summary(), _CHARACTERS,
        )
        assert len(result) == 4

    def test_invalid_emotion_fallback_to_neutral(self, monkeypatch):
        """不正な感情は neutral にフォールバックする"""
        bad_emotion = json.dumps([
            {"speaker": "teacher", "speech": "テスト", "tts_text": "テスト", "emotion": "rage"},
        ], ensure_ascii=False)
        client = MagicMock()
        client.models.generate_content.return_value.text = bad_emotion
        monkeypatch.setattr("src.ai_responder.get_client", lambda: client)

        from src.ai_responder import generate_claude_work_conversation
        result = generate_claude_work_conversation(
            self._make_summary(), _CHARACTERS,
        )
        assert result[0]["emotion"] == "neutral"

    def test_invalid_speaker_fallback_to_teacher(self, monkeypatch):
        """不正なspeakerは teacher にフォールバックする"""
        bad_speaker = json.dumps([
            {"speaker": "unknown", "speech": "テスト", "tts_text": "テスト", "emotion": "neutral"},
        ], ensure_ascii=False)
        client = MagicMock()
        client.models.generate_content.return_value.text = bad_speaker
        monkeypatch.setattr("src.ai_responder.get_client", lambda: client)

        from src.ai_responder import generate_claude_work_conversation
        result = generate_claude_work_conversation(
            self._make_summary(), _CHARACTERS,
        )
        assert result[0]["speaker"] == "teacher"

    def test_last_conversation_passed_to_prompt(self, monkeypatch):
        """last_conversationがプロンプトに含まれる"""
        client = MagicMock()
        client.models.generate_content.return_value.text = _VALID_LLM_RESPONSE
        monkeypatch.setattr("src.ai_responder.get_client", lambda: client)

        from src.ai_responder import generate_claude_work_conversation
        generate_claude_work_conversation(
            self._make_summary(), _CHARACTERS,
            last_conversation=["前回の発話1", "前回の発話2"],
        )

        call_args = client.models.generate_content.call_args
        system = call_args.kwargs["config"].system_instruction
        assert "前回の発話1" in system

    def test_actions_in_user_content(self, monkeypatch):
        """アクション一覧がユーザープロンプトに含まれる"""
        client = MagicMock()
        client.models.generate_content.return_value.text = _VALID_LLM_RESPONSE
        monkeypatch.setattr("src.ai_responder.get_client", lambda: client)

        from src.ai_responder import generate_claude_work_conversation
        generate_claude_work_conversation(
            self._make_summary(actions=["ファイル編集: main.py"]),
            _CHARACTERS,
        )

        call_args = client.models.generate_content.call_args
        user_content = call_args.kwargs["contents"]
        assert "ファイル編集: main.py" in user_content


class TestClaudeWatcherGenerateIntegration:
    """ClaudeWatcher._generate_conversation → generate_claude_work_conversation の結合"""

    @pytest.mark.asyncio
    async def test_generate_conversation_calls_llm(self, mock_speech, tmp_path):
        """_generate_conversationがLLM経由で会話を生成する"""
        watcher = ClaudeWatcher(speech=mock_speech)

        summary = TranscriptSummary(
            user_prompt="テストして",
            actions=["コマンド実行: pytest", "ファイル編集: a.py", "ファイル読み取り: b.py"],
            assistant_texts=["テストを実行します。"],
            line_count=5,
        )

        with patch("src.ai_responder.get_chat_characters", return_value=_CHARACTERS), \
             patch("src.ai_responder.get_client") as mock_client:
            mock_client.return_value.models.generate_content.return_value.text = _VALID_LLM_RESPONSE
            result = await watcher._generate_conversation(summary, elapsed_min=5)

        assert result is not None
        assert len(result) == 3
        assert result[0]["speaker"] == "teacher"

    @pytest.mark.asyncio
    async def test_generate_conversation_no_student_returns_none(self, mock_speech):
        """生徒キャラなし → None"""
        watcher = ClaudeWatcher(speech=mock_speech)
        summary = TranscriptSummary(user_prompt="テスト", actions=["a", "b", "c"], line_count=3)

        with patch("src.ai_responder.get_chat_characters", return_value={"teacher": _CHARACTERS["teacher"]}):
            result = await watcher._generate_conversation(summary, elapsed_min=5)

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_conversation_llm_error_returns_none(self, mock_speech):
        """LLM呼び出しエラー → None"""
        watcher = ClaudeWatcher(speech=mock_speech)
        summary = TranscriptSummary(user_prompt="テスト", actions=["a", "b", "c"], line_count=3)

        with patch("src.ai_responder.get_chat_characters", return_value=_CHARACTERS), \
             patch("src.ai_responder.get_client") as mock_client:
            mock_client.return_value.models.generate_content.side_effect = RuntimeError("API error")
            result = await watcher._generate_conversation(summary, elapsed_min=5)

        assert result is None
