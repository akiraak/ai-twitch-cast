"""lesson_generator/utils.py のテスト

範囲:
- _is_english_mode: 配信言語の primary で判定
- _get_model: 環境変数 GEMINI_CHAT_MODEL の反映とモジュールキャッシュ
- _parse_json_response: parse_llm_json への委譲
- _guess_mime: 拡張子から MIME type
- _build_image_parts: 画像パス→Gemini Parts 変換（存在しないファイルはスキップ）
- get_lesson_characters: teacher/student を DB から取得（persona/self_note 含む）
- _format_character_for_prompt: プロンプト用テキスト整形（日本語/英語モード）
- _format_main_content_for_prompt: main_content リストのプロンプト整形
"""

import json

from src import db
from src.lesson_generator import utils as lg_utils
from src.prompt_builder import set_stream_language


# =====================================================
# _is_english_mode
# =====================================================


class TestIsEnglishMode:
    def teardown_method(self):
        set_stream_language("ja", "en", "low")

    def test_japanese_primary_is_not_english(self):
        set_stream_language("ja", "en", "low")
        assert lg_utils._is_english_mode() is False

    def test_english_primary_is_english(self):
        set_stream_language("en", "ja", "low")
        assert lg_utils._is_english_mode() is True

    def test_korean_primary_is_english_mode(self):
        # 関数仕様: primary が "ja" でない場合はすべて英語モード扱い
        set_stream_language("ko", "ja", "low")
        assert lg_utils._is_english_mode() is True


# =====================================================
# _get_model
# =====================================================


class TestGetModel:
    def setup_method(self):
        # モジュールキャッシュをリセット
        lg_utils._CHAT_MODEL = None

    def teardown_method(self):
        lg_utils._CHAT_MODEL = None

    def test_env_variable_used(self, monkeypatch):
        monkeypatch.setenv("GEMINI_CHAT_MODEL", "custom-model-1")
        assert lg_utils._get_model() == "custom-model-1"

    def test_default_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("GEMINI_CHAT_MODEL", raising=False)
        assert lg_utils._get_model() == "gemini-3-flash-preview"

    def test_result_cached_after_first_call(self, monkeypatch):
        monkeypatch.setenv("GEMINI_CHAT_MODEL", "first")
        assert lg_utils._get_model() == "first"
        # キャッシュ後は環境変数を変えても反映されない
        monkeypatch.setenv("GEMINI_CHAT_MODEL", "second")
        assert lg_utils._get_model() == "first"


# =====================================================
# _parse_json_response
# =====================================================


class TestParseJsonResponse:
    def test_plain_json_parsed(self):
        assert lg_utils._parse_json_response('{"a": 1}') == {"a": 1}

    def test_code_block_stripped(self):
        assert lg_utils._parse_json_response('```json\n[1, 2, 3]\n```') == [1, 2, 3]

    def test_broken_json_repaired(self):
        # 末尾カンマ、シングルクォートなど json_repair で修復可能
        out = lg_utils._parse_json_response("{'a': 1, }")
        assert out == {"a": 1}


# =====================================================
# _guess_mime
# =====================================================


class TestGuessMime:
    def test_png(self):
        assert lg_utils._guess_mime(".png") == "image/png"

    def test_jpg_and_jpeg(self):
        assert lg_utils._guess_mime(".jpg") == "image/jpeg"
        assert lg_utils._guess_mime(".jpeg") == "image/jpeg"

    def test_webp(self):
        assert lg_utils._guess_mime(".webp") == "image/webp"

    def test_gif(self):
        assert lg_utils._guess_mime(".gif") == "image/gif"

    def test_uppercase_normalized(self):
        assert lg_utils._guess_mime(".JPG") == "image/jpeg"

    def test_unknown_defaults_to_png(self):
        assert lg_utils._guess_mime(".bmp") == "image/png"
        assert lg_utils._guess_mime("") == "image/png"


# =====================================================
# _build_image_parts
# =====================================================


