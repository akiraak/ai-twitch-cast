"""topic_talker.py のテスト"""

import time
from unittest.mock import patch, AsyncMock

from src.topic_talker import TopicTalker, DEFAULT_IDLE_THRESHOLD, DEFAULT_MIN_INTERVAL


class TestProperties:
    def test_default_thresholds(self):
        tt = TopicTalker()
        assert tt.idle_threshold == DEFAULT_IDLE_THRESHOLD
        assert tt.min_interval == DEFAULT_MIN_INTERVAL

    def test_set_idle_threshold(self):
        tt = TopicTalker()
        tt.idle_threshold = 60
        assert tt.idle_threshold == 60

    def test_idle_threshold_minimum(self):
        tt = TopicTalker()
        tt.idle_threshold = 5
        assert tt.idle_threshold == 10  # min=10

    def test_set_min_interval(self):
        tt = TopicTalker()
        tt.min_interval = 90
        assert tt.min_interval == 90

    def test_min_interval_minimum(self):
        tt = TopicTalker()
        tt.min_interval = 3
        assert tt.min_interval == 10  # min=10


class TestShouldSpeak:
    def test_paused_returns_false(self):
        tt = TopicTalker()
        assert tt._paused is True
        assert tt.should_speak(idle_seconds=999) is False

    def test_generating_returns_false(self):
        tt = TopicTalker()
        tt._paused = False
        tt._generating = True
        assert tt.should_speak(idle_seconds=999) is False

    def test_below_idle_threshold(self):
        tt = TopicTalker()
        tt._paused = False
        assert tt.should_speak(idle_seconds=5) is False

    def test_within_min_interval(self):
        tt = TopicTalker()
        tt._paused = False
        tt._last_speak_time = time.monotonic()  # just spoke
        assert tt.should_speak(idle_seconds=999) is False

    def test_all_conditions_met(self):
        tt = TopicTalker()
        tt._paused = False
        tt._last_speak_time = 0.0  # long ago
        assert tt.should_speak(idle_seconds=DEFAULT_IDLE_THRESHOLD + 1) is True


class TestMarkSpoken:
    def test_updates_last_speak_time(self):
        tt = TopicTalker()
        before = time.monotonic()
        tt.mark_spoken()
        assert tt._last_speak_time >= before


class TestSetTopic:
    async def test_creates_topic(self, test_db):
        tt = TopicTalker()
        topic = await tt.set_topic("Python", "Pythonについて")
        assert topic["title"] == "Python"
        assert topic["status"] == "active"
        assert tt._paused is False

    async def test_deactivates_previous(self, test_db):
        tt = TopicTalker()
        t1 = await tt.set_topic("Topic1")
        t2 = await tt.set_topic("Topic2")
        # Topic1 should be deactivated
        active = test_db.get_active_topic()
        assert active["title"] == "Topic2"

    async def test_with_image_urls_and_context(self, test_db):
        tt = TopicTalker()
        urls = ["/resources/images/teaching/p1.jpg", "/resources/images/teaching/p2.jpg"]
        topic = await tt.set_topic("授業", "英語教材", image_urls=urls, context="教材テキスト")
        assert topic["title"] == "授業"
        assert tt.get_image_urls() == urls
        assert tt.get_context() == "教材テキスト"

    async def test_default_no_images_or_context(self, test_db):
        tt = TopicTalker()
        await tt.set_topic("雑談")
        assert tt.get_image_urls() == []
        assert tt.get_context() is None


class TestClearTopic:
    async def test_deactivates_all(self, test_db):
        tt = TopicTalker()
        await tt.set_topic("topic")
        await tt.clear_topic()
        assert test_db.get_active_topic() is None

    async def test_clears_images_and_context(self, test_db):
        tt = TopicTalker()
        await tt.set_topic("授業", image_urls=["/img.jpg"], context="ctx")
        await tt.clear_topic()
        assert tt.get_image_urls() == []
        assert tt.get_context() is None


class TestGetStatus:
    def test_no_topic(self, test_db):
        tt = TopicTalker()
        status = tt.get_status()
        assert status["active"] is False
        assert status["topic"] is None

    async def test_with_topic(self, test_db):
        tt = TopicTalker()
        await tt.set_topic("MyTopic", "desc")
        status = tt.get_status()
        assert status["active"] is True
        assert status["topic"]["title"] == "MyTopic"
        assert status["spoken_count"] == 0
        assert status["paused"] is False


class TestGetNext:
    async def test_no_topic_returns_none(self, test_db):
        tt = TopicTalker()
        result = await tt.get_next()
        assert result is None

    async def test_short_text_single_segment(self, test_db, mock_gemini):
        """短い文章は分割されず1セグメント"""
        import json
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "content": "Pythonいいよね", "emotion": "joy", "translation": "Python is great",
        })
        tt = TopicTalker()
        await tt.set_topic("Python")
        result = await tt.get_next()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["content"] == "Pythonいいよね"
        # DBにスクリプトが保存される
        spoken = test_db.get_spoken_scripts(test_db.get_active_topic()["id"])
        assert len(spoken) == 1

    async def test_long_text_split_into_segments(self, test_db, mock_gemini):
        """長い文章は句読点で自動分割される"""
        import json
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "content": "Pythonってほんと便利だよね。特にasyncが使いやすくて最高！",
            "emotion": "joy",
            "translation": "Python is really useful. Especially async is great!",
        })
        tt = TopicTalker()
        await tt.set_topic("Python")
        result = await tt.get_next()
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["content"] == "Pythonってほんと便利だよね。"
        assert result[1]["content"] == "特にasyncが使いやすくて最高！"
        # 感情は全セグメント共通
        assert result[0]["emotion"] == "joy"
        assert result[1]["emotion"] == "joy"
        # DBには全文が1レコードで保存
        spoken = test_db.get_spoken_scripts(test_db.get_active_topic()["id"])
        assert len(spoken) == 1

    async def test_marks_spoken_time(self, test_db, mock_gemini):
        import json
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "content": "test", "emotion": "neutral", "translation": "",
        })
        tt = TopicTalker()
        await tt.set_topic("topic")
        before = time.monotonic()
        await tt.get_next()
        assert tt._last_speak_time >= before

    async def test_error_returns_none(self, test_db, mock_gemini):
        mock_gemini.models.generate_content.side_effect = Exception("API error")
        tt = TopicTalker()
        await tt.set_topic("topic")
        result = await tt.get_next()
        assert result is None
        assert tt._generating is False  # フラグがリセットされる
