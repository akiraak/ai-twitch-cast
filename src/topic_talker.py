"""トピック管理と自発的発話のコアロジック"""

import asyncio
import logging
import time

from src import db
from src.ai_responder import generate_topic_line

logger = logging.getLogger(__name__)

# デフォルト設定
DEFAULT_IDLE_THRESHOLD = 30  # 秒: この時間コメントがなければ発話開始
DEFAULT_MIN_INTERVAL = 45  # 秒: 発話間の最低間隔


class TopicTalker:
    """トピックに基づいた自発的発話を管理する"""

    def __init__(self):
        self._idle_threshold = DEFAULT_IDLE_THRESHOLD
        self._min_interval = DEFAULT_MIN_INTERVAL
        self._last_speak_time = 0.0
        self._generating = False
        self._paused = True

    @property
    def idle_threshold(self):
        return self._idle_threshold

    @idle_threshold.setter
    def idle_threshold(self, value):
        self._idle_threshold = max(10, value)

    @property
    def min_interval(self):
        return self._min_interval

    @min_interval.setter
    def min_interval(self, value):
        self._min_interval = max(10, value)

    def mark_spoken(self):
        """発話したことを記録する（コメント応答・イベント発話も含む）"""
        self._last_speak_time = time.monotonic()

    async def set_topic(self, title, description=""):
        """新しいトピックを設定する"""
        db.deactivate_all_topics()
        topic = db.create_topic(title, description)
        self._paused = False
        logger.info("[topic] トピック設定: %s", title)
        return topic

    async def clear_topic(self):
        """トピックを解除する"""
        db.deactivate_all_topics()
        logger.info("[topic] トピック解除")

    def should_speak(self, idle_seconds):
        """自発的発話すべきかを判定する"""
        if self._paused or self._generating:
            return False
        topic = db.get_active_topic()
        if not topic:
            return False
        if idle_seconds < self._idle_threshold:
            return False
        elapsed = time.monotonic() - self._last_speak_time
        if elapsed < self._min_interval:
            return False
        return True

    async def get_next(self):
        """次の発話をリアルタイム生成する。直前の発話と会話から自然な続きを作る。

        Returns:
            dict: {"content": str, "emotion": str, "english": str} or None
        """
        topic = db.get_active_topic()
        if not topic:
            return None

        self._generating = True
        try:
            # 直前の自分のトピック発話を取得
            spoken = db.get_spoken_scripts(topic["id"])
            last_speeches = [s["content"] for s in spoken[-3:]] if spoken else None

            # 直近の会話履歴
            recent_comments = db.get_recent_comments(5, 2)

            logger.info("[topic] セリフ生成中...")
            result = await asyncio.to_thread(
                generate_topic_line,
                topic["title"], topic["description"],
                last_speeches=last_speeches,
                recent_comments=recent_comments,
            )

            # 発話履歴としてDBに保存
            db.add_topic_scripts(topic["id"], [{
                "content": result["content"],
                "emotion": result["emotion"],
                "sort_order": 0,
            }])
            # 即座に発話済みにする
            script = db.get_next_unspoken_script(topic["id"])
            if script:
                db.mark_script_spoken(script["id"])

            self.mark_spoken()
            logger.info("[topic] セリフ生成完了: %s", result["content"])
            return result
        except Exception as e:
            logger.error("[topic] セリフ生成失敗: %s", e)
            return None
        finally:
            self._generating = False

    def get_status(self):
        """現在の状態を返す"""
        topic = db.get_active_topic()
        if not topic:
            return {"active": False, "topic": None, "generating": self._generating, "paused": self._paused}

        spoken = db.get_spoken_scripts(topic["id"])
        return {
            "active": True,
            "topic": {
                "id": topic["id"],
                "title": topic["title"],
                "description": topic["description"],
            },
            "remaining_scripts": 0,
            "spoken_count": len(spoken),
            "generating": self._generating,
            "paused": self._paused,
            "idle_threshold": self._idle_threshold,
            "min_interval": self._min_interval,
        }
