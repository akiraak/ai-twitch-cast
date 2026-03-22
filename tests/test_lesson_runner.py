"""LessonRunner のテスト"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lesson_runner import LessonRunner, LessonState


@pytest.fixture
def mock_speech():
    speech = MagicMock()
    speech.speak = AsyncMock()
    speech.notify_overlay_end = AsyncMock()
    speech.apply_emotion = MagicMock()
    speech.split_sentences = MagicMock(side_effect=lambda t: [t])
    return speech


@pytest.fixture
def runner(mock_speech):
    on_overlay = AsyncMock()
    r = LessonRunner(speech=mock_speech, on_overlay=on_overlay)
    return r


class TestLessonState:
    def test_initial_state(self, runner):
        assert runner.state == LessonState.IDLE
        assert runner.lesson_id is None
        assert runner.current_index == 0

    def test_get_status(self, runner):
        status = runner.get_status()
        assert status["state"] == "idle"
        assert status["lesson_id"] is None
        assert status["current_index"] == 0
        assert status["total_sections"] == 0


class TestLessonLifecycle:
    @pytest.mark.asyncio
    async def test_start_no_lesson(self, runner, test_db):
        with pytest.raises(ValueError, match="コンテンツが見つかりません"):
            await runner.start(9999)

    @pytest.mark.asyncio
    async def test_start_no_sections(self, runner, test_db):
        lesson = test_db.create_lesson("Empty")
        with pytest.raises(ValueError, match="スクリプトがありません"):
            await runner.start(lesson["id"])

    @pytest.mark.asyncio
    async def test_start_and_stop(self, runner, test_db):
        lesson = test_db.create_lesson("Test")
        test_db.add_lesson_section(lesson["id"], 0, "introduction", "はじめに")

        await runner.start(lesson["id"])
        assert runner.state == LessonState.RUNNING
        assert runner.lesson_id == lesson["id"]
        assert runner.total_sections == 1

        await runner.stop()
        assert runner.state == LessonState.IDLE
        assert runner.lesson_id is None

    @pytest.mark.asyncio
    async def test_pause_and_resume(self, runner, test_db):
        lesson = test_db.create_lesson("PauseTest")
        test_db.add_lesson_section(lesson["id"], 0, "introduction", "A")
        test_db.add_lesson_section(lesson["id"], 1, "explanation", "B")

        await runner.start(lesson["id"])
        assert runner.state == LessonState.RUNNING

        await runner.pause()
        assert runner.state == LessonState.PAUSED

        await runner.resume()
        assert runner.state == LessonState.RUNNING

        await runner.stop()

    @pytest.mark.asyncio
    async def test_stop_when_idle(self, runner):
        # idleでstopしてもエラーにならない
        await runner.stop()
        assert runner.state == LessonState.IDLE

    @pytest.mark.asyncio
    async def test_pause_when_idle(self, runner):
        # idleでpauseしても何も起こらない
        await runner.pause()
        assert runner.state == LessonState.IDLE

    @pytest.mark.asyncio
    async def test_resume_when_not_paused(self, runner):
        await runner.resume()
        assert runner.state == LessonState.IDLE
