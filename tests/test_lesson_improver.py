"""lesson_generator/improver.py のテスト

範囲:
- 純粋ロジック系: _format_sections_for_prompt / determine_targets / apply_prompt_diff / _format_annotated_for_prompt
- ファイルI/O系: _load_prompt / load_learnings / save_learnings_to_files
- LLM呼び出し系: verify_lesson / evaluate_lesson_quality / evaluate_category_fit / improve_sections / analyze_learnings / improve_prompt / create_category_prompt
- DB系: _collect_annotated_sections
"""

import json
from unittest.mock import MagicMock

import pytest

from src.lesson_generator import improver


# =====================================================
# 純粋ロジック: _format_sections_for_prompt
# =====================================================


class TestFormatSectionsForPrompt:
    def test_basic_section(self):
        sections = [{
            "order_index": 0,
            "section_type": "explanation",
            "title": "導入",
            "content": "今日はPythonを学びます",
            "emotion": "happy",
        }]
        out = improver._format_sections_for_prompt(sections)
        assert "### セクション 0: 導入 (explanation, emotion=happy)" in out
        assert "今日はPythonを学びます" in out

    def test_dialogues_from_json_string(self):
        sections = [{
            "order_index": 1,
            "title": "会話",
            "content": "対話あり",
            "dialogues": json.dumps([
                {"speaker": "teacher", "content": "こんにちは"},
                {"speaker": "student", "content": "はい"},
            ]),
        }]
        out = improver._format_sections_for_prompt(sections)
        assert "対話:" in out
        assert "teacher: こんにちは" in out
        assert "student: はい" in out

    def test_dialogues_invalid_json_ignored(self):
        sections = [{
            "order_index": 0,
            "title": "壊れた対話",
            "content": "x",
            "dialogues": "{broken json",
        }]
        out = improver._format_sections_for_prompt(sections)
        # 壊れたJSONは空リスト扱いで落ちない
        assert "壊れた対話" in out
        assert "対話:" not in out

    def test_annotation_rating_rendered(self):
        sections = [{
            "order_index": 2,
            "title": "評価あり",
            "content": "x",
            "annotation_rating": "good",
            "annotation_comment": "分かりやすい",
        }]
        out = improver._format_sections_for_prompt(sections)
        assert "◎良い" in out
        assert "分かりやすい" in out

    def test_empty_list(self):
        assert improver._format_sections_for_prompt([]) == ""


# =====================================================
# 純粋ロジック: determine_targets
# =====================================================


class TestDetermineTargets:
    def test_all_none(self):
        targets, instructions = improver.determine_targets(None, None, None, [])
        assert targets == []
        assert instructions == ""

    def test_verify_weak_coverage_adds_target(self):
        verify = {
            "coverage": [{"section_index": 1, "status": "weak", "detail": "薄い"}],
            "contradictions": [],
        }
        targets, instructions = improver.determine_targets(verify, None, None, [])
        assert targets == [1]
        assert "[教材整合性] セクション1" in instructions

    def test_verify_contradiction_adds_target(self):
        verify = {
            "coverage": [],
            "contradictions": [{"section_index": 3, "issue": "矛盾あり"}],
        }
        targets, _ = improver.determine_targets(verify, None, None, [])
        assert targets == [3]

    def test_missing_with_no_target_selects_all(self):
        # missing のみで他の target 候補が無ければ、全セクションを対象にする
        verify = {
            "coverage": [{"status": "missing", "source_item": "章末問題"}],
            "contradictions": [],
        }
        all_sections = [
            {"order_index": 0},
            {"order_index": 1},
            {"order_index": 2},
        ]
        targets, instructions = improver.determine_targets(verify, None, None, all_sections)
        assert targets == [0, 1, 2]
        assert "章末問題" in instructions

    def test_quality_major_added_minor_not(self):
        quality = {"quality_issues": [
            {"section_index": 1, "severity": "major", "issue": "要修正"},
            {"section_index": 2, "severity": "minor", "issue": "軽微"},
        ]}
        targets, instructions = improver.determine_targets(None, quality, None, [])
        assert targets == [1]
        # minorもinstructionsには入る
        assert "セクション2" in instructions
        assert "セクション1" in instructions

    def test_category_major_added(self):
        category = {"category_issues": [
            {"section_index": 5, "severity": "major", "issue": "カテゴリ不一致"},
        ]}
        targets, _ = improver.determine_targets(None, None, category, [])
        assert targets == [5]

    def test_targets_sorted_and_unique(self):
        verify = {"coverage": [{"section_index": 3, "status": "weak"}], "contradictions": []}
        quality = {"quality_issues": [{"section_index": 1, "severity": "major"}]}
        category = {"category_issues": [{"section_index": 3, "severity": "major"}]}  # 重複
        targets, _ = improver.determine_targets(verify, quality, category, [])
        assert targets == [1, 3]


