"""wsl_path ユーティリティのテスト"""

from unittest.mock import patch

from src.wsl_path import resolve_host


class TestResolveHost:
    def test_normal_host_passthrough(self):
        assert resolve_host("192.168.1.1") == "192.168.1.1"
        assert resolve_host("localhost") == "localhost"
        assert resolve_host("example.com") == "example.com"

    @patch("src.wsl_path.get_windows_host_ip", return_value="172.28.16.1")
    def test_wsl_keyword_resolves(self, _mock):
        result = resolve_host("wsl")
        assert result == "172.28.16.1"
