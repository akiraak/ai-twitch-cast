"""json_utils の parse_llm_json テスト"""

import json

import pytest

from src.json_utils import parse_llm_json


class TestParseLlmJson:
    """parse_llm_json のテスト"""

    def test_valid_json(self):
        """正常なJSONはそのままパースされる"""
        result = parse_llm_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_valid_json_array(self):
        result = parse_llm_json('[{"a": 1}, {"b": 2}]')
        assert isinstance(result, list)
        assert len(result) == 2

    def test_code_block_json(self):
        """```json ... ``` コードブロックが除去される"""
        text = '```json\n{"key": "value"}\n```'
        result = parse_llm_json(text)
        assert result == {"key": "value"}

    def test_code_block_no_lang(self):
        """```のみのコードブロックも除去される"""
        text = '```\n{"key": "value"}\n```'
        result = parse_llm_json(text)
        assert result == {"key": "value"}

    def test_truncated_string_repair(self):
        """途中で切れた文字列が修復される"""
        broken = '{"content": "こんにちは！今日は英語を学び'
        result = parse_llm_json(broken)
        assert isinstance(result, dict)
        assert "content" in result
        assert "こんにちは" in result["content"]

    def test_truncated_object_repair(self):
        """途中で切れたオブジェクトが修復される"""
        broken = '{"content": "hello", "emotion": "excited"'
        result = parse_llm_json(broken)
        assert isinstance(result, dict)
        assert result["content"] == "hello"
        assert result["emotion"] == "excited"

    def test_truncated_array_repair(self):
        """途中で切れた配列が修復される"""
        broken = '[{"section_type": "introduction"}, {"section_type": "explanation"'
        result = parse_llm_json(broken)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_trailing_comma_repair(self):
        """末尾カンマが修復される"""
        broken = '{"key": "value",}'
        result = parse_llm_json(broken)
        assert result == {"key": "value"}

    def test_empty_string(self):
        """空文字列は空文字列として修復される"""
        result = parse_llm_json("")
        assert result == ""

    def test_whitespace_around_json(self):
        """前後の空白は無視される"""
        result = parse_llm_json('  \n  {"key": "value"}  \n  ')
        assert result == {"key": "value"}

    def test_nested_json_repair(self):
        """ネストされたJSONの修復"""
        broken = '{"dialogues": [{"speaker": "teacher", "content": "hello"}, {"speaker": "student"'
        result = parse_llm_json(broken)
        assert isinstance(result, dict)
        assert "dialogues" in result

    def test_code_block_with_truncated_json(self):
        """コードブロック内の壊れたJSONも修復される"""
        broken = '```json\n{"content": "テスト", "emotion": "excited"\n```'
        result = parse_llm_json(broken)
        assert isinstance(result, dict)
        assert result["content"] == "テスト"
