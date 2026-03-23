"""LessonRunner のテスト"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lesson_runner import (
    LESSON_AUDIO_DIR,
    LessonRunner,
    LessonState,
    _cache_path,
    clear_tts_cache,
    get_tts_cache_info,
)


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


class TestTtsCache:
    """TTSキャッシュ関連のテスト"""

    def test_cache_path(self):
        """キャッシュパスの生成"""
        p = _cache_path(1, 0, 2)
        assert p.name == "section_00_part_02.wav"
        assert "lessons/1/" in str(p)

    def test_clear_tts_cache_all(self, tmp_path, monkeypatch):
        """全キャッシュ削除"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        lesson_dir = tmp_path / "42"
        lesson_dir.mkdir()
        (lesson_dir / "section_00_part_00.wav").write_bytes(b"x")
        (lesson_dir / "section_01_part_00.wav").write_bytes(b"x")

        clear_tts_cache(42)
        assert not lesson_dir.exists()

    def test_clear_tts_cache_section(self, tmp_path, monkeypatch):
        """特定セクションのキャッシュ削除"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        lesson_dir = tmp_path / "1"
        lesson_dir.mkdir()
        (lesson_dir / "section_00_part_00.wav").write_bytes(b"x")
        (lesson_dir / "section_01_part_00.wav").write_bytes(b"x")

        clear_tts_cache(1, order_index=0)
        assert not (lesson_dir / "section_00_part_00.wav").exists()
        assert (lesson_dir / "section_01_part_00.wav").exists()

    def test_clear_tts_cache_nonexistent(self, tmp_path, monkeypatch):
        """存在しないキャッシュディレクトリの削除はエラーにならない"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        clear_tts_cache(999)  # no error

    def test_get_tts_cache_info(self, tmp_path, monkeypatch, test_db):
        """キャッシュ情報取得"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        monkeypatch.setattr("src.lesson_runner.PROJECT_DIR", tmp_path.parent)

        # レッスン・セクション作成
        lesson = test_db.create_lesson("CacheInfoTest")
        lid = lesson["id"]
        test_db.add_lesson_section(lid, 0, "intro", "Hello")
        test_db.add_lesson_section(lid, 1, "explain", "World")

        # セクション0のキャッシュを作成
        cache_dir = tmp_path / str(lid)
        cache_dir.mkdir(parents=True)
        (cache_dir / "section_00_part_00.wav").write_bytes(b"wavdata")

        info = get_tts_cache_info(lid)
        assert len(info) == 2
        assert info[0]["order_index"] == 0
        assert len(info[0]["parts"]) == 1
        assert info[0]["parts"][0]["part_index"] == 0
        assert info[0]["parts"][0]["size"] == 7
        assert info[1]["order_index"] == 1
        assert info[1]["parts"] == []
