"""コンテンツ品質分析エンジンのテスト"""

import json

from src.content_analyzer import (
    AnalysisResult,
    ScoreDetail,
    _calc_dialogue_balance,
    _calc_display_text_coverage,
    _calc_pacing,
    _calc_question_richness,
    _calc_section_diversity,
    _calc_rank,
    _extract_ngrams,
    analyze_content,
)


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _section(
    section_type="explanation",
    title="",
    content="",
    tts_text="",
    display_text="",
    emotion="neutral",
    question="",
    answer="",
    wait_seconds=8,
    dialogues="",
    order_index=0,
):
    return {
        "section_type": section_type,
        "title": title,
        "content": content,
        "tts_text": tts_text,
        "display_text": display_text,
        "emotion": emotion,
        "question": question,
        "answer": answer,
        "wait_seconds": wait_seconds,
        "dialogues": dialogues,
        "order_index": order_index,
    }


def _dialogues_json(turns):
    """[{speaker, content}, ...] → JSON文字列"""
    return json.dumps(turns, ensure_ascii=False)


# ---------------------------------------------------------------------------
# ランク判定
# ---------------------------------------------------------------------------

class TestRank:
    def test_rank_s(self):
        assert _calc_rank(85) == "S"
        assert _calc_rank(100) == "S"

    def test_rank_a(self):
        assert _calc_rank(70) == "A"
        assert _calc_rank(84) == "A"

    def test_rank_b(self):
        assert _calc_rank(55) == "B"
        assert _calc_rank(69) == "B"

    def test_rank_c(self):
        assert _calc_rank(40) == "C"
        assert _calc_rank(54) == "C"

    def test_rank_d(self):
        assert _calc_rank(0) == "D"
        assert _calc_rank(39) == "D"


# ---------------------------------------------------------------------------
# A1: display_textカバー率
# ---------------------------------------------------------------------------

class TestDisplayTextCoverage:
    def test_empty_sections(self):
        result = _calc_display_text_coverage([])
        assert result.score == 0
        assert result.max_score == 20.0

    def test_no_display_text(self):
        sections = [_section(content="何かの説明", display_text="")]
        result = _calc_display_text_coverage(sections)
        assert result.max_score == 20.0
        # display_textが空ならカバー率計算不能→半分のスコア
        assert result.score == 10.0

    def test_full_coverage(self):
        # display_textの内容がcontent/tts_textに含まれている
        sections = [_section(
            display_text="猫は可愛い動物です",
            tts_text="猫は可愛い動物ですよね。みんな大好きです。",
        )]
        result = _calc_display_text_coverage(sections)
        assert result.score > 15.0  # 高いカバー率

    def test_low_coverage(self):
        sections = [_section(
            display_text="量子コンピュータの原理",
            tts_text="今日は天気がいいですね。散歩しましょう。",
        )]
        result = _calc_display_text_coverage(sections)
        assert result.score < 10.0  # 低いカバー率

    def test_dialogue_coverage(self):
        dlg = _dialogues_json([
            {"speaker": "teacher", "content": "プログラミングの基礎を学びましょう"},
            {"speaker": "student", "content": "プログラミングって何ですか？"},
        ])
        sections = [_section(
            display_text="プログラミングの基礎",
            dialogues=dlg,
        )]
        result = _calc_display_text_coverage(sections)
        assert result.score > 10.0

    def test_ngram_extraction(self):
        grams = _extract_ngrams("ABC", 2)
        assert grams == {"AB", "BC"}

    def test_ngram_short(self):
        grams = _extract_ngrams("A", 2)
        assert grams == {"A"}

    def test_ngram_empty(self):
        grams = _extract_ngrams("", 2)
        assert grams == set()


# ---------------------------------------------------------------------------
# A2: 対話バランス
# ---------------------------------------------------------------------------

