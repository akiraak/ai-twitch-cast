"""キャラクター・言語モード APIのテスト"""

from src.ai_responder import invalidate_character_cache
from src.prompt_builder import set_language_mode


class TestGetCharacter:
    def test_returns_character(self, api_client):
        resp = api_client.get("/api/character")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert "system_prompt" in data
        assert "emotions" in data
        assert "id" in data


class TestUpdateCharacter:
    def test_update_success(self, api_client):
        body = {
            "name": "new_name",
            "system_prompt": "new prompt",
            "rules": ["rule1"],
            "emotions": {"joy": "嬉しい", "neutral": "通常"},
            "emotion_blendshapes": {"joy": {"Joy": 1.0}, "neutral": {}},
        }
        resp = api_client.put("/api/character", json=body)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_validation_error(self, api_client):
        resp = api_client.put("/api/character", json={"name": "x"})
        assert resp.status_code == 422


class TestGetCharacterLayers:
    def test_returns_layers(self, api_client):
        resp = api_client.get("/api/character/layers")
        assert resp.status_code == 200
        data = resp.json()
        assert "persona" in data
        assert "self_note" in data
        assert "viewer_notes" in data


class TestUpdatePersona:
    def setup_method(self):
        invalidate_character_cache()

    def test_update_persona(self, api_client):
        resp = api_client.put("/api/character/persona", json={"text": "テスト用ペルソナ"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # 更新が反映されていることを確認
        layers = api_client.get("/api/character/layers").json()
        assert layers["persona"] == "テスト用ペルソナ"

    def test_clear_persona(self, api_client):
        api_client.put("/api/character/persona", json={"text": "初期値"})
        resp = api_client.put("/api/character/persona", json={"text": ""})
        assert resp.status_code == 200
        layers = api_client.get("/api/character/layers").json()
        assert layers["persona"] == ""



class TestGetLanguage:
    def test_returns_modes(self, api_client):
        resp = api_client.get("/api/language")
        assert resp.status_code == 200
        data = resp.json()
        assert "current" in data
        assert "modes" in data
        assert len(data["modes"]) >= 5
        # 1つだけactiveがTrue
        active = [m for m in data["modes"] if m["active"]]
        assert len(active) == 1


class TestSetLanguage:
    def setup_method(self):
        set_language_mode("ja")

    def test_set_valid_mode(self, api_client):
        resp = api_client.post("/api/language", json={"mode": "en_bilingual"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["mode"] == "en_bilingual"

    def test_set_invalid_mode(self, api_client):
        resp = api_client.post("/api/language", json={"mode": "invalid"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def teardown_method(self):
        set_language_mode("ja")
