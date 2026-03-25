"""lesson_generator の対話形式スクリプト生成テスト"""

import json

import pytest

from src.lesson_generator import (
    _build_dialogue_output_example,
    _build_dialogue_prompt,
    _build_section_from_dialogues,
    _format_character_for_prompt,
)


# --- テスト用キャラクター設定 ---

TEACHER_CFG = {
    "name": "ちょビ",
    "system_prompt": "明るく楽しい口調で教える先生",
    "emotions": {"joy": "嬉しい", "excited": "ワクワク", "neutral": "通常"},
}

STUDENT_CFG = {
    "name": "まなび",
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
        assert "student: まなび" in text
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
        assert "まなび" in prompt

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
