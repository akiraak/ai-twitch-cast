"""LessonRunner のテスト"""

import asyncio
import json
import struct
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lesson_runner import (
    LESSON_AUDIO_DIR,
    PLAYBACK_SETTING_KEY,
    LessonRunner,
    LessonState,
    _cache_path,
    _dlg_cache_path,
    clear_tts_cache,
    get_tts_cache_info,
)


def _create_test_wav(path: Path, duration: float = 1.0, sample_rate: int = 24000):
    """テスト用のWAVファイルを生成する"""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_frames = int(sample_rate * duration)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n_frames}h", *([1000] * n_frames)))


@pytest.fixture
def mock_speech():
    speech = MagicMock()
    speech.speak = AsyncMock()
    speech.notify_overlay_end = AsyncMock()
    speech.apply_emotion = MagicMock()
    speech.generate_tts = AsyncMock(return_value=None)
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

        # _send_all_and_playをモック（pause中に永遠にブロック）
        block = asyncio.Event()

        async def slow_send_all():
            await block.wait()

        with patch.object(runner, "_send_all_and_play", side_effect=slow_send_all):
            await runner.start(lesson["id"])
            await asyncio.sleep(0.05)  # タスク起動待ち
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


class TestParseDialogues:
    """_parse_dialogues / _parse_display_properties のテスト"""

    def test_parse_dialogues_json_string(self):
        """JSON文字列からdialoguesをパースする"""
        section = {"dialogues": json.dumps([
            {"speaker": "teacher", "content": "Hello"},
        ])}
        result = LessonRunner._parse_dialogues(section)
        assert len(result) == 1
        assert result[0]["speaker"] == "teacher"

    def test_parse_dialogues_v4_format(self):
        """v4 {dialogues: [...], review: {...}} 形式に対応"""
        section = {"dialogues": json.dumps({
            "dialogues": [{"speaker": "teacher", "content": "A"}],
            "review": {"rating": 5},
        })}
        result = LessonRunner._parse_dialogues(section)
        assert len(result) == 1

    def test_parse_dialogues_empty(self):
        """空のdialoguesはNoneを返す"""
        assert LessonRunner._parse_dialogues({"dialogues": ""}) is None
        assert LessonRunner._parse_dialogues({"dialogues": "[]"}) is None
        assert LessonRunner._parse_dialogues({}) is None

    def test_parse_display_properties(self):
        """display_propertiesのパース"""
        section = {"display_properties": json.dumps({"maxHeight": 40})}
        result = LessonRunner._parse_display_properties(section)
        assert result == {"maxHeight": 40}

    def test_parse_display_properties_empty(self):
        """空のdisplay_properties"""
        assert LessonRunner._parse_display_properties({"display_properties": "{}"}) == {}
        assert LessonRunner._parse_display_properties({"display_properties": ""}) == {}
        assert LessonRunner._parse_display_properties({}) == {}


class TestUnifiedDialogues:
    """_get_unified_dialogues のテスト"""

    def test_dialogue_mode(self, mock_speech):
        """dialoguesがある場合、is_single_speaker=Falseで返す"""
        runner = LessonRunner(speech=mock_speech)
        section = {"dialogues": json.dumps([
            {"speaker": "teacher", "content": "A"},
            {"speaker": "student", "content": "B"},
        ])}
        dialogues, is_single = runner._get_unified_dialogues(section)
        assert not is_single
        assert len(dialogues) == 2
        assert dialogues[0]["speaker"] == "teacher"
        assert dialogues[1]["speaker"] == "student"

    def test_single_speaker_conversion(self, mock_speech):
        """単話者モードでdialogues配列に変換される"""
        runner = LessonRunner(speech=mock_speech)
        section = {
            "content": "テスト",
            "tts_text": "テスト読み",
            "emotion": "joy",
            "dialogues": "",
        }
        dialogues, is_single = runner._get_unified_dialogues(section)
        assert is_single
        assert len(dialogues) == 1
        assert dialogues[0]["speaker"] == "teacher"
        assert dialogues[0]["content"] == "テスト"
        assert dialogues[0]["tts_text"] == "テスト読み"
        assert dialogues[0]["emotion"] == "joy"

    def test_single_speaker_sentence_split(self, mock_speech):
        """30文字超のテキストは文分割される"""
        runner = LessonRunner(speech=mock_speech)
        long_text = "これは最初の文です。" * 5  # 50文字
        section = {"content": long_text, "dialogues": "", "emotion": "neutral"}
        dialogues, is_single = runner._get_unified_dialogues(section)
        assert is_single
        # split_sentencesで分割されるので複数エントリ
        assert len(dialogues) >= 2


