"""トピック管理と自発的発話のコアロジック"""

import asyncio
import logging
import time

from src import db
from src.ai_responder import generate_topic_scripts

logger = logging.getLogger(__name__)

# デフォルト設定
DEFAULT_IDLE_THRESHOLD = 30  # 秒: この時間コメントがなければ発話開始
DEFAULT_MIN_INTERVAL = 45  # 秒: 発話間の最低間隔
REPLENISH_THRESHOLD = 2  # 未発話スクリプトがこの数以下で補充


class TopicTalker:
    """トピックに基づいた自発的発話を管理する"""

    def __init__(self):
        self._idle_threshold = DEFAULT_IDLE_THRESHOLD
        self._min_interval = DEFAULT_MIN_INTERVAL
        self._last_speak_time = 0.0
        self._replenishing = False
        self._paused = False

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
        """新しいトピックを設定し、スクリプトを事前生成する"""
        # 既存のアクティブトピックを完了にする
        db.deactivate_all_topics()
        topic = db.create_topic(title, description)
        logger.info("[topic] トピック設定: %s", title)

        # バックグラウンドでスクリプト生成
        asyncio.create_task(self._generate_scripts(topic["id"], title, description))
        return topic

    async def clear_topic(self):
        """トピックを解除する"""
        db.deactivate_all_topics()
        logger.info("[topic] トピック解除")

    def should_speak(self, idle_seconds):
        """自発的発話すべきかを判定する"""
        if self._paused:
            return False
        topic = db.get_active_topic()
        if not topic:
            return False

        # idle時間が閾値未満
        if idle_seconds < self._idle_threshold:
            return False

        # 前回の発話からの経過時間チェック
        elapsed = time.monotonic() - self._last_speak_time
        if elapsed < self._min_interval:
            return False

        # 未発話スクリプトがあるか
        if db.count_unspoken_scripts(topic["id"]) == 0:
            return False

        return True

    async def get_next(self):
        """次の発話スクリプトを取得し、発話済みにする。ストック補充もトリガー。

        Returns:
            dict: {"content": str, "emotion": str} or None
        """
        topic = db.get_active_topic()
        if not topic:
            return None

        script = db.get_next_unspoken_script(topic["id"])
        if not script:
            return None

        db.mark_script_spoken(script["id"])
        self.mark_spoken()

        # ストック補充チェック
        remaining = db.count_unspoken_scripts(topic["id"])
        if remaining <= REPLENISH_THRESHOLD and not self._replenishing:
            asyncio.create_task(
                self._generate_scripts(topic["id"], topic["title"], topic["description"])
            )

        return {"content": script["content"], "emotion": script["emotion"]}

    def get_status(self):
        """現在の状態を返す"""
        topic = db.get_active_topic()
        if not topic:
            return {"active": False, "topic": None, "generating": self._replenishing, "paused": self._paused}

        remaining = db.count_unspoken_scripts(topic["id"])
        spoken = db.get_spoken_scripts(topic["id"])
        return {
            "active": True,
            "topic": {
                "id": topic["id"],
                "title": topic["title"],
                "description": topic["description"],
            },
            "remaining_scripts": remaining,
            "spoken_count": len(spoken),
            "generating": self._replenishing,
            "paused": self._paused,
            "idle_threshold": self._idle_threshold,
            "min_interval": self._min_interval,
        }

    async def _generate_scripts(self, topic_id, title, description):
        """スクリプトをバックグラウンド生成する"""
        self._replenishing = True
        try:
            # 既に話した内容を取得
            spoken = db.get_spoken_scripts(topic_id)
            already_spoken = [s["content"] for s in spoken] if spoken else None

            # 既存の未発話スクリプトのsort_orderの最大値を取得
            all_scripts = db.get_all_scripts(topic_id)
            max_order = max((s["sort_order"] for s in all_scripts), default=-1)

            logger.info("[topic] スクリプト生成中... (topic_id=%d)", topic_id)
            scripts = await asyncio.to_thread(
                generate_topic_scripts, title, description,
                count=5, already_spoken=already_spoken,
            )

            # sort_orderを調整
            for i, s in enumerate(scripts):
                s["sort_order"] = max_order + 1 + i

            db.add_topic_scripts(topic_id, scripts)
            logger.info("[topic] スクリプト%d件生成完了", len(scripts))
        except Exception as e:
            logger.error("[topic] スクリプト生成失敗: %s", e)
        finally:
            self._replenishing = False
