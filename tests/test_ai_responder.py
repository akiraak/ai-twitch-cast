"""ai_responder のテスト（キャラクター管理・AI応答生成）

注: 言語モード・プロンプト構築のテストは test_prompt_builder.py を参照
"""

import json
from unittest.mock import MagicMock, patch

from src.ai_responder import (
    DEFAULT_CHARACTER,
    generate_persona_from_prompt,
    generate_response,
    generate_event_response,
    generate_user_notes,
    generate_self_note,
    get_character,
    invalidate_character_cache,
    load_character,
    seed_character,
)
from src.prompt_builder import set_language_mode


class TestCharacterManagement:
    def setup_method(self):
        invalidate_character_cache()

    def test_seed_character_creates(self, test_db):
        ch = test_db.get_or_create_channel("test_ch")
        char = seed_character(ch["id"])
        assert char["name"] == DEFAULT_CHARACTER["name"]

    def test_seed_character_idempotent(self, test_db):
        ch = test_db.get_or_create_channel("test_ch")
        c1 = seed_character(ch["id"])
        c2 = seed_character(ch["id"])
        assert c1["id"] == c2["id"]

    def test_load_character_from_db(self, test_db, mock_env):
        result = load_character()
        assert result["name"] == DEFAULT_CHARACTER["name"]

    def test_get_character_lazy_loads(self, test_db, mock_env):
        char = get_character()
        assert "system_prompt" in char
        assert "emotions" in char

    def test_invalidate_cache(self, test_db, mock_env):
        load_character()
        invalidate_character_cache()
        # _character is None, get_character will reload
        char = get_character()
        assert char is not None


class TestGenerateResponse:
    def setup_method(self):
        set_language_mode("ja")
        invalidate_character_cache()

    def test_valid_json_response(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "speech": "やほー！",
            "tts_text": "やほー！",
            "emotion": "joy",
            "english": "Hey!",
        })
        result = generate_response("viewer", "こんにちは")
        assert result["speech"] == "やほー！"
        assert result["emotion"] == "joy"
        assert result["english"] == "Hey!"

    def test_invalid_json_fallback(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = "broken json"
        result = generate_response("viewer", "hello")
        assert result["speech"] == "hello"
        assert result["emotion"] == "neutral"

    def test_unknown_emotion_fallback(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "speech": "test", "emotion": "rage"
        })
        result = generate_response("viewer", "msg")
        assert result["emotion"] == "neutral"

    def test_english_defaults_to_empty(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "speech": "test", "emotion": "neutral"
        })
        result = generate_response("viewer", "msg")
        assert result["english"] == ""

    def test_timeline_passed_to_gemini(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "speech": "ok", "emotion": "neutral"
        })
        timeline = [
            {"type": "comment", "user_name": "alice", "text": "hi"},
            {"type": "avatar_comment", "text": "hello"},
        ]
        generate_response("bob", "hey", timeline=timeline)
        call_args = mock_gemini.models.generate_content.call_args
        contents = call_args.kwargs.get("contents") or call_args[1].get("contents")
        # 履歴2件（user+model） + 今回のメッセージ1件 = 3
        assert len(contents) == 3


class TestGenerateEventResponse:
    def setup_method(self):
        set_language_mode("ja")
        invalidate_character_cache()

    def test_valid_response(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "speech": "コミットきた！", "emotion": "joy", "english": "Commit!"
        })
        result = generate_event_response("commit", "fix: bug修正")
        assert result["speech"] == "コミットきた！"

    def test_invalid_json_fallback(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = "bad"
        result = generate_event_response("commit", "detail text")
        assert result["speech"] == "detail text"
        assert result["emotion"] == "neutral"


class TestGenerateUserNotes:
    def setup_method(self):
        set_language_mode("ja")
        invalidate_character_cache()

    def test_empty_input(self, test_db, mock_env, mock_gemini):
        result = generate_user_notes([])
        assert result == {}

    def test_valid_response(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "alice": "Pythonが好き"
        })
        users = [{"name": "alice", "note": "", "comments": [{"text": "Python最高"}]}]
        result = generate_user_notes(users)
        assert result["alice"] == "Pythonが好き"

    def test_invalid_json_returns_empty(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = "bad"
        result = generate_user_notes([{"name": "a", "comments": [{"text": "hi"}]}])
        assert result == {}


class TestGenerateSelfNote:
    def setup_method(self):
        set_language_mode("ja")
        invalidate_character_cache()

    def test_empty_comments_returns_current(self, test_db, mock_env, mock_gemini):
        result = generate_self_note([], current_note="existing")
        assert result == "existing"

    def test_empty_comments_no_note(self, test_db, mock_env, mock_gemini):
        result = generate_self_note([])
        assert result == ""

    def test_valid_response(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "note": "視聴者とPythonの話をした"
        })
        timeline = [
            {"type": "comment", "user_name": "alice", "text": "Python"},
            {"type": "avatar_comment", "text": "いいね"},
        ]
        result = generate_self_note(timeline)
        assert result == "視聴者とPythonの話をした"

    def test_invalid_json_returns_current(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = "bad"
        result = generate_self_note(
            [{"type": "comment", "user_name": "a", "text": "hi"}],
            current_note="fallback"
        )
        assert result == "fallback"

    def test_timestamps_included_in_prompt(self, test_db, mock_env, mock_gemini):
        """タイムスタンプ付きコメントがプロンプトに含まれることを確認"""
        mock_gemini.models.generate_content.return_value.text = json.dumps({"note": "test"})
        timeline = [
            {"type": "comment", "user_name": "alice", "text": "hi",
             "created_at": "2026-03-19T10:30:00"},
        ]
        generate_self_note(timeline)
        call_args = mock_gemini.models.generate_content.call_args
        prompt = call_args.kwargs.get("contents", call_args[1].get("contents", ""))
        assert "2026-03-19T10:30" in prompt

    def test_timestamps_missing_handled(self, test_db, mock_env, mock_gemini):
        """タイムスタンプがないコメントでもエラーにならない"""
        mock_gemini.models.generate_content.return_value.text = json.dumps({"note": "ok"})
        timeline = [{"type": "avatar_comment", "text": "sup"}]
        result = generate_self_note(timeline)
        assert result == "ok"


class TestGeneratePersonaFromPrompt:
    def setup_method(self):
        set_language_mode("ja")
        invalidate_character_cache()

    def test_generates_from_system_prompt(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "persona": "好奇心旺盛でツッコミ気質"
        })
        result = generate_persona_from_prompt()
        assert result == "好奇心旺盛でツッコミ気質"
        # プロンプトにキャラクター設定が含まれていることを確認
        call_args = mock_gemini.models.generate_content.call_args
        prompt = call_args.kwargs.get("contents", call_args[1].get("contents", ""))
        assert "キャラクター設定" in prompt

    def test_invalid_json_returns_empty(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = "bad"
        result = generate_persona_from_prompt()
        assert result == ""
