"""scene_config.py のテスト"""

import json

from src.scene_config import (
    LESSON_TIMINGS_DEFAULTS,
    get_lesson_timings,
    load_config_json,
    load_config_value,
    save_config_json,
    save_config_value,
)


class TestLoadConfigValue:
    def test_from_db(self, test_db):
        test_db.set_setting("audio.master", "0.8")
        assert load_config_value("audio.master") == "0.8"

    def test_from_scenes_json(self, test_db, tmp_path, monkeypatch):
        import src.scene_config as sc
        config_file = tmp_path / "scenes.json"
        config_file.write_text(json.dumps({"audio": {"master": 0.5}}), encoding="utf-8")
        monkeypatch.setattr(sc, "CONFIG_PATH", config_file)
        assert load_config_value("audio.master") == 0.5

    def test_db_takes_precedence(self, test_db, tmp_path, monkeypatch):
        import src.scene_config as sc
        test_db.set_setting("audio.master", "0.9")
        config_file = tmp_path / "scenes.json"
        config_file.write_text(json.dumps({"audio": {"master": 0.5}}), encoding="utf-8")
        monkeypatch.setattr(sc, "CONFIG_PATH", config_file)
        assert load_config_value("audio.master") == "0.9"

    def test_default_fallback(self, test_db):
        assert load_config_value("nonexistent", "fallback") == "fallback"

    def test_missing_file_returns_default(self, test_db, tmp_path, monkeypatch):
        import src.scene_config as sc
        monkeypatch.setattr(sc, "CONFIG_PATH", tmp_path / "missing.json")
        assert load_config_value("key", "default") == "default"

    def test_nested_key(self, test_db, tmp_path, monkeypatch):
        import src.scene_config as sc
        config = {"level1": {"level2": {"level3": "deep"}}}
        config_file = tmp_path / "scenes.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.setattr(sc, "CONFIG_PATH", config_file)
        assert load_config_value("level1.level2.level3") == "deep"


class TestLoadConfigJson:
    def test_from_db_json(self, test_db):
        test_db.set_setting("overlay.panels", json.dumps(["a", "b"]))
        result = load_config_json("overlay.panels")
        assert result == ["a", "b"]

    def test_invalid_json_returns_raw(self, test_db):
        test_db.set_setting("key", "not-json")
        result = load_config_json("key")
        assert result == "not-json"

    def test_default(self, test_db):
        assert load_config_json("missing", {"default": True}) == {"default": True}


class TestSaveConfigValue:
    def test_save_and_load(self, test_db):
        save_config_value("test.key", "hello")
        assert load_config_value("test.key") == "hello"

    def test_overwrite(self, test_db):
        save_config_value("key", "old")
        save_config_value("key", "new")
        assert load_config_value("key") == "new"


class TestSaveConfigJson:
    def test_save_and_load_json(self, test_db):
        save_config_json("test.data", {"list": [1, 2, 3]})
        result = load_config_json("test.data")
        assert result == {"list": [1, 2, 3]}


def _write_scenes(tmp_path, monkeypatch, payload):
    import src.scene_config as sc
    config_file = tmp_path / "scenes.json"
    config_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(sc, "CONFIG_PATH", config_file)
    return config_file


