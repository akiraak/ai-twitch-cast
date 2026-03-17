"""capture_client のテスト（URL生成・マッピング・WS通信・プロキシ）"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.services.capture_client import (
    CAPTURE_PORT,
    PATH_TO_ACTION,
    capture_base_url,
    capture_ws_url,
)


# =====================================================
# URL生成
# =====================================================


class TestCaptureUrls:
    """URL生成のテスト"""

    @patch("scripts.services.capture_client.get_windows_host_ip", return_value="172.28.16.1")
    def test_capture_base_url(self, _):
        assert capture_base_url() == "http://172.28.16.1:9090"

    @patch("scripts.services.capture_client.get_windows_host_ip", return_value="172.28.16.1")
    def test_capture_ws_url(self, _):
        assert capture_ws_url() == "ws://172.28.16.1:9090/ws/control"

    @patch("scripts.services.capture_client.get_windows_host_ip", side_effect=Exception("not WSL"))
    def test_fallback_to_localhost(self, _):
        assert capture_base_url() == "http://localhost:9090"
        assert capture_ws_url() == "ws://localhost:9090/ws/control"

    def test_port_constant(self):
        assert CAPTURE_PORT == 9090

    @patch("scripts.services.capture_client.get_windows_host_ip", return_value="10.0.0.1")
    def test_different_host_ip(self, _):
        assert capture_base_url() == "http://10.0.0.1:9090"
        assert capture_ws_url() == "ws://10.0.0.1:9090/ws/control"


# =====================================================
# PATH_TO_ACTION マッピング
# =====================================================


class TestPathToAction:
    """HTTP path→WebSocketアクションのマッピングテスト"""

    def test_status_mapping(self):
        action, _ = PATH_TO_ACTION[("GET", "/status")]
        assert action == "status"

    def test_windows_mapping(self):
        action, _ = PATH_TO_ACTION[("GET", "/windows")]
        assert action == "windows"

    def test_captures_mapping(self):
        action, _ = PATH_TO_ACTION[("GET", "/captures")]
        assert action == "captures"

    def test_preview_status_mapping(self):
        action, _ = PATH_TO_ACTION[("GET", "/preview/status")]
        assert action == "preview_status"

    def test_preview_close_mapping(self):
        action, _ = PATH_TO_ACTION[("POST", "/preview/close")]
        assert action == "preview_close"

    def test_quit_mapping(self):
        action, _ = PATH_TO_ACTION[("POST", "/quit")]
        assert action == "quit"

    def test_stream_stop_mapping(self):
        action, _ = PATH_TO_ACTION[("POST", "/stream/stop")]
        assert action == "stop_stream"

    def test_stream_status_mapping(self):
        action, _ = PATH_TO_ACTION[("GET", "/stream/status")]
        assert action == "stream_status"

    def test_broadcast_close_mapping(self):
        action, _ = PATH_TO_ACTION[("POST", "/broadcast/close")]
        assert action == "broadcast_close"

    def test_broadcast_status_mapping(self):
        action, _ = PATH_TO_ACTION[("GET", "/broadcast/status")]
        assert action == "broadcast_status"

    def test_all_actions_are_strings(self):
        for key, (action, _) in PATH_TO_ACTION.items():
            assert isinstance(action, str)
            assert len(action) > 0

    def test_all_keys_are_method_path_tuples(self):
        valid_methods = {"GET", "POST", "DELETE", "PUT", "PATCH"}
        for method, path in PATH_TO_ACTION:
            assert method in valid_methods
            assert path.startswith("/")

    def test_unmapped_path_not_in_dict(self):
        assert ("GET", "/nonexistent") not in PATH_TO_ACTION


# =====================================================
# ws_request
# =====================================================


class TestWsRequest:
    """WebSocketリクエスト送受信のテスト"""

    @pytest.mark.asyncio
    async def test_ws_request_sends_and_receives(self):
        """ws_request が正しいJSONを送信し、レスポンスを返すこと"""
        import scripts.services.capture_client as cc

        mock_ws = AsyncMock()
        # send時にレスポンスを_pending_requestsにセットする
        async def fake_send(msg):
            data = json.loads(msg)
            rid = data["requestId"]
            if rid in cc._pending_requests:
                cc._pending_requests[rid].set_result({"requestId": rid, "data": {"ok": True}})

        mock_ws.send = fake_send
        mock_ws.ping = AsyncMock()

        # ensure_capture_ws をモックして既存接続を返す
        original_ws = cc._capture_ws
        original_pending = cc._pending_requests.copy()
        try:
            cc._capture_ws = mock_ws
            result = await cc.ws_request("test_action", timeout=2.0, key="value")
            assert result == {"ok": True}
        finally:
            cc._capture_ws = original_ws
            cc._pending_requests.clear()
            cc._pending_requests.update(original_pending)

    @pytest.mark.asyncio
    async def test_ws_request_timeout(self):
        """ws_request がタイムアウトすること"""
        import scripts.services.capture_client as cc

        mock_ws = AsyncMock()
        # sendしてもレスポンスを返さない（タイムアウトさせる）
        mock_ws.send = AsyncMock()
        mock_ws.ping = AsyncMock()

        original_ws = cc._capture_ws
        try:
            cc._capture_ws = mock_ws
            with pytest.raises(asyncio.TimeoutError):
                await cc.ws_request("slow_action", timeout=0.1)
        finally:
            cc._capture_ws = original_ws
            cc._pending_requests.clear()

    @pytest.mark.asyncio
    async def test_ws_request_cleans_up_pending(self):
        """ws_request が完了後に_pending_requestsをクリーンアップすること"""
        import scripts.services.capture_client as cc

        mock_ws = AsyncMock()
        async def fake_send(msg):
            data = json.loads(msg)
            rid = data["requestId"]
            if rid in cc._pending_requests:
                cc._pending_requests[rid].set_result({"requestId": rid, "data": {}})

        mock_ws.send = fake_send
        mock_ws.ping = AsyncMock()

        original_ws = cc._capture_ws
        try:
            cc._capture_ws = mock_ws
            await cc.ws_request("test", timeout=2.0)
            assert len(cc._pending_requests) == 0
        finally:
            cc._capture_ws = original_ws
            cc._pending_requests.clear()

    @pytest.mark.asyncio
    async def test_ws_request_includes_action_and_params(self):
        """ws_request が action と params を含むJSONを送信すること"""
        import scripts.services.capture_client as cc

        mock_ws = AsyncMock()
        sent_messages = []

        async def capture_send(msg):
            data = json.loads(msg)
            sent_messages.append(data)
            rid = data["requestId"]
            if rid in cc._pending_requests:
                cc._pending_requests[rid].set_result({"requestId": rid, "data": {}})

        mock_ws.send = capture_send
        mock_ws.ping = AsyncMock()

        original_ws = cc._capture_ws
        try:
            cc._capture_ws = mock_ws
            await cc.ws_request("start_stream", timeout=2.0, streamKey="abc", serverUrl="http://x")
            assert len(sent_messages) == 1
            msg = sent_messages[0]
            assert msg["action"] == "start_stream"
            assert msg["streamKey"] == "abc"
            assert msg["serverUrl"] == "http://x"
            assert "requestId" in msg
        finally:
            cc._capture_ws = original_ws
            cc._pending_requests.clear()


# =====================================================
# proxy_request
# =====================================================


class TestProxyRequest:
    """proxy_request のルーティングテスト"""

    @pytest.mark.asyncio
    async def test_mapped_path_uses_ws(self):
        """PATH_TO_ACTIONに存在するパスはws_requestを使うこと"""
        import scripts.services.capture_client as cc

        with patch.object(cc, "ws_request", new_callable=AsyncMock, return_value={"ok": True}) as mock:
            result = await cc.proxy_request("GET", "/status")
            mock.assert_called_once_with("status")
            assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_post_capture_uses_start_capture_action(self):
        """POST /capture は start_capture アクションを使うこと"""
        import scripts.services.capture_client as cc

        with patch.object(cc, "ws_request", new_callable=AsyncMock, return_value={"ok": True}) as mock:
            await cc.proxy_request("POST", "/capture", {"sourceId": "abc"})
            mock.assert_called_once_with("start_capture", sourceId="abc")

    @pytest.mark.asyncio
    async def test_delete_capture_uses_stop_capture_action(self):
        """DELETE /capture/{id} は stop_capture アクションを使うこと"""
        import scripts.services.capture_client as cc

        with patch.object(cc, "ws_request", new_callable=AsyncMock, return_value={"ok": True}) as mock:
            await cc.proxy_request("DELETE", "/capture/cap-123")
            mock.assert_called_once_with("stop_capture", id="cap-123")

    @pytest.mark.asyncio
    async def test_post_preview_open_uses_ws(self):
        """POST /preview/open は preview_open アクションを使うこと"""
        import scripts.services.capture_client as cc

        with patch.object(cc, "ws_request", new_callable=AsyncMock, return_value={"ok": True}) as mock:
            await cc.proxy_request("POST", "/preview/open", {"url": "http://x"})
            mock.assert_called_once_with("preview_open", url="http://x")

    @pytest.mark.asyncio
    async def test_http_fallback_on_ws_failure(self):
        """WebSocket失敗時にHTTPフォールバックすること"""
        import scripts.services.capture_client as cc

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(cc, "ws_request", new_callable=AsyncMock, side_effect=ConnectionError("ws down")), \
             patch("scripts.services.capture_client.capture_base_url", return_value="http://localhost:9090"), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await cc.proxy_request("GET", "/status")
            mock_client.get.assert_called_once_with("http://localhost:9090/status")
            assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_http_fallback_post(self):
        """HTTPフォールバックでPOSTが正しく送信されること"""
        import scripts.services.capture_client as cc

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(cc, "ws_request", new_callable=AsyncMock, side_effect=ConnectionError("ws down")), \
             patch("scripts.services.capture_client.capture_base_url", return_value="http://localhost:9090"), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await cc.proxy_request("POST", "/capture", {"sourceId": "x"})
            mock_client.post.assert_called_once_with("http://localhost:9090/capture", json={"sourceId": "x"})

    @pytest.mark.asyncio
    async def test_http_fallback_delete(self):
        """HTTPフォールバックでDELETEが正しく送信されること"""
        import scripts.services.capture_client as cc

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}

        mock_client = AsyncMock()
        mock_client.delete = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(cc, "ws_request", new_callable=AsyncMock, side_effect=ConnectionError("ws down")), \
             patch("scripts.services.capture_client.capture_base_url", return_value="http://localhost:9090"), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await cc.proxy_request("DELETE", "/capture/cap-1")
            mock_client.delete.assert_called_once_with("http://localhost:9090/capture/cap-1")

    @pytest.mark.asyncio
    async def test_invalid_method_raises(self):
        """未知のHTTPメソッドでValueErrorが発生すること"""
        import scripts.services.capture_client as cc

        mock_response = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(cc, "ws_request", new_callable=AsyncMock, side_effect=ConnectionError("ws down")), \
             patch("scripts.services.capture_client.capture_base_url", return_value="http://localhost:9090"), \
             patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="Unknown method: PATCH"):
                await cc.proxy_request("PATCH", "/status")


# =====================================================
# capture.py が capture_client を使っているか
# =====================================================


class TestCaptureRouteImports:
    """capture.py が capture_client の関数を正しく参照していること"""

    def test_capture_route_uses_capture_client(self):
        """capture.py に旧関数（_ws_request等）が残っていないこと"""
        import inspect
        import scripts.routes.capture as cap

        source = inspect.getsource(cap)
        # 旧プライベート関数が残っていないこと
        assert "_ws_request(" not in source, "capture.py に旧 _ws_request が残っている"
        assert "_proxy_request(" not in source, "capture.py に旧 _proxy_request が残っている"
        assert "_capture_base_url(" not in source, "capture.py に旧 _capture_base_url が残っている"
        assert "_capture_ws_url(" not in source, "capture.py に旧 _capture_ws_url が残っている"

    def test_stream_control_uses_capture_client(self):
        """stream_control.py に旧関数参照が残っていないこと"""
        import inspect
        import scripts.routes.stream_control as sc

        source = inspect.getsource(sc)
        assert "from scripts.routes.capture import" not in source, \
            "stream_control.py に capture.py への直接インポートが残っている"

    def test_comment_reader_no_layer_violation(self):
        """comment_reader.py が scripts/routes/ を直接インポートしていないこと（レイヤー違反解消確認）"""
        import inspect
        import src.comment_reader as cr

        source = inspect.getsource(cr)
        assert "from scripts.routes.capture import" not in source, \
            "comment_reader.py に capture.py への直接インポートが残っている（レイヤー違反）"

    def test_state_uses_capture_client(self):
        """state.py が capture_client を使っていること"""
        import inspect
        import scripts.state as st

        source = inspect.getsource(st)
        assert "from scripts.routes.capture import" not in source, \
            "state.py に capture.py への直接インポートが残っている"
