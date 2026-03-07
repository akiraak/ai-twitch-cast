"""WSL関連ユーティリティ（パス変換・ホストIP取得）"""

import os
import subprocess


def is_wsl() -> bool:
    """WSL環境かどうかを判定する"""
    return os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop") or "microsoft" in os.uname().release.lower()


def get_windows_host_ip() -> str:
    """WSLからWindows側のIPアドレスを取得する"""
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