class TestDialogueBalance:
    def test_empty_sections(self):
        result = _calc_dialogue_balance([])
        assert result.score == 0

    def test_teacher_only(self):
        sections = [_section(content="先生のセリフ" * 10)]
        result = _calc_dialogue_balance(sections)
        # 先生のみ → 40%スコア
        assert result.score == 4.0
        assert "生徒キャラクター" in result.suggestions[0]

    def test_balanced_dialogue(self):
        dlg = _dialogues_json([
            {"speaker": "teacher", "content": "これは重要なポイントです。" * 5},
            {"speaker": "student", "content": "なるほど、わかりました！" * 3},
            {"speaker": "teacher", "content": "次に進みましょう。" * 3},
            {"speaker": "student", "content": "はい、お願いします！" * 2},
        ])
        sections = [_section(dialogues=dlg)]
        result = _calc_dialogue_balance(sections)
        assert result.score >= 7.0  # バランスが良い

    def test_teacher_heavy(self):
        dlg = _dialogues_json([
            {"speaker": "teacher", "content": "長い説明" * 50},
            {"speaker": "student", "content": "はい"},
        ])
        sections = [_section(dialogues=dlg)]
        result = _calc_dialogue_balance(sections)
        assert result.score < 7.0  # 先生偏り

    def test_complex_dialogues_format(self):
        """v4 format: {dialogues: [...], review: {...}}"""
        dlg = json.dumps({
            "dialogues": [
                {"speaker": "teacher", "content": "説明します。" * 5},
                {"speaker": "student", "content": "質問があります。" * 3},
            ],
            "review": {"approved": True},
        }, ensure_ascii=False)
        sections = [_section(dialogues=dlg)]
        result = _calc_dialogue_balance(sections)
        assert result.score > 0


# ---------------------------------------------------------------------------
# A3: セクション構成多様性
# ---------------------------------------------------------------------------

class TestSectionDiversity:
    def test_empty_sections(self):
        result = _calc_section_diversity([])
        assert result.score == 0

    def test_all_types(self):
        sections = [
            _section(section_type="introduction"),
            _section(section_type="explanation"),
            _section(section_type="example"),
            _section(section_type="question"),
            _section(section_type="summary"),
        ]
        result = _calc_section_diversity(sections)
        assert result.score == 10.0  # 全タイプ使用＋intro/summary bonus

    def test_one_type(self):
        sections = [
            _section(section_type="explanation"),
            _section(section_type="explanation"),
        ]
        result = _calc_section_diversity(sections)
        assert result.score == 2.0  # 1/5種
        assert len(result.suggestions) > 0

    def test_missing_intro_summary(self):
        sections = [
            _section(section_type="explanation"),
            _section(section_type="example"),
            _section(section_type="question"),
        ]
        result = _calc_section_diversity(sections)
        # introとsummaryがないのでsuggestion
        assert any("introduction" in s for s in result.suggestions)
        assert any("summary" in s for s in result.suggestions)


# ---------------------------------------------------------------------------
# A4: 質問・クイズ充実度
# ---------------------------------------------------------------------------

class TestQuestionRichness:
    def test_no_questions(self):
        sections = [_section(section_type="explanation")]
        result = _calc_question_richness(sections)
        assert result.score == 0

    def test_good_question_ratio(self):
        sections = [
            _section(section_type="introduction"),
            _section(section_type="explanation"),
            _section(section_type="explanation"),
            _section(section_type="question", question="Q?", answer="A."),
            _section(section_type="summary"),
        ]
        result = _calc_question_richness(sections)
        # 20%質問（理想範囲）+ Q&A記入済み
        assert result.score >= 4.0

    def test_question_without_qa_fields(self):
        sections = [
            _section(section_type="explanation"),
            _section(section_type="question"),  # question/answer未記入
        ]
        result = _calc_question_richness(sections)
        assert result.score > 0  # 質問あるだけでもスコアは出る
        assert any("未記入" in s for s in result.suggestions)


# ---------------------------------------------------------------------------
# A5: ペーシング
# ---------------------------------------------------------------------------

