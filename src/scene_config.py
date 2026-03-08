"""シーン構成の定義（scenes.json から読み込み）"""

import json
import os
from pathlib import Path

# システムが作成するシーン・ソースのプレフィックス
# ユーザーが手動で作成したものと区別するために使う
PREFIX = "[ATC] "

# アバター表示アプリ: "vts"（VTube Studio）or "vsf"（VSeeFace）
AVATAR_APP = os.environ.get("AVATAR_APP", "vts")

_PROJECT_DIR = Path(__file__).resolve().parent.parent
RESOURCES_DIR = _PROJECT_DIR / "resources"
CONFIG_PATH = _PROJECT_DIR / "scenes.json"


def _load_config():
    """scenes.json を読み込んでSCENESリストを生成する"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    # アバターソースの構築
    avatar_cfg = config["avatar"].get(AVATAR_APP, {})
    avatar_source = {
        "name": f"{PREFIX}アバター",
        "kind": "game_capture",
        "window": avatar_cfg.get("window", ""),
        "allow_transparency": avatar_cfg.get("allow_transparency", False),
    }
    if "transform" in avatar_cfg:
        avatar_source["transform"] = avatar_cfg["transform"]

    # シーン定義の構築
    scenes = []
    for scene in config["scenes"]:
        sources = []
        for src in scene["sources"]:
            if src["kind"] == "avatar":
                if "transform" in src:
                    # シーンごとのtransformオーバーライド
                    overridden = dict(avatar_source)
                    overridden["transform"] = {
                        **avatar_source.get("transform", {}),
                        **src["transform"],
                    }
                    sources.append(overridden)
                else:
                    sources.append(avatar_source)
                continue

            resolved = dict(src)
            resolved["name"] = f"{PREFIX}{src['name']}"

            if src["kind"] == "image" and "path" in src:
                resolved["path"] = RESOURCES_DIR / src["path"]
            elif src["kind"] == "browser" and "url" in src:
                resolved["url"] = src["url"]

            sources.append(resolved)

        scenes.append({
            "name": f"{PREFIX}{scene['name']}",
            "sources": sources,
        })

    main_scene = config.get("main_scene")
    if main_scene:
        main_scene = f"{PREFIX}{main_scene}"

    return scenes, main_scene


SCENES, MAIN_SCENE = _load_config()
