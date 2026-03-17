"""scene_config.py のテスト"""

import json

from src.scene_config import (
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
