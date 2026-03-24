"""prompt_builder のテスト（配信言語設定・システムプロンプト構築・モジュール分離）"""

import pytest

from src.prompt_builder import (
    SUPPORTED_LANGUAGES,
    MIX_LEVELS,
    build_language_rules,
    build_system_prompt,
    build_tts_style,
    get_stream_language,
    set_stream_language,
)
from src.ai_responder import DEFAULT_CHARACTER


# =====================================================
# 配信言語設定
# =====================================================


class TestStreamLanguage:
    def setup_method(self):
        set_stream_language("ja", "en", "low")

    def test_default_settings(self):
        lang = get_stream_language()
        assert lang["primary"] == "ja"
        assert lang["sub"] == "en"
        assert lang["mix"] == "low"

    def test_set_valid_language(self):
        set_stream_language("en", "ja", "medium")
        lang = get_stream_language()
        assert lang["primary"] == "en"
        assert lang["sub"] == "ja"
        assert lang["mix"] == "medium"

    def test_set_sub_none(self):
        set_stream_language("ja", "none", "low")
        lang = get_stream_language()
        assert lang["sub"] == "none"

    def test_invalid_primary_raises(self):
        with pytest.raises(ValueError):
            set_stream_language("invalid", "en", "low")

    def test_invalid_sub_raises(self):
        with pytest.raises(ValueError):
            set_stream_language("ja", "invalid", "low")

    def test_invalid_mix_raises(self):
        with pytest.raises(ValueError):
            set_stream_language("ja", "en", "invalid")

    def test_same_primary_sub_raises(self):
        with pytest.raises(ValueError):
            set_stream_language("ja", "ja", "low")

    def test_all_supported_languages_as_primary(self):
        for code in SUPPORTED_LANGUAGES:
            sub = "en" if code != "en" else "ja"
            set_stream_language(code, sub, "low")
            assert get_stream_language()["primary"] == code

    def test_all_mix_levels(self):
        for mix in MIX_LEVELS:
            set_stream_language("ja", "en", mix)
            assert get_stream_language()["mix"] == mix

    def test_returns_copy(self):
        """get_stream_language が内部状態のコピーを返すこと"""
        lang = get_stream_language()
        lang["primary"] = "xx"
        assert get_stream_language()["primary"] != "xx"


# =====================================================
# build_language_rules
# =====================================================


class TestBuildLanguageRules:
    def setup_method(self):
        set_stream_language("ja", "en", "low")

    def test_returns_list_of_strings(self):
        rules = build_language_rules()
        assert isinstance(rules, list)
        assert all(isinstance(r, str) for r in rules)

    def test_mentions_primary_language(self):
        rules = build_language_rules()
        text = "\n".join(rules)
        assert "日本語" in text

    def test_mentions_sub_language(self):
        rules = build_language_rules()
        text = "\n".join(rules)
        assert "English" in text

    def test_sub_none_no_sub_mention(self):
        set_stream_language("ja", "none", "low")
        rules = build_language_rules()
        text = "\n".join(rules)
        assert "日本語" in text
        # "English" は他言語対応ルールに含まれない
        assert "translation" in text

    def test_different_mix_levels_produce_different_rules(self):
        results = set()
        for mix in MIX_LEVELS:
            set_stream_language("en", "ja", mix)
            results.add("\n".join(build_language_rules()))
        assert len(results) == len(MIX_LEVELS)

    def test_different_languages_produce_different_rules(self):
        set_stream_language("ja", "en", "low")
        rules_ja = "\n".join(build_language_rules())
        set_stream_language("en", "ja", "low")
        rules_en = "\n".join(build_language_rules())
        assert rules_ja != rules_en

    def test_ja_sub_warns_no_romaji(self):
        """サブ言語が日本語のとき、ローマ字禁止ルールが含まれること"""
        set_stream_language("en", "ja", "medium")
        rules = build_language_rules()
        text = "\n".join(rules)
        assert "romaji" in text.lower() or "ローマ字" in text

    def test_translation_field_instruction(self):
        """translationフィールドの指示が含まれること"""
        rules = build_language_rules()
        text = "\n".join(rules)
        assert "translation" in text

    def test_other_language_response_rule(self):
        """他言語コメントへの対応ルールが含まれること"""
        rules = build_language_rules()
        text = "\n".join(rules)
        assert "言語" in text

    def test_english_only_mode_rules(self):
        """英語のみモードで英語のルールが生成されること"""
        set_stream_language("en", "none", "low")
        rules = build_language_rules()
        text = "\n".join(rules)
        assert "Respond in English" in text
        assert "Japanese translation" in text
        # 日本語の返答ルールが含まれないこと
        assert "で返答する" not in text

    def test_ja_only_mode_rules(self):
        """日本語のみモードで日本語のルールが生成されること"""
        set_stream_language("ja", "none", "low")
        rules = build_language_rules()
        text = "\n".join(rules)
        assert "日本語で返答する" in text
        assert "Respond in" not in text


# =====================================================
# build_tts_style
# =====================================================


