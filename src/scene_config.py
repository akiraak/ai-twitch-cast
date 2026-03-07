"""シーン構成の定義"""

import os
from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"

# システムが作成するシーン・ソースのプレフィックス
# ユーザーが手動で作成したものと区別するために使う
PREFIX = "[ATC] "

# アバター表示アプリ: "vts"（VTube Studio）or "vsf"（VSeeFace）
AVATAR_APP = os.environ.get("AVATAR_APP", "vts")

_AVATAR_SOURCES = {
    "vts": {
        "name": f"{PREFIX}アバター",
        "kind": "game_capture",
        "window": "VTube Studio:UnityWndClass:VTube Studio.exe",
        "allow_transparency": True,
        "transform": {
            "boundsType": "OBS_BOUNDS_STRETCH",
            "boundsWidth": 1920.0,
            "boundsHeight": 1080.0,
        },
    },
    "vsf": {
        "name": f"{PREFIX}アバター",
        "kind": "game_capture",
        "window": "VSeeFace:UnityWndClass:VSeeFace.exe",
        "allow_transparency": True,
        "transform": {
            "boundsType": "OBS_BOUNDS_STRETCH",
            "boundsWidth": 1920.0,
            "boundsHeight": 1080.0,
        },
    },
}

SCENES = [
    {
        "name": f"{PREFIX}メイン",
        "sources": [
            {
                "name": f"{PREFIX}背景",
                "kind": "image",
                "path": RESOURCES_DIR / "images" / "background.png",
            },
            _AVATAR_SOURCES[AVATAR_APP],
        ],
    },
    {
        "name": f"{PREFIX}開始画面",
        "sources": [
            {
                "name": f"{PREFIX}開始背景",
                "kind": "image",
                "path": RESOURCES_DIR / "images" / "background.png",
            },
            {
                "name": f"{PREFIX}開始テキスト",
                "kind": "text",
                "text": "まもなく開始",
                "font_size": 72,
            },
        ],
    },
    {
        "name": f"{PREFIX}終了画面",
        "sources": [
            {
                "name": f"{PREFIX}終了背景",
                "kind": "image",
                "path": RESOURCES_DIR / "images" / "background.png",
            },
            {
                "name": f"{PREFIX}終了テキスト",
                "kind": "text",
                "text": "配信終了\nご視聴ありがとうございました",
                "font_size": 72,
            },
        ],
    },
]