# =====================================================
# 純粋ロジック: _format_annotated_for_prompt
# =====================================================


class TestFormatAnnotatedForPrompt:
    def test_empty_returns_empty_string(self):
        assert improver._format_annotated_for_prompt([], "◎良い") == ""

    def test_long_content_truncated(self):
        entries = [{
            "lesson_name": "L",
            "section": {"order_index": 0, "title": "t", "section_type": "explanation",
                        "content": "あ" * 500},
            "comment": "c",
        }]
        out = improver._format_annotated_for_prompt(entries, "◎良い")
        assert "..." in out
        assert "コメント: c" in out
        assert "（1件）" in out


# =====================================================
# 純粋ロジック: apply_prompt_diff (tmp_path + monkeypatch)
# =====================================================


class TestApplyPromptDiff:
    @pytest.fixture
    def prompts_dir(self, tmp_path, monkeypatch):
        d = tmp_path / "prompts"
        d.mkdir()
        monkeypatch.setattr(improver, "PROMPTS_DIR", d)
        return d

    def test_replace_success(self, prompts_dir):
        (prompts_dir / "p.md").write_text("Hello World", encoding="utf-8")
        result = improver.apply_prompt_diff("p.md", [
            {"action": "replace", "old_text": "World", "new_text": "Pytest"},
        ])
        assert result["applied"] == 1
        assert result["errors"] == []
        assert (prompts_dir / "p.md").read_text(encoding="utf-8") == "Hello Pytest"

    def test_replace_missing_old_text(self, prompts_dir):
        (prompts_dir / "p.md").write_text("Hello", encoding="utf-8")
        result = improver.apply_prompt_diff("p.md", [
            {"action": "replace", "old_text": "NotHere", "new_text": "X"},
        ])
        assert result["applied"] == 0
        assert any("old_text" in e for e in result["errors"])

    def test_add_appends_content(self, prompts_dir):
        (prompts_dir / "p.md").write_text("Head", encoding="utf-8")
        result = improver.apply_prompt_diff("p.md", [
            {"action": "add", "content": "Tail"},
        ])
        assert result["applied"] == 1
        text = (prompts_dir / "p.md").read_text(encoding="utf-8")
        assert text.startswith("Head")
        assert "Tail" in text

    def test_add_empty_content_error(self, prompts_dir):
        (prompts_dir / "p.md").write_text("x", encoding="utf-8")
        result = improver.apply_prompt_diff("p.md", [{"action": "add", "content": ""}])
        assert result["applied"] == 0
        assert result["errors"]

    def test_unknown_action_error(self, prompts_dir):
        (prompts_dir / "p.md").write_text("x", encoding="utf-8")
        result = improver.apply_prompt_diff("p.md", [{"action": "delete"}])
        assert result["applied"] == 0
        assert any("不明なaction" in e for e in result["errors"])

    def test_file_not_found_returns_error(self, prompts_dir):
        result = improver.apply_prompt_diff("missing.md", [])
        assert "error" in result


# =====================================================
# ファイルI/O: _load_prompt / load_learnings / save_learnings_to_files
# =====================================================