class TestBuildTtsStyle:
    def setup_method(self):
        set_stream_language("ja", "en", "low")

    def test_returns_string(self):
        style = build_tts_style()
        assert isinstance(style, str)
        assert len(style) > 0

    def test_contains_cheerful(self):
        style = build_tts_style()
        assert "cheerful" in style

    def test_mentions_sub_language(self):
        style = build_tts_style()
        assert "English" in style

    def test_sub_none_no_sub_pronunciation(self):
        set_stream_language("ja", "none", "low")
        style = build_tts_style()
        assert "cheerful" in style

    def test_different_languages_different_style(self):
        set_stream_language("ja", "en", "low")
        style_ja = build_tts_style()
        set_stream_language("en", "ja", "low")
        style_en = build_tts_style()
        assert style_ja != style_en

    def test_english_mode_no_nikoniko(self):
        """英語モードでにこにこが含まれないこと"""
        set_stream_language("en", "none", "low")
        style = build_tts_style()
        assert "にこにこ" not in style
        assert "cheerful" in style

    def test_japanese_mode_has_nikoniko(self):
        """日本語モードでにこにこが含まれること"""
        set_stream_language("ja", "none", "low")
        style = build_tts_style()
        assert "にこにこ" in style


# =====================================================
# build_system_prompt
# =====================================================


class TestBuildSystemPrompt:
    def setup_method(self):
        set_stream_language("ja", "en", "low")

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
        set_stream_language("en", "ja", "medium")
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        assert "English" in prompt

    def test_stream_context_included(self):
        ctx = {"title": "テスト配信", "todo_items": ["バグ修正"]}
        prompt = build_system_prompt(DEFAULT_CHARACTER, stream_context=ctx)
        assert "テスト配信" in prompt
        assert "バグ修正" in prompt

    def test_stream_context_partial(self):
        prompt = build_system_prompt(DEFAULT_CHARACTER, stream_context={"title": "テスト"})
        assert "テスト" in prompt

    def test_stream_context_empty(self):
        prompt = build_system_prompt(DEFAULT_CHARACTER, stream_context={})
        assert DEFAULT_CHARACTER["system_prompt"] in prompt

    def test_output_format_includes_translation(self):
        """出力形式にtranslationフィールドが含まれること"""
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        assert '"translation"' in prompt

    def test_self_note_included(self):
        prompt = build_system_prompt(DEFAULT_CHARACTER, self_note="今日はPythonの話で盛り上がった")
        assert "今日はPythonの話で盛り上がった" in prompt
        assert "記憶メモ" in prompt

    def test_no_self_note_no_section(self):
        prompt = build_system_prompt(DEFAULT_CHARACTER, self_note=None)
        assert "記憶メモ" not in prompt

    def test_each_language_setting_produces_different_prompt(self):
        """異なる言語設定で異なるプロンプトが生成されること"""
        prompts = set()
        for primary, sub in [("ja", "en"), ("en", "ja"), ("ja", "none")]:
            set_stream_language(primary, sub, "low")
            prompt = build_system_prompt(DEFAULT_CHARACTER)
            prompts.add(prompt)
        assert len(prompts) == 3

    def test_output_format_section_present(self):
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        assert "出力形式" in prompt
        assert "JSON" in prompt

    def test_tts_text_instructions_present(self):
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        assert "tts_text" in prompt
        assert "lang:" in prompt

    def test_custom_character(self):
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
        minimal = {"system_prompt": "最小構成"}
        prompt = build_system_prompt(minimal)
        assert "最小構成" in prompt

    def test_english_mode_word_count_rule(self):
        """英語モードで語数ルールが生成されること"""
        set_stream_language("en", "none", "low")
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        assert "words" in prompt
        assert "文字以内" not in prompt

    def test_japanese_mode_char_count_rule(self):
        """日本語モードで文字数ルールが生成されること"""
        set_stream_language("ja", "none", "low")
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        assert "文字以内" in prompt

    def test_english_mode_tts_text_instructions(self):
        """英語モードでtts_text説明が英語ベースになること"""
        set_stream_language("en", "none", "low")
        prompt = build_system_prompt(DEFAULT_CHARACTER)
        assert "non-English" not in prompt or "English以外" not in prompt
        # 英語モードではベース言語がEnglishなので「English以外」の説明になる
        assert "tts_text" in prompt


# =====================================================
# モジュール分離の確認
# =====================================================


class TestModuleSeparation:
    """prompt_builder が ai_responder から正しく分離されていること"""

    def test_prompt_builder_has_no_ai_responder_import(self):
        import inspect
        import src.prompt_builder as pb

        source = inspect.getsource(pb)
        assert "from src.ai_responder" not in source
        assert "import src.ai_responder" not in source

    def test_ai_responder_imports_from_prompt_builder(self):
        import inspect
        import src.ai_responder as ar

        source = inspect.getsource(ar)
        assert "from src.prompt_builder import" in source

    def test_ai_responder_no_longer_defines_language_modes(self):
        import inspect
        import src.ai_responder as ar

        source = inspect.getsource(ar)
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("LANGUAGE_MODES") and "=" in stripped and "{" in stripped:
                assert False, f"ai_responder.py に LANGUAGE_MODES の定義が残っている: {stripped}"

    def test_ai_responder_no_longer_defines_build_system_prompt(self):
        import inspect
        import src.ai_responder as ar

        source = inspect.getsource(ar)
        assert "def _build_system_prompt" not in source
        assert "def build_system_prompt" not in source

    def test_tts_imports_from_prompt_builder(self):
        import inspect
        import src.tts as tts_mod

        source = inspect.getsource(tts_mod)
        assert "from src.prompt_builder import" in source

    def test_character_route_imports_split_correctly(self):
        import inspect
        import scripts.routes.character as ch

        source = inspect.getsource(ch)
        assert "from src.prompt_builder import" in source
        assert "from src.ai_responder import" in source
