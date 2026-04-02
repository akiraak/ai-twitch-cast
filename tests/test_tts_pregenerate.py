"""TTS事前生成モジュールのテスト"""

import asyncio
import json

from pathlib import Path
from unittest.mock import patch, MagicMock


class TestGenerateOne:
    """_generate_one のテスト"""

    def test_success(self, tmp_path, monkeypatch):
        """正常生成: キャッシュファイルが作成される"""
        from src.tts_pregenerate import _generate_one

        cache = tmp_path / "lesson" / "audio.wav"

        def fake_synthesize(text, path, **kwargs):
            Path(path).write_bytes(b"RIFF_FAKE_WAV")

        with patch("src.tts_pregenerate.synthesize", side_effect=fake_synthesize):
            result = asyncio.get_event_loop().run_until_complete(
                _generate_one("テスト", cache)
            )

        assert result is True
        assert cache.exists()
        assert cache.read_bytes() == b"RIFF_FAKE_WAV"

    def test_failure(self, tmp_path):
        """生成失敗: Falseを返しキャッシュファイルは作成されない"""
        from src.tts_pregenerate import _generate_one

        cache = tmp_path / "lesson" / "audio.wav"

        with patch("src.tts_pregenerate.synthesize", side_effect=RuntimeError("API error")):
            result = asyncio.get_event_loop().run_until_complete(
                _generate_one("テスト", cache)
            )

        assert result is False
        assert not cache.exists()

    def test_voice_style_passed(self, tmp_path):
        """voice/styleがsynthesizeに渡される"""
        from src.tts_pregenerate import _generate_one

        cache = tmp_path / "audio.wav"
        calls = []

        def fake_synthesize(text, path, **kwargs):
            calls.append(kwargs)
            Path(path).write_bytes(b"WAV")

        with patch("src.tts_pregenerate.synthesize", side_effect=fake_synthesize):
            asyncio.get_event_loop().run_until_complete(
                _generate_one("テスト", cache, voice="Leda", style="happy")
            )

        assert calls[0]["voice"] == "Leda"
        assert calls[0]["style"] == "happy"


class TestParseDialogues:
    """_parse_dialogues のテスト"""

    def test_v4_format(self):
        """v4形式（{"dialogues": [...]}）のパース"""
        from src.tts_pregenerate import _parse_dialogues

        section = {"dialogues": json.dumps({"dialogues": [
            {"speaker": "teacher", "content": "こんにちは"},
            {"speaker": "student", "content": "はい"},
        ]})}
        result = _parse_dialogues(section, {"tts_voice": "v"})
        assert len(result) == 2
        assert result[0]["speaker"] == "teacher"

    def test_list_format(self):
        """リスト形式のパース"""
        from src.tts_pregenerate import _parse_dialogues

        section = {"dialogues": json.dumps([
            {"speaker": "teacher", "content": "テスト"},
        ])}
        result = _parse_dialogues(section, {"tts_voice": "v"})
        assert len(result) == 1

    def test_empty_dialogues(self):
        """空のdialogues → None"""
        from src.tts_pregenerate import _parse_dialogues

        assert _parse_dialogues({"dialogues": ""}, {"v": 1}) is None
        assert _parse_dialogues({"dialogues": "[]"}, {"v": 1}) is None
        assert _parse_dialogues({}, {"v": 1}) is None

    def test_no_student_cfg(self):
        """student_cfgがNone → None"""
        from src.tts_pregenerate import _parse_dialogues

        section = {"dialogues": json.dumps([{"speaker": "teacher"}])}
        assert _parse_dialogues(section, None) is None

    def test_invalid_json(self):
        """不正JSON → None"""
        from src.tts_pregenerate import _parse_dialogues

        assert _parse_dialogues({"dialogues": "NOT JSON"}, {"v": 1}) is None


