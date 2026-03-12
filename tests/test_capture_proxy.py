"""capture.py のプロキシ（WebSocket/HTTPフォールバック）テスト"""

from unittest.mock import patch

from scripts.routes.capture import (
    _PATH_TO_ACTION,
    _capture_base_url,
    _capture_ws_url,
)


class TestCaptureUrls:
    """URL生成のテスト"""

    @patch("scripts.routes.capture.get_windows_host_ip", return_value="172.28.16.1")
    def test_capture_base_url(self, _):
        assert _capture_base_url() == "http://172.28.16.1:9090"

    @patch("scripts.routes.capture.get_windows_host_ip", return_value="172.28.16.1")
    def test_capture_ws_url(self, _):
        assert _capture_ws_url() == "ws://172.28.16.1:9090/ws/control"

    @patch("scripts.routes.capture.get_windows_host_ip", side_effect=Exception("not WSL"))
    def test_fallback_to_localhost(self, _):
        assert _capture_base_url() == "http://localhost:9090"
        assert _capture_ws_url() == "ws://localhost:9090/ws/control"


class TestPathToAction:
    """HTTP path→WebSocketアクションのマッピングテスト"""

    def test_status_mapping(self):
        action, _ = _PATH_TO_ACTION[("GET", "/status")]
        assert action == "status"

    def test_windows_mapping(self):
        action, _ = _PATH_TO_ACTION[("GET", "/windows")]
        assert action == "windows"

    def test_captures_mapping(self):
        action, _ = _PATH_TO_ACTION[("GET", "/captures")]
        assert action == "captures"

    def test_preview_status_mapping(self):
        action, _ = _PATH_TO_ACTION[("GET", "/preview/status")]
        assert action == "preview_status"

    def test_preview_close_mapping(self):
        action, _ = _PATH_TO_ACTION[("POST", "/preview/close")]
        assert action == "preview_close"

    def test_quit_mapping(self):
        action, _ = _PATH_TO_ACTION[("POST", "/quit")]
        assert action == "quit"

    def test_all_actions_are_strings(self):
        for key, (action, _) in _PATH_TO_ACTION.items():
            assert isinstance(action, str)
            assert len(action) > 0
