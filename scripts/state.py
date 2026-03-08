"""共有状態 - コントローラー・接続フラグ・ブロードキャスト"""

import json
import os

from fastapi import WebSocket

from src import db
from src.ai_responder import get_character_id, seed_character
from src.comment_reader import CommentReader
from src.obs_controller import OBSController
from src.scene_config import CONFIG_PATH
from src.twitch_api import TwitchAPI
from src.vsf_controller import VSFController
from src.vts_controller import VTSController

# コントローラー
obs = OBSController()
vts = VTSController()
vsf = VSFController()
twitch_api = TwitchAPI()

# 接続状態
obs_connected = False
vts_connected = False
vsf_connected = False

# エピソード
current_episode = None

# WebSocket オーバーレイクライアント
overlay_clients: set[WebSocket] = set()


async def broadcast_overlay(event: dict):
    """全接続中のオーバーレイクライアントにイベントを送信する"""
    dead = set()
    for ws in overlay_clients:
        try:
            await ws.send_json(event)
        except Exception:
            dead.add(ws)
    overlay_clients.difference_update(dead)


# Reader（broadcast_overlay定義後に作成）
reader = CommentReader(vsf=vsf, on_overlay=broadcast_overlay)


async def ensure_reader():
    """Readerが停止していれば起動する"""
    global current_episode
    if reader.is_running:
        return
    channel_name = os.environ.get("TWITCH_CHANNEL", "default")
    channel = db.get_or_create_channel(channel_name)
    seed_character(channel["id"])
    character_id = get_character_id()
    show = db.get_or_create_show(channel["id"], "デフォルト")
    if not current_episode:
        current_episode = db.start_episode(show["id"], character_id)
    reader.set_episode(current_episode["id"])
    await reader.start()


def load_vsf_defaults():
    """VSeeFaceデフォルト設定を読み込む"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return config.get("vsf_defaults", {"idle_scale": 1.0, "blendshapes": {}})
