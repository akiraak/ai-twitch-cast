"""v2パイプライン: セクション構造生成 → セリフ個別生成 → 監督レビュー → 再生成"""

import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from google.genai import types

from src.content_analyzer import analyze_content_full

from . import utils
from .structure import _build_structure_prompt
from .dialogue import _generate_section_dialogues, _build_section_from_dialogues
from .director import _director_review

logger = logging.getLogger(__name__)


def _build_adjacent_sections(structure_sections: list[dict], idx: int) -> dict:
    """隣接セクションのコンテキストを構築（セクション間の自然なつながり用）"""
    adjacent = {
        "section_index": idx,
        "total_sections": len(structure_sections),
        "prev": None,
        "next": None,
    }
    if idx > 0:
        prev_s = structure_sections[idx - 1]
        adjacent["prev"] = {
            "title": prev_s.get("title", ""),
            "display_text": prev_s.get("display_text", ""),
            "section_type": prev_s.get("section_type", ""),
        }
    if idx < len(structure_sections) - 1:
        next_s = structure_sections[idx + 1]
        adjacent["next"] = {
            "title": next_s.get("title", ""),
            "display_text": next_s.get("display_text", ""),
            "section_type": next_s.get("section_type", ""),
        }
    return adjacent


def generate_lesson_script_v2(
    lesson_name: str,
    extracted_text: str,
    plan_sections: list[dict] | None = None,
    director_sections: list[dict] | None = None,
    source_images: list[str] = None,
    on_progress=None,
    teacher_config: dict = None,
    student_config: dict = None,
    main_content: list[dict] | None = None,
) -> list[dict]:
    """セリフをキャラごとに個別LLM呼び出しで生成する（v2）

    Phase 1: セクション構造 + dialogue_plan 生成（1回のLLM呼び出し）
       → director_sections がある場合はスキップ（v3パス）
    Phase 2: 各セリフをキャラのペルソナで個別生成（セクション間並列）
    """
    def _progress(step, total, msg):
        if on_progress:
            on_progress(step, total, msg)

    en = utils._is_english_mode()
    client = utils.get_client()

    if director_sections:
        # --- v3パス: 監督の設計をそのまま使う（Phase B-1スキップ） ---
        structure_sections = director_sections
        if en:
            _progress(1, None, "Using director's section design (Phase B-1 skipped)")
        else:
            _progress(1, None, "監督のセクション設計を使用（Phase B-1スキップ）")
        logger.info("v3パス: director_sections使用、Phase B-1スキップ（%dセクション）", len(director_sections))
    else:
        # --- v2フォールバック: Phase 1 セクション構造生成 ---
        if en:
            _progress(1, None, "Generating section structure...")
        else:
            _progress(1, None, "セクション構造を生成中...")

        plan_text = None
        if plan_sections:
            if en:
                plan_text = "\n".join(
                    f"{i+1}. [{s.get('section_type', 'explanation')}] {s.get('title', '')} — {s.get('summary', '')} (emotion: {s.get('emotion', 'neutral')}, pause: {s.get('wait_seconds', 2)}s)"
                    + (" *has question" if s.get("has_question") else "")
                    for i, s in enumerate(plan_sections)
                )
            else:
                plan_text = "\n".join(
                    f"{i+1}. [{s.get('section_type', 'explanation')}] {s.get('title', '')} — {s.get('summary', '')} (感情: {s.get('emotion', 'neutral')}, 間: {s.get('wait_seconds', 2)}秒)"
                    + (" ※問いかけあり" if s.get("has_question") else "")
                    for i, s in enumerate(plan_sections)
                )

        structure_prompt = _build_structure_prompt(en, plan_text, main_content=main_content)

        parts = utils._build_image_parts(source_images)
        if en:
            user_text = f"# Lesson title: {lesson_name}\n\n# Source text:\n{extracted_text}"
        else:
            user_text = f"# 授業タイトル: {lesson_name}\n\n# 教材テキスト:\n{extracted_text}"
        parts.append(types.Part(text=user_text))

        max_retries = 3
        last_error = None
        structure_sections = None
        for attempt in range(max_retries):
            if attempt > 0:
                if en:
                    _progress(1, None, f"Retrying structure generation ({attempt + 1}/{max_retries})...")
                else:
                    _progress(1, None, f"セクション構造を再生成中（リトライ {attempt + 1}/{max_retries}）...")
            response = client.models.generate_content(
                model=utils._get_director_model(),
                contents=[types.Content(parts=parts)],
                config=types.GenerateContentConfig(
                    system_instruction=structure_prompt,
                    response_mime_type="application/json",
                    temperature=1.0,
                    max_output_tokens=8192,
                ),
            )
            try:
                structure_sections = utils._parse_json_response(response.text)
                if not isinstance(structure_sections, list):
                    raise ValueError("セクション構造が配列ではありません")
                break
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                logger.warning("セクション構造のJSONパース失敗 (attempt=%d): %s", attempt + 1, e)
                continue
        else:
            raise ValueError(f"セクション構造の生成に{max_retries}回失敗: {last_error}")

    # dialogue_directions（v3）またはdialogue_plan（v2）のターン数を集計
    total_turns = sum(
        len(s.get("dialogue_directions") or s.get("dialogue_plan", []))
        for s in structure_sections
    )
    logger.info("Phase 1完了: %dセクション, %dターン", len(structure_sections), total_turns)

    if en:
        _progress(1, 1 + total_turns, f"Structure done: {len(structure_sections)} sections, {total_turns} turns")
    else:
        _progress(1, 1 + total_turns, f"構造完了: {len(structure_sections)}セクション, {total_turns}ターン")

    # --- Phase 2: セリフ個別生成（セクション間並列） ---
    step_lock = threading.Lock()
    current_step = [1]

    def section_worker(sec_idx, section):
        dialogue_plan = section.get("dialogue_directions") or section.get("dialogue_plan", [])
        if not dialogue_plan:
            return sec_idx, []

        def dlg_progress(speaker, turn_num, turn_total):
            with step_lock:
                current_step[0] += 1
                step = current_step[0]
            t_name = teacher_config.get("name", "先生") if speaker == "teacher" else student_config.get("name", "生徒")
            if en:
                msg = f"Section {sec_idx + 1}: {t_name} ({turn_num}/{turn_total})"
            else:
                msg = f"セクション{sec_idx + 1}: {t_name} ({turn_num}/{turn_total})"
            _progress(step, 1 + total_turns, msg)

        adjacent = _build_adjacent_sections(structure_sections, sec_idx)
        dialogues = _generate_section_dialogues(
            client=client,
            teacher_config=teacher_config,
            student_config=student_config,
            section=section,
            extracted_text=extracted_text,
            lesson_name=lesson_name,
            en=en,
            on_progress=dlg_progress,
            adjacent_sections=adjacent,
        )
        return sec_idx, dialogues

    section_dialogues = [None] * len(structure_sections)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(section_worker, i, s)
            for i, s in enumerate(structure_sections)
        ]
        for future in futures:
            sec_idx, dialogues = future.result()
            section_dialogues[sec_idx] = dialogues

    # --- Phase B-3: 監督レビュー ---
    if en:
        _progress(1 + total_turns, 1 + total_turns + 1 + 1, "Director reviewing dialogue...")
    else:
        _progress(1 + total_turns, 1 + total_turns + 1 + 1, "監督がセリフをレビュー中...")

    sections_for_review = []
    for i, s in enumerate(structure_sections):
        sections_for_review.append({
            **s,
            "dialogues": section_dialogues[i] or [],
        })

    review_result = _director_review(
        client, sections_for_review, extracted_text, lesson_name, en,
        main_content=main_content,
    )

    # --- Phase B-4: 再生成（不合格セクションのみ、1回のみ） ---
    rejected = [r for r in review_result["reviews"] if not r.get("approved")]
    review_map = {r["section_index"]: r for r in review_result["reviews"]}
    original_dialogues_map = {}
    regen_turns = 0

    if rejected:
        regen_turns = sum(len(r.get("revised_directions", [])) for r in rejected)
        if en:
            _progress(1 + total_turns, 1 + total_turns + 1 + regen_turns + 1,
                      f"Director feedback: {len(rejected)} section(s) need revision")
        else:
            _progress(1 + total_turns, 1 + total_turns + 1 + regen_turns + 1,
                      f"監督のフィードバック: {len(rejected)}セクションが不合格")

        regen_step = [0]
        regen_step_lock = threading.Lock()

        def regen_worker(r):
            idx = r["section_index"]
            revised = r.get("revised_directions", [])
            if not revised or idx >= len(structure_sections):
                return idx, section_dialogues[idx]

            # 元のセリフを保存
            original_dialogues_map[idx] = section_dialogues[idx] or []

            # dialogue_directions を差し替えて再生成
            section_copy = {**structure_sections[idx], "dialogue_directions": revised}

            def regen_progress(speaker, turn_num, turn_total):
                with regen_step_lock:
                    regen_step[0] += 1
                    step = regen_step[0]
                t_name = teacher_config.get("name", "先生") if speaker == "teacher" else student_config.get("name", "生徒")
                if en:
                    msg = f"Revising section {idx + 1}: {t_name} ({turn_num}/{turn_total})"
                else:
                    msg = f"セクション{idx + 1}を再生成中: {t_name} ({turn_num}/{turn_total})"
                _progress(1 + total_turns + 1 + step, 1 + total_turns + 1 + regen_turns + 1, msg)

            adjacent = _build_adjacent_sections(structure_sections, idx)
            new_dialogues = _generate_section_dialogues(
                client=client,
                teacher_config=teacher_config,
                student_config=student_config,
                section=section_copy,
                extracted_text=extracted_text,
                lesson_name=lesson_name,
                en=en,
                on_progress=regen_progress,
                adjacent_sections=adjacent,
            )
            return idx, new_dialogues

        with ThreadPoolExecutor(max_workers=3) as executor:
            regen_futures = [executor.submit(regen_worker, r) for r in rejected]
            for future in regen_futures:
                idx, new_dialogues = future.result()
                # 再生成フラグを立てる
                if idx in review_map:
                    review_map[idx]["is_regenerated"] = True
                section_dialogues[idx] = new_dialogues

        logger.info("Phase B-4完了: %dセクションを再生成", len(rejected))

    # --- 結果の組み立て ---
    valid_types = {"introduction", "explanation", "example", "question", "summary"}
    result = []
    for i, s in enumerate(structure_sections):
        # v3: director_sectionsにはtitleが含まれる。v2: plan_sectionsから取得
        if director_sections:
            plan_title = s.get("title", "")
        else:
            plan_title = plan_sections[i].get("title", "") if plan_sections and i < len(plan_sections) else ""
        dialogues = section_dialogues[i] or []

        # レビュー結果をdialoguesデータに埋め込む
        review_info = review_map.get(i)
        review_data = None
        if review_info:
            review_data = {
                "approved": review_info.get("approved", True),
                "feedback": review_info.get("feedback", ""),
                "is_regenerated": review_info.get("is_regenerated", False),
                "revised_directions": review_info.get("revised_directions", []),
            }
        # 再生成前の元セリフ（不合格→再生成されたセクションのみ存在）
        original_dlgs = original_dialogues_map.get(i)

        section = {
            "section_type": s.get("section_type", "explanation"),
            "title": plan_title,
            "content": "",
            "tts_text": "",
            "display_text": s.get("display_text", ""),
            "emotion": s.get("emotion", "neutral"),
            "question": s.get("question", ""),
            "answer": s.get("answer", ""),
            "wait_seconds": int(s.get("wait_seconds", 0)),
        }

        if dialogues:
            # dialoguesにreview情報を含めたJSONを構築
            dialogues_with_meta = {
                "dialogues": dialogues,
            }
            if original_dlgs is not None:
                dialogues_with_meta["original_dialogues"] = original_dlgs
            if review_data:
                dialogues_with_meta["review"] = review_data
            # 監督レビューのgeneration情報も保存
            if review_result.get("generation"):
                dialogues_with_meta["review_generation"] = review_result["generation"]
                dialogues_with_meta["review_overall_feedback"] = review_result.get("overall_feedback", "")

            section["dialogues"] = dialogues
            section = _build_section_from_dialogues(section)
            section["dialogues"] = json.dumps(dialogues_with_meta, ensure_ascii=False)
        else:
            section["dialogues"] = ""

        if section["section_type"] not in valid_types:
            section["section_type"] = "explanation"
        result.append(section)

    # --- Phase B-5: 品質分析（アルゴリズム + LLM評価） ---
    analysis_total = 1 + total_turns + 1 + regen_turns + 1
    if en:
        _progress(analysis_total, analysis_total, "Analyzing quality (with LLM)...")
    else:
        _progress(analysis_total, analysis_total, "品質分析中（LLM評価含む）...")

    analysis = asyncio.run(analyze_content_full(
        result, lesson_name=lesson_name,
        extracted_text=extracted_text,
        lang="en" if en else "ja",
    ))
    logger.info("Phase B-5完了: score=%.1f/%s, rank=%s",
                analysis.total_score, analysis.max_score, analysis.rank)

    return {"sections": result, "analysis": analysis.to_dict()}
