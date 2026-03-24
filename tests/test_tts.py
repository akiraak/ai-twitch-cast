"""tts.py の純粋ロジックテスト"""

from src.tts import _convert_lang_tags, _get_tts_style, DEFAULT_STYLE


class TestConvertLangTags:
    """言語タグ変換のテスト（日本語モード）"""

    def setup_method(self):
        from src.prompt_builder import set_stream_language
        set_stream_language("ja", "en", "low")

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
        assert "[English]" not in result

    def test_pure_japanese_unchanged(self):
        result = _convert_lang_tags("今日はいい天気ですね")
        assert result == "今日はいい天気ですね"

    def test_fallback_multi_word_english(self):
        result = _convert_lang_tags("Claude Codeすごい")
        assert "[English]Claude Code[Japanese]" in result


class TestConvertLangTagsEnglishMode:
    """英語モードでの言語タグ変換テスト"""

    def setup_method(self):
        from src.prompt_builder import set_stream_language
        set_stream_language("en", "none", "low")

    def teardown_method(self):
        from src.prompt_builder import set_stream_language
        set_stream_language("ja", "en", "low")

    def test_explicit_japanese_tag(self):
        """英語モードで[lang:ja]タグが正しく変換されること"""
        result = _convert_lang_tags("Let's learn [lang:ja]こんにちは[/lang] today")
        assert "[Japanese]こんにちは[English]" in result

    def test_explicit_spanish_tag(self):
        """英語モードで他言語タグも正しく変換されること"""
        result = _convert_lang_tags("How to say [lang:es]¡Hola![/lang]")
        assert "[Spanish]¡Hola![English]" in result

    def test_no_tags_cjk_fallback(self):
        """英語モードでタグなし時にCJK文字が検出されること"""
        result = _convert_lang_tags("The word こんにちは means hello")
        assert "[Japanese]こんにちは[English]" in result

    def test_no_tags_pure_english_unchanged(self):
        """英語モードで純粋な英語テキストが変更されないこと"""
        result = _convert_lang_tags("Hello everyone, welcome to the stream")
        assert result == "Hello everyone, welcome to the stream"

    def test_multiple_cjk_segments(self):
        """複数のCJKセグメントが正しくタグ付けされること"""
        result = _convert_lang_tags("Learn 日本語 and 中国語 today")
        assert "[Japanese]日本語[English]" in result
        assert "[Japanese]中国語[English]" in result


class TestGetTtsStyle:
    def test_returns_style_string(self):
        style = _get_tts_style()
        assert isinstance(style, str)
        assert len(style) > 0

    def test_contains_cheerful(self):
        style = _get_tts_style()
        assert "cheerful" in style

    def test_different_settings_different_style(self):
        from src.prompt_builder import set_stream_language
        set_stream_language("ja", "en", "low")
        style_ja = _get_tts_style()
        set_stream_language("en", "ja", "low")
        style_en = _get_tts_style()
        assert style_ja != style_en
        set_stream_language("ja", "en", "low")  # cleanup
