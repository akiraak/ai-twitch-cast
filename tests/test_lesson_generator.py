"""lesson_generator の対話形式スクリプト生成テスト"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.lesson_generator import (
    _build_adjacent_sections,
    _build_dialogue_output_example,
    _build_dialogue_prompt,
    _build_section_from_dialogues,
    _build_structure_prompt,
    _director_review,
    _format_character_for_prompt,
    _generate_single_dialogue,
    _generate_section_dialogues,
    _normalize_roles,
    _parse_json_response,
    clean_extracted_text,
    extract_main_content,
)


# --- テスト用キャラクター設定 ---

TEACHER_CFG = {
    "name": "ちょビ",
    "system_prompt": "明るく楽しい口調で教える先生",
    "emotions": {"joy": "嬉しい", "excited": "ワクワク", "neutral": "通常"},
}

STUDENT_CFG = {
    "name": "なるこ",
    "system_prompt": "好奇心旺盛で素直な生徒",
    "emotions": {"joy": "嬉しい", "surprise": "驚き", "neutral": "通常"},
}


class TestBuildSectionFromDialogues:
    """_build_section_from_dialogues のテスト"""

    def test_basic(self):
        """dialoguesからcontent/tts_text/emotionが構築される"""
        section = {
            "section_type": "introduction",
            "dialogues": [
                {"speaker": "teacher", "content": "こんにちは！", "tts_text": "こんにちは！", "emotion": "excited"},
                {"speaker": "student", "content": "よろしく！", "tts_text": "よろしく！", "emotion": "joy"},
            ],
        }
        result = _build_section_from_dialogues(section)
        assert result["content"] == "こんにちは！よろしく！"
        assert result["tts_text"] == "こんにちは！よろしく！"
        assert result["emotion"] == "excited"  # 先生の最初の感情

    def test_teacher_only(self):
        """先生のみのセクション"""
        section = {
            "section_type": "explanation",
            "dialogues": [
                {"speaker": "teacher", "content": "説明です。", "tts_text": "説明です。", "emotion": "neutral"},
            ],
        }
        result = _build_section_from_dialogues(section)
        assert result["content"] == "説明です。"
        assert result["emotion"] == "neutral"

    def test_student_only_emotion_fallback(self):
        """生徒のみの場合、emotionはneutralにフォールバック"""
        section = {
            "section_type": "example",
            "dialogues": [
                {"speaker": "student", "content": "わかった！", "tts_text": "わかった！", "emotion": "joy"},
            ],
        }
        result = _build_section_from_dialogues(section)
        assert result["emotion"] == "neutral"

    def test_empty_dialogues(self):
        """dialoguesが空ならそのまま返す"""
        section = {
            "section_type": "explanation",
            "content": "既存コンテンツ",
            "tts_text": "既存TTS",
            "emotion": "joy",
            "dialogues": [],
        }
        result = _build_section_from_dialogues(section)
        assert result["content"] == "既存コンテンツ"
        assert result["emotion"] == "joy"

    def test_no_dialogues_key(self):
        """dialoguesキーがなければそのまま返す"""
        section = {"section_type": "explanation", "content": "テスト"}
        result = _build_section_from_dialogues(section)
        assert result["content"] == "テスト"

    def test_tts_text_fallback(self):
        """tts_textがなければcontentをフォールバック"""
        section = {
            "section_type": "introduction",
            "dialogues": [
                {"speaker": "teacher", "content": "Hello!", "emotion": "excited"},
            ],
        }
        result = _build_section_from_dialogues(section)
        assert result["tts_text"] == "Hello!"

    def test_multiple_turns(self):
        """複数ターンの会話"""
        section = {
            "section_type": "question",
            "dialogues": [
                {"speaker": "teacher", "content": "問題です。", "tts_text": "問題です。", "emotion": "thinking"},
                {"speaker": "student", "content": "えーと…2？", "tts_text": "えーと…2？", "emotion": "thinking"},
                {"speaker": "teacher", "content": "正解！", "tts_text": "正解！", "emotion": "excited"},
            ],
        }
        result = _build_section_from_dialogues(section)
        assert result["content"] == "問題です。えーと…2？正解！"
        assert result["emotion"] == "thinking"  # 最初のteacherのemotion


class TestFormatCharacterForPrompt:
    """_format_character_for_prompt のテスト"""

    def test_japanese(self):
        text = _format_character_for_prompt(TEACHER_CFG, "teacher", en=False)
        assert "teacher: ちょビ" in text
        assert "明るく楽しい口調で教える先生" in text
        assert "使用可能な感情" in text
        assert "joy" in text

    def test_english(self):
        text = _format_character_for_prompt(STUDENT_CFG, "student", en=True)
        assert "student: なるこ" in text
        assert "Available emotions" in text

    def test_no_emotions(self):
        cfg = {"name": "テスト", "system_prompt": "テスト用"}
        text = _format_character_for_prompt(cfg, "teacher", en=False)
        assert "使用可能な感情" not in text

    def test_no_system_prompt(self):
        cfg = {"name": "テスト", "emotions": {"joy": "嬉しい"}}
        text = _format_character_for_prompt(cfg, "teacher", en=False)
        assert "テスト" in text
        assert "joy" in text


class TestBuildDialoguePrompt:
    """_build_dialogue_prompt のテスト"""

    def test_japanese_prompt(self):
        prompt = _build_dialogue_prompt(TEACHER_CFG, STUDENT_CFG, en=False)
        assert "登場キャラクター" in prompt
        assert "dialogues フィールド" in prompt
        assert "teacher" in prompt
        assert "student" in prompt
        assert "ちょビ" in prompt
        assert "なるこ" in prompt

    def test_english_prompt(self):
        prompt = _build_dialogue_prompt(TEACHER_CFG, STUDENT_CFG, en=True)
        assert "Characters" in prompt
        assert "dialogues field" in prompt
        assert "teacher" in prompt
        assert "student" in prompt


class TestBuildDialogueOutputExample:
    """_build_dialogue_output_example のテスト"""

    def test_japanese_example(self):
        example = _build_dialogue_output_example(en=False)
        assert "dialogues" in example
        assert "speaker" in example
        assert "teacher" in example
        assert "student" in example
        assert "JSON配列のみを出力" in example

    def test_english_example(self):
        example = _build_dialogue_output_example(en=True)
        assert "dialogues" in example
        assert "Output ONLY the JSON array" in example

    def test_json_parseable_example(self):
        """出力例のJSON部分がパース可能"""
        import re
        for en in [True, False]:
            example = _build_dialogue_output_example(en=en)
            m = re.search(r'```json\s*\n(.*?)\n```', example, re.DOTALL)
            assert m, f"JSON block not found (en={en})"
            parsed = json.loads(m.group(1))
            assert isinstance(parsed, list)
            assert len(parsed) > 0
            assert "dialogues" in parsed[0]


# --- v2: セリフ個別生成テスト ---


class TestParseJsonResponse:
    """_parse_json_response のテスト"""

    def test_plain_json(self):
        result = _parse_json_response('{"content": "hello"}')
        assert result == {"content": "hello"}

    def test_code_block(self):
        result = _parse_json_response('```json\n{"content": "hello"}\n```')
        assert result == {"content": "hello"}

    def test_array(self):
        result = _parse_json_response('[{"a": 1}]')
        assert isinstance(result, list)

    def test_invalid_json_repaired(self):
        """不正なJSONはjson-repairで修復される"""
        result = _parse_json_response("not json")
        assert result is not None


class TestBuildStructurePrompt:
    """_build_structure_prompt のテスト"""

    def test_japanese_no_plan(self):
        prompt = _build_structure_prompt(en=False)
        assert "dialogue_plan" in prompt
        assert "セクション構造デザイナー" in prompt
        assert "授業プラン" not in prompt

    def test_japanese_with_plan(self):
        prompt = _build_structure_prompt(en=False, plan_text="1. [introduction] テスト")
        assert "dialogue_plan" in prompt
        assert "授業プラン" in prompt
        assert "テスト" in prompt

    def test_english_no_plan(self):
        prompt = _build_structure_prompt(en=True)
        assert "dialogue_plan" in prompt
        assert "structure designer" in prompt

    def test_english_with_plan(self):
        prompt = _build_structure_prompt(en=True, plan_text="1. [introduction] Test")
        assert "Lesson plan" in prompt
        assert "Test" in prompt

    def test_json_example_parseable(self):
        """プロンプト内のJSON例がパース可能"""
        import re
        for en in [True, False]:
            prompt = _build_structure_prompt(en=en)
            m = re.search(r'```json\s*\n(.*?)\n```', prompt, re.DOTALL)
            assert m, f"JSON block not found (en={en})"
            parsed = json.loads(m.group(1))
            assert isinstance(parsed, list)
            assert "dialogue_plan" in parsed[0]

    def test_english_with_main_content(self):
        """英語版: main_contentありで種別ルール・優先度・コンテンツが含まれる"""
        mc = [
            {"content_type": "conversation", "content": "A: Hi\nB: Hello", "label": "Greeting", "role": "main"},
            {"content_type": "passage", "content": "Some explanation text.", "label": "Explanation", "role": "sub"},
        ]
        prompt = _build_structure_prompt(en=True, main_content=mc)
        assert "How to handle main content by type" in prompt
        assert "conversation" in prompt
        assert "passage" in prompt
        assert "word_list" in prompt
        assert "Pre-analyzed main content" in prompt
        assert "[conversation]" in prompt
        assert "Greeting" in prompt
        assert "A: Hi" in prompt
        # role タグが含まれる
        assert "PRIMARY" in prompt
        assert "supplementary" in prompt
        # 優先度ガイダンスが含まれる
        assert "Main vs supplementary content priority" in prompt

    def test_japanese_with_main_content(self):
        """日本語版: main_contentありで種別ルール・優先度・コンテンツが含まれる"""
        mc = [
            {"content_type": "word_list", "content": "apple: りんご\ndog: 犬", "label": "単語リスト", "role": "main"},
        ]
        prompt = _build_structure_prompt(en=False, main_content=mc)
        assert "メインコンテンツの種別ごとの読み上げ方" in prompt
        assert "conversation（会話文）" in prompt
        assert "word_list（単語・フレーズ集）" in prompt
        assert "事前分析済み" in prompt
        assert "[word_list]" in prompt
        assert "単語リスト" in prompt
        assert "apple: りんご" in prompt
        # role タグが含まれる
        assert "★ 主要" in prompt
        # 優先度ガイダンスが含まれる
        assert "主要コンテンツと補助コンテンツの優先度" in prompt

    def test_no_main_content_no_rules(self):
        """main_contentがNone/空の場合はルール追加なし"""
        for mc in [None, []]:
            prompt = _build_structure_prompt(en=True, main_content=mc)
            assert "How to handle main content" not in prompt
            prompt_ja = _build_structure_prompt(en=False, main_content=mc)
            assert "メインコンテンツの種別" not in prompt_ja

    def test_main_content_role_fallback(self):
        """roleフィールドなしの後方互換: 最初=main, 残り=sub"""
        mc = [
            {"content_type": "conversation", "content": "A: Hi", "label": "Dialog"},
            {"content_type": "word_list", "content": "hi: こんにちは", "label": "Vocab"},
        ]
        prompt = _build_structure_prompt(en=True, main_content=mc)
        assert "PRIMARY" in prompt
        assert "supplementary" in prompt


class TestGenerateSingleDialogue:
    """_generate_single_dialogue のテスト"""

    def test_basic_generation(self):
        """基本的なセリフ生成とメタデータ付き返却"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "content": "こんにちは！",
            "tts_text": "こんにちは！",
            "emotion": "excited",
        })
        mock_client.models.generate_content.return_value = mock_response

        with patch("src.lesson_generator._get_dialogue_model", return_value="test-model"):
            result = _generate_single_dialogue(
                client=mock_client,
                character_config=TEACHER_CFG,
                role="teacher",
                section_context={"section_type": "introduction", "display_text": "テスト"},
                dialogue_plan_entry={"speaker": "teacher", "direction": "挨拶する"},
                conversation_history=[],
                extracted_text="テスト教材",
                lesson_name="テスト授業",
                en=False,
            )

        assert result["speaker"] == "teacher"
        assert result["content"] == "こんにちは！"
        assert result["emotion"] == "excited"
        assert "generation" in result
        gen = result["generation"]
        assert "ちょビ" in gen["system_prompt"]
        assert "明るく楽しい口調" in gen["system_prompt"]
        assert "挨拶する" in gen["user_prompt"]
        assert gen["model"] == "test-model"
        assert gen["temperature"] == 1.0
        assert gen["raw_output"] == mock_response.text

    def test_conversation_history_in_prompt(self):
        """会話履歴がuser_promptに含まれる"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "content": "わかった！", "tts_text": "わかった！", "emotion": "joy",
        })
        mock_client.models.generate_content.return_value = mock_response

        with patch("src.lesson_generator._get_dialogue_model", return_value="test-model"):
            result = _generate_single_dialogue(
                client=mock_client,
                character_config=STUDENT_CFG,
                role="student",
                section_context={"section_type": "explanation"},
                dialogue_plan_entry={"speaker": "student", "direction": "リアクション"},
                conversation_history=[
                    {"speaker": "teacher", "content": "今日は英語を学びます"},
                ],
                extracted_text="テスト",
                lesson_name="テスト",
                en=False,
            )

        assert "今日は英語を学びます" in result["generation"]["user_prompt"]
        assert result["speaker"] == "student"

    def test_system_prompt_uses_character_persona(self):
        """system_promptにキャラのペルソナが使われる"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"content":"test","tts_text":"test","emotion":"neutral"}'
        mock_client.models.generate_content.return_value = mock_response

        with patch("src.lesson_generator._get_model", return_value="m"):
            result = _generate_single_dialogue(
                client=mock_client,
                character_config=STUDENT_CFG,
                role="student",
                section_context={"section_type": "introduction"},
                dialogue_plan_entry={"speaker": "student", "direction": "test"},
                conversation_history=[],
                extracted_text="",
                lesson_name="test",
                en=False,
            )

        # system_instructionにキャラのsystem_promptが使われている
        call_args = mock_client.models.generate_content.call_args
        config = call_args[1]["config"] if "config" in call_args[1] else call_args.kwargs["config"]
        assert "好奇心旺盛" in config.system_instruction
        assert "なるこ" in config.system_instruction


