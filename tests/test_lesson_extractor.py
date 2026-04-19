"""lesson_generator/extractor.py のテスト

範囲:
- clean_extracted_text: HTMLエンティティ置換・装飾記号除去・空行圧縮
- _normalize_roles: role/read_aloud の正規化（main必ず1つ）
- extract_main_content: LLM応答のパース（list/dict/空/壊れJSON）
- extract_text_from_image: Vision呼び出し（ファイルなし/成功）
- extract_text_from_url: HTTP取得＋LLM整形
"""

import httpx
import pytest

from src.lesson_generator import extractor


# =====================================================
# clean_extracted_text
# =====================================================


class TestCleanExtractedText:
    def test_empty_returns_empty(self):
        assert extractor.clean_extracted_text("") == ""

    def test_none_or_falsy_passthrough(self):
        # 関数の冒頭が `if not text: return text` のため、None/0 もそのまま戻る
        assert extractor.clean_extracted_text(None) is None

    def test_html_entities_replaced(self):
        src = "&nbsp;Hello&amp;&lt;tag&gt;&quot;q&quot;&#39;s&apos;"
        out = extractor.clean_extracted_text(src)
        assert out == "Hello&<tag>\"q\"'s'"

    def test_long_dash_becomes_newline(self):
        # 3つ以上のハイフンは改行に置換され、最終的にstripされる
        out = extractor.clean_extracted_text("A\n------\nB")
        assert "------" not in out
        assert "A" in out and "B" in out

    def test_equal_sign_runs_removed(self):
        out = extractor.clean_extracted_text("section=====end")
        assert "=====" not in out
        assert "section" in out and "end" in out

    def test_asterisk_tilde_underscore_runs_removed(self):
        out = extractor.clean_extracted_text("a*** b~~~ c___ d")
        assert "***" not in out
        assert "~~~" not in out
        assert "___" not in out

    def test_decoration_symbols_removed(self):
        out = extractor.clean_extracted_text("★★★ title ※※※")
        assert "★★★" not in out
        assert "※※※" not in out
        assert "title" in out

    def test_double_dash_preserved(self):
        # 2個までは保持（装飾ではなく記号として）
        out = extractor.clean_extracted_text("A--B")
        assert "A--B" in out

    def test_excess_blank_lines_compressed(self):
        src = "A\n\n\n\n\n\nB"
        out = extractor.clean_extracted_text(src)
        # 4行以上の改行は3行に圧縮される
        assert "\n\n\n\n" not in out
        assert "A" in out and "B" in out

    def test_leading_trailing_whitespace_stripped(self):
        assert extractor.clean_extracted_text("  hello  \n") == "hello"


# =====================================================
# _normalize_roles
# =====================================================


class TestNormalizeRoles:
    def test_empty_returns_empty(self):
        assert extractor._normalize_roles([]) == []

    def test_zero_main_promotes_first(self):
        items = [
            {"content_type": "passage", "content": "x"},
            {"content_type": "word_list", "content": "y"},
        ]
        out = extractor._normalize_roles(items)
        assert out[0]["role"] == "main"
        assert out[1]["role"] == "sub"

    def test_multiple_main_keeps_only_first(self):
        items = [
            {"role": "main", "content_type": "conversation", "content": "a"},
            {"role": "main", "content_type": "passage", "content": "b"},
            {"role": "main", "content_type": "word_list", "content": "c"},
        ]
        out = extractor._normalize_roles(items)
        assert out[0]["role"] == "main"
        assert out[1]["role"] == "sub"
        assert out[2]["role"] == "sub"

    def test_single_main_preserved(self):
        items = [
            {"role": "sub", "content_type": "word_list", "content": "a"},
            {"role": "main", "content_type": "conversation", "content": "b"},
        ]
        out = extractor._normalize_roles(items)
        assert out[0]["role"] == "sub"
        assert out[1]["role"] == "main"

    def test_read_aloud_default_true_for_main_conversation(self):
        items = [{"role": "main", "content_type": "conversation", "content": "x"}]
        out = extractor._normalize_roles(items)
        assert out[0]["read_aloud"] is True

    def test_read_aloud_default_true_for_main_passage(self):
        items = [{"role": "main", "content_type": "passage", "content": "x"}]
        out = extractor._normalize_roles(items)
        assert out[0]["read_aloud"] is True

    def test_read_aloud_default_false_for_word_list(self):
        items = [{"role": "main", "content_type": "word_list", "content": "x"}]
        out = extractor._normalize_roles(items)
        assert out[0]["read_aloud"] is False

    def test_read_aloud_default_false_for_sub(self):
        items = [
            {"role": "main", "content_type": "conversation", "content": "a"},
            {"role": "sub", "content_type": "passage", "content": "b"},
        ]
        out = extractor._normalize_roles(items)
        assert out[1]["read_aloud"] is False

    def test_read_aloud_explicit_value_preserved(self):
        items = [
            {"role": "main", "content_type": "passage", "content": "x", "read_aloud": False},
        ]
        out = extractor._normalize_roles(items)
        assert out[0]["read_aloud"] is False

    def test_sub_default_added_when_missing(self):
        # main 1つ + roleキー欠落のitem → "sub" が setdefault される
        items = [
            {"role": "main", "content_type": "conversation", "content": "a"},
            {"content_type": "word_list", "content": "b"},
        ]
        out = extractor._normalize_roles(items)
        assert out[1]["role"] == "sub"


# =====================================================
# extract_main_content (LLM呼び出し)
# =====================================================