class TestBuildImageParts:
    def test_none_returns_empty_list(self):
        assert lg_utils._build_image_parts(None) == []

    def test_empty_list_returns_empty_list(self):
        assert lg_utils._build_image_parts([]) == []

    def test_existing_file_converted_to_part(self, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"\x89PNGdata")
        parts = lg_utils._build_image_parts([str(img)])
        assert len(parts) == 1
        assert parts[0].inline_data.mime_type == "image/png"
        assert parts[0].inline_data.data == b"\x89PNGdata"

    def test_missing_files_skipped(self, tmp_path):
        existing = tmp_path / "real.jpg"
        existing.write_bytes(b"jpegdata")
        missing = tmp_path / "ghost.png"
        parts = lg_utils._build_image_parts([str(missing), str(existing)])
        # 存在しないファイルは無視され、1件だけ返る
        assert len(parts) == 1
        assert parts[0].inline_data.mime_type == "image/jpeg"

    def test_multiple_files_preserved_in_order(self, tmp_path):
        a = tmp_path / "1.png"
        a.write_bytes(b"a")
        b = tmp_path / "2.jpg"
        b.write_bytes(b"b")
        parts = lg_utils._build_image_parts([str(a), str(b)])
        assert [p.inline_data.data for p in parts] == [b"a", b"b"]
        assert [p.inline_data.mime_type for p in parts] == ["image/png", "image/jpeg"]


# =====================================================
# get_lesson_characters
# =====================================================


class TestGetLessonCharacters:
    def test_returns_teacher_and_student(self, test_db, monkeypatch):
        monkeypatch.setenv("TWITCH_CHANNEL", "ch-test")
        result = lg_utils.get_lesson_characters()
        assert "teacher" in result
        assert "student" in result
        assert result["teacher"] is not None
        assert result["student"] is not None
        # seed_all_characters が走ることで必ず入っている

    def test_teacher_config_includes_name(self, test_db, monkeypatch):
        monkeypatch.setenv("TWITCH_CHANNEL", "ch-name")
        result = lg_utils.get_lesson_characters()
        # name は config に注入される
        assert result["teacher"]["name"]
        assert result["student"]["name"]
        # teacher と student の name は異なる
        assert result["teacher"]["name"] != result["student"]["name"]

    def test_persona_and_self_note_included(self, test_db, monkeypatch):
        from src.character_manager import get_channel_id

        monkeypatch.setenv("TWITCH_CHANNEL", "ch-memory")
        # まず seed するために一度取得
        lg_utils.get_lesson_characters()
        channel_id = get_channel_id()
        teacher_row = db.get_character_by_role(channel_id, "teacher")
        assert teacher_row is not None
        db.update_character_persona(teacher_row["id"], "優しい先生")
        db.update_character_self_note(teacher_row["id"], "生徒思い")
        # 二回目: persona/self_note が反映される
        result = lg_utils.get_lesson_characters()
        assert result["teacher"]["persona"] == "優しい先生"
        assert result["teacher"]["self_note"] == "生徒思い"

    def test_persona_defaults_to_empty_string(self, test_db, monkeypatch):
        monkeypatch.setenv("TWITCH_CHANNEL", "ch-empty")
        result = lg_utils.get_lesson_characters()
        # 未設定時は空文字
        assert result["teacher"]["persona"] == ""
        assert result["teacher"]["self_note"] == ""


# =====================================================
# _format_character_for_prompt
# =====================================================


