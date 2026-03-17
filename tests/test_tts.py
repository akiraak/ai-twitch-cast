"""tts.py の純粋ロジックテスト"""

from src.tts import _convert_lang_tags, _get_tts_style, DEFAULT_STYLE


class TestConvertLangTags:
    """言語タグ変換のテスト"""

    def test_explicit_english_tag(self):
        result = _convert_lang_tags("今日は[lang:en]YouTube[/lang]の動画")
        assert result == "今日は[English]YouTube[Japanese]の動画"

    def test_explicit_spanish_tag(self):
        result = _convert_lang_tags("[lang:es]¡Hola![/lang]いらっしゃい")
        assert result == "[Spanish]¡Hola![Japanese]いらっしゃい"

    def test_multiple_tags(self):
        text = "[lang:en]Hello[/lang]、[lang:ko]안녕[/lang]！"
        result = _convert_lang_tags(text)
        assert "[English]Hello[Japanese]" in result
        assert "[Korean]안녕[Japanese]" in result

    def test_unknown_lang_code(self):
        result = _convert_lang_tags("[lang:xx]text[/lang]")
        assert result == "[XX]text[Japanese]"

    def test_no_tags_fallback_english(self):
        """タグなし → 英語部分を自動検出"""
        result = _convert_lang_tags("今日はPythonを使います")
        assert "[English]Python[Japanese]" in result

    def test_no_tags_short_word_ignored(self):
        """1文字の英語はタグ付けしない"""
        result = _convert_lang_tags("AはBです")
        # 1文字 "A" と "B" はそのまま（< 2文字なのでスキップ）
        assert "[English]" not in result

    def test_pure_japanese_unchanged(self):
        result = _convert_lang_tags("今日はいい天気ですね")
        assert result == "今日はいい天気ですね"

    def test_fallback_multi_word_english(self):
        result = _convert_lang_tags("Claude Codeすごい")
        assert "[English]Claude Code[Japanese]" in result


class TestGetTtsStyle:
    def test_returns_style_string(self):
        style = _get_tts_style()
        assert isinstance(style, str)
        assert len(style) > 0

    def test_ja_mode_returns_ja_style(self):
        from src.prompt_builder import set_language_mode, LANGUAGE_MODES
        set_language_mode("ja")
        style = _get_tts_style()
        assert style == LANGUAGE_MODES["ja"]["tts_style"]

    def test_en_mode_returns_en_style(self):
        from src.prompt_builder import set_language_mode, LANGUAGE_MODES
        set_language_mode("en_bilingual")
        style = _get_tts_style()
        assert style == LANGUAGE_MODES["en_bilingual"]["tts_style"]
        set_language_mode("ja")  # cleanup
