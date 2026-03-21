"""ai_responder のテスト（キャラクター管理・AI応答生成）

注: 言語モード・プロンプト構築のテストは test_prompt_builder.py を参照
"""

import json
from unittest.mock import MagicMock, patch

from src.ai_responder import (
    DEFAULT_CHARACTER,
    _make_image_part,
    analyze_images,
    analyze_url,
    generate_lesson_script,
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
from src.prompt_builder import set_stream_language


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
        set_stream_language("ja", "en", "low")
        invalidate_character_cache()

    def test_valid_json_response(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "speech": "やほー！",
            "tts_text": "やほー！",
            "emotion": "joy",
            "translation": "Hey!",
        })
        result = generate_response("viewer", "こんにちは")
        assert result["speech"] == "やほー！"
        assert result["emotion"] == "joy"
        assert result["translation"] == "Hey!"

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

    def test_translation_defaults_to_empty(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "speech": "test", "emotion": "neutral"
        })
        result = generate_response("viewer", "msg")
        assert result["translation"] == ""

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
        set_stream_language("ja", "en", "low")
        invalidate_character_cache()

    def test_valid_response(self, test_db, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "speech": "コミットきた！", "emotion": "joy", "translation": "Commit!"
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
        set_stream_language("ja", "en", "low")
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
        set_stream_language("ja", "en", "low")
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
        set_stream_language("ja", "en", "low")
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


class TestMakeImagePart:
    def test_png_mime_type(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic
        part = _make_image_part(str(img))
        assert part.inline_data.mime_type == "image/png"
        assert part.inline_data.data == b"\x89PNG\r\n\x1a\n"

    def test_jpg_mime_type(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff")
        part = _make_image_part(str(img))
        assert part.inline_data.mime_type == "image/jpeg"

    def test_jpeg_mime_type(self, tmp_path):
        img = tmp_path / "photo.jpeg"
        img.write_bytes(b"\xff\xd8\xff")
        part = _make_image_part(str(img))
        assert part.inline_data.mime_type == "image/jpeg"

    def test_webp_mime_type(self, tmp_path):
        img = tmp_path / "test.webp"
        img.write_bytes(b"RIFF")
        part = _make_image_part(str(img))
        assert part.inline_data.mime_type == "image/webp"

    def test_unknown_ext_defaults_to_jpeg(self, tmp_path):
        img = tmp_path / "test.bmp"
        img.write_bytes(b"BM")
        part = _make_image_part(str(img))
        assert part.inline_data.mime_type == "image/jpeg"


class TestAnalyzeImages:
    def test_calls_gemini_with_images_and_prompt(self, mock_env, mock_gemini, tmp_path):
        img1 = tmp_path / "a.png"
        img1.write_bytes(b"\x89PNG")
        img2 = tmp_path / "b.jpg"
        img2.write_bytes(b"\xff\xd8")
        mock_gemini.models.generate_content.return_value.text = "解析結果テキスト"

        result = analyze_images([str(img1), str(img2)], "この画像を説明してください")
        assert result == "解析結果テキスト"

        # Gemini APIに画像2枚+テキスト1件が送られたことを確認
        call_args = mock_gemini.models.generate_content.call_args
        contents = call_args.kwargs.get("contents") or call_args[1].get("contents")
        parts = contents[0].parts
        assert len(parts) == 3  # 2 images + 1 text
        assert parts[2].text == "この画像を説明してください"


class TestAnalyzeUrl:
    def test_extracts_title_and_text(self, mock_env):
        html = """<html><head><title>テスト記事</title>
        <meta property="og:title" content="OGPタイトル">
        <meta property="og:image" content="https://example.com/img.jpg">
        </head><body><p>本文テキスト</p></body></html>"""

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            result = analyze_url("https://example.com/article")
            assert result["title"] == "OGPタイトル"
            assert "本文テキスト" in result["text"]
            assert result["image_url"] == "https://example.com/img.jpg"

    def test_fallback_to_title_tag(self, mock_env):
        html = "<html><head><title>タイトルタグ</title></head><body>本文</body></html>"

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            result = analyze_url("https://example.com")
            assert result["title"] == "タイトルタグ"
            assert result["image_url"] is None

    def test_strips_nav_and_script(self, mock_env):
        html = "<html><body><nav>ナビ</nav><script>alert(1)</script><p>本文</p></body></html>"

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            result = analyze_url("https://example.com")
            assert "ナビ" not in result["text"]
            assert "alert" not in result["text"]
            assert "本文" in result["text"]

    def test_long_text_truncated(self, mock_env):
        html = "<html><body><p>" + "あ" * 40000 + "</p></body></html>"

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            result = analyze_url("https://example.com")
            assert len(result["text"]) < 40000
            assert "以下省略" in result["text"]


class TestGenerateLessonScript:
    def setup_method(self):
        invalidate_character_cache()

    def test_valid_script_response(self, mock_env, mock_gemini):
        scripts = [
            {"step": 1, "content": "導入", "tts_text": "導入", "image_index": 0},
            {"step": 2, "content": "解説", "tts_text": "解説", "image_index": 0},
        ]
        mock_gemini.models.generate_content.return_value.text = json.dumps(scripts)
        result = generate_lesson_script("テストコンテキスト", num_images=1)
        assert len(result) == 2
        assert result[0]["content"] == "導入"
        assert result[1]["image_index"] == 0

    def test_invalid_json_returns_empty(self, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = "bad json"
        result = generate_lesson_script("テスト")
        assert result == []

    def test_non_list_response_returns_empty(self, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps({"error": "oops"})
        result = generate_lesson_script("テスト")
        assert result == []

    def test_no_images_prompt_contains_null_rule(self, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps([])
        generate_lesson_script("テスト", num_images=0)
        call_args = mock_gemini.models.generate_content.call_args
        contents = call_args.kwargs.get("contents") or call_args[1].get("contents")
        prompt_text = contents[0].parts[0].text
        assert "常にnull" in prompt_text

    def test_with_images_prompt_contains_range(self, mock_env, mock_gemini):
        mock_gemini.models.generate_content.return_value.text = json.dumps([])
        generate_lesson_script("テスト", num_images=3)
        call_args = mock_gemini.models.generate_content.call_args
        contents = call_args.kwargs.get("contents") or call_args[1].get("contents")
        prompt_text = contents[0].parts[0].text
        assert "0〜2" in prompt_text
