"""WSL関連ユーティリティ（パス変換・ホストIP取得）"""

import os
import subprocess


def is_wsl() -> bool:
    """WSL環境かどうかを判定する"""
    return os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop") or "microsoft" in os.uname().release.lower()


def _is_mirrored_mode() -> bool:
    """WSL2がmirroredネットワーキングモードかどうかを判定する"""
    try:
        wslconfig = os.path.expanduser("/mnt/c/Users") + "/" + os.environ.get("WIN_USER", "akira") + "/.wslconfig"
        with open(wslconfig, "r") as f:
            for line in f:
                stripped = line.strip().lower()
                if stripped.startswith("networkingmode") and "mirrored" in stripped:
                    return True
    except Exception:
        pass
    # フォールバック: localhostでWindows側ポートにアクセスできるか（mirroredの特徴）
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        # ポート445(SMB)はWindows側で通常LISTEN
        result = s.connect_ex(("localhost", 445))
        s.close()
        if result == 0:
            # デフォルトゲートウェイがeth0でなくeth1ならmirroredの可能性が高い
            r = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True)
            if "eth1" in r.stdout:
                return True
    except Exception:
        pass
    return False


def get_windows_host_ip() -> str:
    """WSLからWindows側のIPアドレスを取得する。mirroredモードではlocalhostを返す"""
    if _is_mirrored_mode():
        return "localhost"
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
        )
        # "default via 172.28.16.1 dev eth0 ..." から IP を抽出
        return result.stdout.strip().split()[2]
    except (IndexError, FileNotFoundError):
        raise RuntimeError("Windows側のIPアドレスを取得できませんでした")


def resolve_host(host: str) -> str:
    """ホスト名を解決する。'wsl' の場合はWindows側IPを自動取得する"""
    if host == "wsl":
        ip = get_windows_host_ip()
        return ip
    return host


def get_wsl_ip() -> str:
    """WSL2自身のIPアドレスを取得する。mirroredモードではlocalhostを返す"""
    if _is_mirrored_mode():
        return "localhost"
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip().split()[0]
    except (IndexError, FileNotFoundError):
        return "localhost"


def to_windows_path(wsl_path: str) -> str:
    """WSLのパスをWindowsパス（UNC形式）に変換する"""
    result = subprocess.run(
        ["wslpath", "-w", wsl_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"wslpath変換に失敗しました: {wsl_path}")
    return result.stdout.strip()