class TestGenerateSectionDialogues:
    """_generate_section_dialogues のテスト"""

    def test_sequential_generation(self):
        """dialogue_planの各ターンが順次生成される"""
        responses = [
            json.dumps({"content": "先生の発話", "tts_text": "先生の発話", "emotion": "excited"}),
            json.dumps({"content": "生徒の発話", "tts_text": "生徒の発話", "emotion": "joy"}),
            json.dumps({"content": "先生の続き", "tts_text": "先生の続き", "emotion": "neutral"}),
        ]
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [
            MagicMock(text=r) for r in responses
        ]

        section = {
            "section_type": "introduction",
            "display_text": "テスト",
            "dialogue_plan": [
                {"speaker": "teacher", "direction": "挨拶"},
                {"speaker": "student", "direction": "リアクション"},
                {"speaker": "teacher", "direction": "続き"},
            ],
        }

        with patch("src.lesson_generator._get_model", return_value="m"):
            dialogues = _generate_section_dialogues(
                client=mock_client,
                teacher_config=TEACHER_CFG,
                student_config=STUDENT_CFG,
                section=section,
                extracted_text="テスト",
                lesson_name="テスト",
                en=False,
            )

        assert len(dialogues) == 3
        assert dialogues[0]["speaker"] == "teacher"
        assert dialogues[1]["speaker"] == "student"
        assert dialogues[2]["speaker"] == "teacher"
        assert mock_client.models.generate_content.call_count == 3

        # 3番目の呼び出しでは会話履歴に前2ターンが含まれる
        assert "先生の発話" in dialogues[2]["generation"]["user_prompt"]
        assert "生徒の発話" in dialogues[2]["generation"]["user_prompt"]

    def test_empty_plan(self):
        """dialogue_planが空なら空リストを返す"""
        result = _generate_section_dialogues(
            client=MagicMock(),
            teacher_config=TEACHER_CFG,
            student_config=STUDENT_CFG,
            section={"dialogue_plan": []},
            extracted_text="",
            lesson_name="",
            en=False,
        )
        assert result == []

    def test_progress_callback(self):
        """進捗コールバックが各ターンで呼ばれる"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text='{"content":"x","tts_text":"x","emotion":"neutral"}'
        )

        progress_calls = []

        section = {
            "section_type": "explanation",
            "dialogue_plan": [
                {"speaker": "teacher", "direction": "a"},
                {"speaker": "student", "direction": "b"},
            ],
        }

        with patch("src.lesson_generator._get_model", return_value="m"):
            _generate_section_dialogues(
                client=mock_client,
                teacher_config=TEACHER_CFG,
                student_config=STUDENT_CFG,
                section=section,
                extracted_text="",
                lesson_name="",
                en=False,
                on_progress=lambda s, n, t: progress_calls.append((s, n, t)),
            )

        assert len(progress_calls) == 2
        assert progress_calls[0] == ("teacher", 1, 2)
        assert progress_calls[1] == ("student", 2, 2)


class TestBuildSectionFromDialoguesWithGeneration:
    """generation メタデータ付きdialoguesでも_build_section_from_dialoguesが動作するか"""

    def test_with_generation_metadata(self):
        section = {
            "section_type": "introduction",
            "dialogues": [
                {
                    "speaker": "teacher",
                    "content": "こんにちは！",
                    "tts_text": "こんにちは！",
                    "emotion": "excited",
                    "generation": {
                        "system_prompt": "...",
                        "user_prompt": "...",
                        "raw_output": "...",
                        "model": "m",
                        "temperature": 0.7,
                    },
                },
                {
                    "speaker": "student",
                    "content": "よろしく！",
                    "tts_text": "よろしく！",
                    "emotion": "joy",
                    "generation": {"system_prompt": "...", "user_prompt": "...", "raw_output": "...", "model": "m", "temperature": 0.7},
                },
            ],
        }
        result = _build_section_from_dialogues(section)
        assert result["content"] == "こんにちは！よろしく！"
        assert result["emotion"] == "excited"


class TestDialogueDirectionsCompat:
    """dialogue_directions（v3）がdialogue_planと同等に扱われるテスト"""

    def test_dialogue_directions_used(self):
        """dialogue_directionsキーでもセリフ生成される"""
        responses = [
            json.dumps({"content": "先生発話", "tts_text": "先生発話", "emotion": "excited"}),
            json.dumps({"content": "生徒発話", "tts_text": "生徒発話", "emotion": "joy"}),
        ]
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [
            MagicMock(text=r) for r in responses
        ]

        section = {
            "section_type": "introduction",
            "display_text": "テスト",
            "dialogue_directions": [
                {"speaker": "teacher", "direction": "挨拶する", "key_content": "本日のテーマ"},
                {"speaker": "student", "direction": "リアクション", "key_content": ""},
            ],
        }

        with patch("src.lesson_generator._get_model", return_value="m"):
            dialogues = _generate_section_dialogues(
                client=mock_client,
                teacher_config=TEACHER_CFG,
                student_config=STUDENT_CFG,
                section=section,
                extracted_text="テスト",
                lesson_name="テスト",
                en=False,
            )

        assert len(dialogues) == 2
        assert dialogues[0]["speaker"] == "teacher"
        assert dialogues[1]["speaker"] == "student"

    def test_dialogue_directions_takes_priority(self):
        """dialogue_directionsとdialogue_planが両方あるとdialogue_directionsが優先"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text='{"content":"x","tts_text":"x","emotion":"neutral"}'
        )

        section = {
            "section_type": "explanation",
            "display_text": "テスト",
            "dialogue_directions": [
                {"speaker": "teacher", "direction": "v3の指示"},
            ],
            "dialogue_plan": [
                {"speaker": "teacher", "direction": "v2の指示"},
                {"speaker": "student", "direction": "v2の指示2"},
            ],
        }

        with patch("src.lesson_generator._get_model", return_value="m"):
            dialogues = _generate_section_dialogues(
                client=mock_client,
                teacher_config=TEACHER_CFG,
                student_config=STUDENT_CFG,
                section=section,
                extracted_text="",
                lesson_name="",
                en=False,
            )

        # dialogue_directionsの1ターンだけが使われる（dialogue_planの2ターンではなく）
        assert len(dialogues) == 1

    def test_key_content_included_in_prompt(self):
        """key_contentがユーザープロンプトに含まれる"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text='{"content":"先生発話","tts_text":"先生発話","emotion":"excited"}'
        )

        section = {
            "section_type": "introduction",
            "display_text": "テスト",
            "dialogue_directions": [
                {"speaker": "teacher", "direction": "挨拶する", "key_content": "How are you?の本当の意味"},
            ],
        }

        with patch("src.lesson_generator._get_model", return_value="m"):
            dialogues = _generate_section_dialogues(
                client=mock_client,
                teacher_config=TEACHER_CFG,
                student_config=STUDENT_CFG,
                section=section,
                extracted_text="",
                lesson_name="テスト授業",
                en=False,
            )

        # generationのuser_promptにkey_contentが含まれる
        user_prompt = dialogues[0]["generation"]["user_prompt"]
        assert "How are you?の本当の意味" in user_prompt
        assert "このターンで触れるべき内容" in user_prompt

    def test_key_content_empty_not_included(self):
        """key_contentが空文字の場合はプロンプトに含めない"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text='{"content":"発話","tts_text":"発話","emotion":"neutral"}'
        )

        section = {
            "section_type": "explanation",
            "display_text": "テスト",
            "dialogue_directions": [
                {"speaker": "teacher", "direction": "説明する", "key_content": ""},
            ],
        }

        with patch("src.lesson_generator._get_model", return_value="m"):
            dialogues = _generate_section_dialogues(
                client=mock_client,
                teacher_config=TEACHER_CFG,
                student_config=STUDENT_CFG,
                section=section,
                extracted_text="",
                lesson_name="テスト",
                en=False,
            )

        user_prompt = dialogues[0]["generation"]["user_prompt"]
        assert "このターンで触れるべき内容" not in user_prompt

    def test_key_content_english_mode(self):
        """英語モードでkey_contentがプロンプトに含まれる"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text='{"content":"Hello","tts_text":"Hello","emotion":"excited"}'
        )

        section = {
            "section_type": "introduction",
            "display_text": "Test",
            "dialogue_directions": [
                {"speaker": "teacher", "direction": "Greet viewers", "key_content": "The real meaning of How are you?"},
            ],
        }

        with patch("src.lesson_generator._get_model", return_value="m"):
            dialogues = _generate_section_dialogues(
                client=mock_client,
                teacher_config=TEACHER_CFG,
                student_config=STUDENT_CFG,
                section=section,
                extracted_text="",
                lesson_name="Test lesson",
                en=True,
            )

        user_prompt = dialogues[0]["generation"]["user_prompt"]
        assert "The real meaning of How are you?" in user_prompt
        assert "Key content to mention" in user_prompt


# --- テキストクリーニング ---


class TestCleanExtractedText:
    """clean_extracted_text のテスト"""

    def test_empty_string(self):
        assert clean_extracted_text("") == ""

    def test_none_returns_none(self):
        assert clean_extracted_text(None) is None

    def test_normal_text_unchanged(self):
        text = "Hello, world!\nThis is a test."
        assert clean_extracted_text(text) == text

    def test_consecutive_hyphens(self):
        """連続ハイフン(3つ以上)が空行に置換される"""
        text = "Title\n---\nContent\n----------\nMore"
        result = clean_extracted_text(text)
        assert "---" not in result
        assert "----------" not in result
        assert "Title" in result
        assert "Content" in result
        assert "More" in result

    def test_consecutive_equals(self):
        """連続等号(3つ以上)が除去される"""
        text = "Title\n===\nContent\n======\nMore"
        result = clean_extracted_text(text)
        assert "===" not in result
        assert "Title" in result
        assert "Content" in result

    def test_consecutive_asterisks(self):
        """連続アスタリスク(3つ以上)が除去される"""
        text = "Before ***separator*** After"
        result = clean_extracted_text(text)
        assert "***" not in result
        assert "Before" in result
        assert "After" in result

    def test_consecutive_tildes(self):
        """連続チルダ(3つ以上)が除去される"""
        text = "Before ~~~ After"
        result = clean_extracted_text(text)
        assert "~~~" not in result

    def test_consecutive_underscores(self):
        """連続アンダースコア(3つ以上)が除去される"""
        text = "Before ___ After"
        result = clean_extracted_text(text)
        assert "___" not in result

    def test_decorative_symbols(self):
        """装飾記号の連続(3つ以上)が除去される"""
        text = "★☆★☆★ タイトル ★☆★☆★"
        result = clean_extracted_text(text)
        assert "★☆★" not in result
        assert "タイトル" in result

    def test_decorative_symbols_various(self):
        """各種装飾記号の連続が除去される"""
        text = "●○●テスト■□■□■□テスト◆◇◆◇◆"
        result = clean_extracted_text(text)
        assert "●○●" not in result
        assert "■□■□■□" not in result
        assert "◆◇◆◇◆" not in result
        assert "テスト" in result

    def test_two_symbols_kept(self):
        """2つ以下の装飾記号は保持される"""
        text = "★☆ タイトル"
        result = clean_extracted_text(text)
        assert "★☆" in result

    def test_html_entities(self):
        """HTMLエンティティが対応文字に置換される"""
        text = "A &amp; B &lt;tag&gt; C&nbsp;D &quot;E&quot; F&#39;s"
        result = clean_extracted_text(text)
        assert "A & B" in result
        assert "<tag>" in result
        assert "C D" in result
        assert '"E"' in result
        assert "F's" in result

    def test_excessive_blank_lines(self):
        """3行以上の空行が2行に圧縮される"""
        text = "Line1\n\n\n\n\nLine2\n\n\n\n\n\nLine3"
        result = clean_extracted_text(text)
        # 最大で空行2つ（= 改行3つ）
        assert "\n\n\n\n" not in result
        assert "Line1" in result
        assert "Line2" in result
        assert "Line3" in result

    def test_two_blank_lines_kept(self):
        """空行2つはそのまま保持される"""
        text = "Line1\n\n\nLine2"
        result = clean_extracted_text(text)
        assert result == "Line1\n\n\nLine2"

    def test_leading_trailing_whitespace(self):
        """先頭・末尾の空白行がstripされる"""
        text = "\n\n  Hello  \n\n"
        result = clean_extracted_text(text)
        assert result == "Hello"

    def test_combined_noise(self):
        """複数のノイズが同時に除去される"""
        text = (
            "★☆★☆★\n"
            "タイトル\n"
            "===============\n"
            "本文テキスト\n"
            "---------------\n"
            "&nbsp;&nbsp;スペース付き\n"
            "\n\n\n\n\n"
            "最後の行"
        )
        result = clean_extracted_text(text)
        assert "★☆★" not in result
        assert "===" not in result
        assert "---" not in result
        assert "&nbsp;" not in result
        assert "タイトル" in result
        assert "本文テキスト" in result
        assert "スペース付き" in result
        assert "最後の行" in result


# --- メインコンテンツ識別 ---


class TestExtractMainContent:
    """extract_main_content のテスト"""

    def test_empty_text(self):
        """空テキストなら空リスト"""
        assert extract_main_content("") == []
        assert extract_main_content("   ") == []
        assert extract_main_content(None) == []

    def test_valid_json_response(self):
        """LLMが正しいJSON配列を返す場合、role が正規化される"""
        mock_response = MagicMock()
        mock_response.text = json.dumps([
            {"content_type": "conversation", "content": "A: Hi\nB: Hello", "label": "Greeting", "role": "main"},
            {"content_type": "passage", "content": "Text here.", "label": "Explanation", "role": "sub"},
        ])
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("src.lesson_generator.get_client", return_value=mock_client):
            result = extract_main_content("Some text")

        assert len(result) == 2
        assert result[0]["content_type"] == "conversation"
        assert result[0]["role"] == "main"
        assert result[1]["content_type"] == "passage"
        assert result[1]["role"] == "sub"

    def test_single_dict_response(self):
        """LLMがdict(配列でなく)を返した場合、1要素のリストにラップ+role=main"""
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {"content_type": "passage", "content": "Text", "label": "Label"}
        )
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("src.lesson_generator.get_client", return_value=mock_client):
            result = extract_main_content("Some text")

        assert len(result) == 1
        assert result[0]["content_type"] == "passage"
        assert result[0]["role"] == "main"

    def test_invalid_response_returns_empty(self):
        """LLMがパース不能な応答を返した場合、空リスト"""
        mock_response = MagicMock()
        mock_response.text = "This is not JSON at all and cannot be repaired"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("src.lesson_generator.get_client", return_value=mock_client), \
             patch("src.lesson_generator._parse_json_response", side_effect=Exception("parse error")):
            result = extract_main_content("Some text")

        assert result == []

    def test_prompt_contains_text(self):
        """プロンプトに入力テキストが含まれる"""
        mock_response = MagicMock()
        mock_response.text = "[]"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("src.lesson_generator.get_client", return_value=mock_client):
            extract_main_content("教材テキストの内容")

        call_args = mock_client.models.generate_content.call_args
        contents = call_args[1]["contents"] if "contents" in call_args[1] else call_args.kwargs.get("contents", call_args[0][0] if not call_args[0] else "")
        # positional or keyword
        if not contents:
            contents = call_args[1].get("contents", "")
        assert "教材テキストの内容" in str(contents)


class TestNormalizeRoles:
    """_normalize_roles のテスト"""

    def test_empty_list(self):
        assert _normalize_roles([]) == []

    def test_single_item_no_role(self):
        """1件でroleなし → main"""
        items = [{"content_type": "passage", "content": "x"}]
        result = _normalize_roles(items)
        assert result[0]["role"] == "main"

    def test_no_main_assigns_first(self):
        """mainが0件 → 最初をmainに"""
        items = [
            {"content_type": "conversation", "content": "A"},
            {"content_type": "word_list", "content": "B"},
        ]
        result = _normalize_roles(items)
        assert result[0]["role"] == "main"
        assert result[1]["role"] == "sub"

    def test_multiple_main_keeps_first(self):
        """mainが複数 → 最初だけ残す"""
        items = [
            {"content_type": "conversation", "content": "A", "role": "main"},
            {"content_type": "passage", "content": "B", "role": "main"},
            {"content_type": "word_list", "content": "C", "role": "sub"},
        ]
        result = _normalize_roles(items)
        assert result[0]["role"] == "main"
        assert result[1]["role"] == "sub"
        assert result[2]["role"] == "sub"

    def test_correct_roles_preserved(self):
        """正常なケース（main1つ+sub）はそのまま"""
        items = [
            {"content_type": "conversation", "content": "A", "role": "main"},
            {"content_type": "word_list", "content": "B", "role": "sub"},
        ]
        result = _normalize_roles(items)
        assert result[0]["role"] == "main"
        assert result[1]["role"] == "sub"

    def test_fills_missing_role_on_sub(self):
        """mainは明示、残りにroleなし → subを補完"""
        items = [
            {"content_type": "passage", "content": "A"},
            {"content_type": "conversation", "content": "B", "role": "main"},
        ]
        result = _normalize_roles(items)
        assert result[0]["role"] == "sub"
        assert result[1]["role"] == "main"


# --- 監督レビュー + main_content ---


class TestDirectorReviewMainContent:
    """_director_review の main_content 対応テスト"""

    def _make_review_response(self, approved=True):
        return json.dumps({
            "reviews": [{"section_index": 0, "approved": approved, "feedback": "OK"}],
            "overall_feedback": "Good",
        })

    def test_english_with_main_content(self):
        """英語版: main_contentありでコンテンツ種別レビュー観点・ロール基準が含まれる"""
        mc = [{"content_type": "conversation", "content": "A: Hi", "label": "Dialog", "role": "main"}]
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text=self._make_review_response()
        )

        result = _director_review(
            mock_client,
            [{"section_type": "example", "display_text": "A: Hi", "dialogues": []}],
            "text", "Test", en=True, main_content=mc,
        )

        # システムプロンプトにコンテンツ種別レビュー観点が含まれる
        call_args = mock_client.models.generate_content.call_args
        config = call_args[1]["config"] if "config" in call_args[1] else call_args.kwargs["config"]
        assert "Content type review" in config.system_instruction
        assert "conversation" in config.system_instruction
        assert "PRIMARY" in config.system_instruction
        # ユーザープロンプトにメインコンテンツ情報が含まれる
        contents = call_args[1].get("contents", call_args.kwargs.get("contents", ""))
        assert "[conversation]" in str(contents)
        assert "PRIMARY" in str(contents)
        assert result["reviews"][0]["approved"] is True

    def test_japanese_with_main_content(self):
        """日本語版: main_contentありでコンテンツ種別レビュー観点・ロール基準が含まれる"""
        mc = [{"content_type": "passage", "content": "説明文です。", "label": "説明", "role": "main"}]
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text=self._make_review_response()
        )

        _director_review(
            mock_client,
            [{"section_type": "explanation", "display_text": "説明", "dialogues": []}],
            "テキスト", "テスト授業", en=False, main_content=mc,
        )

        call_args = mock_client.models.generate_content.call_args
        config = call_args[1]["config"] if "config" in call_args[1] else call_args.kwargs["config"]
        assert "コンテンツ種別レビュー" in config.system_instruction
        assert "★ 主要" in config.system_instruction
        contents = call_args[1].get("contents", call_args.kwargs.get("contents", ""))
        assert "[passage]" in str(contents)
        assert "★ 主要" in str(contents)

    def test_no_main_content_no_extra_criteria(self):
        """main_contentなしではコンテンツ種別レビューが追加されない"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text=self._make_review_response()
        )

        _director_review(
            mock_client,
            [{"section_type": "introduction", "display_text": "Hi", "dialogues": []}],
            "text", "Test", en=True,
        )

        call_args = mock_client.models.generate_content.call_args
        config = call_args[1]["config"] if "config" in call_args[1] else call_args.kwargs["config"]
        assert "Content type review" not in config.system_instruction