class TestPromptsAndLearningsIO:
    @pytest.fixture
    def dirs(self, tmp_path, monkeypatch):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        learnings = prompts / "learnings"
        learnings.mkdir()
        monkeypatch.setattr(improver, "PROMPTS_DIR", prompts)
        monkeypatch.setattr(improver, "LEARNINGS_DIR", learnings)
        return prompts, learnings

    def test_load_prompt_existing(self, dirs):
        prompts, _ = dirs
        (prompts / "a.md").write_text("content", encoding="utf-8")
        assert improver._load_prompt("a.md") == "content"

    def test_load_prompt_missing_raises(self, dirs):
        with pytest.raises(FileNotFoundError):
            improver._load_prompt("nope.md")

    def test_load_learnings_both(self, dirs):
        _, learnings = dirs
        (learnings / "_common.md").write_text("共通", encoding="utf-8")
        (learnings / "python.md").write_text("Py固有", encoding="utf-8")
        result = improver.load_learnings("python")
        assert "共通" in result
        assert "Py固有" in result

    def test_load_learnings_only_common(self, dirs):
        _, learnings = dirs
        (learnings / "_common.md").write_text("共通のみ", encoding="utf-8")
        assert improver.load_learnings("nonexistent") == "共通のみ"

    def test_load_learnings_none(self, dirs):
        assert improver.load_learnings("python") == ""

    def test_load_learnings_empty_category_arg(self, dirs):
        _, learnings = dirs
        (learnings / "_common.md").write_text("C", encoding="utf-8")
        # category="" なら category 個別ファイルは見にいかない
        assert improver.load_learnings("") == "C"

    def test_save_learnings_writes_both(self, dirs):
        _, learnings = dirs
        improver.save_learnings_to_files("python", "カテゴリ学習", "共通学習")
        assert (learnings / "python.md").read_text(encoding="utf-8") == "カテゴリ学習"
        assert (learnings / "_common.md").read_text(encoding="utf-8") == "共通学習"

    def test_save_learnings_skips_empty(self, dirs):
        _, learnings = dirs
        improver.save_learnings_to_files("python", "", "")
        assert not (learnings / "python.md").exists()
        assert not (learnings / "_common.md").exists()

    def test_save_learnings_skips_empty_category(self, dirs):
        _, learnings = dirs
        # category="" の場合、カテゴリファイルは書かれない（共通のみ）
        improver.save_learnings_to_files("", "カテゴリ内容", "共通内容")
        assert (learnings / "_common.md").read_text(encoding="utf-8") == "共通内容"


# =====================================================
# LLM呼び出し系: verify_lesson / evaluate_* / improve_sections / analyze / improve_prompt / create_category_prompt
# =====================================================


def _set_llm_response(mock_gemini, text: str):
    """mock_gemini の generate_content 応答テキストを差し替える"""
    mock_gemini.models.generate_content.return_value.text = text


@pytest.fixture
def prompts_dir_with_templates(tmp_path, monkeypatch):
    """最小限のプロンプトテンプレートを用意した PROMPTS_DIR"""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    learnings = prompts / "learnings"
    learnings.mkdir()
    # 必要なテンプレをダミーで用意
    for name in [
        "lesson_verify.md",
        "lesson_evaluate_quality.md",
        "lesson_evaluate_category.md",
        "lesson_improve.md",
        "lesson_analyze.md",
        "lesson_improve_prompt.md",
        "lesson_generate.md",
    ]:
        (prompts / name).write_text(f"# {name}\n{{generation_prompt}}{{category_name}}{{category_description}}{{category_prompt_content}}", encoding="utf-8")
    monkeypatch.setattr(improver, "PROMPTS_DIR", prompts)
    monkeypatch.setattr(improver, "LEARNINGS_DIR", learnings)
    return prompts, learnings


class TestVerifyLesson:
    async def test_normal_response(self, mock_gemini, prompts_dir_with_templates):
        _set_llm_response(mock_gemini, json.dumps({
            "coverage": [{"section_index": 0, "status": "ok"}],
            "contradictions": [],
        }))
        out = await improver.verify_lesson(
            extracted_text="教材本文",
            main_content=[{"content_type": "passage", "label": "L", "content": "c"}],
            sections=[{"order_index": 0, "title": "t", "content": "c"}],
        )
        assert "coverage" in out["result"]
        assert "system" in out["prompt"] and "user" in out["prompt"]
        assert "教材本文" in out["prompt"]["user"]

    async def test_non_dict_response_falls_back(self, mock_gemini, prompts_dir_with_templates):
        _set_llm_response(mock_gemini, json.dumps(["not", "a", "dict"]))
        out = await improver.verify_lesson("x", [], [])
        assert out["result"]["coverage"] == []
        assert out["result"]["contradictions"] == []

    async def test_missing_keys_filled(self, mock_gemini, prompts_dir_with_templates):
        _set_llm_response(mock_gemini, json.dumps({"coverage": [{"x": 1}]}))
        out = await improver.verify_lesson("x", [], [])
        assert out["result"]["coverage"] == [{"x": 1}]
        assert out["result"]["contradictions"] == []


