"""共有状態 - コントローラー・接続フラグ・ブロードキャスト"""

import os
import re

from fastapi import WebSocket

from src import db

# テキストフィールドから言語タグを除去するキー
_TEXT_KEYS_TO_STRIP = {"speech", "trigger_text", "translation", "text"}
_LANG_TAG_RE = re.compile(r'\[/?lang(?::\w+)?\]|<lang\b[^>]*>|</lang>', re.IGNORECASE)


def _strip_text_fields(event: dict) -> dict:
    """イベント内のテキストフィールドから言語タグを除去する（非破壊）"""
    needs_strip = False
    for key in _TEXT_KEYS_TO_STRIP:
        val = event.get(key)
        if isinstance(val, str) and _LANG_TAG_RE.search(val):
            needs_strip = True
            break
    if not needs_strip:
        return event
    cleaned = dict(event)
    for key in _TEXT_KEYS_TO_STRIP:
        val = cleaned.get(key)
        if isinstance(val, str):
            cleaned[key] = _LANG_TAG_RE.sub('', val)
    return cleaned
from src.ai_responder import get_character_id, seed_character
from src.comment_reader import CommentReader
from src.git_watcher import GitWatcher
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
    """オーバーレイ（画面表示）にイベントを送信する（テキストフィールドの言語タグは自動除去）"""
    import logging
    _log = logging.getLogger(__name__)
    if event.get("type") == "blendshape":
        _log.info("[ws] blendshape broadcast to %d clients: %s", len(broadcast_clients), event)
    # テキスト系イベントのみタグ除去（blendshape/lipsync等はスキップ）
    cleaned = _strip_text_fields(event)
    if cleaned is not event:
        _log.info("[ws] _strip_text_fields がタグ除去: type=%s", event.get("type"))
        for key in _TEXT_KEYS_TO_STRIP:
            if event.get(key) != cleaned.get(key):
                _log.info("[ws]   %s: %s → %s", key, repr(event.get(key, "")[:100]), repr(cleaned.get(key, "")[:100]))
    # SSMLタグ残存チェック
    for key in _TEXT_KEYS_TO_STRIP:
        val = cleaned.get(key, "")
        if isinstance(val, str) and ('<lang' in val or '</lang>' in val):
            _log.warning("[ws] ⚠ broadcast後もSSMLタグ残存: %s=%s", key, repr(val[:200]))
    await _broadcast(broadcast_clients, cleaned)


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


async def broadcast_se(event: dict):
    """SE（効果音）をC#アプリに送信する"""
    import logging
    _logger = logging.getLogger(__name__)
    try:
        from scripts.services.capture_client import ws_request
        if event.get("type") == "se_play":
            result = await ws_request("se_play", url=event.get("url", ""), volume=event.get("volume", 1.0))
            _logger.info("[SE] C#アプリに送信: se_play url=%s volume=%.2f result=%s",
                         event.get("url"), event.get("volume", 1.0), result)
    except Exception as e:
        _logger.warning("[SE] C#アプリへの送信失敗: %s", e)


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


# Reader（_dispatch_event定義後に作成）
reader = CommentReader(on_overlay=_dispatch_event)


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
