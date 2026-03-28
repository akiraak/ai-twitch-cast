"""コンテンツ品質分析エンジン — アルゴリズム指標 + LLM評価"""

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from google.genai import types

from src.gemini_client import get_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------

@dataclass
class ScoreDetail:
    score: float
    max_score: float
    details: str
    suggestions: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    lesson_id: int
    lang: str
    algorithmic_scores: dict[str, ScoreDetail]
    llm_scores: dict[str, ScoreDetail] | None
    total_score: float
    max_score: float
    rank: str
    suggestions: list[str]
    analyzed_at: str

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# ランク判定
# ---------------------------------------------------------------------------

def _calc_rank(score: float) -> str:
    if score >= 85:
        return "S"
    if score >= 70:
        return "A"
    if score >= 55:
        return "B"
    if score >= 40:
        return "C"
    return "D"


# ---------------------------------------------------------------------------
# メイン分析関数
# ---------------------------------------------------------------------------

def analyze_content(sections: list[dict], lang: str = "ja") -> AnalysisResult:
    """コンテンツをアルゴリズム指標で分析し、スコアを返す。

    sections: lesson_sectionsテーブルの行リスト（dict）
    """
    algo_scores = {
        "display_text_coverage": _calc_display_text_coverage(sections),
        "dialogue_balance": _calc_dialogue_balance(sections),
        "section_diversity": _calc_section_diversity(sections),
        "question_richness": _calc_question_richness(sections),
        "pacing": _calc_pacing(sections),
    }

    total = sum(s.score for s in algo_scores.values())
    max_total = sum(s.max_score for s in algo_scores.values())

    all_suggestions = []
    for sd in algo_scores.values():
        all_suggestions.extend(sd.suggestions)

    return AnalysisResult(
        lesson_id=0,
        lang=lang,
        algorithmic_scores=algo_scores,
        llm_scores=None,
        total_score=round(total, 1),
        max_score=round(max_total, 1),
        rank=_calc_rank(total),
        suggestions=all_suggestions,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )


async def analyze_content_full(
    sections: list[dict],
    lesson_name: str,
    extracted_text: str,
    lang: str = "ja",
) -> AnalysisResult:
    """アルゴリズム指標 + LLM評価のフル分析"""
    result = analyze_content(sections, lang)

    llm_scores = await _evaluate_with_llm(sections, extracted_text, lesson_name, lang)
    result.llm_scores = llm_scores

    llm_total = sum(s.score for s in llm_scores.values())
    llm_max = sum(s.max_score for s in llm_scores.values())

    result.total_score = round(result.total_score + llm_total, 1)
    result.max_score = round(result.max_score + llm_max, 1)
    result.rank = _calc_rank(result.total_score)

    for sd in llm_scores.values():
        result.suggestions.extend(sd.suggestions)

    return result


# ---------------------------------------------------------------------------
# A1: display_textカバー率（20点満点）
# ---------------------------------------------------------------------------

