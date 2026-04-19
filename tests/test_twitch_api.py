"""src/twitch_api.py のテスト

対象:
- TwitchAPI._headers
- TwitchAPI.get_broadcaster_id（成功・キャッシュ・チャンネル未発見）
- TwitchAPI.get_channel_info（データ有無）
- TwitchAPI.update_channel_info（部分フィールド・空body短絡）
- TwitchAPI.search_categories（box_art_url 整形）
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.twitch_api import HELIX_BASE, TwitchAPI


# =====================================================
# aiohttp.ClientSession を差し替えるユーティリティ
# =====================================================


def _make_session(*, get_json=None, get_error=None, patch_error=None):
    """aiohttp.ClientSession() が返す async context manager を組み立てる。

    - get_json: session.get の `await resp.json()` が返す値
    - get_error: `resp.raise_for_status()` が投げる例外
    - patch_error: session.patch の `resp.raise_for_status()` が投げる例外
    """
    resp = MagicMock()
    resp.raise_for_status = MagicMock(side_effect=get_error)
    resp.json = AsyncMock(return_value=get_json)

    patch_resp = MagicMock()
    patch_resp.raise_for_status = MagicMock(side_effect=patch_error)

    get_ctx = MagicMock()
    get_ctx.__aenter__ = AsyncMock(return_value=resp)
    get_ctx.__aexit__ = AsyncMock(return_value=False)

    patch_ctx = MagicMock()
    patch_ctx.__aenter__ = AsyncMock(return_value=patch_resp)
    patch_ctx.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get = MagicMock(return_value=get_ctx)
    session.patch = MagicMock(return_value=patch_ctx)

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    class_mock = MagicMock(return_value=session_ctx)
    return class_mock, session, resp, patch_resp


# =====================================================
# _headers
# =====================================================


class TestHeaders:
    def test_strip_oauth_prefix(self):
        api = TwitchAPI(token="oauth:abcdef", client_id="cid")
        h = api._headers()
        assert h == {"Authorization": "Bearer abcdef", "Client-Id": "cid"}

    def test_no_prefix(self):
        api = TwitchAPI(token="plain-token", client_id="cid")
        h = api._headers()
        assert h["Authorization"] == "Bearer plain-token"

    def test_reads_env_when_unset(self, monkeypatch):
        monkeypatch.setenv("TWITCH_TOKEN", "oauth:envtok")
        monkeypatch.setenv("TWITCH_CLIENT_ID", "envcid")
        api = TwitchAPI()
        h = api._headers()
        assert h == {"Authorization": "Bearer envtok", "Client-Id": "envcid"}


# =====================================================
# get_broadcaster_id
# =====================================================


class TestGetBroadcasterId:
    async def test_success(self, monkeypatch):
        monkeypatch.setenv("TWITCH_CHANNEL", "mychannel")
        class_mock, session, _, _ = _make_session(
            get_json={"data": [{"id": "12345", "login": "mychannel"}]}
        )
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            bid = await api.get_broadcaster_id()
        assert bid == "12345"
        session.get.assert_called_once_with(
            f"{HELIX_BASE}/users",
            headers={"Authorization": "Bearer t", "Client-Id": "c"},
            params={"login": "mychannel"},
        )

    async def test_cached(self, monkeypatch):
        monkeypatch.setenv("TWITCH_CHANNEL", "mychannel")
        class_mock, session, _, _ = _make_session(
            get_json={"data": [{"id": "99"}]}
        )
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            first = await api.get_broadcaster_id()
            second = await api.get_broadcaster_id()
        assert first == "99"
        assert second == "99"
        # 2回目はキャッシュが効きHTTP呼び出しは発生しない
        assert session.get.call_count == 1

    async def test_channel_not_found(self, monkeypatch):
        monkeypatch.setenv("TWITCH_CHANNEL", "ghost")
        class_mock, _, _, _ = _make_session(get_json={"data": []})
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            with pytest.raises(ValueError, match="ghost"):
                await api.get_broadcaster_id()

    async def test_http_error_propagates(self, monkeypatch):
        monkeypatch.setenv("TWITCH_CHANNEL", "mychannel")
        class_mock, _, _, _ = _make_session(get_error=RuntimeError("401"))
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            with pytest.raises(RuntimeError, match="401"):
                await api.get_broadcaster_id()


# =====================================================
# get_channel_info
# =====================================================


class TestGetChannelInfo:
    async def test_success(self):
        class_mock, session, _, _ = _make_session(
            get_json={
                "data": [{
                    "title": "テスト配信",
                    "game_id": "509658",
                    "game_name": "Just Chatting",
                    "tags": ["JP", "VTuber"],
                }]
            }
        )
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            api._broadcaster_id = "42"  # get_broadcaster_id をバイパス
            info = await api.get_channel_info()
        assert info == {
            "title": "テスト配信",
            "game_id": "509658",
            "game_name": "Just Chatting",
            "tags": ["JP", "VTuber"],
        }
        session.get.assert_called_once_with(
            f"{HELIX_BASE}/channels",
            headers={"Authorization": "Bearer t", "Client-Id": "c"},
            params={"broadcaster_id": "42"},
        )

    async def test_empty_data_returns_empty_dict(self):
        class_mock, _, _, _ = _make_session(get_json={"data": []})
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            api._broadcaster_id = "42"
            info = await api.get_channel_info()
        assert info == {}

    async def test_missing_fields_default_to_empty(self):
        class_mock, _, _, _ = _make_session(
            get_json={"data": [{}]}  # 全フィールド欠落
        )
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            api._broadcaster_id = "42"
            info = await api.get_channel_info()
        assert info == {"title": "", "game_id": "", "game_name": "", "tags": []}


# =====================================================
# update_channel_info
# =====================================================


class TestUpdateChannelInfo:
    async def test_partial_title_only(self):
        class_mock, session, _, _ = _make_session()
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            api._broadcaster_id = "42"
            await api.update_channel_info(title="新しいタイトル")
        session.patch.assert_called_once_with(
            f"{HELIX_BASE}/channels",
            headers={"Authorization": "Bearer t", "Client-Id": "c"},
            params={"broadcaster_id": "42"},
            json={"title": "新しいタイトル"},
        )

    async def test_all_fields(self):
        class_mock, session, _, _ = _make_session()
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            api._broadcaster_id = "42"
            await api.update_channel_info(
                title="X", game_id="509658", tags=["A", "B"]
            )
        kwargs = session.patch.call_args.kwargs
        assert kwargs["json"] == {
            "title": "X",
            "game_id": "509658",
            "tags": ["A", "B"],
        }

    async def test_empty_body_skips_patch(self):
        class_mock, session, _, _ = _make_session()
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            api._broadcaster_id = "42"
            await api.update_channel_info()
        session.patch.assert_not_called()

    async def test_error_propagates(self):
        class_mock, _, _, _ = _make_session(patch_error=RuntimeError("400"))
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            api._broadcaster_id = "42"
            with pytest.raises(RuntimeError, match="400"):
                await api.update_channel_info(title="X")

    async def test_none_fields_skipped(self):
        class_mock, session, _, _ = _make_session()
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            api._broadcaster_id = "42"
            await api.update_channel_info(title=None, game_id="g1", tags=None)
        kwargs = session.patch.call_args.kwargs
        assert kwargs["json"] == {"game_id": "g1"}


# =====================================================
# search_categories
# =====================================================


class TestSearchCategories:
    async def test_normalized_output(self):
        class_mock, session, _, _ = _make_session(
            get_json={
                "data": [
                    {"id": "1", "name": "Just Chatting", "box_art_url": "http://x"},
                    {"id": "2", "name": "Art"},  # box_art_url 欠落
                ]
            }
        )
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            result = await api.search_categories("just")
        assert result == [
            {"id": "1", "name": "Just Chatting", "box_art_url": "http://x"},
            {"id": "2", "name": "Art", "box_art_url": ""},
        ]
        session.get.assert_called_once_with(
            f"{HELIX_BASE}/search/categories",
            headers={"Authorization": "Bearer t", "Client-Id": "c"},
            params={"query": "just", "first": 10},
        )

    async def test_empty_data(self):
        class_mock, _, _, _ = _make_session(get_json={"data": []})
        with patch("src.twitch_api.aiohttp.ClientSession", class_mock):
            api = TwitchAPI(token="t", client_id="c")
            result = await api.search_categories("nothing")
        assert result == []