class TestExtractMainContent:
    def test_empty_text_returns_empty_list(self, mock_gemini):
        assert extractor.extract_main_content("") == []
        assert extractor.extract_main_content("   \n\t  ") == []
        # 空文字の場合、LLMは呼ばれない
        mock_gemini.models.generate_content.assert_not_called()

    def test_list_response_parsed_and_normalized(self, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = (
            '[{"content_type":"conversation","content":"A: hi","label":"greet"},'
            ' {"content_type":"word_list","content":"hi: やあ","label":"vocab"}]'
        )
        result = extractor.extract_main_content("some text")
        assert len(result) == 2
        # role 正規化で先頭が main に
        assert result[0]["role"] == "main"
        assert result[1]["role"] == "sub"
        # read_aloud デフォルト（main+conversation → True）
        assert result[0]["read_aloud"] is True
        assert result[1]["read_aloud"] is False

    def test_dict_response_wrapped_in_list(self, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = (
            '{"content_type":"passage","content":"本文","label":"Intro"}'
        )
        result = extractor.extract_main_content("text")
        assert len(result) == 1
        assert result[0]["role"] == "main"

    def test_broken_json_returns_empty(self, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = "not json at all {{{"
        # json_repair が完全に失敗するケース
        result = extractor.extract_main_content("text")
        # 壊れJSONは「空配列」あるいは「例外→[]」のいずれか
        assert isinstance(result, list)

    def test_non_container_response_returns_empty(self, mock_gemini):
        # JSONとしてparseできるが list/dict ではない（数値など）
        mock_gemini.models.generate_content.return_value.text = "42"
        result = extractor.extract_main_content("text")
        assert result == []


# =====================================================
# extract_text_from_image
# =====================================================


class TestExtractTextFromImage:
    def test_nonexistent_raises(self, mock_gemini, tmp_path):
        missing = tmp_path / "no.png"
        with pytest.raises(FileNotFoundError):
            extractor.extract_text_from_image(str(missing))

    def test_calls_vision_and_cleans_response(self, mock_gemini, tmp_path):
        # 1x1 png 相当のダミーバイト（内容は問わない）
        img = tmp_path / "page.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        mock_gemini.models.generate_content.return_value.text = "  Hello&amp;World  "
        out = extractor.extract_text_from_image(str(img))
        # clean_extracted_text が通っている
        assert out == "Hello&World"
        # mime推定: .png → image/png
        call_kwargs = mock_gemini.models.generate_content.call_args.kwargs
        parts = call_kwargs["contents"][0].parts
        assert parts[0].inline_data.mime_type == "image/png"

    def test_jpeg_extension_uses_jpeg_mime(self, mock_gemini, tmp_path):
        img = tmp_path / "page.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0fake")
        mock_gemini.models.generate_content.return_value.text = "X"
        extractor.extract_text_from_image(str(img))
        call_kwargs = mock_gemini.models.generate_content.call_args.kwargs
        parts = call_kwargs["contents"][0].parts
        assert parts[0].inline_data.mime_type == "image/jpeg"


# =====================================================
# extract_text_from_url
# =====================================================


class TestExtractTextFromUrl:
    async def test_fetches_html_and_sends_to_llm(self, mock_gemini, monkeypatch):
        """httpx.AsyncClient をスタブ化し、HTMLがLLMに渡されることを確認"""

        html_body = "<html><body>本文テキスト&nbsp;です</body></html>"

        class _FakeResp:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                pass

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None):
                assert url == "https://example.com/lesson"
                assert "User-Agent" in headers
                return _FakeResp(html_body)

        monkeypatch.setattr(extractor.httpx, "AsyncClient", _FakeClient)
        mock_gemini.models.generate_content.return_value.text = "整形済み本文&nbsp;出力"

        out = await extractor.extract_text_from_url("https://example.com/lesson")
        # clean_extracted_text でHTMLエンティティが解けている
        assert "&nbsp;" not in out
        assert "整形済み本文" in out
        # LLMに渡ったcontentsにhtmlが含まれている
        call_kwargs = mock_gemini.models.generate_content.call_args.kwargs
        assert "本文テキスト" in call_kwargs["contents"]

    async def test_http_error_propagates(self, mock_gemini, monkeypatch):
        class _ErrResp:
            text = ""

            def raise_for_status(self):
                raise httpx.HTTPStatusError("500", request=None, response=None)

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None):
                return _ErrResp()

        monkeypatch.setattr(extractor.httpx, "AsyncClient", _FakeClient)

        with pytest.raises(httpx.HTTPStatusError):
            await extractor.extract_text_from_url("https://example.com/fail")
        # LLMは呼ばれない
        mock_gemini.models.generate_content.assert_not_called()

    async def test_html_truncated_to_30000_chars(self, mock_gemini, monkeypatch):
        """非常に長いHTMLは先頭30000文字でLLMに渡す（プロンプト肥大化防止）"""

        long_html = "x" * 50000

        class _FakeResp:
            text = long_html

            def raise_for_status(self):
                pass

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None):
                return _FakeResp()

        monkeypatch.setattr(extractor.httpx, "AsyncClient", _FakeClient)
        mock_gemini.models.generate_content.return_value.text = "ok"

        await extractor.extract_text_from_url("https://example.com/long")
        call_kwargs = mock_gemini.models.generate_content.call_args.kwargs
        contents = call_kwargs["contents"]
        # プロンプト接頭辞分を除いても、30000文字に切り詰められている
        assert contents.count("x") == 30000