def _extract_ngrams(text: str, n: int) -> set[str]:
    """テキストからn-gramのセットを生成"""
    text = re.sub(r'\s+', '', text)
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def _calc_display_text_coverage(sections: list[dict]) -> ScoreDetail:
    """display_textの内容がtts_text（またはdialogues）に含まれているか"""
    MAX_SCORE = 20.0

    if not sections:
        return ScoreDetail(0, MAX_SCORE, "セクションなし", ["コンテンツを生成してください"])

    total_ngrams = 0
    covered_ngrams = 0
    uncovered_sections = []

    for sec in sections:
        display_text = sec.get("display_text", "").strip()
        if not display_text:
            continue

        # tts_textとdialogues両方からカバー対象テキストを構築
        cover_text = sec.get("tts_text", "") or sec.get("content", "")
        dialogues_raw = sec.get("dialogues", "")
        if dialogues_raw:
            try:
                ddata = json.loads(dialogues_raw)
                if isinstance(ddata, list):
                    dlg_list = ddata
                elif isinstance(ddata, dict):
                    dlg_list = ddata.get("dialogues", [])
                else:
                    dlg_list = []
                for dlg in dlg_list:
                    if isinstance(dlg, dict):
                        cover_text += " " + dlg.get("content", "")
                        cover_text += " " + dlg.get("tts_text", "")
            except (json.JSONDecodeError, TypeError):
                pass

        # n-gramマッチ（2-gramで日本語対応）
        display_grams = _extract_ngrams(display_text, 2)
        cover_grams = _extract_ngrams(cover_text, 2)

        if display_grams:
            matched = display_grams & cover_grams
            total_ngrams += len(display_grams)
            covered_ngrams += len(matched)
            coverage = len(matched) / len(display_grams)
            if coverage < 0.5:
                uncovered_sections.append(sec.get("title", f"セクション{sec.get('order_index', '?')}"))

    if total_ngrams == 0:
        return ScoreDetail(MAX_SCORE * 0.5, MAX_SCORE, "display_textが空",
                           ["教材テキストをdisplay_textに設定してください"])

    ratio = covered_ngrams / total_ngrams
    score = round(MAX_SCORE * ratio, 1)

    details = f"カバー率 {ratio:.0%}（{covered_ngrams}/{total_ngrams} 2-gram）"
    suggestions = []
    if uncovered_sections:
        suggestions.append(
            f"以下のセクションでdisplay_textが読み上げに反映されていません: {', '.join(uncovered_sections)}"
        )
    if ratio < 0.7:
        suggestions.append("display_textの内容をセリフに盛り込んでください")

    return ScoreDetail(score, MAX_SCORE, details, suggestions)


# ---------------------------------------------------------------------------
# A2: 対話バランス（10点満点）
# ---------------------------------------------------------------------------

def _calc_dialogue_balance(sections: list[dict]) -> ScoreDetail:
    """teacher/studentの発話回数・文字数のバランス"""
    MAX_SCORE = 10.0

    teacher_chars = 0
    student_chars = 0
    teacher_turns = 0
    student_turns = 0

    for sec in sections:
        dialogues_raw = sec.get("dialogues", "")
        if not dialogues_raw:
            # dialoguesがない場合はteacher発話扱い
            content = sec.get("content", "") or sec.get("tts_text", "")
            teacher_chars += len(content)
            teacher_turns += 1 if content else 0
            continue
        try:
            ddata = json.loads(dialogues_raw)
            if isinstance(ddata, list):
                dlg_list = ddata
            elif isinstance(ddata, dict):
                dlg_list = ddata.get("dialogues", [])
            else:
                dlg_list = []
            for dlg in dlg_list:
                if not isinstance(dlg, dict):
                    continue
                speaker = dlg.get("speaker", "teacher")
                content = dlg.get("content", "")
                if speaker == "student":
                    student_chars += len(content)
                    student_turns += 1
                else:
                    teacher_chars += len(content)
                    teacher_turns += 1
        except (json.JSONDecodeError, TypeError):
            content = sec.get("content", "")
            teacher_chars += len(content)
            teacher_turns += 1 if content else 0

    total_chars = teacher_chars + student_chars
    total_turns = teacher_turns + student_turns

    if total_turns == 0:
        return ScoreDetail(0, MAX_SCORE, "発話なし", ["コンテンツを生成してください"])

    # 対話モードでない（studentなし）場合
    if student_turns == 0:
        return ScoreDetail(MAX_SCORE * 0.4, MAX_SCORE,
                           f"先生のみ（{teacher_turns}発話, {teacher_chars}文字）",
                           ["生徒キャラクターを追加して対話形式にすると評価が上がります"])

    # 理想的な比率: teacher 60-70%, student 30-40%
    teacher_ratio = teacher_chars / total_chars if total_chars > 0 else 1.0
    student_ratio = 1.0 - teacher_ratio

    # バランス評価: teacher 50-80%が許容範囲、60-70%が最適
    if 0.55 <= teacher_ratio <= 0.75:
        balance_score = 1.0  # 最適
    elif 0.45 <= teacher_ratio <= 0.85:
        balance_score = 0.7  # 許容
    else:
        balance_score = 0.3  # 偏りすぎ

    score = round(MAX_SCORE * balance_score, 1)
    details = (f"先生 {teacher_ratio:.0%}({teacher_turns}発話) / "
               f"生徒 {student_ratio:.0%}({student_turns}発話)")
    suggestions = []
    if teacher_ratio > 0.85:
        suggestions.append("先生の発話が多すぎます。生徒の質問や反応を増やしてください")
    elif teacher_ratio < 0.45:
        suggestions.append("生徒の発話が多すぎます。先生の説明を増やしてください")

    return ScoreDetail(score, MAX_SCORE, details, suggestions)


