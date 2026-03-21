"""トピック管理と自発的発話のコアロジック"""

import asyncio
import logging
import time

from src import db
from src.ai_responder import generate_topic_line, generate_topic_title

logger = logging.getLogger(__name__)

# デフォルト設定
DEFAULT_IDLE_THRESHOLD = 30  # 秒: この時間コメントがなければ発話開始
DEFAULT_MIN_INTERVAL = 45  # 秒: 発話間の最低間隔
TOPIC_ROTATE_INTERVAL = 10 * 60  # 秒: トピック自動ローテーション間隔（10分）
TOPIC_ROTATE_SPEECHES = 5  # 発話数: この回数話したらトピック変更


class TopicTalker:
    """トピックに基づいた自発的発話を管理する"""

    def __init__(self):
        self._idle_threshold = DEFAULT_IDLE_THRESHOLD
        self._min_interval = DEFAULT_MIN_INTERVAL
        self._last_speak_time = 0.0
        self._generating = False
        self._paused = True
        self._topic_set_time = 0.0  # トピック設定時刻

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
        self._topic_set_time = time.monotonic()
        logger.info("[topic] トピック設定: %s", title)
        return topic

    async def clear_topic(self):
        """トピックを解除する"""
        db.deactivate_all_topics()
        logger.info("[topic] トピック解除")

    def _should_rotate(self):
        """トピックをローテーションすべきか判定する"""
        topic = db.get_active_topic()
        if not topic:
            return False
        # 経過時間チェック
        elapsed = time.monotonic() - self._topic_set_time
        if elapsed < TOPIC_ROTATE_INTERVAL:
            return False
        # 発話数チェック
        spoken = db.get_spoken_scripts(topic["id"])
        return len(spoken) >= TOPIC_ROTATE_SPEECHES

    def should_speak(self, idle_seconds):
        """自発的発話すべきかを判定する（トピックがなければ自動生成も含む）"""
        if self._paused or self._generating:
            return False
        if idle_seconds < self._idle_threshold:
            return False
        elapsed = time.monotonic() - self._last_speak_time
        if elapsed < self._min_interval:
            return False
        return True

    async def maybe_rotate_topic(self, stream_context=None, self_note=None):
        """トピックがなければ自動生成、条件を満たしていればローテーションする

        Args:
            stream_context: 配信情報（トピック生成の参考に）
            self_note: アバター自身の記憶メモ

        Returns:
            dict or None: 新しいトピック、またはローテーション/生成不要ならNone
        """
        if self._paused or self._generating:
            return None

        current_topic = db.get_active_topic()
        needs_new = current_topic is None or self._should_rotate()
        if not needs_new:
            return None

        self._generating = True
        try:
            current_title = current_topic["title"] if current_topic else None
            timeline = db.get_recent_timeline(10, 2)

            action = "自動生成" if not current_topic else "自動ローテーション"
            logger.info("[topic] トピック%s中...", action)
            new_title = await asyncio.to_thread(
                generate_topic_title,
                timeline=timeline,
                current_topic=current_title,
                stream_context=stream_context,
                self_note=self_note,
            )

            topic = await self.set_topic(new_title)
            logger.info("[topic] 新トピック: %s", new_title)
            return topic
        except Exception as e:
            logger.error("[topic] トピック生成失敗: %s", e)
            return None
        finally:
            self._generating = False

    async def get_next(self):
        """次の発話をリアルタイム生成する。直前の発話と会話から自然な続きを作る。

        Returns:
            dict: {"content": str, "emotion": str, "translation": str} or None
        """
        topic = db.get_active_topic()
        if not topic:
            return None

        self._generating = True
        try:
            # 直前の自分のトピック発話を取得
            spoken = db.get_spoken_scripts(topic["id"])
            last_speeches = [s["content"] for s in spoken[-3:]] if spoken else None

            # 直近の会話タイムライン
            timeline = db.get_recent_timeline(5, 2)

            logger.info("[topic] セリフ生成中...")
            result = await asyncio.to_thread(
                generate_topic_line,
                topic["title"], topic["description"],
                last_speeches=last_speeches,
                timeline=timeline,
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
