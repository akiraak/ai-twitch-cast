"""Twitch Helix API制御モジュール（配信情報の取得・更新）"""

import logging
import os

import aiohttp

logger = logging.getLogger(__name__)

HELIX_BASE = "https://api.twitch.tv/helix"


class TwitchAPI:
    """Twitch Helix APIを通じて配信情報を管理するクラス"""

    def __init__(self, token=None, client_id=None):
        self.token = token or os.environ.get("TWITCH_TOKEN", "")
        self.client_id = client_id or os.environ.get("TWITCH_CLIENT_ID", "")
        self._broadcaster_id = None

    def _headers(self):
        token = self.token.removeprefix("oauth:")
        return {
            "Authorization": f"Bearer {token}",
            "Client-Id": self.client_id,
        }

    async def _get(self, path, params=None):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{HELIX_BASE}{path}", headers=self._headers(), params=params
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _patch(self, path, params=None, json=None):
        async with aiohttp.ClientSession() as session:
            async with session.patch(
                f"{HELIX_BASE}{path}", headers=self._headers(), params=params, json=json
            ) as resp:
                resp.raise_for_status()

    async def get_broadcaster_id(self):
        """ブロードキャスターIDを取得する（キャッシュ付き）"""
        if self._broadcaster_id:
            return self._broadcaster_id
        channel = os.environ.get("TWITCH_CHANNEL", "")
        data = await self._get("/users", params={"login": channel})
        users = data.get("data", [])
        if not users:
            raise ValueError(f"チャンネル '{channel}' が見つかりません")
        self._broadcaster_id = users[0]["id"]
        logger.info("Broadcaster ID: %s", self._broadcaster_id)
        return self._broadcaster_id

    async def get_channel_info(self):
        """チャンネル情報を取得する（タイトル・カテゴリ・タグ）"""
        bid = await self.get_broadcaster_id()
        data = await self._get("/channels", params={"broadcaster_id": bid})
        channels = data.get("data", [])
        if not channels:
            return {}
        ch = channels[0]
        return {
            "title": ch.get("title", ""),
            "game_id": ch.get("game_id", ""),
            "game_name": ch.get("game_name", ""),
            "tags": ch.get("tags", []),
        }

    async def update_channel_info(self, title=None, game_id=None, tags=None):
        """チャンネル情報を更新する"""
        bid = await self.get_broadcaster_id()
        body = {}
        if title is not None:
            body["title"] = title
        if game_id is not None:
            body["game_id"] = game_id
        if tags is not None:
            body["tags"] = tags
        if not body:
            return
        await self._patch("/channels", params={"broadcaster_id": bid}, json=body)
        logger.info("チャンネル情報を更新しました: %s", body)

    async def search_categories(self, query):
        """カテゴリ（ゲーム）を検索する"""
        data = await self._get("/search/categories", params={"query": query, "first": 10})
        return [
            {"id": c["id"], "name": c["name"], "box_art_url": c.get("box_art_url", "")}
            for c in data.get("data", [])
        ]
