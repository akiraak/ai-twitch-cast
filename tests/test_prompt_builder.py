"""prompt_builder のテスト（言語モード・システムプロンプト構築・モジュール分離）"""

import pytest

from src.prompt_builder import (
    LANGUAGE_MODES,
    build_system_prompt,
    get_language_mode,
    set_language_mode,
)
from src.ai_responder import DEFAULT_CHARACTER


# =====================================================
# 言語モード管理
# =====================================================


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
        with pytest.raises(ValueError):
            set_language_mode("nonexistent")

    def test_all_modes_have_required_fields(self):
        for name, mode in LANGUAGE_MODES.items():
            assert "name" in mode, f"{name} missing 'name'"
            assert "rules" in mode, f"{name} missing 'rules'"
            assert "english_label" in mode, f"{name} missing 'english_label'"
            assert "tts_style" in mode, f"{name} missing 'tts_style'"

    def test_all_modes_have_non_empty_rules(self):
        for name, mode in LANGUAGE_MODES.items():
            assert len(mode["rules"]) > 0, f"{name} has empty rules"

    def test_mode_count(self):
        """少なくとも5つの言語モードがあること"""
        assert len(LANGUAGE_MODES) >= 5


# =====================================================
# build_system_prompt
# =====================================================


class TestBuildSystemPrompt:
    def setup_method(self):
        set_language_mode("ja")

    def test_contains_system_prompt(self):
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        assert DEFAULT_CHARACTER["system_prompt"] in prompt

    def test_contains_rules(self):
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        for rule in DEFAULT_CHARACTER["rules"]:
            assert rule in prompt

    def test_contains_emotions(self):
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        for emotion in DEFAULT_CHARACTER["emotions"]:
            assert emotion in prompt

    def test_contains_language_rules(self):
        set_language_mode("en_bilingual")
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        assert "English" in prompt

    def test_stream_context_included(self):
        ctx = {"title": "テスト配信", "topic": "Python", "todo_items": ["バグ修正"]}
        prompt = build_system_prompt(DEFAULT_CHARACTER, stream_context=ctx)
        assert "テスト配信" in prompt
        assert "Python" in prompt
        assert "バグ修正" in prompt

    def test_stream_context_partial(self):
        """stream_contextの一部だけ指定した場合も動くこと"""
        prompt = build_system_prompt(DEFAULT_CHARACTER, stream_context={"title": "テスト"})
        assert "テスト" in prompt

    def test_stream_context_empty(self):
        """空のstream_contextでもエラーにならないこと"""
        prompt = build_system_prompt(DEFAULT_CHARACTER, stream_context={})
        assert DEFAULT_CHARACTER["system_prompt"] in prompt

    def test_output_format_includes_english_label(self):
        set_language_mode("en_mixed")
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        label = LANGUAGE_MODES["en_mixed"]["english_label"]
        assert label in prompt

    def test_self_note_included(self):
        prompt = build_system_prompt(DEFAULT_CHARACTER, self_note="今日はPythonの話で盛り上がった")
        assert "今日はPythonの話で盛り上がった" in prompt
        assert "記憶メモ" in prompt

    def test_no_self_note_no_section(self):
        prompt = build_system_prompt(DEFAULT_CHARACTER, self_note=None)
        assert "記憶メモ" not in prompt

    def test_each_language_mode_produces_different_prompt(self):
        """各言語モードで異なるプロンプトが生成されること"""
        prompts = set()
        for mode in LANGUAGE_MODES:
            set_language_mode(mode)
            prompt = build_system_prompt(DEFAULT_CHARACTER)
            prompts.add(prompt)
        assert len(prompts) == len(LANGUAGE_MODES)

    def test_output_format_section_present(self):
        """出力形式セクションが含まれること"""
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        assert "出力形式" in prompt
        assert "JSON" in prompt

    def test_tts_text_instructions_present(self):
        """tts_textの説明が含まれること"""
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        assert "tts_text" in prompt
        assert "lang:" in prompt

    def test_custom_character(self):
        """DEFAULT_CHARACTER以外のキャラクターでも動作すること"""
        custom = {
            "system_prompt": "カスタムプロンプト",
            "rules": ["ルール1"],
            "emotions": {"happy": "ハッピー"},
        }
        prompt = build_system_prompt(custom)
        assert "カスタムプロンプト" in prompt
        assert "ルール1" in prompt
        assert "happy" in prompt

    def test_character_without_optional_fields(self):
        """rules/emotionsが空でもエラーにならないこと"""
        minimal = {"system_prompt": "最小構成"}
        prompt = build_system_prompt(minimal)
        assert "最小構成" in prompt


# =====================================================
# モジュール分離の確認
# =====================================================


class TestModuleSeparation:
    """prompt_builder が ai_responder から正しく分離されていること"""

    def test_prompt_builder_has_no_ai_responder_import(self):
        """prompt_builder が ai_responder をインポートしていないこと（循環インポート防止）"""
        import inspect
        import src.prompt_builder as pb

        source = inspect.getsource(pb)
        assert "from src.ai_responder" not in source
        assert "import src.ai_responder" not in source

    def test_ai_responder_imports_from_prompt_builder(self):
        """ai_responder が prompt_builder から正しくインポートしていること"""
        import inspect
        import src.ai_responder as ar

        source = inspect.getsource(ar)
        assert "from src.prompt_builder import" in source

    def test_ai_responder_no_longer_defines_language_modes(self):
        """ai_responder に LANGUAGE_MODES 定義が残っていないこと"""
        import inspect
        import src.ai_responder as ar

        source = inspect.getsource(ar)
        # LANGUAGE_MODES = { のような定義がないこと（importは OK）
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("LANGUAGE_MODES") and "=" in stripped and "{" in stripped:
                assert False, f"ai_responder.py に LANGUAGE_MODES の定義が残っている: {stripped}"

    def test_ai_responder_no_longer_defines_build_system_prompt(self):
        """ai_responder に _build_system_prompt / build_system_prompt 定義が残っていないこと"""
        import inspect
        import src.ai_responder as ar

        source = inspect.getsource(ar)
        assert "def _build_system_prompt" not in source
        assert "def build_system_prompt" not in source

    def test_tts_imports_from_prompt_builder(self):
        """tts.py が prompt_builder から言語モードを取得していること"""
        import inspect
        import src.tts as tts_mod

        source = inspect.getsource(tts_mod)
        assert "from src.prompt_builder import" in source
        assert "from src.ai_responder import" not in source.replace(
            "from src.ai_responder import get_language_mode", ""
        ).replace("from src.ai_responder import LANGUAGE_MODES", "")

    def test_character_route_imports_split_correctly(self):
        """character.py がキャラ管理はai_responder、言語モードはprompt_builderからインポートすること"""
        import inspect
        import scripts.routes.character as ch

        source = inspect.getsource(ch)
        assert "from src.prompt_builder import" in source
        assert "from src.ai_responder import" in source
        # prompt_builder からの import に LANGUAGE_MODES があること
        assert "LANGUAGE_MODES" not in [
            line for line in source.split("\n")
            if "from src.ai_responder import" in line
        ]
