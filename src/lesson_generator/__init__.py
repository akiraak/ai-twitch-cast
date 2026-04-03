"""教師モード — 画像/URL解析 + 授業スクリプト生成

パッケージ化されたモジュール。既存の import パスとの互換性を維持するため、
全公開関数と一部のプライベート関数を re-export する。
"""

# --- utils ---
from .utils import (
    get_client,
    _is_english_mode,
    _get_model,
    _parse_json_response,
    _guess_mime,
    _build_image_parts,
    _format_main_content_for_prompt,
    get_lesson_characters,
    _format_character_for_prompt,
)

# --- extractor ---
from .extractor import (
    clean_extracted_text,
    _normalize_roles,
    extract_main_content,
    extract_text_from_image,
    extract_text_from_url,
)

# --- improver ---
from .improver import (
    _load_prompt,
    verify_lesson,
    evaluate_lesson_quality,
    evaluate_category_fit,
    determine_targets,
    improve_sections,
    load_learnings,
    analyze_learnings,
    save_learnings_to_files,
    improve_prompt,
    apply_prompt_diff,
    create_category_prompt,
)