class TestGenerateLessonScriptV2ReturnFormat:
    """generate_lesson_script_v2 が dict（sections + analysis）を返すことを確認"""

    def _run_v2_pipeline(self, mock_analysis=None):
        """v2パイプラインを実行するヘルパー。mock_analysisでanalyze_content_fullの戻り値を差し替え可能"""
        import json as _json
        from src.lesson_generator import generate_lesson_script_v2
        from src.content_analyzer import AnalysisResult, ScoreDetail

        # Phase B-1: 構造生成レスポンス
        structure_resp = _json.dumps([
            {"section_type": "introduction", "display_text": "導入",
             "emotion": "excited", "question": "", "answer": "", "wait_seconds": 0,
             "dialogue_plan": [{"speaker": "teacher", "direction": "挨拶"}]},
        ])
        # Phase B-2: セリフ生成
        dlg_resp = _json.dumps({"content": "こんにちは", "tts_text": "こんにちは", "emotion": "excited"})
        # Phase B-3: レビュー（全合格）
        review_resp = _json.dumps({
            "reviews": [{"section_index": 0, "approved": True, "feedback": "OK"}],
            "overall_feedback": "良い",
        })

        mock_client = MagicMock()
        responses = [structure_resp, dlg_resp, review_resp]
        call_idx = [0]
        def _side_effect(*args, **kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            text = responses[idx] if idx < len(responses) else dlg_resp
            return MagicMock(text=text)
        mock_client.models.generate_content.side_effect = _side_effect

        if mock_analysis is None:
            mock_analysis = AnalysisResult(
                lesson_id=0, lang="ja",
                algorithmic_scores={"test": ScoreDetail(score=10.0, max_score=10.0, details="ok")},
                llm_scores={"entertainment": ScoreDetail(score=12.0, max_score=15.0, details="good")},
                total_score=22.0, max_score=25.0, rank="C",
                suggestions=[], analyzed_at="2026-01-01T00:00:00+00:00",
            )

        async def _fake_analyze_full(*args, **kwargs):
            return mock_analysis

        with patch("src.lesson_generator.get_client", return_value=mock_client), \
             patch("src.lesson_generator._get_model", return_value="test-model"), \
             patch("src.lesson_generator._get_dialogue_model", return_value="test-model"), \
             patch("src.lesson_generator.analyze_content_full", side_effect=_fake_analyze_full) as mock_acf:
            result = generate_lesson_script_v2(
                "テスト授業", "テスト教材",
                teacher_config=TEACHER_CFG,
                student_config=STUDENT_CFG,
            )

        return result, mock_acf

    def test_returns_dict_with_sections_and_analysis(self):
        """v2パイプラインの戻り値がsectionsとanalysisを含むdictである"""
        result, _ = self._run_v2_pipeline()

        # 戻り値がdict形式であること
        assert isinstance(result, dict)
        assert "sections" in result
        assert "analysis" in result
        # sectionsはlist[dict]
        assert isinstance(result["sections"], list)
        assert len(result["sections"]) == 1
        assert result["sections"][0]["section_type"] == "introduction"
        # analysisはto_dict()の結果（dict）
        assert isinstance(result["analysis"], dict)
        assert "total_score" in result["analysis"]
        assert "rank" in result["analysis"]

    def test_analyze_content_full_called_with_correct_args(self):
        """Phase B-5でanalyze_content_fullが正しい引数で呼ばれる"""
        result, mock_acf = self._run_v2_pipeline()

        mock_acf.assert_called_once()
        call_args = mock_acf.call_args
        # 第1引数はsectionsリスト
        assert isinstance(call_args[0][0], list)
        # キーワード引数
        assert call_args[1]["lesson_name"] == "テスト授業"
        assert call_args[1]["extracted_text"] == "テスト教材"
        assert call_args[1]["lang"] == "ja"

    def test_analysis_includes_llm_scores(self):
        """分析結果にllm_scoresが含まれる"""
        result, _ = self._run_v2_pipeline()

        analysis = result["analysis"]
        assert analysis["llm_scores"] is not None
        assert "entertainment" in analysis["llm_scores"]


# --- _build_adjacent_sections テスト ---

SAMPLE_SECTIONS = [
    {"title": "挨拶", "display_text": "今日のテーマ: 挨拶", "section_type": "introduction"},
    {"title": "基本表現", "display_text": "基本的な英語の挨拶表現を学びます", "section_type": "explanation"},
    {"title": "まとめ", "display_text": "今日学んだことの復習", "section_type": "summary"},
]


class TestBuildAdjacentSections:
    """_build_adjacent_sections のテスト"""

    def test_first_section_no_prev(self):
        """先頭セクションは prev なし、next あり"""
        result = _build_adjacent_sections(SAMPLE_SECTIONS, 0)
        assert result["section_index"] == 0
        assert result["total_sections"] == 3
        assert result["prev"] is None
        assert result["next"] is not None
        assert result["next"]["title"] == "基本表現"
        assert result["next"]["section_type"] == "explanation"

    def test_middle_section_has_both(self):
        """中間セクションは prev/next 両方あり"""
        result = _build_adjacent_sections(SAMPLE_SECTIONS, 1)
        assert result["section_index"] == 1
        assert result["prev"] is not None
        assert result["prev"]["title"] == "挨拶"
        assert result["next"] is not None
        assert result["next"]["title"] == "まとめ"

    def test_last_section_no_next(self):
        """末尾セクションは next なし、prev あり"""
        result = _build_adjacent_sections(SAMPLE_SECTIONS, 2)
        assert result["section_index"] == 2
        assert result["next"] is None
        assert result["prev"] is not None
        assert result["prev"]["title"] == "基本表現"

    def test_single_section(self):
        """セクションが1つだけの場合、prev/next 両方なし"""
        result = _build_adjacent_sections([SAMPLE_SECTIONS[0]], 0)
        assert result["total_sections"] == 1
        assert result["prev"] is None
        assert result["next"] is None


class TestAdjacentSectionsInPrompt:
    """adjacent_sections がプロンプトに反映されるかのテスト"""

    def _make_mock_client(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "content": "テスト", "tts_text": "テスト", "emotion": "neutral",
        })
        mock_client.models.generate_content.return_value = mock_response
        return mock_client

    def _call_with_adjacent(self, en, adjacent_sections):
        mock_client = self._make_mock_client()
        with patch("src.lesson_generator._get_dialogue_model", return_value="test-model"):
            result = _generate_single_dialogue(
                client=mock_client,
                character_config=TEACHER_CFG,
                role="teacher",
                section_context={"section_type": "explanation", "display_text": "テスト"},
                dialogue_plan_entry={"speaker": "teacher", "direction": "説明する"},
                conversation_history=[],
                extracted_text="",
                lesson_name="テスト授業",
                en=en,
                adjacent_sections=adjacent_sections,
            )
        return result

    def test_adjacent_sections_in_prompt_ja(self):
        """JA版プロンプトに前後セクション情報が含まれる"""
        adjacent = _build_adjacent_sections(SAMPLE_SECTIONS, 1)
        result = self._call_with_adjacent(en=False, adjacent_sections=adjacent)
        prompt = result["generation"]["user_prompt"]
        assert "セクション位置: 2 / 3" in prompt
        assert "前のセクション [introduction]: 挨拶" in prompt
        assert "次のセクション [summary]: まとめ" in prompt

    def test_adjacent_sections_in_prompt_en(self):
        """EN版プロンプトに前後セクション情報が含まれる"""
        adjacent = _build_adjacent_sections(SAMPLE_SECTIONS, 1)
        result = self._call_with_adjacent(en=True, adjacent_sections=adjacent)
        prompt = result["generation"]["user_prompt"]
        assert "Section position: 2 / 3" in prompt
        assert "Previous section [introduction]: 挨拶" in prompt
        assert "Next section [summary]: まとめ" in prompt

    def test_adjacent_sections_none_no_change(self):
        """adjacent_sections が None の場合、位置情報が含まれない"""
        result = self._call_with_adjacent(en=False, adjacent_sections=None)
        prompt = result["generation"]["user_prompt"]
        assert "セクション位置" not in prompt
        assert "前のセクション" not in prompt
        assert "次のセクション" not in prompt

    def test_adjacent_sections_first_no_prev(self):
        """先頭セクションでは prev 情報が含まれない"""
        adjacent = _build_adjacent_sections(SAMPLE_SECTIONS, 0)
        result = self._call_with_adjacent(en=False, adjacent_sections=adjacent)
        prompt = result["generation"]["user_prompt"]
        assert "セクション位置: 1 / 3" in prompt
        assert "前のセクション" not in prompt
        assert "次のセクション [explanation]: 基本表現" in prompt

    def test_adjacent_sections_last_no_next(self):
        """末尾セクションでは next 情報が含まれない"""
        adjacent = _build_adjacent_sections(SAMPLE_SECTIONS, 2)
        result = self._call_with_adjacent(en=False, adjacent_sections=adjacent)
        prompt = result["generation"]["user_prompt"]
        assert "セクション位置: 3 / 3" in prompt
        assert "前のセクション [explanation]: 基本表現" in prompt
        assert "次のセクション" not in prompt