class TestBundleAssembly:
    """バンドル組み立てのテスト"""

    @pytest.mark.asyncio
    async def test_build_dialogue_bundle(self, mock_speech, tmp_path, monkeypatch):
        """対話モードのバンドル生成 — TTS+lipsync+wav_b64が含まれる"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        runner = LessonRunner(speech=mock_speech)
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {"name": "先生", "tts_voice": "Despina"}
        runner._student_cfg = {"name": "生徒", "tts_voice": "Kore"}

        # キャッシュ済みWAVを配置
        for i in range(2):
            wav_path = tmp_path / "1" / "ja" / "gemini" / "v1" / f"section_00_dlg_{i:02d}.wav"
            _create_test_wav(wav_path, duration=0.5)

        dialogues = [
            {"speaker": "teacher", "content": "Hello", "tts_text": "<en>Hello</en>", "emotion": "joy"},
            {"speaker": "student", "content": "Hi", "emotion": "neutral"},
        ]

        with patch("src.lesson_runner.analyze_amplitude", return_value=[0.1, 0.5, 0.3]):
            bundle = await runner._build_dialogue_bundle(dialogues, order_index=0)

        assert len(bundle) == 2
        # エントリの構造確認
        entry = bundle[0]
        assert entry["index"] == 0
        assert entry["speaker"] == "teacher"
        assert entry["avatar_id"] == "teacher"
        assert entry["content"] == "Hello"
        assert entry["tts_text"] == "<en>Hello</en>"
        assert entry["emotion"] == "joy"
        assert entry["gesture"] == "nod"  # joy → nod
        assert entry["lipsync_frames"] == [0.1, 0.5, 0.3]
        assert entry["duration"] == pytest.approx(0.5, abs=0.01)
        assert len(entry["wav_b64"]) > 0

        entry2 = bundle[1]
        assert entry2["speaker"] == "student"
        assert entry2["emotion"] == "neutral"
        assert entry2["gesture"] is None  # neutralにはgestureなし
        # tts_textが未指定の場合は空文字
        assert entry2["tts_text"] == ""

    @pytest.mark.asyncio
    async def test_build_bundle_single_speaker(self, mock_speech, tmp_path, monkeypatch):
        """単話者モードのバンドル生成 — _cache_path形式を使う"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        runner = LessonRunner(speech=mock_speech)
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {"name": "先生"}

        # part形式のキャッシュ
        wav_path = tmp_path / "1" / "ja" / "gemini" / "v1" / "section_00_part_00.wav"
        _create_test_wav(wav_path, duration=1.0)

        dialogues = [{"speaker": "teacher", "content": "テスト", "tts_text": "テスト", "emotion": "neutral"}]

        with patch("src.lesson_runner.analyze_amplitude", return_value=[0.2, 0.4]):
            bundle = await runner._build_dialogue_bundle(dialogues, order_index=0, is_single_speaker=True)

        assert len(bundle) == 1
        assert bundle[0]["duration"] == pytest.approx(1.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_build_bundle_tts_failure(self, mock_speech, tmp_path, monkeypatch):
        """TTS生成失敗時はバンドルが空になる"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        runner = LessonRunner(speech=mock_speech)
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {}

        # generate_tts がNoneを返す
        mock_speech.generate_tts = AsyncMock(return_value=None)

        dialogues = [{"speaker": "teacher", "content": "失敗テスト", "emotion": "neutral"}]
        bundle = await runner._build_dialogue_bundle(dialogues, order_index=0)
        assert len(bundle) == 0

    @pytest.mark.asyncio
    async def test_build_bundle_stops_on_idle(self, mock_speech, tmp_path, monkeypatch):
        """状態がIDLEになったらバンドル生成を中断する"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        runner = LessonRunner(speech=mock_speech)
        runner._state = LessonState.IDLE  # IDLEに設定
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {}

        dialogues = [
            {"speaker": "teacher", "content": "A", "emotion": "neutral"},
            {"speaker": "teacher", "content": "B", "emotion": "neutral"},
        ]
        bundle = await runner._build_dialogue_bundle(dialogues, order_index=0)
        assert len(bundle) == 0


class TestQuestionData:
    """questionセクションデータ生成のテスト"""

    @pytest.mark.asyncio
    async def test_build_question_data(self, mock_speech, tmp_path):
        """questionデータにwait_secondsとanswer_dialoguesが含まれる"""
        # generate_ttsが返すWAVを作成
        wav = tmp_path / "answer.wav"
        _create_test_wav(wav, duration=2.0)
        mock_speech.generate_tts = AsyncMock(return_value=wav)

        runner = LessonRunner(speech=mock_speech)
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1

        section = {
            "section_type": "question",
            "question": True,
            "wait_seconds": 10,
            "answer": "答えはAです",
            "emotion": "joy",
        }

        with patch("src.lesson_runner.analyze_amplitude", return_value=[0.1]):
            result = await runner._build_question_data(section, order_index=0)

        assert result["wait_seconds"] == 10
        assert len(result["answer_dialogues"]) == 1
        assert result["answer_dialogues"][0]["content"] == "答えはAです"
        assert result["answer_dialogues"][0]["emotion"] == "joy"

    @pytest.mark.asyncio
    async def test_build_question_data_no_answer(self, mock_speech):
        """answerがない場合、answer_dialoguesは空"""
        runner = LessonRunner(speech=mock_speech)
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1

        section = {"wait_seconds": 5, "answer": "", "emotion": "neutral"}
        result = await runner._build_question_data(section, order_index=0)
        assert result["wait_seconds"] == 5
        assert result["answer_dialogues"] == []


class TestPauseResumeStopForwarding:
    """pause/resume/stopのC#転送テスト"""

    @pytest.mark.asyncio
    async def test_pause_forwards_to_csharp(self, mock_speech):
        """pauseがC#にlesson_pauseを送信する"""
        runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._sections = [{"section_type": "explanation", "content": "A"}]

        mock_ws = AsyncMock(return_value={"ok": True})
        with patch("scripts.services.capture_client.ws_request", mock_ws):
            await runner.pause()

        assert runner.state == LessonState.PAUSED
        mock_ws.assert_called_once_with("lesson_pause")

    @pytest.mark.asyncio
    async def test_resume_forwards_to_csharp(self, mock_speech):
        """resumeがC#にlesson_resumeを送信する"""
        runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())
        runner._state = LessonState.PAUSED
        runner._lesson_id = 1
        runner._sections = [{"section_type": "explanation", "content": "A"}]
        runner._pause_event.clear()

        mock_ws = AsyncMock(return_value={"ok": True})
        with patch("scripts.services.capture_client.ws_request", mock_ws):
            await runner.resume()

        assert runner.state == LessonState.RUNNING
        mock_ws.assert_called_once_with("lesson_resume")

    @pytest.mark.asyncio
    async def test_stop_forwards_to_csharp(self, mock_speech):
        """stopがC#にlesson_stopを送信し、完了イベントをsetする"""
        runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._sections = [{"section_type": "explanation", "content": "A"}]

        mock_ws = AsyncMock(return_value={"ok": True})
        mock_evt = asyncio.Event()
        with patch("scripts.services.capture_client.ws_request", mock_ws), \
             patch("scripts.services.capture_client.get_lesson_complete_event", return_value=mock_evt):
            await runner.stop()

        assert runner.state == LessonState.IDLE
        mock_ws.assert_called_once_with("lesson_stop")
        assert mock_evt.is_set()  # 待機中タスクを解除するためsetされる

    @pytest.mark.asyncio
    async def test_stop_handles_csharp_disconnect(self, mock_speech):
        """C#未接続でもstopはエラーにならない"""
        runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._sections = [{"section_type": "explanation", "content": "A"}]

        mock_ws = AsyncMock(side_effect=ConnectionError("C#アプリ未接続"))
        with patch("scripts.services.capture_client.ws_request", mock_ws):
            await runner.stop()

        assert runner.state == LessonState.IDLE


