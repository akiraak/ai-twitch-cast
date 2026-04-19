"""src/twitch_chat.py のテスト

対象:
- TwitchChat.__init__（env / 明示引数）
- TwitchChat.start / stop / is_running
- TwitchChat.send_message（未接続・成功・チャンネル未発見・例外握りつぶし）
- _ChatClient.event_message（echo無視・author存在/不在の分岐）
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import twitch_chat as tc_mod
from src.twitch_chat import TwitchChat, _ChatClient


# =====================================================
# __init__
# =====================================================


class TestInit:
    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv("TWITCH_TOKEN", "envtok")
        monkeypatch.setenv("TWITCH_CHANNEL", "envchan")
        chat = TwitchChat()
        assert chat.token == "envtok"
        assert chat.channel == "envchan"
        assert chat._client is None
        assert chat._task is None

    def test_explicit_args_win(self, monkeypatch):
        monkeypatch.setenv("TWITCH_TOKEN", "envtok")
        monkeypatch.setenv("TWITCH_CHANNEL", "envchan")
        chat = TwitchChat(token="explicit", channel="expchan")
        assert chat.token == "explicit"
        assert chat.channel == "expchan"


# =====================================================
# start
# =====================================================


class TestStart:
    async def test_creates_client_and_task(self):
        fake_client = MagicMock()
        fake_client.start = AsyncMock()
        fake_client.close = AsyncMock()

        async def cb(a, m):  # pragma: no cover - passed through
            pass

        with patch.object(tc_mod, "_ChatClient", return_value=fake_client) as ctor:
            chat = TwitchChat(token="t", channel="chan")
            await chat.start(cb)

            ctor.assert_called_once_with("t", "chan", cb)
            assert chat._client is fake_client
            assert chat._task is not None
            # task 内で client.start が呼ばれる
            await asyncio.sleep(0)  # task に実行機会を与える
            fake_client.start.assert_awaited_once()

            # クリーンアップ
            await chat.stop()


# =====================================================
# stop
# =====================================================


class TestStop:
    async def test_stops_running_client(self):
        fake_client = MagicMock()
        fake_client.close = AsyncMock()

        async def _long():
            await asyncio.sleep(10)

        task = asyncio.create_task(_long())

        chat = TwitchChat(token="t", channel="c")
        chat._client = fake_client
        chat._task = task

        await chat.stop()

        fake_client.close.assert_awaited_once()
        assert chat._client is None
        assert chat._task is None
        assert task.cancelled() or task.done()

    async def test_stop_swallows_task_exception(self):
        fake_client = MagicMock()
        fake_client.close = AsyncMock()

        async def _bad():
            raise RuntimeError("boom")

        task = asyncio.create_task(_bad())
        await asyncio.sleep(0)  # 例外が task に溜まる

        chat = TwitchChat(token="t", channel="c")
        chat._client = fake_client
        chat._task = task

        # 例外は握りつぶされる（再スローしない）
        await chat.stop()
        assert chat._task is None

    async def test_stop_noop_when_not_started(self):
        chat = TwitchChat(token="t", channel="c")
        # _client も _task も None のまま stop() を呼んでも落ちない
        await chat.stop()
        assert chat._client is None
        assert chat._task is None


# =====================================================
# send_message
# =====================================================


class TestSendMessage:
    async def test_skip_when_not_connected(self, caplog):
        chat = TwitchChat(token="t", channel="c")
        # _client は None のまま
        with caplog.at_level("WARNING"):
            await chat.send_message("hi")
        assert any("チャット未接続" in r.message for r in caplog.records)

    async def test_sends_to_channel(self):
        channel = MagicMock()
        channel.send = AsyncMock()
        fake_client = MagicMock()
        fake_client.get_channel = MagicMock(return_value=channel)

        chat = TwitchChat(token="t", channel="mychan")
        chat._client = fake_client

        await chat.send_message("hello")

        fake_client.get_channel.assert_called_once_with("mychan")
        channel.send.assert_awaited_once_with("hello")

    async def test_warns_when_channel_missing(self, caplog):
        fake_client = MagicMock()
        fake_client.get_channel = MagicMock(return_value=None)
        fake_client.connected_channels = []

        chat = TwitchChat(token="t", channel="ghost")
        chat._client = fake_client

        with caplog.at_level("WARNING"):
            await chat.send_message("hi")
        assert any("見つかりません" in r.message for r in caplog.records)

    async def test_exception_is_swallowed(self, caplog):
        channel = MagicMock()
        channel.send = AsyncMock(side_effect=RuntimeError("ws closed"))
        fake_client = MagicMock()
        fake_client.get_channel = MagicMock(return_value=channel)

        chat = TwitchChat(token="t", channel="c")
        chat._client = fake_client

        with caplog.at_level("ERROR"):
            # 例外は send_message 内で握りつぶされて再スローされない
            await chat.send_message("hi")
        assert any("チャット送信失敗" in r.message for r in caplog.records)


# =====================================================
# is_running
# =====================================================


class TestIsRunning:
    async def test_false_when_task_none(self):
        chat = TwitchChat(token="t", channel="c")
        assert chat.is_running is False

    async def test_true_while_task_pending(self):
        chat = TwitchChat(token="t", channel="c")

        async def _sleep():
            await asyncio.sleep(10)

        chat._task = asyncio.create_task(_sleep())
        try:
            assert chat.is_running is True
        finally:
            chat._task.cancel()
            try:
                await chat._task
            except asyncio.CancelledError:
                pass

    async def test_false_after_task_done(self):
        chat = TwitchChat(token="t", channel="c")

        async def _noop():
            return None

        chat._task = asyncio.create_task(_noop())
        await chat._task  # 完了させる
        assert chat.is_running is False


# =====================================================
# _ChatClient.event_message
# =====================================================


class TestChatClientEventMessage:
    async def test_echo_is_ignored(self):
        received = []

        async def cb(author, content):
            received.append((author, content))

        client = _ChatClient("t", "chan", cb)
        msg = MagicMock()
        msg.echo = True
        await client.event_message(msg)
        assert received == []

    async def test_prefers_display_name(self):
        received = []

        async def cb(author, content):
            received.append((author, content))

        client = _ChatClient("t", "chan", cb)
        author = MagicMock()
        author.display_name = "Alice"
        author.name = "alice"
        msg = MagicMock()
        msg.echo = False
        msg.author = author
        msg.content = "hello"
        await client.event_message(msg)
        assert received == [("Alice", "hello")]

    async def test_falls_back_to_name_when_display_empty(self):
        received = []

        async def cb(author, content):
            received.append((author, content))

        client = _ChatClient("t", "chan", cb)
        author = MagicMock()
        author.display_name = ""  # 空
        author.name = "alice"
        msg = MagicMock()
        msg.echo = False
        msg.author = author
        msg.content = "hi"
        await client.event_message(msg)
        assert received == [("alice", "hi")]

    async def test_unknown_when_author_is_none(self):
        received = []

        async def cb(author, content):
            received.append((author, content))

        client = _ChatClient("t", "chan", cb)
        msg = MagicMock()
        msg.echo = False
        msg.author = None
        msg.content = "anonymous"
        await client.event_message(msg)
        assert received == [("unknown", "anonymous")]

    async def test_event_ready_logs_without_error(self, caplog):
        async def cb(a, m):  # pragma: no cover
            pass

        client = _ChatClient("t", "chan", cb)
        # nick 属性を差し替えて実行
        with patch.object(_ChatClient, "nick", new="mybot", create=True):
            with caplog.at_level("INFO"):
                await client.event_ready()
        assert any("mybot" in r.message or "Twitchに接続" in r.message for r in caplog.records)
