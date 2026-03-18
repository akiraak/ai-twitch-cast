"""配信制御 APIのテスト（stream_control.py）"""


class TestScenes:
    def test_get_scenes(self, api_client):
        resp = api_client.get("/api/broadcast/scenes")
        assert resp.status_code == 200
        scenes = resp.json()["scenes"]
        names = [s["name"] for s in scenes]
        assert "main" in names
        assert "start" in names
        assert "end" in names

    def test_set_valid_scene(self, api_client):
        resp = api_client.post("/api/broadcast/scene", json={"name": "main"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_set_invalid_scene(self, api_client):
        resp = api_client.post("/api/broadcast/scene", json={"name": "invalid"})
        assert resp.status_code == 400


class TestVolume:
    def test_get_volumes(self, api_client):
        resp = api_client.get("/api/broadcast/volume")
        assert resp.status_code == 200
        data = resp.json()
        assert "master" in data
        assert "tts" in data
        assert "bgm" in data

    def test_set_volume(self, api_client):
        resp = api_client.post("/api/broadcast/volume", json={"source": "master", "volume": 0.5})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # 反映確認
        resp2 = api_client.get("/api/broadcast/volume")
        assert resp2.json()["master"] == 0.5

    def test_set_tts_volume(self, api_client):
        resp = api_client.post("/api/broadcast/volume", json={"source": "tts", "volume": 0.3})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_invalid_source(self, api_client):
        resp = api_client.post("/api/broadcast/volume", json={"source": "invalid", "volume": 0.5})
        assert resp.status_code == 400


class TestAvatar:
    def test_get_avatar(self, api_client):
        resp = api_client.get("/api/broadcast/avatar")
        assert resp.status_code == 200
        assert "url" in resp.json()

    def test_set_avatar(self, api_client):
        resp = api_client.post("/api/broadcast/avatar", json={"url": "http://example.com/stream"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_stop_avatar(self, api_client):
        resp = api_client.post("/api/broadcast/avatar/stop")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestStatus:
    def test_api_status(self, api_client):
        resp = api_client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "server_started_at" in data
        assert "reader" in data
        assert "version" in data
        assert "updated_at" in data

    def test_env_masks_secrets(self, api_client):
        resp = api_client.get("/api/env")
        assert resp.status_code == 200
        data = resp.json()
        tokens = [e for e in data if e["key"] == "TWITCH_TOKEN"]
        assert tokens[0]["value"] == "***"

    def test_env_shows_non_secret(self, api_client):
        resp = api_client.get("/api/env")
        data = resp.json()
        ports = [e for e in data if e["key"] == "WEB_PORT"]
        assert ports[0]["value"] == "8888"
