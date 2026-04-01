"""授業スクリプト検証・改善 — 元教材との整合性チェック & 部分再生成"""

import json
import logging
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
