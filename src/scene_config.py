"""シーン構成の定義（scenes.json から読み込み）"""

import json
import os
import re
from pathlib import Path

from src.wsl_path import get_wsl_ip, is_wsl

# システムが作成するシーン・ソースのプレフィックス
# ユーザーが手動で作成したものと区別するために使う
PREFIX = "[ATC] "

# アバター表示アプリ: "vts"（VTube Studio）or "vsf"（VSeeFace）
AVATAR_APP = os.environ.get("AVATAR_APP", "vts")

_PROJECT_DIR = Path(__file__).resolve().parent.parent
RESOURCES_DIR = _PROJECT_DIR / "resources"
TODO_PATH = _PROJECT_DIR / "TODO.md"
CONFIG_PATH = _PROJECT_DIR / "scenes.json"


def _format_todo_text():
    """TODO.mdをOBSテキストソース用にフォーマットする"""
    if not TODO_PATH.exists():
        return ""
    lines = TODO_PATH.read_text(encoding="utf-8").splitlines()
    # パディング用の先頭空行 + タイトル
    result = ["", "   TODO", ""]
    for line in lines:
        if line.startswith("# "):
            continue
        if not line.strip():
            continue
        m = re.match(r'^- \[([ x])\] (.+)', line)
        if m:
            if m.group(1) == "x":
                result.append(f"   \u2611 {m.group(2)}")
            else:
                result.append(f"   \u2610 {m.group(2)}")
            continue
        m2 = re.match(r'^\s{2,}(.+)', line)
        if m2:
            result.append(f"      {m2.group(1)}")
    # 末尾パディング
    result.append("")
    return "\n".join(result)


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
                url = src["url"]
                # WSL2環境ではlocalhostをWSL2のIPに置換（OBSはWindows上で動作）
                if is_wsl() and "localhost" in url:
                    url = url.replace("localhost", get_wsl_ip())
                resolved["url"] = url

            if src["kind"] == "todo":
                resolved["text"] = _format_todo_text()

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


def reload():
    """scenes.json を再読み込みしてSCENES, MAIN_SCENEを更新する"""
    global SCENES, MAIN_SCENE
    SCENES, MAIN_SCENE = _load_config()