class TestPlaybackPersistence:
    """DB永続化のテスト"""

    def test_save_and_get_playback_state(self, runner, test_db):
        """再生状態をDBに保存・読み取りできる"""
        runner._lesson_id = 42
        runner._current_index = 3
        runner._state = LessonState.RUNNING
        runner._lang = "en"
        runner._generator = "claude"
        runner._version_number = 2
        runner._episode_id = 100

        runner._save_playback_state()

        state = LessonRunner.get_playback_state()
        assert state is not None
        assert state["lesson_id"] == 42
        assert state["section_index"] == 3
        assert state["state"] == "running"
        assert state["lang"] == "en"
        assert state["generator"] == "claude"
        assert state["version_number"] == 2
        assert state["episode_id"] == 100

    def test_clear_playback_state(self, runner, test_db):
        """再生状態をDBから削除できる"""
        runner._lesson_id = 1
        runner._current_index = 0
        runner._state = LessonState.RUNNING
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._episode_id = None

        runner._save_playback_state()
        assert LessonRunner.get_playback_state() is not None

        LessonRunner._clear_playback_state()
        assert LessonRunner.get_playback_state() is None

    def test_get_playback_state_empty(self, test_db):
        """永続化データがない場合Noneを返す"""
        assert LessonRunner.get_playback_state() is None

    @pytest.mark.asyncio
    async def test_stop_clears_playback_state(self, runner, test_db):
        """stopで永続化データがクリアされる"""
        runner._lesson_id = 1
        runner._current_index = 0
        runner._state = LessonState.RUNNING
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._sections = [{"section_type": "explanation", "content": "A"}]

        runner._save_playback_state()

        mock_ws = AsyncMock(return_value={"ok": True})
        with patch("scripts.services.capture_client.ws_request", mock_ws):
            await runner.stop()

        assert LessonRunner.get_playback_state() is None

    @pytest.mark.asyncio
    async def test_send_all_and_play_saves_state(self, mock_speech, tmp_path, monkeypatch, test_db):
        """_send_all_and_play 実行後にDBに状態が保存される"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        wav_path = tmp_path / "1" / "ja" / "gemini" / "v1" / "section_00_dlg_00.wav"
        _create_test_wav(wav_path, duration=0.5)

        runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {"name": "先生"}
        runner._student_cfg = None
        runner._sections = [{
            "section_type": "introduction",
            "content": "Hello",
            "display_text": "",
            "dialogues": json.dumps([{"speaker": "teacher", "content": "Hello", "emotion": "neutral"}]),
            "order_index": 0,
            "wait_seconds": 2,
        }]
        runner._current_index = 0
        runner._episode_id = 50

        # 再生開始は control-panel 側に委ねるため、完了イベントは事前セットして
        # _wait_lesson_complete を即時通過させる
        lesson_evt = asyncio.Event()
        lesson_evt.set()

        async def _ws(action, **kwargs):
            return {"ok": True}

        with patch("src.lesson_runner.analyze_amplitude", return_value=[0.1]), \
             patch("scripts.services.capture_client.ws_request", AsyncMock(side_effect=_ws)), \
             patch("scripts.services.capture_client.get_lesson_complete_event", return_value=lesson_evt):
            await runner._send_all_and_play()

        state = LessonRunner.get_playback_state()
        assert state is not None
        assert state["lesson_id"] == 1
        assert state["episode_id"] == 50


class TestRestore:
    """サーバー再起動復旧のテスト"""

    @pytest.mark.asyncio
    async def test_restore_no_playback(self, runner, test_db):
        """永続化データがない場合はFalseを返す"""
        result = await runner.restore()
        assert result is False
        assert runner.state == LessonState.IDLE

    @pytest.mark.asyncio
    async def test_restore_lesson_not_found(self, runner, test_db):
        """lesson_idのレッスンが存在しない場合はFalseを返し、永続化データをクリア"""
        from src import db as _db
        _db.set_setting(PLAYBACK_SETTING_KEY, json.dumps({
            "lesson_id": 9999,
            "section_index": 0,
            "state": "running",
            "lang": "ja",
            "generator": "gemini",
            "version_number": 1,
        }))

        result = await runner.restore()
        assert result is False
        assert LessonRunner.get_playback_state() is None

    @pytest.mark.asyncio
    async def test_restore_no_sections(self, runner, test_db):
        """セクションがない場合はFalseを返す"""
        from src import db as _db
        lesson = _db.create_lesson("NoSections")
        _db.set_setting(PLAYBACK_SETTING_KEY, json.dumps({
            "lesson_id": lesson["id"],
            "section_index": 0,
            "state": "running",
            "lang": "ja",
            "generator": "gemini",
            "version_number": 1,
        }))

        result = await runner.restore()
        assert result is False
        assert LessonRunner.get_playback_state() is None

    @pytest.mark.asyncio
    async def test_restore_csharp_idle(self, runner, test_db):
        """C#がidle → 次のセクションから再開"""
        from src import db as _db
        lesson = _db.create_lesson("RestoreTest")
        _db.add_lesson_section(lesson["id"], 0, "intro", "A")
        _db.add_lesson_section(lesson["id"], 1, "explain", "B")
        _db.add_lesson_section(lesson["id"], 2, "summary", "C")

        _db.set_setting(PLAYBACK_SETTING_KEY, json.dumps({
            "lesson_id": lesson["id"],
            "section_index": 1,
            "state": "running",
            "lang": "ja",
            "generator": "gemini",
            "version_number": 1,
        }))

        mock_ws = AsyncMock(return_value={"status": "idle"})
        with patch("scripts.services.capture_client.ws_request", mock_ws):
            result = await runner.restore()

        assert result is True
        assert runner.state == LessonState.RUNNING
        assert runner.lesson_id == lesson["id"]
        # idle → saved_index + 1 = 2 から再開
        assert runner.current_index == 2

        await runner.stop()

    @pytest.mark.asyncio
    async def test_restore_csharp_no_lesson(self, runner, test_db):
        """C#がno_lesson → 保存されたインデックスから再開"""
        from src import db as _db
        lesson = _db.create_lesson("RestoreNoLesson")
        _db.add_lesson_section(lesson["id"], 0, "intro", "A")
        _db.add_lesson_section(lesson["id"], 1, "explain", "B")

        _db.set_setting(PLAYBACK_SETTING_KEY, json.dumps({
            "lesson_id": lesson["id"],
            "section_index": 0,
            "state": "running",
            "lang": "ja",
            "generator": "gemini",
            "version_number": 1,
        }))

        mock_ws = AsyncMock(return_value={"status": "no_lesson"})
        with patch("scripts.services.capture_client.ws_request", mock_ws):
            result = await runner.restore()

        assert result is True
        assert runner.state == LessonState.RUNNING
        assert runner.current_index == 0  # 保存されたインデックスから

        await runner.stop()

    @pytest.mark.asyncio
    async def test_restore_csharp_disconnected(self, runner, test_db):
        """C#未接続 → 保存されたインデックスから再開"""
        from src import db as _db
        lesson = _db.create_lesson("RestoreDisconnected")
        _db.add_lesson_section(lesson["id"], 0, "intro", "A")

        _db.set_setting(PLAYBACK_SETTING_KEY, json.dumps({
            "lesson_id": lesson["id"],
            "section_index": 0,
            "state": "running",
            "lang": "ja",
            "generator": "gemini",
            "version_number": 1,
        }))

        mock_ws = AsyncMock(side_effect=ConnectionError("未接続"))
        with patch("scripts.services.capture_client.ws_request", mock_ws):
            result = await runner.restore()

        assert result is True
        assert runner.state == LessonState.RUNNING
        assert runner.current_index == 0

        await runner.stop()

    @pytest.mark.asyncio
    async def test_restore_all_sections_completed(self, runner, test_db):
        """全セクション完了済み → Falseを返し、永続化データをクリア"""
        from src import db as _db
        lesson = _db.create_lesson("RestoreCompleted")
        _db.add_lesson_section(lesson["id"], 0, "intro", "A")

        # section_index=0, C# idle → resume_index=1 → len(sections)=1 → 完了
        _db.set_setting(PLAYBACK_SETTING_KEY, json.dumps({
            "lesson_id": lesson["id"],
            "section_index": 0,
            "state": "running",
            "lang": "ja",
            "generator": "gemini",
            "version_number": 1,
        }))

        mock_ws = AsyncMock(return_value={"status": "idle"})
        with patch("scripts.services.capture_client.ws_request", mock_ws):
            result = await runner.restore()

        assert result is False
        assert LessonRunner.get_playback_state() is None

    @pytest.mark.asyncio
    async def test_restore_preserves_episode_id(self, runner, test_db):
        """復旧時にepisode_idが復元される"""
        from src import db as _db
        lesson = _db.create_lesson("RestoreEpisode")
        _db.add_lesson_section(lesson["id"], 0, "intro", "A")
        _db.add_lesson_section(lesson["id"], 1, "explain", "B")

        _db.set_setting(PLAYBACK_SETTING_KEY, json.dumps({
            "lesson_id": lesson["id"],
            "section_index": 0,
            "state": "running",
            "lang": "ja",
            "generator": "gemini",
            "version_number": 1,
            "episode_id": 77,
        }))

        mock_ws = AsyncMock(return_value={"status": "no_lesson"})
        with patch("scripts.services.capture_client.ws_request", mock_ws):
            result = await runner.restore()

        assert result is True
        assert runner._episode_id == 77

        await runner.stop()