class TestPacing:
    def test_empty_sections(self):
        result = _calc_pacing([])
        assert result.score == 0

    def test_uniform_pacing(self):
        sections = [
            _section(content="あ" * 100, wait_seconds=8),
            _section(content="い" * 100, wait_seconds=8),
            _section(content="う" * 100, wait_seconds=8),
        ]
        result = _calc_pacing(sections)
        assert result.score >= 4.0  # 均一なペーシング

    def test_extreme_variation(self):
        sections = [
            _section(content="短", wait_seconds=8),
            _section(content="長い" * 500, wait_seconds=8),
        ]
        result = _calc_pacing(sections)
        assert result.score < 4.0  # 大きなばらつき

    def test_bad_wait_seconds(self):
        sections = [
            _section(content="あ" * 50, wait_seconds=1),   # 短すぎ
            _section(content="い" * 50, wait_seconds=30),  # 長すぎ
        ]
        result = _calc_pacing(sections)
        assert any("範囲外" in s for s in result.suggestions)


# ---------------------------------------------------------------------------
# 統合テスト: analyze_content
# ---------------------------------------------------------------------------

class TestAnalyzeContent:
    def test_basic_analysis(self):
        sections = [
            _section(section_type="introduction", content="導入です" * 20,
                     display_text="プログラミング入門", tts_text="プログラミング入門について話します" * 5,
                     wait_seconds=5),
            _section(section_type="explanation", content="説明です" * 30,
                     display_text="変数とは", tts_text="変数とはデータを入れる箱です" * 5,
                     wait_seconds=8),
            _section(section_type="question", content="質問です" * 15,
                     display_text="クイズ", question="変数とは？", answer="データの箱",
                     wait_seconds=10),
            _section(section_type="summary", content="まとめです" * 15,
                     display_text="まとめ", tts_text="今日のまとめです" * 5,
                     wait_seconds=6),
        ]
        result = analyze_content(sections, lang="ja")

        assert isinstance(result, AnalysisResult)
        assert result.llm_scores is None
        assert result.max_score == 50.0
        assert result.total_score > 0
        assert result.rank in ("S", "A", "B", "C", "D")
        assert len(result.algorithmic_scores) == 5

    def test_to_dict(self):
        sections = [_section(content="テスト")]
        result = analyze_content(sections)
        d = result.to_dict()
        assert "algorithmic_scores" in d
        assert "total_score" in d
        assert "rank" in d


# ---------------------------------------------------------------------------
# APIテスト
# ---------------------------------------------------------------------------

class TestAnalyzeAPI:
    def test_analyze_no_lesson(self, api_client):
        resp = api_client.post("/api/lessons/9999/analyze")
        data = resp.json()
        assert data["ok"] is False

    def test_analyze_no_sections(self, api_client, test_db):
        r = api_client.post("/api/lessons", json={"name": "Empty"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.post(f"/api/lessons/{lid}/analyze")
        data = resp.json()
        assert data["ok"] is False
        assert "セクション" in data["error"]

    def test_analyze_algo_only(self, api_client, test_db):
        r = api_client.post("/api/lessons", json={"name": "Test"})
        lid = r.json()["lesson"]["id"]
        # セクションを直接DBに追加
        test_db.add_lesson_section(lid, 0, "introduction", "導入テキスト" * 10,
                                   tts_text="導入テキスト" * 10, display_text="テスト導入",
                                   emotion="joy", wait_seconds=5, lang="ja")
        test_db.add_lesson_section(lid, 1, "explanation", "説明テキスト" * 20,
                                   tts_text="説明テキスト" * 20, display_text="テスト説明",
                                   emotion="neutral", wait_seconds=8, lang="ja")

        resp = api_client.post(f"/api/lessons/{lid}/analyze")
        data = resp.json()
        assert data["ok"] is True
        analysis = data["analysis"]
        assert analysis["lesson_id"] == lid
        assert analysis["max_score"] == 50.0
        assert analysis["llm_scores"] is None
        assert "display_text_coverage" in analysis["algorithmic_scores"]
        assert analysis["rank"] in ("S", "A", "B", "C", "D")
