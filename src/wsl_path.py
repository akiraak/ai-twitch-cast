"""WSLパスをWindowsパスに変換するユーティリティ"""

import subprocess


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