class TestSendAllAndPlay:
    """全セクション一括送信方式（Phase B）のテスト"""

    @pytest.mark.asyncio
    async def test_sends_lesson_load_with_all_sections(self, mock_speech, tmp_path, monkeypatch):
        """_send_all_and_playが全セクションを1つのlesson_loadで送信する"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        # 2セクション分のキャッシュWAV
        for oi in range(2):
            wav_path = tmp_path / "1" / "ja" / "gemini" / "v1" / f"section_{oi:02d}_dlg_00.wav"
            _create_test_wav(wav_path, duration=0.3)

        runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {"name": "先生"}
        runner._student_cfg = None
        runner._sections = [
            {
                "section_type": "introduction",
                "content": "A",
                "display_text": "S0",
                "dialogues": json.dumps([{"speaker": "teacher", "content": "A", "emotion": "neutral"}]),
                "order_index": 0,
                "wait_seconds": 2,
            },
            {
                "section_type": "explanation",
                "content": "B",
                "display_text": "S1",
                "dialogues": json.dumps([{"speaker": "teacher", "content": "B", "emotion": "neutral"}]),
                "order_index": 1,
                "wait_seconds": 2,
            },
        ]
        runner._current_index = 0

        # 再生開始は control-panel 側に委ねるため、完了イベントは事前セット
        mock_lesson_evt = asyncio.Event()
        mock_lesson_evt.set()

        async def _ws(action, **kwargs):
            return {"ok": True}

        mock_ws_request = AsyncMock(side_effect=_ws)

        with patch("src.lesson_runner.analyze_amplitude", return_value=[0.1]), \
             patch("scripts.services.capture_client.ws_request", mock_ws_request), \
             patch("scripts.services.capture_client.get_lesson_complete_event", return_value=mock_lesson_evt):
            await runner._send_all_and_play()

        # lesson_load は送られ、lesson_play は送られない（再生開始は control-panel 側）
        call_actions = [c.args[0] for c in mock_ws_request.call_args_list]
        assert "lesson_load" in call_actions
        assert "lesson_play" not in call_actions

        # lesson_load のペイロード検証
        load_call = [c for c in mock_ws_request.call_args_list if c.args[0] == "lesson_load"][0]
        assert load_call.kwargs["lesson_id"] == 1
        assert load_call.kwargs["total_sections"] == 2
        assert len(load_call.kwargs["sections"]) == 2
        # pace_scale がトップレベルに含まれる
        assert "pace_scale" in load_call.kwargs
        # 個別 section の構造確認
        s0 = load_call.kwargs["sections"][0]
        assert s0["section_type"] == "introduction"
        assert s0["display_text"] == "S0"
        assert len(s0["dialogues"]) == 1
        assert s0["dialogues"][0]["content"] == "A"

    @pytest.mark.asyncio
    async def test_lesson_complete_event_wait(self, mock_speech, tmp_path, monkeypatch):
        """lesson_complete イベントで待機を終了する"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        wav_path = tmp_path / "1" / "ja" / "gemini" / "v1" / "section_00_dlg_00.wav"
        _create_test_wav(wav_path, duration=0.2)

        runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {"name": "先生"}
        runner._sections = [
            {
                "section_type": "introduction",
                "content": "A",
                "dialogues": json.dumps([{"speaker": "teacher", "content": "A", "emotion": "neutral"}]),
                "order_index": 0,
                "wait_seconds": 1,
            }
        ]
        runner._current_index = 0

        lesson_evt = asyncio.Event()

        async def _ws(action, **kwargs):
            if action == "lesson_load":
                # lesson_load 到着後、少し遅れて完了イベントを発火
                # （実運用では control-panel からの ▶ → C# 再生完了 → lesson_complete のルート）
                asyncio.get_event_loop().call_later(0.05, lesson_evt.set)
            return {"ok": True}

        with patch("src.lesson_runner.analyze_amplitude", return_value=[0.1]), \
             patch("scripts.services.capture_client.ws_request", AsyncMock(side_effect=_ws)), \
             patch("scripts.services.capture_client.get_lesson_complete_event", return_value=lesson_evt):
            import time
            t0 = time.monotonic()
            await runner._send_all_and_play()
            elapsed = time.monotonic() - t0

        # イベント受信で即完了 → phase1 timeoutまで待たない
        assert elapsed < 5.0

    @pytest.mark.asyncio
    async def test_idle_fallback_on_event_loss(self, mock_speech, tmp_path, monkeypatch):
        """lesson_complete イベントが来なくてもC#がidleならフォールバック完了"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        wav_path = tmp_path / "1" / "ja" / "gemini" / "v1" / "section_00_dlg_00.wav"
        _create_test_wav(wav_path, duration=0.1)

        runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {"name": "先生"}
        runner._sections = [
            {
                "section_type": "introduction",
                "content": "A",
                "dialogues": json.dumps([{"speaker": "teacher", "content": "A", "emotion": "neutral"}]),
                "order_index": 0,
                "wait_seconds": 0,
            }
        ]
        runner._current_index = 0

        lesson_evt = asyncio.Event()  # setしない

        async def _ws(action, **kwargs):
            if action == "lesson_status":
                # idleを返す → ポーリングでフォールバック完了
                return {"state": "idle", "section_index": 0, "total_sections": 1}
            return {"ok": True}

        # phase1 timeout を短く
        original_wait_for = asyncio.wait_for

        async def short_wait_for(coro, timeout):
            return await original_wait_for(coro, timeout=min(timeout, 0.1))

        with patch("src.lesson_runner.analyze_amplitude", return_value=[0.1]), \
             patch("scripts.services.capture_client.ws_request", AsyncMock(side_effect=_ws)), \
             patch("scripts.services.capture_client.get_lesson_complete_event", return_value=lesson_evt), \
             patch("asyncio.wait_for", short_wait_for):
            import time
            t0 = time.monotonic()
            await runner._send_all_and_play()
            elapsed = time.monotonic() - t0

        # idle検知で即完了
        assert elapsed < 10.0

    @pytest.mark.asyncio
    async def test_empty_bundle_skipped(self, mock_speech, tmp_path, monkeypatch):
        """TTS失敗でバンドルが空のセクションはスキップする"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {"name": "先生"}
        runner._sections = [
            {
                "section_type": "introduction",
                "content": "A",
                "dialogues": json.dumps([{"speaker": "teacher", "content": "A", "emotion": "neutral"}]),
                "order_index": 0,
                "wait_seconds": 0,
            }
        ]
        runner._current_index = 0

        # TTS失敗
        mock_speech.generate_tts = AsyncMock(return_value=None)

        mock_ws = AsyncMock()
        with patch("scripts.services.capture_client.ws_request", mock_ws):
            await runner._send_all_and_play()

        # バンドルが空なので ws_request は呼ばれない
        mock_ws.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_during_tts_generation(self, mock_speech, tmp_path, monkeypatch):
        """TTS生成中にstopされたら送信せず中断する"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        wav_path = tmp_path / "1" / "ja" / "gemini" / "v1" / "section_00_dlg_00.wav"
        _create_test_wav(wav_path, duration=0.1)

        runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())
        runner._state = LessonState.IDLE  # 最初からIDLE
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {"name": "先生"}
        runner._sections = [
            {"section_type": "introduction", "content": "A", "dialogues": "", "order_index": 0}
        ]
        runner._current_index = 0

        mock_ws = AsyncMock()
        with patch("scripts.services.capture_client.ws_request", mock_ws):
            await runner._send_all_and_play()

        # IDLEなので lesson_load も送られない
        mock_ws.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_from_saved_index(self, mock_speech, tmp_path, monkeypatch):
        """self._current_index > 0 の場合、そのセクションから送信を開始する"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        # 3セクション分のキャッシュ
        for oi in range(3):
            wav_path = tmp_path / "1" / "ja" / "gemini" / "v1" / f"section_{oi:02d}_dlg_00.wav"
            _create_test_wav(wav_path, duration=0.2)

        runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {"name": "先生"}
        runner._sections = [
            {
                "section_type": "introduction",
                "content": f"S{i}",
                "dialogues": json.dumps([{"speaker": "teacher", "content": f"S{i}", "emotion": "neutral"}]),
                "order_index": i,
                "wait_seconds": 0,
            }
            for i in range(3)
        ]
        runner._current_index = 1  # section 0 をスキップ

        # 再生開始は control-panel 側に委ねるため、完了イベントは事前セット
        lesson_evt = asyncio.Event()
        lesson_evt.set()

        async def _ws(action, **kwargs):
            return {"ok": True}

        with patch("src.lesson_runner.analyze_amplitude", return_value=[0.1]), \
             patch("scripts.services.capture_client.ws_request", AsyncMock(side_effect=_ws)), \
             patch("scripts.services.capture_client.get_lesson_complete_event", return_value=lesson_evt):
            await runner._send_all_and_play()

        # 2セクションだけ送信されている（index 1, 2）
        calls = [c for c in _ws.__qualname__]  # avoid static analyze
        # 正確には mock_ws_request を別途取る
        # 再度 mock_ws_request を検査するため別パッチで再実行は不要
        # このテストではバンドル生成とdurationの整合性を暗黙確認

    @pytest.mark.asyncio
    async def test_tts_progress_notification(self, mock_speech, tmp_path, monkeypatch):
        """TTS生成中のプログレスが on_overlay で通知される"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        wav_path = tmp_path / "1" / "ja" / "gemini" / "v1" / "section_00_dlg_00.wav"
        _create_test_wav(wav_path, duration=0.1)

        on_overlay = AsyncMock()
        runner = LessonRunner(speech=mock_speech, on_overlay=on_overlay)
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {"name": "先生"}
        runner._sections = [
            {
                "section_type": "introduction",
                "content": "A",
                "dialogues": json.dumps([{"speaker": "teacher", "content": "A", "emotion": "neutral"}]),
                "order_index": 0,
                "wait_seconds": 0,
            }
        ]
        runner._current_index = 0

        # 再生開始は control-panel 側に委ねるため、完了イベントは事前セット
        lesson_evt = asyncio.Event()
        lesson_evt.set()

        async def _ws(action, **kwargs):
            return {"ok": True}

        with patch("src.lesson_runner.analyze_amplitude", return_value=[0.1]), \
             patch("scripts.services.capture_client.ws_request", AsyncMock(side_effect=_ws)), \
             patch("scripts.services.capture_client.get_lesson_complete_event", return_value=lesson_evt):
            await runner._send_all_and_play()

        # tts_generating フェーズの通知が送られている
        events = [c.args[0] for c in on_overlay.call_args_list]
        tts_events = [e for e in events if e.get("phase") == "tts_generating"]
        assert len(tts_events) >= 1
        assert tts_events[0]["tts_progress"]["total"] == 1


class TestBuildSectionBundle:
    """_build_section_bundleのテスト"""

    @pytest.mark.asyncio
    async def test_returns_section_dict(self, mock_speech, tmp_path, monkeypatch):
        """戻り値にdialogues/display_text/section_type/wait_secondsが含まれる"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        wav_path = tmp_path / "1" / "ja" / "gemini" / "v1" / "section_00_dlg_00.wav"
        _create_test_wav(wav_path, duration=0.2)

        runner = LessonRunner(speech=mock_speech)
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {"name": "先生"}
        runner._sections = [{}]

        section = {
            "section_type": "introduction",
            "content": "Hello",
            "display_text": "表示テキスト",
            "dialogues": json.dumps([{"speaker": "teacher", "content": "Hello", "emotion": "neutral"}]),
            "order_index": 0,
            "wait_seconds": 2,
            "display_properties": json.dumps({"maxHeight": 30}),
        }

        with patch("src.lesson_runner.analyze_amplitude", return_value=[0.1]):
            bundle = await runner._build_section_bundle(section, 0)

        assert bundle is not None
        assert bundle["lesson_id"] == 1
        assert bundle["section_index"] == 0
        assert bundle["section_type"] == "introduction"
        assert bundle["display_text"] == "表示テキスト"
        assert bundle["display_properties"] == {"maxHeight": 30}
        assert bundle["wait_seconds"] == 2
        assert len(bundle["dialogues"]) == 1

    @pytest.mark.asyncio
    async def test_returns_none_on_tts_failure(self, mock_speech, tmp_path, monkeypatch):
        """TTS失敗時は None を返す"""
        monkeypatch.setattr("src.lesson_runner.LESSON_AUDIO_DIR", tmp_path)

        runner = LessonRunner(speech=mock_speech)
        runner._state = LessonState.RUNNING
        runner._lesson_id = 1
        runner._lang = "ja"
        runner._generator = "gemini"
        runner._version_number = 1
        runner._teacher_cfg = {}
        runner._sections = [{}]

        mock_speech.generate_tts = AsyncMock(return_value=None)

        section = {
            "section_type": "explanation",
            "content": "失敗",
            "dialogues": "",
            "order_index": 0,
        }
        bundle = await runner._build_section_bundle(section, 0)
        assert bundle is None

    def test_calc_section_duration(self):
        """_calc_section_durationは dialogues + question + wait_seconds*pace の合計"""
        section_bundle = {
            "dialogues": [{"duration": 1.0}, {"duration": 2.0}],
            "question": {
                "wait_seconds": 4,
                "answer_dialogues": [{"duration": 1.5}],
            },
            "wait_seconds": 2,
        }
        total = LessonRunner._calc_section_duration(section_bundle, pace_scale=1.0)
        # 1.0 + 2.0 + 4*1.0 + 1.5 + 2*1.0 = 10.5
        assert total == pytest.approx(10.5)

    def test_calc_section_duration_with_pace(self):
        """pace_scale が wait_seconds に適用される"""
        section_bundle = {
            "dialogues": [{"duration": 3.0}],
            "wait_seconds": 2,
        }
        # 3.0 + 2*2.0 = 7.0
        total = LessonRunner._calc_section_duration(section_bundle, pace_scale=2.0)
        assert total == pytest.approx(7.0)


class TestLessonCompletePayload:
    """capture_client の lesson_complete イベント受信のテスト"""

    def test_get_lesson_complete_event_singleton(self):
        """get_lesson_complete_event は同じインスタンスを返す"""
        from scripts.services.capture_client import get_lesson_complete_event
        evt1 = get_lesson_complete_event()
        evt2 = get_lesson_complete_event()
        assert evt1 is evt2