class TestEvaluateLessonQuality:
    async def test_normal(self, mock_gemini, prompts_dir_with_templates):
        _set_llm_response(mock_gemini, json.dumps({
            "quality_issues": [{"section_index": 0, "severity": "minor"}],
            "overall_score": 80,
        }))
        out = await improver.evaluate_lesson_quality(
            sections=[{"order_index": 0, "title": "t", "content": "c"}],
            generation_prompt="品質基準",
        )
        assert out["result"]["overall_score"] == 80
        assert "品質基準" in out["prompt"]["system"]

    async def test_non_dict_fallback(self, mock_gemini, prompts_dir_with_templates):
        _set_llm_response(mock_gemini, "[1, 2, 3]")
        out = await improver.evaluate_lesson_quality([], "")
        assert out["result"]["quality_issues"] == []


class TestEvaluateCategoryFit:
    async def test_normal(self, mock_gemini, prompts_dir_with_templates):
        _set_llm_response(mock_gemini, json.dumps({
            "category_issues": [{"section_index": 1, "severity": "major"}],
        }))
        out = await improver.evaluate_category_fit(
            sections=[],
            category_prompt="カテゴリ専用",
            category_name="Python",
            category_description="プログラミング",
        )
        assert out["result"]["category_issues"][0]["severity"] == "major"
        assert "Python" in out["prompt"]["system"]
        assert "プログラミング" in out["prompt"]["system"]

    async def test_non_dict_fallback(self, mock_gemini, prompts_dir_with_templates):
        _set_llm_response(mock_gemini, "null")
        out = await improver.evaluate_category_fit([], "", "", "")
        assert out["result"]["category_issues"] == []


class TestImproveSections:
    async def test_list_response_returned(self, mock_gemini, prompts_dir_with_templates):
        sections_out = [
            {"order_index": 1, "content": "改善済み"},
        ]
        _set_llm_response(mock_gemini, json.dumps(sections_out))
        out = await improver.improve_sections(
            extracted_text="教材",
            main_content=[],
            all_sections=[{"order_index": 1, "title": "t", "content": "c"}],
            target_indices=[1],
            user_instructions="もっと丁寧に",
        )
        assert out["sections"][0]["content"] == "改善済み"
        assert "もっと丁寧に" in out["prompt"]["user"]

    async def test_dict_response_wrapped_in_list(self, mock_gemini, prompts_dir_with_templates):
        _set_llm_response(mock_gemini, json.dumps({"order_index": 0, "content": "x"}))
        out = await improver.improve_sections("", [], [], [])
        assert isinstance(out["sections"], list)
        assert len(out["sections"]) == 1


class TestAnalyzeLearnings:
    async def test_no_annotated_sections_short_circuits(self, mock_gemini, prompts_dir_with_templates, test_db, monkeypatch):
        # DB空 → section_count=0 → LLM呼ばずにerror返す
        out = await improver.analyze_learnings("python")
        assert out["section_count"] == 0
        assert "error" in out
        mock_gemini.models.generate_content.assert_not_called()

    async def test_with_data_calls_llm(self, mock_gemini, prompts_dir_with_templates, test_db):
        from src import db
        # 注釈付きセクションを1件作成
        lesson = db.create_lesson("L1", category="python")
        db.create_lesson_version(lesson["id"], version_number=1)
        sec = db.add_lesson_section(lesson["id"], 0, "explanation", "c", title="t", version_number=1)
        db.update_section_annotation(sec["id"], rating="good", comment="わかりやすい")

        _set_llm_response(mock_gemini, json.dumps({
            "category_learnings": "## カテゴリ学習",
            "common_learnings": "## 共通学習",
        }))
        out = await improver.analyze_learnings("python", "Python", "プログラミング")
        assert out["section_count"] == 1
        assert out["category_learnings"] == "## カテゴリ学習"
        assert out["common_learnings"] == "## 共通学習"


class TestImprovePrompt:
    async def test_missing_learnings_returns_error(self, mock_gemini, prompts_dir_with_templates):
        # 学習ファイルなし
        out = await improver.improve_prompt(category="python")
        assert "error" in out

    async def test_missing_prompt_file_returns_error(self, mock_gemini, prompts_dir_with_templates):
        out = await improver.improve_prompt(prompt_file="nonexistent.md")
        assert "error" in out

    async def test_success_with_prompt_content(self, mock_gemini, prompts_dir_with_templates):
        prompts, learnings = prompts_dir_with_templates
        (learnings / "_common.md").write_text("共通学習", encoding="utf-8")

        _set_llm_response(mock_gemini, json.dumps({
            "summary": "要約",
            "diff_instructions": [{"action": "replace", "old_text": "a", "new_text": "b"}],
            "learnings_to_graduate": ["卒業した学び"],
        }))
        out = await improver.improve_prompt(
            category="python",
            prompt_content="現在のカテゴリプロンプト本文",
        )
        assert out["summary"] == "要約"
        assert out["diff_instructions"][0]["action"] == "replace"
        assert "[DB]" in out["prompt_file"]

    async def test_non_dict_fallback(self, mock_gemini, prompts_dir_with_templates):
        _, learnings = prompts_dir_with_templates
        (learnings / "_common.md").write_text("x", encoding="utf-8")
        _set_llm_response(mock_gemini, "42")
        out = await improver.improve_prompt(prompt_content="p")
        assert out["summary"] == ""
        assert out["diff_instructions"] == []


