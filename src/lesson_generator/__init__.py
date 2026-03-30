"""教師モード — 画像/URL解析 + 授業スクリプト生成

パッケージ化されたモジュール。既存の import パスとの互換性を維持するため、
全公開関数と一部のプライベート関数を re-export する。
"""

# --- utils ---
from .utils import (
    get_client,
    _is_english_mode,
    _get_model,
    _get_knowledge_model,
    _get_entertainment_model,
    _get_director_model,
    _get_dialogue_model,
    _parse_json_response,
    _guess_mime,
    _build_image_parts,
    _format_main_content_for_prompt,
)

# --- extractor ---
from .extractor import (
    clean_extracted_text,
    _normalize_roles,
    extract_main_content,
    extract_text_from_image,
    extract_text_from_url,
)

# --- dialogue ---
from .dialogue import (
    get_lesson_characters,
    _format_character_for_prompt,
    _build_dialogue_prompt,
    _build_dialogue_output_example,
    _build_section_from_dialogues,
    _generate_single_dialogue,
    _generate_section_dialogues,
)

# --- structure ---
from .structure import _build_structure_prompt

# --- director ---
from .director import _director_review

# --- planner ---
from .planner import generate_lesson_plan

# --- script ---
from .script import generate_lesson_script, generate_lesson_script_from_plan

# --- v2 ---
from .v2 import _build_adjacent_sections, generate_lesson_script_v2
