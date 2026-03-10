"""ai_responder の純粋ロジックテスト"""

import json
from unittest.mock import patch

from src.ai_responder import (
    DEFAULT_CHARACTER,
    LANGUAGE_MODES,
    _build_system_prompt,
    get_language_mode,
    set_language_mode,
)


class TestLanguageMode:
    def setup_method(self):
        set_language_mode("ja")

    def test_default_mode_is_ja(self):
        set_language_mode("ja")
        assert get_language_mode() == "ja"

    def test_set_valid_mode(self):
        for mode in LANGUAGE_MODES:
            set_language_mode(mode)
            assert get_language_mode() == mode

    def test_set_invalid_mode_raises(self):
        import pytest
        with pytest.raises(ValueError):
            set_language_mode("nonexistent")

    def test_all_modes_have_required_fields(self):
        for name, mode in LANGUAGE_MODES.items():
            assert "name" in mode, f"{name} missing 'name'"
            assert "rules" in mode, f"{name} missing 'rules'"
            assert "english_label" in mode, f"{name} missing 'english_label'"
            assert "tts_style" in mode, f"{name} missing 'tts_style'"


class TestBuildSystemPrompt:
    def setup_method(self):
        set_language_mode("ja")

    @patch("src.ai_responder.get_character", return_value=DEFAULT_CHARACTER)
    def test_contains_system_prompt(self, _mock):
        prompt = _build_system_prompt()
        assert DEFAULT_CHARACTER["system_prompt"] in prompt

    @patch("src.ai_responder.get_character", return_value=DEFAULT_CHARACTER)
    def test_contains_rules(self, _mock):
        prompt = _build_system_prompt()
        for rule in DEFAULT_CHARACTER["rules"]:
            assert rule in prompt

    @patch("src.ai_responder.get_character", return_value=DEFAULT_CHARACTER)
    def test_contains_emotions(self, _mock):
        prompt = _build_system_prompt()
        for emotion in DEFAULT_CHARACTER["emotions"]:
            assert emotion in prompt

    @patch("src.ai_responder.get_character", return_value=DEFAULT_CHARACTER)
    def test_contains_language_rules(self, _mock):
        set_language_mode("en_bilingual")
        prompt = _build_system_prompt()
        assert "English" in prompt

    @patch("src.ai_responder.get_character", return_value=DEFAULT_CHARACTER)
    def test_stream_context_included(self, _mock):
        ctx = {"title": "テスト配信", "topic": "Python", "todo_items": ["バグ修正"]}
        prompt = _build_system_prompt(stream_context=ctx)
        assert "テスト配信" in prompt
        assert "Python" in prompt
        assert "バグ修正" in prompt

    @patch("src.ai_responder.get_character", return_value=DEFAULT_CHARACTER)
    def test_output_format_includes_english_label(self, _mock):
        set_language_mode("en_mixed")
        prompt = _build_system_prompt()
        label = LANGUAGE_MODES["en_mixed"]["english_label"]
        assert label in prompt
