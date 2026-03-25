"""LessonRunner のテスト"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lesson_runner import (
    LESSON_AUDIO_DIR,
    LessonRunner,
    LessonState,
    _cache_path,
    _dlg_cache_path,
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

    def test_dlg_cache_path(self):
        """dialogue用キャッシュパスの生成"""
        p = _dlg_cache_path(1, 3, 1, lang="en")
        assert p.name == "section_03_dlg_01.wav"
        assert "lessons/1/en" in str(p)

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

        # セクション0のキャッシュを作成（lang="ja" サブディレクトリ）
        cache_dir = tmp_path / str(lid) / "ja"
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


class TestDialoguePlayback:
    """対話再生のテスト"""

    @pytest.mark.asyncio
    async def test_play_dialogues_calls_speak_per_dialogue(self, mock_speech, test_db):
        """dialoguesがあると話者別に個別speak呼び出しされる"""
        dialogues = json.dumps([
            {"speaker": "teacher", "content": "こんにちは！", "tts_text": "こんにちは！", "emotion": "excited"},
            {"speaker": "student", "content": "よろしく！", "tts_text": "よろしく！", "emotion": "joy"},
            {"speaker": "teacher", "content": "始めよう！", "tts_text": "始めよう！", "emotion": "neutral"},
        ])
        teacher_cfg = {"name": "先生", "tts_voice": "Despina", "tts_style": "にこにこ"}
        student_cfg = {"name": "生徒", "tts_voice": "Kore", "tts_style": "元気"}

        on_overlay = AsyncMock()
        runner = LessonRunner(speech=mock_speech, on_overlay=on_overlay)
        runner._teacher_cfg = teacher_cfg
        runner._student_cfg = student_cfg
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._sections = [{}]
        runner._current_index = 0

        # generate_tts はNone返す（キャッシュなし、WAVなし）
        mock_speech.generate_tts = AsyncMock(return_value=None)

        section = {
            "section_type": "introduction",
            "content": "こんにちは！よろしく！始めよう！",
            "dialogues": dialogues,
            "order_index": 0,
        }
        await runner._play_dialogues(section, json.loads(dialogues))

        # speak が 3回呼ばれる（dialogue 3つ）
        assert mock_speech.speak.call_count == 3

        # 1回目: teacher
        call1 = mock_speech.speak.call_args_list[0]
        assert call1.kwargs["avatar_id"] == "teacher"
        assert call1.kwargs["voice"] == "Despina"

        # 2回目: student
        call2 = mock_speech.speak.call_args_list[1]
        assert call2.kwargs["avatar_id"] == "student"
        assert call2.kwargs["voice"] == "Kore"

        # 3回目: teacher
        call3 = mock_speech.speak.call_args_list[2]
        assert call3.kwargs["avatar_id"] == "teacher"

    @pytest.mark.asyncio
    async def test_play_section_falls_back_to_single_speaker(self, mock_speech, test_db):
        """dialoguesが空なら従来の単話者再生にフォールバック"""
        on_overlay = AsyncMock()
        runner = LessonRunner(speech=mock_speech, on_overlay=on_overlay)
        runner._teacher_cfg = {"name": "先生"}
        runner._student_cfg = {"name": "生徒"}
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._sections = [{}]
        runner._current_index = 0

        mock_speech.generate_tts = AsyncMock(return_value=None)

        section = {
            "section_type": "explanation",
            "content": "テスト",
            "tts_text": "テスト",
            "emotion": "neutral",
            "dialogues": "",  # 空
            "order_index": 0,
        }
        await runner._play_section(section)

        # 単話者モード: speakが1回
        assert mock_speech.speak.call_count == 1
        call = mock_speech.speak.call_args_list[0]
        assert call.kwargs.get("avatar_id", "teacher") == "teacher"

    @pytest.mark.asyncio
    async def test_play_section_no_student_config(self, mock_speech, test_db):
        """student_cfgがNoneならdialoguesがあっても単話者再生"""
        dialogues = json.dumps([
            {"speaker": "teacher", "content": "Hello", "emotion": "neutral"},
            {"speaker": "student", "content": "Hi", "emotion": "joy"},
        ])
        on_overlay = AsyncMock()
        runner = LessonRunner(speech=mock_speech, on_overlay=on_overlay)
        runner._teacher_cfg = {"name": "先生"}
        runner._student_cfg = None  # 生徒なし
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._sections = [{}]
        runner._current_index = 0

        mock_speech.generate_tts = AsyncMock(return_value=None)

        section = {
            "section_type": "introduction",
            "content": "HelloHi",
            "tts_text": "HelloHi",
            "emotion": "neutral",
            "dialogues": dialogues,
            "order_index": 0,
        }
        await runner._play_section(section)

        # 単話者モード: speakはcontent分割分だけ
        assert mock_speech.speak.call_count == 1
