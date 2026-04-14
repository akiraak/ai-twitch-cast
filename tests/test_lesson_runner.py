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
        assert status["generator"] == "gemini"
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
        """キャッシュパスの生成（バージョン別サブディレクトリ）"""
        p = _cache_path(1, 0, 2)
        assert p.name == "section_00_part_02.wav"
        assert "lessons/1/ja/gemini/v1/" in str(p)

    def test_cache_path_with_generator(self):
        """claude generatorのキャッシュパス"""
        p = _cache_path(1, 0, 2, generator="claude")
        assert "lessons/1/ja/claude/v1/" in str(p)
        assert p.name == "section_00_part_02.wav"

    def test_cache_path_with_version(self):
        """バージョン指定のキャッシュパス"""
        p = _cache_path(1, 0, 2, version_number=3)
        assert "lessons/1/ja/gemini/v3/" in str(p)
        assert p.name == "section_00_part_02.wav"

    def test_cache_path_v2_no_legacy_fallback(self, tmp_path, monkeypatch):
        """v2以降ではレガシーパスにフォールバックしない"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        # generator直下にファイル（バージョニング前レガシー）
        gen_dir = tmp_path / "1" / "ja" / "gemini"
        gen_dir.mkdir(parents=True)
        (gen_dir / "section_00_part_00.wav").write_bytes(b"legacy")

        p = _cache_path(1, 0, 0, generator="gemini", version_number=2)
        assert "v2" in str(p)
        assert not p.exists()  # フォールバックしない

    def test_cache_path_legacy_fallback(self, tmp_path, monkeypatch):
        """geminiの場合、旧パス（lang直下）のキャッシュにフォールバック"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        # 旧パスにキャッシュファイルを配置
        legacy_dir = tmp_path / "1" / "ja"
        legacy_dir.mkdir(parents=True)
        legacy_file = legacy_dir / "section_00_part_00.wav"
        legacy_file.write_bytes(b"legacy")

        p = _cache_path(1, 0, 0, generator="gemini")
        assert p == legacy_file

    def test_cache_path_no_legacy_for_claude(self, tmp_path, monkeypatch):
        """claude generatorでは旧パスにフォールバックしない"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        legacy_dir = tmp_path / "1" / "ja"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "section_00_part_00.wav").write_bytes(b"legacy")

        p = _cache_path(1, 0, 0, generator="claude")
        # 新パスを返す（存在しない）
        assert "claude" in str(p)
        assert not p.exists()

    def test_cache_path_pre_versioning_fallback(self, tmp_path, monkeypatch):
        """v1でgenerator直下のキャッシュにフォールバック（バージョニング導入前互換）"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        gen_dir = tmp_path / "1" / "ja" / "gemini"
        gen_dir.mkdir(parents=True)
        pre_ver_file = gen_dir / "section_00_part_00.wav"
        pre_ver_file.write_bytes(b"pre-versioning")

        p = _cache_path(1, 0, 0, generator="gemini", version_number=1)
        assert p == pre_ver_file

    def test_cache_path_new_path_preferred(self, tmp_path, monkeypatch):
        """v{N}パスが存在する場合はそちらを優先"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        # 旧パスと新パスの両方にファイルを配置
        legacy_dir = tmp_path / "1" / "ja"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "section_00_part_00.wav").write_bytes(b"legacy")
        gen_dir = tmp_path / "1" / "ja" / "gemini"
        gen_dir.mkdir(parents=True)
        (gen_dir / "section_00_part_00.wav").write_bytes(b"pre-ver")
        new_dir = gen_dir / "v1"
        new_dir.mkdir(parents=True)
        new_file = new_dir / "section_00_part_00.wav"
        new_file.write_bytes(b"new")

        p = _cache_path(1, 0, 0, generator="gemini")
        assert p == new_file

    def test_dlg_cache_path(self):
        """dialogue用キャッシュパスの生成"""
        p = _dlg_cache_path(1, 3, 1, lang="en")
        assert p.name == "section_03_dlg_01.wav"
        assert "lessons/1/en/gemini/v1/" in str(p)

    def test_dlg_cache_path_with_version(self):
        """dialogue用: バージョン指定のキャッシュパス"""
        p = _dlg_cache_path(1, 3, 1, lang="en", version_number=2)
        assert "lessons/1/en/gemini/v2/" in str(p)

    def test_dlg_cache_path_legacy_fallback(self, tmp_path, monkeypatch):
        """dialogue用: geminiの場合、旧パスにフォールバック"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        legacy_dir = tmp_path / "1" / "ja"
        legacy_dir.mkdir(parents=True)
        legacy_file = legacy_dir / "section_00_dlg_00.wav"
        legacy_file.write_bytes(b"legacy")

        p = _dlg_cache_path(1, 0, 0, generator="gemini")
        assert p == legacy_file

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
        """特定セクションのキャッシュ削除（レガシーファイル）"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        lesson_dir = tmp_path / "1"
        lesson_dir.mkdir()
        (lesson_dir / "section_00_part_00.wav").write_bytes(b"x")
        (lesson_dir / "section_01_part_00.wav").write_bytes(b"x")

        clear_tts_cache(1, order_index=0)
        assert not (lesson_dir / "section_00_part_00.wav").exists()
        assert (lesson_dir / "section_01_part_00.wav").exists()

    def test_clear_tts_cache_section_with_generator_subdir(self, tmp_path, monkeypatch):
        """特定セクション削除時にgeneratorサブディレクトリも削除される"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        lang_dir = tmp_path / "1" / "ja"
        # レガシーファイル
        lang_dir.mkdir(parents=True)
        (lang_dir / "section_00_part_00.wav").write_bytes(b"x")
        # generatorサブディレクトリのファイル
        gen_dir = lang_dir / "gemini"
        gen_dir.mkdir()
        (gen_dir / "section_00_part_00.wav").write_bytes(b"x")
        (gen_dir / "section_01_part_00.wav").write_bytes(b"x")

        clear_tts_cache(1, order_index=0, lang="ja")
        assert not (lang_dir / "section_00_part_00.wav").exists()
        assert not (gen_dir / "section_00_part_00.wav").exists()
        assert (gen_dir / "section_01_part_00.wav").exists()

    def test_clear_tts_cache_specific_generator(self, tmp_path, monkeypatch):
        """特定generatorのキャッシュのみ削除"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        # geminiとclaudeのキャッシュ
        gemini_dir = tmp_path / "1" / "ja" / "gemini"
        claude_dir = tmp_path / "1" / "ja" / "claude"
        gemini_dir.mkdir(parents=True)
        claude_dir.mkdir(parents=True)
        (gemini_dir / "section_00_part_00.wav").write_bytes(b"x")
        (claude_dir / "section_00_part_00.wav").write_bytes(b"x")

        clear_tts_cache(1, lang="ja", generator="claude")
        assert not claude_dir.exists()
        assert (gemini_dir / "section_00_part_00.wav").exists()

    def test_clear_tts_cache_specific_generator_section(self, tmp_path, monkeypatch):
        """特定generator+特定セクションのキャッシュ削除"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        gen_dir = tmp_path / "1" / "ja" / "claude"
        gen_dir.mkdir(parents=True)
        (gen_dir / "section_00_part_00.wav").write_bytes(b"x")
        (gen_dir / "section_00_dlg_00.wav").write_bytes(b"x")
        (gen_dir / "section_01_part_00.wav").write_bytes(b"x")

        clear_tts_cache(1, order_index=0, lang="ja", generator="claude")
        assert not (gen_dir / "section_00_part_00.wav").exists()
        assert not (gen_dir / "section_00_dlg_00.wav").exists()
        assert (gen_dir / "section_01_part_00.wav").exists()

    def test_clear_tts_cache_nonexistent(self, tmp_path, monkeypatch):
        """存在しないキャッシュディレクトリの削除はエラーにならない"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        clear_tts_cache(999)  # no error
        clear_tts_cache(999, generator="claude")  # no error

    def test_get_tts_cache_info(self, tmp_path, monkeypatch, test_db):
        """キャッシュ情報取得（レガシーパス互換）"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        monkeypatch.setattr("src.lesson_runner.PROJECT_DIR", tmp_path.parent)

        # レッスン・セクション作成
        lesson = test_db.create_lesson("CacheInfoTest")
        lid = lesson["id"]
        test_db.add_lesson_section(lid, 0, "intro", "Hello")
        test_db.add_lesson_section(lid, 1, "explain", "World")

        # セクション0のキャッシュを作成（レガシー: lang直下）
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

    def test_get_tts_cache_info_new_path(self, tmp_path, monkeypatch, test_db):
        """キャッシュ情報取得（新パス構造: generator別サブディレクトリ）"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        monkeypatch.setattr("src.lesson_runner.PROJECT_DIR", tmp_path.parent)

        lesson = test_db.create_lesson("NewPathTest")
        lid = lesson["id"]
        test_db.add_lesson_section(lid, 0, "intro", "Hello", generator="claude")

        # 新パス構造のキャッシュ
        cache_dir = tmp_path / str(lid) / "ja" / "claude"
        cache_dir.mkdir(parents=True)
        (cache_dir / "section_00_part_00.wav").write_bytes(b"data")

        info = get_tts_cache_info(lid, generator="claude")
        assert len(info) == 1
        assert info[0]["order_index"] == 0
        assert len(info[0]["parts"]) == 1
        assert info[0]["parts"][0]["size"] == 4


class TestVersionedTtsCache:
    """バージョン別TTSキャッシュのテスト"""

    def test_cache_path_versioned(self, tmp_path, monkeypatch):
        """バージョン別パスにキャッシュファイルが見つかる"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        v2_dir = tmp_path / "1" / "ja" / "gemini" / "v2"
        v2_dir.mkdir(parents=True)
        v2_file = v2_dir / "section_00_part_00.wav"
        v2_file.write_bytes(b"v2data")

        p = _cache_path(1, 0, 0, version_number=2)
        assert p == v2_file

    def test_clear_tts_cache_specific_version(self, tmp_path, monkeypatch):
        """特定バージョンのキャッシュのみ削除"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        v1_dir = tmp_path / "1" / "ja" / "claude" / "v1"
        v2_dir = tmp_path / "1" / "ja" / "claude" / "v2"
        v1_dir.mkdir(parents=True)
        v2_dir.mkdir(parents=True)
        (v1_dir / "section_00_part_00.wav").write_bytes(b"v1")
        (v2_dir / "section_00_part_00.wav").write_bytes(b"v2")

        clear_tts_cache(1, lang="ja", generator="claude", version_number=2)
        assert (v1_dir / "section_00_part_00.wav").exists()
        assert not (v2_dir / "section_00_part_00.wav").exists()

    def test_clear_tts_cache_version_with_section(self, tmp_path, monkeypatch):
        """特定バージョン+特定セクションのキャッシュ削除"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        v1_dir = tmp_path / "1" / "ja" / "claude" / "v1"
        v1_dir.mkdir(parents=True)
        (v1_dir / "section_00_part_00.wav").write_bytes(b"x")
        (v1_dir / "section_01_part_00.wav").write_bytes(b"x")

        clear_tts_cache(1, order_index=0, lang="ja", generator="claude", version_number=1)
        assert not (v1_dir / "section_00_part_00.wav").exists()
        assert (v1_dir / "section_01_part_00.wav").exists()

    def test_clear_v1_also_clears_legacy(self, tmp_path, monkeypatch):
        """v1削除時はgenerator直下のレガシーファイルも削除"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        gen_dir = tmp_path / "1" / "ja" / "gemini"
        gen_dir.mkdir(parents=True)
        # バージョニング前レガシー（generator直下）
        (gen_dir / "section_00_part_00.wav").write_bytes(b"legacy")
        # v1サブディレクトリ
        v1_dir = gen_dir / "v1"
        v1_dir.mkdir()
        (v1_dir / "section_01_part_00.wav").write_bytes(b"v1")
        # lang直下レガシー（gemini + v1）
        lang_dir = tmp_path / "1" / "ja"
        (lang_dir / "section_02_part_00.wav").write_bytes(b"old-legacy")

        clear_tts_cache(1, lang="ja", generator="gemini", version_number=1)
        assert not (gen_dir / "section_00_part_00.wav").exists()
        assert not (v1_dir / "section_01_part_00.wav").exists()
        assert not (lang_dir / "section_02_part_00.wav").exists()

    def test_clear_all_versions_none(self, tmp_path, monkeypatch):
        """version_number=None: 全バージョン削除"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        gen_dir = tmp_path / "1" / "ja" / "claude"
        v1_dir = gen_dir / "v1"
        v2_dir = gen_dir / "v2"
        v1_dir.mkdir(parents=True)
        v2_dir.mkdir(parents=True)
        (v1_dir / "section_00_part_00.wav").write_bytes(b"v1")
        (v2_dir / "section_00_part_00.wav").write_bytes(b"v2")

        clear_tts_cache(1, lang="ja", generator="claude", version_number=None)
        assert not gen_dir.exists()

    def test_get_tts_cache_info_versioned(self, tmp_path, monkeypatch, test_db):
        """バージョン別のキャッシュ情報取得"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        monkeypatch.setattr("src.lesson_runner.PROJECT_DIR", tmp_path.parent)

        lesson = test_db.create_lesson("VersionedCacheTest")
        lid = lesson["id"]
        test_db.add_lesson_section(lid, 0, "intro", "Hello", version_number=2)

        # v2のキャッシュ
        cache_dir = tmp_path / str(lid) / "ja" / "gemini" / "v2"
        cache_dir.mkdir(parents=True)
        (cache_dir / "section_00_part_00.wav").write_bytes(b"v2wav")

        info = get_tts_cache_info(lid, version_number=2)
        assert len(info) == 1
        assert info[0]["order_index"] == 0
        assert len(info[0]["parts"]) == 1
        assert info[0]["parts"][0]["size"] == 5

    def test_get_tts_cache_info_v1_legacy(self, tmp_path, monkeypatch, test_db):
        """v1のキャッシュ情報取得ではレガシーパスも含む"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)
        monkeypatch.setattr("src.lesson_runner.PROJECT_DIR", tmp_path.parent)

        lesson = test_db.create_lesson("LegacyCacheTest")
        lid = lesson["id"]
        test_db.add_lesson_section(lid, 0, "intro", "Hello")

        # レガシーパス（lang直下）
        cache_dir = tmp_path / str(lid) / "ja"
        cache_dir.mkdir(parents=True)
        (cache_dir / "section_00_part_00.wav").write_bytes(b"legacy")

        info = get_tts_cache_info(lid, version_number=1)
        assert len(info) == 1
        assert len(info[0]["parts"]) == 1

    def test_get_status_includes_version(self, runner):
        """get_statusにversion_numberが含まれる"""
        status = runner.get_status()
        assert "version_number" in status
        assert status["version_number"] == 1


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
        """student_cfgがNoneでもdialoguesがあれば対話モードで再生"""
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

        # 対話モード: dialogueの各エントリ分speakが呼ばれる
        assert mock_speech.speak.call_count == 2

    @pytest.mark.asyncio
    async def test_play_section_sends_display_properties(self, mock_speech, test_db):
        """display_propertiesがあればWebSocketイベントに含まれる"""
        on_overlay = AsyncMock()
        runner = LessonRunner(speech=mock_speech, on_overlay=on_overlay)
        runner._teacher_cfg = {"name": "先生"}
        runner._student_cfg = None
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
            "display_text": "表示テキスト",
            "emotion": "neutral",
            "dialogues": "",
            "order_index": 0,
            "display_properties": json.dumps({"maxHeight": 40, "fontSize": 1.2}),
        }
        await runner._play_section(section)

        # lesson_text_showイベントにdisplay_propertiesが含まれる
        overlay_calls = [c.args[0] for c in on_overlay.call_args_list
                         if c.args[0].get("type") == "lesson_text_show"]
        assert len(overlay_calls) >= 1
        assert overlay_calls[0]["display_properties"] == {"maxHeight": 40, "fontSize": 1.2}

    @pytest.mark.asyncio
    async def test_play_section_no_display_properties(self, mock_speech, test_db):
        """display_propertiesが空ならイベントに含まれない"""
        on_overlay = AsyncMock()
        runner = LessonRunner(speech=mock_speech, on_overlay=on_overlay)
        runner._teacher_cfg = {"name": "先生"}
        runner._student_cfg = None
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
            "display_text": "表示テキスト",
            "emotion": "neutral",
            "dialogues": "",
            "order_index": 0,
            "display_properties": "{}",
        }
        await runner._play_section(section)

        overlay_calls = [c.args[0] for c in on_overlay.call_args_list
                         if c.args[0].get("type") == "lesson_text_show"]
        assert len(overlay_calls) >= 1
        assert "display_properties" not in overlay_calls[0]
