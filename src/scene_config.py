"""設定の定義（scenes.json から読み込み）"""

import os
from pathlib import Path

# Webサーバーのポート
WEB_PORT = int(os.environ.get("WEB_PORT", "8080"))

# アバター表示アプリ: "vts"（VTube Studio）or "vsf"（VSeeFace）
AVATAR_APP = os.environ.get("AVATAR_APP", "vts")

_PROJECT_DIR = Path(__file__).resolve().parent.parent
RESOURCES_DIR = _PROJECT_DIR / "resources"
CONFIG_PATH = _PROJECT_DIR / "scenes.json"