class TestGetLessonTimings:
    def test_defaults_when_missing_file(self, test_db, tmp_path, monkeypatch):
        import src.scene_config as sc
        monkeypatch.setattr(sc, "CONFIG_PATH", tmp_path / "missing.json")
        result = get_lesson_timings()
        assert result == LESSON_TIMINGS_DEFAULTS
        assert result is not LESSON_TIMINGS_DEFAULTS  # 防御コピー
        assert result["section_wait_sec"] is not LESSON_TIMINGS_DEFAULTS["section_wait_sec"]

    def test_defaults_when_key_absent(self, test_db, tmp_path, monkeypatch):
        _write_scenes(tmp_path, monkeypatch, {"audio_volumes": {"master": 0.8}})
        assert get_lesson_timings() == LESSON_TIMINGS_DEFAULTS

    def test_full_config_from_scenes_json(self, test_db, tmp_path, monkeypatch):
        payload = {
            "lesson_timings": {
                "inter_dialogue_gap_ms": 500,
                "playback_stopped_fallback_extra_sec": 2.0,
                "section_wait_sec": {
                    "introduction": 1,
                    "explanation": 2,
                    "example": 3,
                    "question": 4,
                    "summary": 5,
                    "default": 1.5,
                },
                "question_answer_wait_sec": 6,
            }
        }
        _write_scenes(tmp_path, monkeypatch, payload)
        assert get_lesson_timings() == payload["lesson_timings"]

    def test_partial_config_fills_defaults(self, test_db, tmp_path, monkeypatch):
        _write_scenes(
            tmp_path,
            monkeypatch,
            {"lesson_timings": {"inter_dialogue_gap_ms": 100}},
        )
        result = get_lesson_timings()
        assert result["inter_dialogue_gap_ms"] == 100
        assert result["playback_stopped_fallback_extra_sec"] == LESSON_TIMINGS_DEFAULTS[
            "playback_stopped_fallback_extra_sec"
        ]
        assert result["question_answer_wait_sec"] == LESSON_TIMINGS_DEFAULTS["question_answer_wait_sec"]
        assert result["section_wait_sec"] == LESSON_TIMINGS_DEFAULTS["section_wait_sec"]

    def test_partial_section_wait_fills_defaults(self, test_db, tmp_path, monkeypatch):
        _write_scenes(
            tmp_path,
            monkeypatch,
            {"lesson_timings": {"section_wait_sec": {"question": 10}}},
        )
        result = get_lesson_timings()
        assert result["section_wait_sec"]["question"] == 10
        assert result["section_wait_sec"]["default"] == LESSON_TIMINGS_DEFAULTS[
            "section_wait_sec"
        ]["default"]
        assert result["section_wait_sec"]["introduction"] == LESSON_TIMINGS_DEFAULTS[
            "section_wait_sec"
        ]["introduction"]

    def test_invalid_top_level_uses_defaults(self, test_db, tmp_path, monkeypatch):
        _write_scenes(tmp_path, monkeypatch, {"lesson_timings": "not-a-dict"})
        assert get_lesson_timings() == LESSON_TIMINGS_DEFAULTS

    def test_invalid_values_clamped_to_defaults(self, test_db, tmp_path, monkeypatch):
        _write_scenes(
            tmp_path,
            monkeypatch,
            {
                "lesson_timings": {
                    "inter_dialogue_gap_ms": -100,
                    "playback_stopped_fallback_extra_sec": "1.5",
                    "question_answer_wait_sec": None,
                    "section_wait_sec": {
                        "question": -1,
                        "explanation": "abc",
                        "summary": float("nan"),
                    },
                }
            },
        )
        result = get_lesson_timings()
        assert result["inter_dialogue_gap_ms"] == LESSON_TIMINGS_DEFAULTS["inter_dialogue_gap_ms"]
        assert result["playback_stopped_fallback_extra_sec"] == LESSON_TIMINGS_DEFAULTS[
            "playback_stopped_fallback_extra_sec"
        ]
        assert result["question_answer_wait_sec"] == LESSON_TIMINGS_DEFAULTS["question_answer_wait_sec"]
        assert result["section_wait_sec"]["question"] == LESSON_TIMINGS_DEFAULTS[
            "section_wait_sec"
        ]["question"]
        assert result["section_wait_sec"]["explanation"] == LESSON_TIMINGS_DEFAULTS[
            "section_wait_sec"
        ]["explanation"]
        assert result["section_wait_sec"]["summary"] == LESSON_TIMINGS_DEFAULTS[
            "section_wait_sec"
        ]["summary"]

    def test_invalid_section_wait_uses_defaults(self, test_db, tmp_path, monkeypatch):
        _write_scenes(
            tmp_path,
            monkeypatch,
            {"lesson_timings": {"section_wait_sec": "oops"}},
        )
        result = get_lesson_timings()
        assert result["section_wait_sec"] == LESSON_TIMINGS_DEFAULTS["section_wait_sec"]

    def test_unknown_section_type_passed_through(self, test_db, tmp_path, monkeypatch):
        _write_scenes(
            tmp_path,
            monkeypatch,
            {"lesson_timings": {"section_wait_sec": {"recap": 4}}},
        )
        result = get_lesson_timings()
        assert result["section_wait_sec"]["recap"] == 4
        assert result["section_wait_sec"]["default"] == LESSON_TIMINGS_DEFAULTS[
            "section_wait_sec"
        ]["default"]

    def test_unknown_section_type_invalid_dropped(self, test_db, tmp_path, monkeypatch):
        _write_scenes(
            tmp_path,
            monkeypatch,
            {"lesson_timings": {"section_wait_sec": {"recap": "bad"}}},
        )
        result = get_lesson_timings()
        assert "recap" not in result["section_wait_sec"]
        # 既知キーは defaults のまま
        assert result["section_wait_sec"]["default"] == LESSON_TIMINGS_DEFAULTS[
            "section_wait_sec"
        ]["default"]

    def test_zero_is_valid(self, test_db, tmp_path, monkeypatch):
        _write_scenes(
            tmp_path,
            monkeypatch,
            {
                "lesson_timings": {
                    "inter_dialogue_gap_ms": 0,
                    "section_wait_sec": {"question": 0},
                }
            },
        )
        result = get_lesson_timings()
        assert result["inter_dialogue_gap_ms"] == 0
        assert result["section_wait_sec"]["question"] == 0

    def test_bool_rejected(self, test_db, tmp_path, monkeypatch):
        _write_scenes(
            tmp_path,
            monkeypatch,
            {"lesson_timings": {"inter_dialogue_gap_ms": True}},
        )
        result = get_lesson_timings()
        assert result["inter_dialogue_gap_ms"] == LESSON_TIMINGS_DEFAULTS["inter_dialogue_gap_ms"]

    def test_db_takes_precedence(self, test_db, tmp_path, monkeypatch):
        _write_scenes(
            tmp_path,
            monkeypatch,
            {"lesson_timings": {"inter_dialogue_gap_ms": 100}},
        )
        test_db.set_setting(
            "lesson_timings",
            json.dumps({"inter_dialogue_gap_ms": 999, "question_answer_wait_sec": 5}),
        )
        result = get_lesson_timings()
        assert result["inter_dialogue_gap_ms"] == 999
        assert result["question_answer_wait_sec"] == 5
        # DB に書いてないキーは defaults
        assert result["section_wait_sec"] == LESSON_TIMINGS_DEFAULTS["section_wait_sec"]