class TestFormatCharacterForPrompt:
    def test_minimal_config(self):
        config = {"name": "ちょビ", "system_prompt": "元気な先生"}
        out = lg_utils._format_character_for_prompt(config, "teacher", en=False)
        assert "### teacher: ちょビ" in out
        assert 'speaker: "teacher"' in out
        assert "元気な先生" in out

    def test_fallback_name_from_role_label(self):
        config = {"system_prompt": "x"}
        out = lg_utils._format_character_for_prompt(config, "student", en=False)
        # name が無いと role_label が代わりに使われる
        assert "### student: student" in out

    def test_emotions_listed_in_japanese(self):
        config = {
            "name": "N",
            "system_prompt": "p",
            "emotions": {"happy": "嬉しい", "sad": "悲しい"},
        }
        out = lg_utils._format_character_for_prompt(config, "teacher", en=False)
        assert "使用可能な感情:" in out
        assert "happy" in out and "sad" in out

    def test_emotions_listed_in_english(self):
        config = {
            "name": "N",
            "system_prompt": "p",
            "emotions": {"happy": "glad"},
        }
        out = lg_utils._format_character_for_prompt(config, "teacher", en=True)
        assert "Available emotions:" in out
        assert "happy" in out

    def test_no_emotions_no_emotions_section(self):
        config = {"name": "N", "system_prompt": "p"}
        out = lg_utils._format_character_for_prompt(config, "teacher", en=False)
        assert "使用可能な感情" not in out
        assert "Available emotions" not in out

    def test_empty_system_prompt_omitted(self):
        config = {"name": "N", "system_prompt": ""}
        out = lg_utils._format_character_for_prompt(config, "teacher", en=False)
        # system_prompt が空なら本文行が出ない
        lines = out.splitlines()
        assert len(lines) == 1  # 先頭の ### だけ


# =====================================================
# _format_main_content_for_prompt
# =====================================================


class TestFormatMainContentForPrompt:
    def test_empty_returns_empty_string(self):
        assert lg_utils._format_main_content_for_prompt([], en=False) == ""
        assert lg_utils._format_main_content_for_prompt(None, en=False) == ""

    def test_main_conversation_read_aloud_full_content(self):
        mc = [{
            "content_type": "conversation",
            "label": "greet",
            "content": "A: hi\nB: hello",
            "role": "main",
            "read_aloud": True,
        }]
        out = lg_utils._format_main_content_for_prompt(mc, en=False)
        assert "★ 主要" in out
        assert "🔊 読み上げ対象" in out
        assert "A: hi" in out
        assert "B: hello" in out

    def test_sub_content_truncated_to_200_chars(self):
        long_content = "x" * 500
        mc = [{
            "content_type": "word_list",
            "label": "vocab",
            "content": long_content,
            "role": "sub",
        }]
        out = lg_utils._format_main_content_for_prompt(mc, en=False)
        assert "..." in out
        # 200文字までのプレビューのみ（500文字分は入らない）
        assert out.count("x") == 200

    def test_main_read_aloud_truncated_at_2000(self):
        long = "z" * 3000
        mc = [{
            "content_type": "passage",
            "label": "本文",
            "content": long,
            "role": "main",
            "read_aloud": True,
        }]
        out = lg_utils._format_main_content_for_prompt(mc, en=False)
        assert "..." in out
        # 2000文字切り詰め後に "..." が付く（label に 'z' は含まれない）
        assert out.count("z") == 2000

    def test_english_mode_uses_english_labels(self):
        mc = [{
            "content_type": "passage",
            "label": "body",
            "content": "text",
            "role": "main",
            "read_aloud": True,
        }]
        out = lg_utils._format_main_content_for_prompt(mc, en=True)
        assert "★ PRIMARY" in out
        assert "🔊 READ ALOUD" in out
        assert "★ 主要" not in out

    def test_multiple_items_numbered(self):
        mc = [
            {"content_type": "conversation", "label": "a", "content": "x",
             "role": "main", "read_aloud": True},
            {"content_type": "word_list", "label": "b", "content": "y",
             "role": "sub"},
        ]
        out = lg_utils._format_main_content_for_prompt(mc, en=False)
        assert "1. [conversation]" in out
        assert "2. [word_list]" in out

    def test_first_item_default_role_main(self):
        # role キーが無い → 1件目は main, 2件目以降は sub がデフォルト
        mc = [
            {"content_type": "passage", "label": "a", "content": "x"},
            {"content_type": "word_list", "label": "b", "content": "y"},
        ]
        out = lg_utils._format_main_content_for_prompt(mc, en=False)
        assert "1. [passage] (★ 主要)" in out
        assert "2. [word_list] (補助)" in out
