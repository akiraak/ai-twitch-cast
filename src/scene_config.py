"""設定の定義（DB優先 → scenes.json フォールバック）"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Webサーバーのポート
WEB_PORT = int(os.environ.get("WEB_PORT", "8080"))

_PROJECT_DIR = Path(__file__).resolve().parent.parent
RESOURCES_DIR = _PROJECT_DIR / "resources"
CONFIG_PATH = _PROJECT_DIR / "scenes.json"

# 授業再生の各種「間」の既定値（plans/lesson-pause-investigation.md §3.2）
LESSON_TIMINGS_DEFAULTS = {
    "inter_dialogue_gap_ms": 300,
    "playback_stopped_fallback_extra_sec": 1.5,
    "section_wait_sec": {
        "introduction": 2,
        "explanation": 2,
        "example": 2,
        "question": 3,
        "summary": 3,
        "default": 2,
    },
    "question_answer_wait_sec": 8,
}


def load_config_value(key, default=None):
    """設定値を取得する（DB優先 → scenes.json → default）"""
    from src import db
    val = db.get_setting(key)
    if val is not None:
        return val
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        parts = key.split(".")
        obj = config
        for p in parts:
            obj = obj[p]
        return obj if obj is not None else default
    except (KeyError, TypeError, FileNotFoundError):
        return default


def load_config_json(key, default=None):
    """JSON値を取得する（DB優先 → scenes.json → default）"""
    from src import db
    val = db.get_setting(key)
    if val is not None:
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        parts = key.split(".")
        obj = config
        for p in parts:
            obj = obj[p]
        return obj if obj is not None else default
    except (KeyError, TypeError, FileNotFoundError):
        return default


def save_config_value(key, value):
    """設定値をDBに保存する"""
    from src import db
    db.set_setting(key, str(value))


def save_config_json(key, value):
    """JSON値をDBに保存する"""
    from src import db
    db.set_setting(key, json.dumps(value, ensure_ascii=False))


def _is_valid_nonneg_number(v):
    """非負の有限数値か判定（bool は除外、NaN/Inf も除外）"""
    if isinstance(v, bool):
        return False
    if not isinstance(v, (int, float)):
        return False
    if v != v:  # NaN
        return False
    if v == float("inf") or v == float("-inf"):
        return False
    return v >= 0


def get_lesson_timings() -> dict:
    """授業再生の各種「間」設定を取得する（DB → scenes.json → 既定値）。

    plans/lesson-pause-investigation.md §3 のスキーマに従う:
      - inter_dialogue_gap_ms: dialogue 間ギャップ (ms)
      - playback_stopped_fallback_extra_sec: PlaybackStopped fallback 余裕 (sec)
      - section_wait_sec: section_type 別のセクション間 (sec)、未指定 type は default
      - question_answer_wait_sec: question セクション解答前の間 (sec)

    不正値（非数値/NaN/負数）は既定値にフォールバックし、警告を出す。
    """
    raw = load_config_json("lesson_timings", {})
    if not isinstance(raw, dict):
        logger.warning("lesson_timings is not a dict (%r), using defaults", type(raw).__name__)
        raw = {}

    result: dict = {}

    for key in ("inter_dialogue_gap_ms", "playback_stopped_fallback_extra_sec", "question_answer_wait_sec"):
        default = LESSON_TIMINGS_DEFAULTS[key]
        if key in raw:
            v = raw[key]
            if _is_valid_nonneg_number(v):
                result[key] = v
            else:
                logger.warning("lesson_timings.%s invalid (%r), falling back to %r", key, v, default)
                result[key] = default
        else:
            result[key] = default

    sw_defaults = LESSON_TIMINGS_DEFAULTS["section_wait_sec"]
    sw_raw = raw.get("section_wait_sec")
    if sw_raw is None:
        result["section_wait_sec"] = dict(sw_defaults)
    elif not isinstance(sw_raw, dict):
        logger.warning("lesson_timings.section_wait_sec is not a dict (%r), using defaults", type(sw_raw).__name__)
        result["section_wait_sec"] = dict(sw_defaults)
    else:
        sw: dict = dict(sw_defaults)
        for k, default in sw_defaults.items():
            if k in sw_raw:
                v = sw_raw[k]
                if _is_valid_nonneg_number(v):
                    sw[k] = v
                else:
                    logger.warning(
                        "lesson_timings.section_wait_sec.%s invalid (%r), falling back to %r",
                        k, v, default,
                    )
        for k, v in sw_raw.items():
            if k in sw_defaults:
                continue
            if _is_valid_nonneg_number(v):
                sw[k] = v
            else:
                logger.warning(
                    "lesson_timings.section_wait_sec.%s invalid (%r), ignored",
                    k, v,
                )
        result["section_wait_sec"] = sw

    return result
