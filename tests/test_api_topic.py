"""トピック管理 APIのテスト"""


class TestGetTopic:
    def test_no_topic(self, api_client):
        resp = api_client.get("/api/topic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is False
        assert data["topic"] is None


class TestSetTopic:
    def test_set_topic(self, api_client):
        resp = api_client.post("/api/topic", json={"title": "Python"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["topic"]["title"] == "Python"

    def test_empty_title(self, api_client):
        resp = api_client.post("/api/topic", json={"title": ""})
        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def test_with_description(self, api_client):
        resp = api_client.post("/api/topic", json={"title": "AI", "description": "AIについて"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestClearTopic:
    def test_clear(self, api_client):
        api_client.post("/api/topic", json={"title": "temp"})
        resp = api_client.delete("/api/topic")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # 確認
        resp2 = api_client.get("/api/topic")
        assert resp2.json()["active"] is False


class TestTopicScripts:
    def test_no_topic(self, api_client):
        resp = api_client.get("/api/topic/scripts")
        assert resp.status_code == 200
        assert resp.json()["scripts"] == []

    def test_with_topic(self, api_client):
        api_client.post("/api/topic", json={"title": "test"})
        resp = api_client.get("/api/topic/scripts")
        assert resp.status_code == 200
        assert "scripts" in resp.json()


class TestPauseResume:
    def test_pause(self, api_client):
        resp = api_client.post("/api/topic/pause")
        assert resp.status_code == 200
        assert resp.json()["paused"] is True

    def test_resume(self, api_client):
        api_client.post("/api/topic/pause")
        resp = api_client.post("/api/topic/resume")
        assert resp.status_code == 200
        assert resp.json()["paused"] is False


class TestTopicSettings:
    def test_update_idle_threshold(self, api_client):
        resp = api_client.post("/api/topic/settings", json={"idle_threshold": 60})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_update_min_interval(self, api_client):
        resp = api_client.post("/api/topic/settings", json={"min_interval": 90})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
