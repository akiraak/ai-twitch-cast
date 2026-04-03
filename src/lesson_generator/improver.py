"""授業スクリプト検証・改善・学習ループ — 元教材整合性チェック & 部分再生成 & パターン分析"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.genai import types

from .utils import get_client, _get_model, _parse_json_response, _format_main_content_for_prompt

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = PROJECT_DIR / "prompts"
LEARNINGS_DIR = PROMPTS_DIR / "learnings"


def _load_prompt(name: str) -> str:
    """プロンプトファイルを読み込む"""
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"プロンプトファイルが見つかりません: {path}")
    return path.read_text(encoding="utf-8")


def load_learnings(category: str) -> str:
    """カテゴリ別 + 共通の学習結果を読み込んで結合する。

    Returns:
        学習結果テキスト（空文字列 = 学習なし）
    """
    parts = []
    # 共通学習結果
    common_path = LEARNINGS_DIR / "_common.md"
    if common_path.exists():
        text = common_path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(text)
    # カテゴリ別学習結果
    if category:
        cat_path = LEARNINGS_DIR / f"{category}.md"
        if cat_path.exists():
            text = cat_path.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _format_sections_for_prompt(sections: list[dict]) -> str:
    """セクションリストをプロンプト用テキストに整形する"""
    lines = []
    for s in sections:
        idx = s.get("order_index", 0)
        stype = s.get("section_type", "explanation")
        title = s.get("title", "")
        content = s.get("content", "")
        emotion = s.get("emotion", "neutral")
        annotation_rating = s.get("annotation_rating", "")
        annotation_comment = s.get("annotation_comment", "")

        lines.append(f"### セクション {idx}: {title} ({stype}, emotion={emotion})")
        lines.append(content)

        # 対話があれば含める
        dialogues_raw = s.get("dialogues", "")
        if dialogues_raw:
            if isinstance(dialogues_raw, str):
                try:
                    dialogues = json.loads(dialogues_raw)
                except (json.JSONDecodeError, TypeError):
                    dialogues = []
            else:
                dialogues = dialogues_raw
            if dialogues:
                lines.append("\n対話:")
                for d in dialogues:
                    speaker = d.get("speaker", "teacher")
                    dcontent = d.get("content", "")
                    lines.append(f"  {speaker}: {dcontent}")

        # 注釈があれば含める
        if annotation_rating:
            rating_label = {"good": "◎良い", "needs_improvement": "△要改善", "redo": "✕作り直し"}.get(
                annotation_rating, annotation_rating)
            ann = f"\n[注釈: {rating_label}]"
            if annotation_comment:
                ann += f" {annotation_comment}"
            lines.append(ann)

        lines.append("")
    return "\n".join(lines)


async def verify_lesson(
    extracted_text: str,
    main_content: list[dict],
    sections: list[dict],
    en: bool = False,
) -> dict:
    """元教材との整合性チェックを実行する。

    Returns:
        {"coverage": [...], "contradictions": [...]}
    """
    system_prompt = _load_prompt("lesson_verify.md")

    # ユーザープロンプト構築
    user_parts = []
    user_parts.append("## 元教材テキスト\n")
    if extracted_text:
        user_parts.append(extracted_text[:5000])
    user_parts.append("\n\n## 構造化コンテンツ\n")
    if main_content:
        user_parts.append(_format_main_content_for_prompt(main_content, en))
    user_parts.append("\n\n## 授業セクション\n")
    user_parts.append(_format_sections_for_prompt(sections))

    user_prompt = "\n".join(user_parts)

    client = get_client()
    response = client.models.generate_content(
        model=_get_model(),
        contents=[
            types.Content(role="user", parts=[
                types.Part(text=f"{system_prompt}\n\n---\n\n{user_prompt}"),
            ]),
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=8192,
        ),
    )

    result = _parse_json_response(response.text)
    # 最低限の構造保証
    if not isinstance(result, dict):
        result = {"coverage": [], "contradictions": []}
    if "coverage" not in result:
        result["coverage"] = []
    if "contradictions" not in result:
        result["contradictions"] = []

    return {
        "result": result,
        "prompt": {
            "system": system_prompt,
            "user": user_prompt,
        },
        "raw_output": response.text,
    }


async def improve_sections(
    extracted_text: str,
    main_content: list[dict],
    all_sections: list[dict],
    target_indices: list[int],
    verify_result: dict | None = None,
    user_instructions: str = "",
    category: str = "",
    character_info: str = "",
    en: bool = False,
) -> dict:
    """指定セクションを改善して再生成する。

    Args:
        extracted_text: 元教材テキスト
        main_content: 構造化コンテンツ
        all_sections: 全セクション（コンテキスト用）
        target_indices: 改善対象のorder_indexリスト
        verify_result: 整合性チェック結果（任意）
        user_instructions: ユーザーの追加指示
        category: 授業のカテゴリslug（学習結果注入用）
        character_info: キャラクター情報テキスト
        en: 英語モードかどうか

    Returns:
        {"sections": [...], "prompt": {...}, "raw_output": str}
    """
    system_prompt = _load_prompt("lesson_improve.md")

    # 学習結果を注入
    learnings = load_learnings(category)

    # ユーザープロンプト構築
    user_parts = []

    # キャラクター情報
    if character_info:
        user_parts.append(f"## キャラクター情報\n\n{character_info}\n")

    # 元教材
    user_parts.append("## 元教材テキスト\n")
    if extracted_text:
        user_parts.append(extracted_text[:5000])
    user_parts.append("\n\n## 構造化コンテンツ\n")
    if main_content:
        user_parts.append(_format_main_content_for_prompt(main_content, en))

    # 全セクション（コンテキスト）
    user_parts.append("\n\n## 現在の授業セクション（全体）\n")
    user_parts.append(_format_sections_for_prompt(all_sections))

    # 改善対象
    user_parts.append(f"\n## 改善対象セクション\n")
    user_parts.append(f"order_index: {target_indices}\n")
    user_parts.append("上記のセクションのみ再生成してください。それ以外は出力不要です。\n")

    # 整合性チェック結果
    if verify_result:
        user_parts.append("\n## 整合性チェック結果\n")
        user_parts.append(f"```json\n{json.dumps(verify_result, ensure_ascii=False, indent=2)}\n```\n")

    # ユーザー追加指示
    if user_instructions:
        user_parts.append(f"\n## ユーザーの追加指示\n\n{user_instructions}\n")

    # 学習結果
    if learnings:
        user_parts.append(f"\n## 過去の学習結果\n\n{learnings}\n")

    user_prompt = "\n".join(user_parts)

    client = get_client()
    response = client.models.generate_content(
        model=_get_model(),
        contents=[
            types.Content(role="user", parts=[
                types.Part(text=f"{system_prompt}\n\n---\n\n{user_prompt}"),
            ]),
        ],
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=16384,
        ),
    )

    result = _parse_json_response(response.text)
    if not isinstance(result, list):
        result = [result] if isinstance(result, dict) else []

    return {
        "sections": result,
        "prompt": {
            "system": system_prompt,
            "user": user_prompt,
        },
        "raw_output": response.text,
    }


# --- 授業横断の学習ループ ---


def _collect_annotated_sections(category: str) -> dict:
    """カテゴリ別に注釈付きセクションを収集する。

    Returns:
        {
            "good": [{"lesson_name", "section", "comment"}...],
            "needs_improvement": [...],
            "redo": [...],
            "improvement_pairs": [{"before": section, "after": section}...],
        }
    """
    from src import db

    lessons = db.get_all_lessons()
    if category:
        lessons = [l for l in lessons if l.get("category") == category]

    good = []
    needs_improvement = []
    redo = []
    improvement_pairs = []

    for lesson in lessons:
        lid = lesson["id"]
        lesson_name = lesson["name"]

        # 全バージョンのセクションを取得
        versions = db.get_lesson_versions(lid)
        sections_by_version = {}
        for ver in versions:
            vn = ver["version_number"]
            lang = ver["lang"]
            gen = ver["generator"]
            secs = db.get_lesson_sections(lid, lang=lang, generator=gen, version_number=vn)
            sections_by_version[(lang, gen, vn)] = secs

            for s in secs:
                rating = s.get("annotation_rating", "")
                if not rating:
                    continue
                entry = {
                    "lesson_name": lesson_name,
                    "lesson_id": lid,
                    "version": vn,
                    "section": s,
                    "comment": s.get("annotation_comment", ""),
                }
                if rating == "good":
                    good.append(entry)
                elif rating == "needs_improvement":
                    needs_improvement.append(entry)
                elif rating == "redo":
                    redo.append(entry)

            # 改善ペア: improve_source_version があるバージョンからbefore/afterを構築
            if ver.get("improve_source_version") and ver.get("improved_sections"):
                src_vn = ver["improve_source_version"]
                try:
                    improved_indices = json.loads(ver["improved_sections"])
                except (json.JSONDecodeError, TypeError):
                    improved_indices = []

                src_key = (lang, gen, src_vn)
                if src_key in sections_by_version and improved_indices:
                    src_secs = {s["order_index"]: s for s in sections_by_version[src_key]}
                    cur_secs = {s["order_index"]: s for s in secs}
                    for idx in improved_indices:
                        if idx in src_secs and idx in cur_secs:
                            before_sec = src_secs[idx]
                            after_sec = cur_secs[idx]
                            # after が ◎ なら改善成功ペア
                            if after_sec.get("annotation_rating") == "good":
                                improvement_pairs.append({
                                    "lesson_name": lesson_name,
                                    "before": before_sec,
                                    "after": after_sec,
                                })

    return {
        "good": good,
        "needs_improvement": needs_improvement,
        "redo": redo,
        "improvement_pairs": improvement_pairs,
    }


def _format_annotated_for_prompt(entries: list[dict], label: str) -> str:
    """注釈付きセクション群をプロンプト用テキストに整形する"""
    if not entries:
        return ""
    lines = [f"### {label}（{len(entries)}件）\n"]
    for e in entries:
        s = e["section"]
        lines.append(f"**{e['lesson_name']}** セクション{s.get('order_index', '?')}: {s.get('title', '')} ({s.get('section_type', '')})")
        content = s.get("content", "")
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(content)
        if e.get("comment"):
            lines.append(f"コメント: {e['comment']}")
        lines.append("")
    return "\n".join(lines)


async def analyze_learnings(
    category: str,
    category_name: str = "",
    category_description: str = "",
) -> dict:
    """カテゴリ別に注釈付きセクションを収集しAIがパターンを抽出する。

    Returns:
        {
            "category_learnings": str (Markdown),
            "common_learnings": str (Markdown),
            "section_count": int,
            "prompt": {"system": str, "user": str},
            "raw_output": str,
        }
    """
    system_prompt = _load_prompt("lesson_analyze.md")

    # 注釈データ収集
    data = _collect_annotated_sections(category)
    section_count = len(data["good"]) + len(data["needs_improvement"]) + len(data["redo"])

    if section_count == 0:
        return {
            "category_learnings": "",
            "common_learnings": "",
            "section_count": 0,
            "prompt": {"system": system_prompt, "user": ""},
            "raw_output": "",
            "error": "注釈付きセクションがありません",
        }

    # ユーザープロンプト構築
    user_parts = []

    # カテゴリ情報
    user_parts.append("## カテゴリ情報\n")
    if category:
        user_parts.append(f"- slug: {category}")
        if category_name:
            user_parts.append(f"- 名前: {category_name}")
        if category_description:
            user_parts.append(f"- 説明: {category_description}")
    else:
        user_parts.append("- カテゴリ: 全体（カテゴリ未指定）")
    user_parts.append("")

    # ◎セクション
    user_parts.append(_format_annotated_for_prompt(data["good"], "◎良いセクション"))

    # △セクション
    user_parts.append(_format_annotated_for_prompt(data["needs_improvement"], "△要改善セクション"))

    # ✕セクション
    user_parts.append(_format_annotated_for_prompt(data["redo"], "✕作り直しセクション"))

    # 改善ペア
    if data["improvement_pairs"]:
        user_parts.append(f"### 改善ペア（✕→◎）（{len(data['improvement_pairs'])}件）\n")
        for pair in data["improvement_pairs"]:
            before = pair["before"]
            after = pair["after"]
            user_parts.append(f"**{pair['lesson_name']}** セクション{before.get('order_index', '?')}")
            user_parts.append(f"Before: {before.get('content', '')[:200]}")
            user_parts.append(f"After: {after.get('content', '')[:200]}")
            if after.get("annotation_comment"):
                user_parts.append(f"改善コメント: {after['annotation_comment']}")
            user_parts.append("")

    # 現在の学習結果
    existing = load_learnings(category)
    if existing:
        user_parts.append(f"## 現在の学習結果\n\n{existing}\n")

    # 日付
    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).strftime("%Y-%m-%d")
    user_parts.append(f"\n## 分析日: {today}、注釈件数: {section_count}件")

    user_prompt = "\n".join(user_parts)

    client = get_client()
    response = client.models.generate_content(
        model=_get_model(),
        contents=[
            types.Content(role="user", parts=[
                types.Part(text=f"{system_prompt}\n\n---\n\n{user_prompt}"),
            ]),
        ],
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=8192,
        ),
    )

    result = _parse_json_response(response.text)
    if not isinstance(result, dict):
        result = {"category_learnings": "", "common_learnings": ""}

    return {
        "category_learnings": result.get("category_learnings", ""),
        "common_learnings": result.get("common_learnings", ""),
        "section_count": section_count,
        "prompt": {
            "system": system_prompt,
            "user": user_prompt,
        },
        "raw_output": response.text,
    }


def save_learnings_to_files(category: str, category_learnings: str, common_learnings: str):
    """学習結果をファイルに書き出す。

    - カテゴリ別: prompts/learnings/{category}.md
    - 共通: prompts/learnings/_common.md（追記ではなく上書き）
    """
    LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)

    if category and category_learnings:
        cat_path = LEARNINGS_DIR / f"{category}.md"
        cat_path.write_text(category_learnings, encoding="utf-8")
        logger.info("学習結果書き出し: %s", cat_path)

    if common_learnings:
        common_path = LEARNINGS_DIR / "_common.md"
        common_path.write_text(common_learnings, encoding="utf-8")
        logger.info("共通学習結果書き出し: %s", common_path)


async def improve_prompt(
    category: str = "",
    category_name: str = "",
    category_description: str = "",
    prompt_file: str = "",
    prompt_content: str = "",
) -> dict:
    """学習結果をもとに生成プロンプトの改善案をdiff形式で生成する。

    Args:
        category: カテゴリslug（空なら共通プロンプト lesson_generate.md）
        category_name: カテゴリ表示名
        category_description: カテゴリ説明
        prompt_file: カテゴリ専用プロンプトファイル名（空ならベース、後方互換）
        prompt_content: カテゴリ専用プロンプト内容（DB保存、優先）

    Returns:
        {"summary", "diff_instructions", "learnings_to_graduate", "prompt", "raw_output"}
    """
    system_prompt = _load_prompt("lesson_improve_prompt.md")

    # 改善対象プロンプトを読み込む（prompt_content優先）
    if prompt_content:
        current_prompt = prompt_content
        target_name = f"[DB] {category} カテゴリプロンプト"
    elif prompt_file:
        target_path = PROMPTS_DIR / prompt_file
        if not target_path.exists():
            return {"error": f"プロンプトファイルが見つかりません: {target_path.name}"}
        current_prompt = target_path.read_text(encoding="utf-8")
        target_name = target_path.name
    else:
        target_path = PROMPTS_DIR / "lesson_generate.md"
        if not target_path.exists():
            return {"error": f"プロンプトファイルが見つかりません: {target_path.name}"}
        current_prompt = target_path.read_text(encoding="utf-8")
        target_name = target_path.name

    # 学習結果を読み込む
    learnings = load_learnings(category)
    if not learnings:
        return {"error": "学習結果がありません（prompts/learnings/ が空）"}

    # ユーザープロンプト構築
    user_parts = []
    user_parts.append("## 現在の生成プロンプト\n")
    user_parts.append(f"ファイル: {target_name}\n")
    user_parts.append(current_prompt)
    user_parts.append("\n\n## 学習結果\n")
    user_parts.append(learnings)
    if category:
        user_parts.append(f"\n\n## カテゴリ情報\n")
        user_parts.append(f"- slug: {category}")
        if category_name:
            user_parts.append(f"- 名前: {category_name}")
        if category_description:
            user_parts.append(f"- 説明: {category_description}")

    user_prompt = "\n".join(user_parts)

    client = get_client()
    response = client.models.generate_content(
        model=_get_model(),
        contents=[
            types.Content(role="user", parts=[
                types.Part(text=f"{system_prompt}\n\n---\n\n{user_prompt}"),
            ]),
        ],
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=8192,
        ),
    )

    result = _parse_json_response(response.text)
    if not isinstance(result, dict):
        result = {"summary": "", "diff_instructions": [], "learnings_to_graduate": []}

    return {
        "summary": result.get("summary", ""),
        "diff_instructions": result.get("diff_instructions", []),
        "learnings_to_graduate": result.get("learnings_to_graduate", []),
        "prompt_file": target_name,
        "prompt": {
            "system": system_prompt,
            "user": user_prompt,
        },
        "raw_output": response.text,
    }


def apply_prompt_diff(prompt_file: str, diff_instructions: list[dict]) -> dict:
    """プロンプト改善diffを適用する。

    Args:
        prompt_file: プロンプトファイル名（例: "lesson_generate.md"）
        diff_instructions: improve_prompt() が返した diff_instructions

    Returns:
        {"applied": int, "errors": list, "prompt_file": str}
    """
    target_path = PROMPTS_DIR / prompt_file
    if not target_path.exists():
        return {"error": f"プロンプトファイルが見つかりません: {prompt_file}"}

    content = target_path.read_text(encoding="utf-8")
    applied = 0
    errors = []

    for i, instr in enumerate(diff_instructions):
        action = instr.get("action", "")
        if action == "replace":
            old_text = instr.get("old_text", "")
            new_text = instr.get("new_text", "")
            if old_text and old_text in content:
                content = content.replace(old_text, new_text, 1)
                applied += 1
            else:
                errors.append(f"指示{i}: old_text が見つかりません")
        elif action == "add":
            add_content = instr.get("content", "")
            if add_content:
                content = content.rstrip() + "\n\n" + add_content + "\n"
                applied += 1
            else:
                errors.append(f"指示{i}: content が空です")
        else:
            errors.append(f"指示{i}: 不明なaction '{action}'")

    if applied > 0:
        target_path.write_text(content, encoding="utf-8")
        logger.info("プロンプト改善適用: %s, %d件", prompt_file, applied)

    return {"applied": applied, "errors": errors, "prompt_file": prompt_file}


async def create_category_prompt(
    base_prompt_file: str,
    category_slug: str,
    category_name: str,
    category_description: str,
) -> dict:
    """ベースプロンプト + カテゴリ説明からカテゴリ専用プロンプトを生成する。

    生成したプロンプトはDB（lesson_categories.prompt_content）に保存される。

    Returns:
        {"content": str}
    """
    base_path = PROMPTS_DIR / base_prompt_file
    if not base_path.exists():
        return {"error": f"ベースプロンプトが見つかりません: {base_prompt_file}"}

    base_content = base_path.read_text(encoding="utf-8")

    user_prompt = (
        f"以下のベースプロンプトを、カテゴリ「{category_name}」に特化したプロンプトに調整してください。\n\n"
        f"## カテゴリ情報\n"
        f"- slug: {category_slug}\n"
        f"- 名前: {category_name}\n"
        f"- 説明: {category_description}\n\n"
        f"## ベースプロンプト\n\n{base_content}\n\n"
        f"## 指示\n\n"
        f"ベースプロンプトの構造を維持しつつ、カテゴリの特性に合わせた調整を加えてください。\n"
        f"出力はプロンプトのMarkdownテキストのみ（JSON不要）。"
    )

    client = get_client()
    response = client.models.generate_content(
        model=_get_model(),
        contents=[
            types.Content(role="user", parts=[
                types.Part(text=user_prompt),
            ]),
        ],
        config=types.GenerateContentConfig(
            temperature=0.5,
            max_output_tokens=16384,
        ),
    )

    generated = response.text.strip()

    # DBに保存（呼び出し元で update_category を使う）
    logger.info("カテゴリ専用プロンプト生成: %s (DB保存)", category_slug)

    return {
        "content": generated,
    }