class TestCreateCategoryPrompt:
    async def test_missing_base_returns_error(self, mock_gemini, prompts_dir_with_templates, tmp_path, monkeypatch):
        # 空のディレクトリに差し替え → base が無い
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr(improver, "PROMPTS_DIR", empty)
        out = await improver.create_category_prompt(
            base_prompt_file="lesson_generate.md",
            category_slug="py",
            category_name="Python",
            category_description="プログラミング言語",
        )
        assert "error" in out

    async def test_success_returns_content(self, mock_gemini, prompts_dir_with_templates):
        _set_llm_response(mock_gemini, "生成されたカテゴリ専用プロンプト")
        out = await improver.create_category_prompt(
            base_prompt_file="lesson_generate.md",
            category_slug="py",
            category_name="Python",
            category_description="プログラミング言語",
        )
        assert out["content"] == "生成されたカテゴリ専用プロンプト"


# =====================================================
# DB系: _collect_annotated_sections
# =====================================================


class TestCollectAnnotatedSections:
    def test_empty_db(self, test_db):
        out = improver._collect_annotated_sections("python")
        assert out["good"] == []
        assert out["needs_improvement"] == []
        assert out["redo"] == []
        assert out["improvement_pairs"] == []

    def test_category_filter(self, test_db):
        from src import db
        # python カテゴリに1件、他カテゴリに1件
        l_py = db.create_lesson("L-py", category="python")
        db.create_lesson_version(l_py["id"], version_number=1)
        s1 = db.add_lesson_section(l_py["id"], 0, "explanation", "c", title="t", version_number=1)
        db.update_section_annotation(s1["id"], rating="good", comment="")

        l_other = db.create_lesson("L-other", category="math")
        db.create_lesson_version(l_other["id"], version_number=1)
        s2 = db.add_lesson_section(l_other["id"], 0, "explanation", "c", title="t", version_number=1)
        db.update_section_annotation(s2["id"], rating="redo", comment="")

        out_py = improver._collect_annotated_sections("python")
        assert len(out_py["good"]) == 1
        assert out_py["redo"] == []

    def test_ratings_classified(self, test_db):
        from src import db
        lesson = db.create_lesson("L", category="python")
        db.create_lesson_version(lesson["id"], version_number=1)
        for idx, rating in enumerate(["good", "needs_improvement", "redo", ""]):
            sec = db.add_lesson_section(lesson["id"], idx, "explanation", "c", title=f"t{idx}", version_number=1)
            if rating:
                db.update_section_annotation(sec["id"], rating=rating, comment=f"C{idx}")

        out = improver._collect_annotated_sections("python")
        assert len(out["good"]) == 1
        assert len(out["needs_improvement"]) == 1
        assert len(out["redo"]) == 1

    def test_improvement_pair_built(self, test_db):
        from src import db
        lesson = db.create_lesson("L", category="python")
        # v1: before セクション（"redo"評価）
        db.create_lesson_version(lesson["id"], version_number=1)
        before = db.add_lesson_section(lesson["id"], 0, "explanation", "before", title="t",
                                       version_number=1)
        db.update_section_annotation(before["id"], rating="redo", comment="")
        # v2: after セクション（"good"評価）+ v1から改善されたバージョン
        db.create_lesson_version(
            lesson["id"], version_number=2,
            improve_source_version=1,
            improved_sections=json.dumps([0]),
        )
        after = db.add_lesson_section(lesson["id"], 0, "explanation", "after", title="t",
                                      version_number=2)
        db.update_section_annotation(after["id"], rating="good", comment="改善された")

        out = improver._collect_annotated_sections("python")
        assert len(out["improvement_pairs"]) == 1
        pair = out["improvement_pairs"][0]
        assert pair["before"]["content"] == "before"
        assert pair["after"]["content"] == "after"
