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


class TestClearTopic:
    async def test_deactivates_all(self, test_db):
        tt = TopicTalker()
        await tt.set_topic("topic")
        await tt.clear_topic()
        assert test_db.get_active_topic() is None


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

    async def test_generates_and_saves(self, test_db, mock_gemini):
        import json
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "content": "Pythonいいよね", "emotion": "joy", "translation": "Python is great",
        })
        tt = TopicTalker()
        await tt.set_topic("Python")
        result = await tt.get_next()
        assert result["content"] == "Pythonいいよね"
        # DBにスクリプトが保存される
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
