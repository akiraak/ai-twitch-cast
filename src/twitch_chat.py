"""Twitch チャット受信モジュール (twitchio v2)"""

import asyncio
import logging
import os

from twitchio import Client

logger = logging.getLogger(__name__)


class TwitchChat:
    """Twitchチャットを受信するクラス"""

    def __init__(self, token=None, channel=None):
        self.token = token or os.environ.get("TWITCH_TOKEN", "")
        self.channel = channel or os.environ.get("TWITCH_CHANNEL", "")
        self._client = None
        self._task = None

    async def start(self, on_message):
        """チャットにバックグラウンドで接続する

        Args:
            on_message: コールバック関数 async (author: str, message: str) -> None
        """
        self._client = _ChatClient(self.token, self.channel, on_message)
        self._task = asyncio.create_task(self._client.start())

    async def stop(self):
        """チャットから切断する"""
        if self._client:
            await self._client.close()
            self._client = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def send_message(self, text):
        """チャットにメッセージを送信する"""
        if not self._client:
            logger.warning("チャット未接続のためメッセージ送信をスキップ")
            return
        try:
            channel = self._client.get_channel(self.channel)
            if channel:
                await channel.send(text)
            else:
                logger.warning("チャンネル '%s' が見つかりません", self.channel)
        except Exception as e:
            logger.error("チャット送信失敗: %s", e)

    @property
    def is_running(self):
        return self._task is not None and not self._task.done()


class _ChatClient(Client):
    """twitchio.Clientのラッパー"""

    def __init__(self, token, channel, on_message):
        super().__init__(token=token, initial_channels=[channel])
        self._on_message = on_message

    async def event_ready(self):
        logger.info("Twitchに接続しました (ユーザー: %s)", self.nick)

    async def event_message(self, message):
        if message.echo:
            return
        author = (message.author.display_name or message.author.name) if message.author else "unknown"
        await self._on_message(author, message.content)