# ---------------------------------------------------------------------------
# A3: セクション構成多様性（10点満点）
# ---------------------------------------------------------------------------

_EXPECTED_TYPES = {"introduction", "explanation", "example", "question", "summary"}


def _calc_section_diversity(sections: list[dict]) -> ScoreDetail:
    """section_typeの種類数とバランス"""
    MAX_SCORE = 10.0

    if not sections:
        return ScoreDetail(0, MAX_SCORE, "セクションなし", ["コンテンツを生成してください"])

    type_counts: dict[str, int] = {}
    for sec in sections:
        st = sec.get("section_type", "explanation")
        type_counts[st] = type_counts.get(st, 0) + 1

    used_types = set(type_counts.keys())
    expected_used = used_types & _EXPECTED_TYPES

    # 種類数スコア: 5種類中いくつ使っているか
    variety_ratio = len(expected_used) / len(_EXPECTED_TYPES)
    # intro/summaryの存在ボーナス
    has_intro = "introduction" in used_types
    has_summary = "summary" in used_types
    structure_bonus = 0.0
    if has_intro:
        structure_bonus += 0.1
    if has_summary:
        structure_bonus += 0.1

    raw_score = min(1.0, variety_ratio + structure_bonus)
    score = round(MAX_SCORE * raw_score, 1)

    details = f"使用タイプ: {', '.join(sorted(used_types))}（{len(expected_used)}/{len(_EXPECTED_TYPES)}種）"
    suggestions = []
    missing = _EXPECTED_TYPES - used_types
    if missing:
        suggestions.append(f"不足しているセクションタイプ: {', '.join(sorted(missing))}")
    if not has_intro:
        suggestions.append("導入（introduction）セクションを追加してください")
    if not has_summary:
        suggestions.append("まとめ（summary）セクションを追加してください")

    return ScoreDetail(score, MAX_SCORE, details, suggestions)


# ---------------------------------------------------------------------------
# A4: 質問・クイズ充実度（5点満点）
# ---------------------------------------------------------------------------

def _calc_question_richness(sections: list[dict]) -> ScoreDetail:
    """question型セクションの有無と割合"""
    MAX_SCORE = 5.0

    if not sections:
        return ScoreDetail(0, MAX_SCORE, "セクションなし", ["コンテンツを生成してください"])

    total = len(sections)
    question_sections = [s for s in sections if s.get("section_type") == "question"]
    q_count = len(question_sections)

    # 質問がないと0点
    if q_count == 0:
        return ScoreDetail(0, MAX_SCORE, "質問セクションなし",
                           ["クイズや質問を追加して視聴者参加を促してください"])

    # 理想: 全体の10-30%が質問
    q_ratio = q_count / total
    if 0.1 <= q_ratio <= 0.35:
        ratio_score = 1.0
    elif q_ratio < 0.1:
        ratio_score = 0.5
    else:
        ratio_score = 0.6  # 多すぎても少し減点

    # question/answerフィールドが埋まっているか
    filled = sum(1 for s in question_sections
                 if s.get("question", "").strip() and s.get("answer", "").strip())
    fill_ratio = filled / q_count if q_count > 0 else 0

    combined = ratio_score * 0.6 + fill_ratio * 0.4
    score = round(MAX_SCORE * combined, 1)

    details = f"質問セクション {q_count}/{total}（{q_ratio:.0%}）、Q&A記入率 {fill_ratio:.0%}"
    suggestions = []
    if q_ratio < 0.1:
        suggestions.append("質問セクションが少なすぎます。もっとクイズを追加してください")
    if fill_ratio < 1.0:
        suggestions.append("question/answerフィールドが未記入の質問セクションがあります")

    return ScoreDetail(score, MAX_SCORE, details, suggestions)


