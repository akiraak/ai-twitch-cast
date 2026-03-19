"""共有状態 - コントローラー・接続フラグ・ブロードキャスト"""

import os

from fastapi import WebSocket

from src import db
from src.ai_responder import get_character_id, seed_character
from src.comment_reader import CommentReader
from src.dev_stream import DevStreamManager
from src.git_watcher import GitWatcher
from src.topic_talker import TopicTalker
from src.twitch_api import TwitchAPI

# コントローラー
twitch_api = TwitchAPI()

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
    import logging
    _log = logging.getLogger(__name__)
    if event.get("type") == "blendshape":
        _log.info("[ws] blendshape broadcast to %d clients: %s", len(broadcast_clients), event)
    await _broadcast(broadcast_clients, event)


async def broadcast_tts(event: dict):
    """TTS音声ソースにイベントを送信する"""
    await _broadcast(broadcast_clients, event)


async def broadcast_bgm(event: dict):
    """BGM音声ソースにイベントを送信する"""
    import logging
    _logger = logging.getLogger(__name__)
    await _broadcast(broadcast_clients, event)
    # C#アプリにもBGMコマンドを送信
    try:
        from scripts.services.capture_client import ws_request
        event_type = event.get("type", "")
        if event_type == "bgm_play":
            result = await ws_request("bgm_play", url=event.get("url", ""), volume=event.get("volume", 1.0))
            _logger.info("[BGM] C#アプリに送信: bgm_play url=%s volume=%.2f result=%s",
                         event.get("url"), event.get("volume", 1.0), result)
        elif event_type == "bgm_stop":
            await ws_request("bgm_stop")
            _logger.info("[BGM] C#アプリに送信: bgm_stop")
        elif event_type == "bgm_volume":
            result = await ws_request("bgm_volume",
                                      source=event.get("source", ""),
                                      volume=event.get("volume", 1.0))
            _logger.info("[BGM] C#アプリに送信: bgm_volume source=%s volume=%.2f",
                         event.get("source"), event.get("volume", 1.0))
    except Exception as e:
        _logger.warning("[BGM] C#アプリへの送信失敗: %s", e)


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
reader = CommentReader(on_overlay=_dispatch_event, topic_talker=topic_talker)


async def _on_git_commit(commit_hash, message):
    """Gitコミット検知時のコールバック"""
    await reader.speak_event("コミット", f"{commit_hash}: {message}")


# Git監視
git_watcher = GitWatcher(on_commit=_on_git_commit)


async def _on_dev_stream_event(repo_name, commits_info):
    """外部リポジトリのコミット検知時のコールバック"""
    # Overlay に開発アクティビティを表示
    await broadcast_overlay({
        "type": "dev_commit",
        "repo": repo_name,
        "commits": [{"hash": c["hash"], "message": c["message"], "author": c.get("author", "")} for c in commits_info],
    })
    # AI実況
    if len(commits_info) == 1:
        c = commits_info[0]
        detail = f"{repo_name} — {c['hash'][:8]}: {c['message']}"
        if c.get("diff_summary"):
            detail += f"\n{c['diff_summary']}"
    else:
        lines = [f"- {c['hash'][:8]}: {c['message']}" for c in commits_info]
        detail = f"{repo_name} — {len(commits_info)}件のコミット\n" + "\n".join(lines)
    await reader.speak_event("開発実況", detail)


# 外部リポジトリ監視
dev_stream_manager = DevStreamManager(on_event=_on_dev_stream_event)


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
