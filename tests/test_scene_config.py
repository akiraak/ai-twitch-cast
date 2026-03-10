"""scene_config の純粋ロジックテスト"""

from unittest.mock import patch

from src.scene_config import PREFIX


class TestResolveURL:
    @patch("src.scene_config.is_wsl", return_value=False)
    @patch("src.scene_config.get_wsl_ip", return_value="172.0.0.1")
    def test_relative_path_non_wsl(self, _ip, _wsl):
        from src.scene_config import _resolve_browser_url, WEB_PORT
        result = _resolve_browser_url("overlay")
        assert result == f"http://localhost:{WEB_PORT}/overlay"

    @patch("src.scene_config.is_wsl", return_value=True)
    @patch("src.scene_config.get_wsl_ip", return_value="172.28.1.5")
    def test_relative_path_wsl(self, _ip, _wsl):
        from src.scene_config import _resolve_browser_url, WEB_PORT
        result = _resolve_browser_url("overlay")
        assert result == f"http://172.28.1.5:{WEB_PORT}/overlay"

    @patch("src.scene_config.is_wsl", return_value=False)
    @patch("src.scene_config.get_wsl_ip", return_value="172.0.0.1")
    def test_full_url_passthrough(self, _ip, _wsl):
        from src.scene_config import _resolve_browser_url
        url = "https://example.com/page"
        assert _resolve_browser_url(url) == url

    @patch("src.scene_config.is_wsl", return_value=True)
    @patch("src.scene_config.get_wsl_ip", return_value="172.28.1.5")
    def test_localhost_replaced_in_wsl(self, _ip, _wsl):
        from src.scene_config import _resolve_browser_url
        result = _resolve_browser_url("http://localhost:8080/test")
        assert "172.28.1.5" in result
        assert "localhost" not in result

    @patch("src.scene_config.is_wsl", return_value=False)
    @patch("src.scene_config.get_wsl_ip", return_value="172.0.0.1")
    def test_relative_with_leading_slash(self, _ip, _wsl):
        from src.scene_config import _resolve_browser_url, WEB_PORT
        result = _resolve_browser_url("/api/test")
        assert result == f"http://localhost:{WEB_PORT}/api/test"


class TestPrefix:
    def test_prefix_value(self):
        assert PREFIX == "[ATC] "