# ---------------------------------------------------------------------------
# A5: ペーシング適正度（5点満点）
# ---------------------------------------------------------------------------

def _calc_pacing(sections: list[dict]) -> ScoreDetail:
    """セクション長のばらつきとwait_secondsの適正範囲"""
    MAX_SCORE = 5.0

    if not sections:
        return ScoreDetail(0, MAX_SCORE, "セクションなし", ["コンテンツを生成してください"])

    # セクション長（content文字数）の分布
    lengths = []
    waits = []
    for sec in sections:
        content = sec.get("content", "") or sec.get("tts_text", "")
        # dialoguesがある場合はdialoguesの合計文字数
        dialogues_raw = sec.get("dialogues", "")
        if dialogues_raw:
            try:
                ddata = json.loads(dialogues_raw)
                dlg_list = ddata if isinstance(ddata, list) else ddata.get("dialogues", [])
                content = "".join(d.get("content", "") for d in dlg_list if isinstance(d, dict))
            except (json.JSONDecodeError, TypeError):
                pass
        lengths.append(len(content))
        waits.append(sec.get("wait_seconds", 8))

    # 長さのばらつき（変動係数）
    if lengths:
        avg_len = sum(lengths) / len(lengths)
        if avg_len > 0:
            variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
            cv = (variance ** 0.5) / avg_len
        else:
            cv = 0
    else:
        cv = 0

    # CV < 0.5が理想、1.0以上は問題
    if cv < 0.5:
        length_score = 1.0
    elif cv < 0.8:
        length_score = 0.7
    elif cv < 1.2:
        length_score = 0.4
    else:
        length_score = 0.2

    # wait_secondsの適正範囲（3-15秒）
    out_of_range = sum(1 for w in waits if w < 3 or w > 15)
    wait_score = 1.0 - (out_of_range / len(waits)) if waits else 0.5

    combined = length_score * 0.6 + wait_score * 0.4
    score = round(MAX_SCORE * combined, 1)

    details = (f"セクション長: 平均{avg_len:.0f}文字, CV={cv:.2f} / "
               f"wait: {min(waits)}-{max(waits)}秒")
    suggestions = []
    if cv > 0.8:
        short = [f"#{i}" for i, l in enumerate(lengths) if l < avg_len * 0.3]
        long = [f"#{i}" for i, l in enumerate(lengths) if l > avg_len * 2.0]
        if short:
            suggestions.append(f"極端に短いセクション: {', '.join(short)}")
        if long:
            suggestions.append(f"極端に長いセクション: {', '.join(long)}")
    if out_of_range > 0:
        suggestions.append(f"wait_secondsが範囲外（3-15秒）のセクションが{out_of_range}個あります")

    return ScoreDetail(score, MAX_SCORE, details, suggestions)


# ---------------------------------------------------------------------------
# B1-B4: LLM評価（1回の呼び出しで4指標）
# ---------------------------------------------------------------------------

def _get_director_model():
    return os.environ.get(
        "GEMINI_DIRECTOR_MODEL",
        os.environ.get("GEMINI_CHAT_MODEL", "gemini-3.1-pro-preview"),
    )


