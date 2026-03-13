"""共有状態 - コントローラー・接続フラグ・ブロードキャスト"""

import os

from fastapi import WebSocket

from src import db
from src.ai_responder import get_character_id, seed_character
from src.comment_reader import CommentReader
from src.git_watcher import GitWatcher
from src.topic_talker import TopicTalker
from src.scene_config import load_config_json
from src.twitch_api import TwitchAPI
from src.vsf_controller import VSFController
from src.vts_controller import VTSController

# コントローラー
vts = VTSController()
vsf = VSFController()
twitch_api = TwitchAPI()

# 接続状態
vts_connected = False
vsf_connected = False

# エピソード
current_episode = None

# WebSocket クライアント
broadcast_clients: set[WebSocket] = set()


async def _broadcast(clients: set, event: dict):
    dead = set()
    for ws in clients:
        try:
            await ws.send_json(event)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)


async def broadcast_overlay(event: dict):
    """オーバーレイ（画面表示）にイベントを送信する"""
    await _broadcast(broadcast_clients, event)


async def broadcast_tts(event: dict):
    """TTS音声ソースにイベントを送信する"""
    await _broadcast(broadcast_clients, event)


async def broadcast_bgm(event: dict):
    """BGM音声ソースにイベントを送信する"""
    await _broadcast(broadcast_clients, event)


async def broadcast_to_broadcast(event: dict):
    """broadcast.html専用イベントを送信する（シーン切替・音量等）"""
    await _broadcast(broadcast_clients, event)


async def _dispatch_event(event: dict):
    """イベントタイプに応じて適切なクライアントに振り分ける"""
    event_type = event.get("type", "")
    if event_type == "play_audio":
        await broadcast_tts(event)
    elif event_type in ("bgm_play", "bgm_stop", "bgm_volume"):
        await broadcast_bgm(event)
    else:
        await broadcast_overlay(event)


# トピック管理
topic_talker = TopicTalker()

# Reader（_dispatch_event定義後に作成）
reader = CommentReader(vsf=vsf, on_overlay=_dispatch_event, topic_talker=topic_talker)


async def _on_git_commit(commit_hash, message):
    """Gitコミット検知時のコールバック"""
    await reader.speak_event("コミット", f"{commit_hash}: {message}")


# Git監視
git_watcher = GitWatcher(on_commit=_on_git_commit)


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
    """VSeeFaceデフォルト設定を読み込む（DB優先 → scenes.json）"""
    return load_config_json("vsf_defaults", {"idle_scale": 1.0, "blendshapes": {}})