class TestPregenerateSectionTts:
    """pregenerate_section_tts のテスト"""

    def test_single_speaker(self, tmp_path, monkeypatch):
        """単話者モード: contentが分割され各パートが生成される"""
        from src.tts_pregenerate import pregenerate_section_tts
        from src import lesson_runner

        monkeypatch.setattr(lesson_runner, "LESSON_AUDIO_DIR", tmp_path)

        gen_count = 0

        def fake_synthesize(text, path, **kwargs):
            nonlocal gen_count
            gen_count += 1
            Path(path).write_bytes(b"WAV")

        section = {
            "content": "これは最初の文です。これは二つ目の文です。これは三つ目の文です。",
            "tts_text": None,
        }

        with patch("src.tts_pregenerate.synthesize", side_effect=fake_synthesize):
            result = asyncio.get_event_loop().run_until_complete(
                pregenerate_section_tts(
                    lesson_id=1, section=section, order_index=0,
                    lang="ja", generator="claude", version_number=1,
                    teacher_cfg=None, student_cfg=None,
                )
            )

        assert result["generated"] == 3
        assert result["cached"] == 0
        assert result["failed"] == 0

    def test_single_speaker_cache_hit(self, tmp_path, monkeypatch):
        """単話者モード: キャッシュ存在時はスキップ"""
        from src.tts_pregenerate import pregenerate_section_tts
        from src import lesson_runner

        monkeypatch.setattr(lesson_runner, "LESSON_AUDIO_DIR", tmp_path)

        # キャッシュファイルを先に作成
        cache_dir = tmp_path / "1" / "ja" / "claude" / "v1"
        cache_dir.mkdir(parents=True)
        (cache_dir / "section_00_part_00.wav").write_bytes(b"CACHED")

        section = {"content": "短い文", "tts_text": None}

        with patch("src.tts_pregenerate.synthesize") as mock_synth:
            result = asyncio.get_event_loop().run_until_complete(
                pregenerate_section_tts(
                    lesson_id=1, section=section, order_index=0,
                    lang="ja", generator="claude", version_number=1,
                    teacher_cfg=None, student_cfg=None,
                )
            )

        assert result["cached"] == 1
        assert result["generated"] == 0
        mock_synth.assert_not_called()

    def test_dialogue_mode(self, tmp_path, monkeypatch):
        """対話モード: speaker別voice/styleで生成"""
        from src.tts_pregenerate import pregenerate_section_tts
        from src import lesson_runner

        monkeypatch.setattr(lesson_runner, "LESSON_AUDIO_DIR", tmp_path)

        calls = []

        def fake_synthesize(text, path, **kwargs):
            calls.append({"text": text, **kwargs})
            Path(path).write_bytes(b"WAV")

        section = {
            "dialogues": json.dumps({"dialogues": [
                {"speaker": "teacher", "content": "説明", "tts_text": "説明TTS"},
                {"speaker": "student", "content": "質問", "tts_text": "質問TTS"},
            ]}),
            "content": "fallback",
        }
        teacher_cfg = {"tts_voice": "Despina", "tts_style": "にこにこ"}
        student_cfg = {"tts_voice": "Leda", "tts_style": "curious"}

        with patch("src.tts_pregenerate.synthesize", side_effect=fake_synthesize):
            result = asyncio.get_event_loop().run_until_complete(
                pregenerate_section_tts(
                    lesson_id=1, section=section, order_index=0,
                    lang="ja", generator="claude", version_number=1,
                    teacher_cfg=teacher_cfg, student_cfg=student_cfg,
                )
            )

        assert result["generated"] == 2
        # teacher voice/style
        assert calls[0]["voice"] == "Despina"
        assert calls[0]["style"] == "にこにこ"
        assert calls[0]["text"] == "説明TTS"
        # student voice/style
        assert calls[1]["voice"] == "Leda"
        assert calls[1]["style"] == "curious"

    def test_cancel_during_generation(self, tmp_path, monkeypatch):
        """キャンセル: cancel_event.set()後に即座に停止"""
        from src.tts_pregenerate import pregenerate_section_tts
        from src import lesson_runner

        monkeypatch.setattr(lesson_runner, "LESSON_AUDIO_DIR", tmp_path)

        cancel_event = asyncio.Event()
        gen_count = 0

        def fake_synthesize(text, path, **kwargs):
            nonlocal gen_count
            gen_count += 1
            # 1つ生成したらキャンセル
            cancel_event.set()
            Path(path).write_bytes(b"WAV")

        section = {
            "content": "最初の文です。二つ目の文です。三つ目の文です。",
            "tts_text": None,
        }

        with patch("src.tts_pregenerate.synthesize", side_effect=fake_synthesize):
            result = asyncio.get_event_loop().run_until_complete(
                pregenerate_section_tts(
                    lesson_id=1, section=section, order_index=0,
                    lang="ja", generator="claude", version_number=1,
                    teacher_cfg=None, student_cfg=None,
                    cancel_event=cancel_event,
                )
            )

        # 1つだけ生成して停止
        assert result["generated"] == 1
        assert gen_count == 1

    def test_empty_content(self, tmp_path, monkeypatch):
        """空のcontent: 何も生成しない"""
        from src.tts_pregenerate import pregenerate_section_tts
        from src import lesson_runner

        monkeypatch.setattr(lesson_runner, "LESSON_AUDIO_DIR", tmp_path)

        section = {"content": "", "tts_text": None}

        result = asyncio.get_event_loop().run_until_complete(
            pregenerate_section_tts(
                lesson_id=1, section=section, order_index=0,
                lang="ja", generator="claude", version_number=1,
                teacher_cfg=None, student_cfg=None,
            )
        )

        assert result == {"generated": 0, "cached": 0, "failed": 0}

    def test_retry_on_failure(self, tmp_path, monkeypatch):
        """1回目失敗→リトライ成功"""
        from src.tts_pregenerate import pregenerate_section_tts
        from src import lesson_runner

        monkeypatch.setattr(lesson_runner, "LESSON_AUDIO_DIR", tmp_path)

        call_count = 0

        def fake_synthesize(text, path, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            Path(path).write_bytes(b"WAV")

        section = {"content": "短い文", "tts_text": None}

        with patch("src.tts_pregenerate.synthesize", side_effect=fake_synthesize):
            result = asyncio.get_event_loop().run_until_complete(
                pregenerate_section_tts(
                    lesson_id=1, section=section, order_index=0,
                    lang="ja", generator="claude", version_number=1,
                    teacher_cfg=None, student_cfg=None,
                )
            )

        assert result["generated"] == 1
        assert result["failed"] == 0
        assert call_count == 2  # 1回失敗 + 1回リトライ成功

    def test_tts_text_override(self, tmp_path, monkeypatch):
        """tts_textがcontentと異なる場合、tts_textが使われる"""
        from src.tts_pregenerate import pregenerate_section_tts
        from src import lesson_runner

        monkeypatch.setattr(lesson_runner, "LESSON_AUDIO_DIR", tmp_path)

        calls = []

        def fake_synthesize(text, path, **kwargs):
            calls.append(text)
            Path(path).write_bytes(b"WAV")

        section = {"content": "表示テキスト", "tts_text": "読み上げテキスト"}

        with patch("src.tts_pregenerate.synthesize", side_effect=fake_synthesize):
            asyncio.get_event_loop().run_until_complete(
                pregenerate_section_tts(
                    lesson_id=1, section=section, order_index=0,
                    lang="ja", generator="claude", version_number=1,
                    teacher_cfg=None, student_cfg=None,
                )
            )

        assert calls[0] == "読み上げテキスト"


class TestPregenerateLessonTts:
    """pregenerate_lesson_tts のテスト"""

    def _create_sections(self, test_db):
        """テスト用レッスン+セクション作成"""
        lesson = test_db.create_lesson("テスト授業")
        lid = lesson["id"]
        test_db.add_lesson_section(
            lid, order_index=0, section_type="explanation",
            title="Sec1", content="最初のセクション",
            tts_text="最初のセクション", display_text="最初",
            emotion="neutral", lang="ja", generator="claude",
            version_number=1,
        )
        test_db.add_lesson_section(
            lid, order_index=1, section_type="example",
            title="Sec2", content="二つ目のセクション",
            tts_text="二つ目のセクション", display_text="二つ",
            emotion="happy", lang="ja", generator="claude",
            version_number=1,
        )
        return lid

    def test_full_generation(self, test_db, mock_gemini, tmp_path, monkeypatch):
        """全セクション一括生成"""
        from src.tts_pregenerate import pregenerate_lesson_tts
        from src import lesson_runner

        monkeypatch.setattr(lesson_runner, "LESSON_AUDIO_DIR", tmp_path)
        lid = self._create_sections(test_db)

        def fake_synthesize(text, path, **kwargs):
            Path(path).write_bytes(b"WAV")

        with patch("src.tts_pregenerate.synthesize", side_effect=fake_synthesize), \
             patch("src.tts_pregenerate.get_lesson_characters", return_value={"teacher": None, "student": None}):
            result = asyncio.get_event_loop().run_until_complete(
                pregenerate_lesson_tts(lid, "ja", "claude", 1)
            )

        assert result["total"] == 2
        assert result["generated"] == 2
        assert result["cached"] == 0
        assert result["failed"] == 0
        assert result["cancelled"] is False

    def test_progress_callback(self, test_db, mock_gemini, tmp_path, monkeypatch):
        """on_progressコールバックが各セクションで呼ばれる"""
        from src.tts_pregenerate import pregenerate_lesson_tts
        from src import lesson_runner

        monkeypatch.setattr(lesson_runner, "LESSON_AUDIO_DIR", tmp_path)
        lid = self._create_sections(test_db)

        progress_calls = []

        def on_progress(completed, total, result):
            progress_calls.append((completed, total))

        def fake_synthesize(text, path, **kwargs):
            Path(path).write_bytes(b"WAV")

        with patch("src.tts_pregenerate.synthesize", side_effect=fake_synthesize), \
             patch("src.tts_pregenerate.get_lesson_characters", return_value={"teacher": None, "student": None}):
            asyncio.get_event_loop().run_until_complete(
                pregenerate_lesson_tts(lid, "ja", "claude", 1, on_progress=on_progress)
            )

        assert progress_calls == [(1, 2), (2, 2)]

    def test_cancel_midway(self, test_db, mock_gemini, tmp_path, monkeypatch):
        """途中でキャンセル"""
        from src.tts_pregenerate import pregenerate_lesson_tts
        from src import lesson_runner

        monkeypatch.setattr(lesson_runner, "LESSON_AUDIO_DIR", tmp_path)
        lid = self._create_sections(test_db)

        cancel_event = asyncio.Event()
        cancel_event.set()  # 最初からキャンセル状態

        with patch("src.tts_pregenerate.get_lesson_characters", return_value={"teacher": None, "student": None}):
            result = asyncio.get_event_loop().run_until_complete(
                pregenerate_lesson_tts(lid, "ja", "claude", 1, cancel_event=cancel_event)
            )

        assert result["cancelled"] is True
        assert result["generated"] == 0

    def test_no_sections(self, test_db, mock_gemini, tmp_path, monkeypatch):
        """セクション0件: 即座にreturn"""
        from src.tts_pregenerate import pregenerate_lesson_tts
        from src import lesson_runner

        monkeypatch.setattr(lesson_runner, "LESSON_AUDIO_DIR", tmp_path)
        lid = test_db.create_lesson("空のレッスン")["id"]

        result = asyncio.get_event_loop().run_until_complete(
            pregenerate_lesson_tts(lid, "ja", "claude", 1)
        )

        assert result["total"] == 0
        assert result["cancelled"] is False