async def _evaluate_with_llm(
    sections: list[dict],
    extracted_text: str,
    lesson_name: str,
    lang: str,
) -> dict[str, ScoreDetail]:
    """B1-B4: LLMによるエンタメ性・教育効果・キャラ活用・構成力の評価"""

    # セクション情報を整形
    section_summary = []
    for i, sec in enumerate(sections):
        entry = {
            "index": i,
            "section_type": sec.get("section_type", ""),
            "title": sec.get("title", ""),
            "display_text": sec.get("display_text", "")[:200],
            "emotion": sec.get("emotion", "neutral"),
        }
        # セリフ概要
        dialogues_raw = sec.get("dialogues", "")
        if dialogues_raw:
            try:
                ddata = json.loads(dialogues_raw)
                dlg_list = ddata if isinstance(ddata, list) else ddata.get("dialogues", [])
                turns = []
                for d in dlg_list:
                    if isinstance(d, dict):
                        turns.append(f"{d.get('speaker','?')}: {d.get('content','')[:80]}")
                entry["dialogue_preview"] = turns[:6]
            except (json.JSONDecodeError, TypeError):
                entry["content_preview"] = (sec.get("content", "") or "")[:150]
        else:
            entry["content_preview"] = (sec.get("content", "") or "")[:150]
        section_summary.append(entry)

    en = lang == "en"

    system_prompt = """あなたは配信コンテンツの品質評価者です。以下の4つの観点で授業コンテンツを評価してください。

## 評価基準

### entertainment（エンタメ性, 15点満点）
- 視聴者を引きつける展開があるか
- 意外性・ユーモア・フックがあるか
- 飽きさせない工夫があるか

### education（教育効果, 15点満点）
- 学習目標が明確か
- 段階的に理解が深まる構成か
- 教材の内容を正確に伝えているか

### character（キャラクター活用, 10点満点）
- キャラクターの個性が活きているか
- 掛け合いが自然で楽しいか
- 感情表現が適切か

### structure（全体構成力, 10点満点）
- 導入→展開→転→まとめの流れがあるか
- セクション間のつながりが自然か
- 全体のテンポが良いか

## 出力形式（JSON）

```json
{
  "entertainment": {"score": 0-15, "reasoning": "根拠", "suggestions": ["改善提案"]},
  "education": {"score": 0-15, "reasoning": "根拠", "suggestions": ["改善提案"]},
  "character": {"score": 0-10, "reasoning": "根拠", "suggestions": ["改善提案"]},
  "structure": {"score": 0-10, "reasoning": "根拠", "suggestions": ["改善提案"]}
}
```

各suggestionsは具体的に、何をどう変えれば改善するかを書いてください。"""

    if en:
        system_prompt = """You are a broadcast content quality evaluator. Evaluate the lesson content on these 4 criteria:

## Criteria

### entertainment (15 points max)
- Does it have engaging developments to attract viewers?
- Are there surprises, humor, or hooks?
- Are there techniques to prevent boredom?

### education (15 points max)
- Are learning objectives clear?
- Does understanding deepen progressively?
- Is the source material accurately conveyed?

### character (10 points max)
- Do characters show distinct personalities?
- Is the banter natural and enjoyable?
- Are emotions expressed appropriately?

### structure (10 points max)
- Is there a clear intro→development→twist→summary flow?
- Are transitions between sections natural?
- Is the overall pacing good?

## Output format (JSON)

```json
{
  "entertainment": {"score": 0-15, "reasoning": "basis", "suggestions": ["improvement"]},
  "education": {"score": 0-15, "reasoning": "basis", "suggestions": ["improvement"]},
  "character": {"score": 0-10, "reasoning": "basis", "suggestions": ["improvement"]},
  "structure": {"score": 0-10, "reasoning": "basis", "suggestions": ["improvement"]}
}
```

Each suggestion should be specific about what to change and how."""

    user_prompt = f"""## 授業名: {lesson_name}

## 教材テキスト（抜粋）:
{extracted_text[:2000]}

## セクション構成:
{json.dumps(section_summary, ensure_ascii=False, indent=2)}
"""

    try:
        client = get_client()
        response = client.models.generate_content(
            model=_get_director_model(),
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.5,
                max_output_tokens=4096,
            ),
        )

        result = json.loads(response.text)
        scores = {}
        for key, max_score, ja_name in [
            ("entertainment", 15.0, "エンタメ性"),
            ("education", 15.0, "教育効果"),
            ("character", 10.0, "キャラクター活用"),
            ("structure", 10.0, "全体構成力"),
        ]:
            item = result.get(key, {})
            raw_score = min(max_score, max(0, float(item.get("score", 0))))
            scores[key] = ScoreDetail(
                score=round(raw_score, 1),
                max_score=max_score,
                details=item.get("reasoning", ""),
                suggestions=item.get("suggestions", []),
            )
        return scores

    except Exception as e:
        logger.error("LLM評価エラー: %s", e)
        # エラー時はすべて0点で返す
        return {
            key: ScoreDetail(0, max_s, f"LLM評価エラー: {e}", [])
            for key, max_s in [
                ("entertainment", 15.0),
                ("education", 15.0),
                ("character", 10.0),
                ("structure", 10.0),
            ]
        }
