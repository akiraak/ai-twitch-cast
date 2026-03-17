"""wsl_path ユーティリティのテスト"""

from unittest.mock import patch, MagicMock
import subprocess

from src.wsl_path import (
    get_windows_host_ip,
    get_wsl_ip,
    is_wsl,
    resolve_host,
    to_windows_path,
)


class TestResolveHost:
    def test_normal_host_passthrough(self):
        assert resolve_host("192.168.1.1") == "192.168.1.1"
        assert resolve_host("localhost") == "localhost"
        assert resolve_host("example.com") == "example.com"

    @patch("src.wsl_path.get_windows_host_ip", return_value="172.28.16.1")
    def test_wsl_keyword_resolves(self, _mock):
        result = resolve_host("wsl")
        assert result == "172.28.16.1"


class TestIsWsl:
    @patch("os.path.exists", return_value=True)
    def test_wsl_interop_exists(self, _mock):
        assert is_wsl() is True

    @patch("os.path.exists", return_value=False)
    @patch("os.uname")
    def test_microsoft_in_release(self, mock_uname, _mock_exists):
        mock_uname.return_value = MagicMock(release="5.15.0-microsoft-standard-WSL2")
        assert is_wsl() is True

    @patch("os.path.exists", return_value=False)
    @patch("os.uname")
    def test_not_wsl(self, mock_uname, _mock_exists):
        mock_uname.return_value = MagicMock(release="5.15.0-generic")
        assert is_wsl() is False


class TestGetWindowsHostIp:
    @patch("src.wsl_path._is_mirrored_mode", return_value=True)
    def test_mirrored_returns_localhost(self, _mock):
        assert get_windows_host_ip() == "localhost"

    @patch("src.wsl_path._is_mirrored_mode", return_value=False)
    @patch("subprocess.run")
    def test_extracts_gateway_ip(self, mock_run, _mock_mirrored):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="default via 172.28.16.1 dev eth0 proto kernel\n",
        )
        assert get_windows_host_ip() == "172.28.16.1"

    @patch("src.wsl_path._is_mirrored_mode", return_value=False)
    @patch("subprocess.run")
    def test_empty_output_raises(self, mock_run, _mock_mirrored):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        import pytest
        with pytest.raises((RuntimeError, IndexError)):
            get_windows_host_ip()


class TestGetWslIp:
    @patch("src.wsl_path._is_mirrored_mode", return_value=True)
    def test_mirrored_returns_localhost(self, _mock):
        assert get_wsl_ip() == "localhost"

    @patch("src.wsl_path._is_mirrored_mode", return_value=False)
    @patch("subprocess.run")
    def test_extracts_ip(self, mock_run, _mock_mirrored):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="172.28.20.5 \n",
        )
        assert get_wsl_ip() == "172.28.20.5"

    @patch("src.wsl_path._is_mirrored_mode", return_value=False)
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_fallback_to_localhost(self, _mock_run, _mock_mirrored):
        assert get_wsl_ip() == "localhost"


class TestToWindowsPath:
    @patch("subprocess.run")
    def test_converts_path(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="\\\\wsl$\\Ubuntu\\home\\user\\project\n",
        )
        result = to_windows_path("/home/user/project")
        assert result == "\\\\wsl$\\Ubuntu\\home\\user\\project"

    @patch("subprocess.run")
    def test_failure_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        import pytest
        with pytest.raises(RuntimeError):
            to_windows_path("/bad/path")
