"""シーン構成の定義"""

from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"

SCENES = [
    {
        "name": "メイン",
        "sources": [
            {
                "name": "背景",
                "kind": "image",
                "path": RESOURCES_DIR / "images" / "background.png",
            },
            {
                "name": "アバター",
                "kind": "game_capture",
            },
        ],
    },
    {
        "name": "開始画面",
        "sources": [
            {
                "name": "開始背景",
                "kind": "image",
                "path": RESOURCES_DIR / "images" / "background.png",
            },
            {
                "name": "開始テキスト",
                "kind": "text",
                "text": "まもなく開始",
                "font_size": 72,
            },
        ],
    },
    {
        "name": "終了画面",
        "sources": [
            {
                "name": "終了背景",
                "kind": "image",
                "path": RESOURCES_DIR / "images" / "background.png",
            },
            {
                "name": "終了テキスト",
                "kind": "text",
                "text": "配信終了\nご視聴ありがとうございました",
                "font_size": 72,
            },
        ],
    },
]
