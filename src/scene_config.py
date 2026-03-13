"""設定の定義（DB優先 → scenes.json フォールバック）"""

import json
import os
from pathlib import Path

# Webサーバーのポート
WEB_PORT = int(os.environ.get("WEB_PORT", "8080"))

_PROJECT_DIR = Path(__file__).resolve().parent.parent
RESOURCES_DIR = _PROJECT_DIR / "resources"
CONFIG_PATH = _PROJECT_DIR / "scenes.json"


def load_config_value(key, default=None):
    """設定値を取得する（DB優先 → scenes.json → default）"""
    from src import db
    val = db.get_setting(key)
    if val is not None:
        return val
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        parts = key.split(".")
        obj = config
        for p in parts:
            obj = obj[p]
        return obj if obj is not None else default
    except (KeyError, TypeError, FileNotFoundError):
        return default


def load_config_json(key, default=None):
    """JSON値を取得する（DB優先 → scenes.json → default）"""
    from src import db
    val = db.get_setting(key)
    if val is not None:
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        parts = key.split(".")
        obj = config
        for p in parts:
            obj = obj[p]
        return obj if obj is not None else default
    except (KeyError, TypeError, FileNotFoundError):
        return default


def save_config_value(key, value):
    """設定値をDBに保存する"""
    from src import db
    db.set_setting(key, str(value))


def save_config_json(key, value):
    """JSON値をDBに保存する"""
    from src import db
    db.set_setting(key, json.dumps(value, ensure_ascii=False))
