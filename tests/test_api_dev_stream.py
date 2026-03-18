"""開発配信 APIのテスト"""

from unittest.mock import AsyncMock


class TestGetRepos:
    def test_empty(self, api_client):
        resp = api_client.get("/api/dev-stream/repos")
        assert resp.status_code == 200
        assert resp.json()["repos"] == []

    def test_with_repos(self, api_client, test_db):
        test_db.add_dev_repo("o/r", "https://o.git", "repos/r")
        resp = api_client.get("/api/dev-stream/repos")
        assert len(resp.json()["repos"]) == 1
        assert resp.json()["repos"][0]["name"] == "o/r"


class TestAddRepo:
    def test_success(self, api_client, monkeypatch):
        import scripts.state as st
        st.dev_stream_manager.add_repo = AsyncMock(return_value={
            "id": 1, "name": "t/r", "url": "https://t.git",
            "local_path": "repos/t-r", "branch": "main",
            "last_commit_hash": "abc", "active": 1,
        })
        resp = api_client.post("/api/dev-stream/repos", json={
            "url": "https://github.com/t/r.git", "branch": "main",
        })
        assert resp.json()["ok"] is True
        assert resp.json()["repo"]["name"] == "t/r"

    def test_missing_url(self, api_client):
        resp = api_client.post("/api/dev-stream/repos", json={"url": ""})
        assert resp.json()["ok"] is False

    def test_clone_failure(self, api_client, monkeypatch):
        import scripts.state as st
        st.dev_stream_manager.add_repo = AsyncMock(side_effect=ValueError("clone失敗"))
        resp = api_client.post("/api/dev-stream/repos", json={"url": "https://bad.git"})
        assert resp.json()["ok"] is False
        assert "clone失敗" in resp.json()["error"]


class TestDeleteRepo:
    def test_delete(self, api_client):
        resp = api_client.delete("/api/dev-stream/repos/1")
        assert resp.json()["ok"] is True


class TestToggleRepo:
    def test_activate_exclusive(self, api_client, test_db):
        """有効化すると他は無効化される"""
        r1 = test_db.add_dev_repo("a", "https://a.git", "repos/a")
        r2 = test_db.add_dev_repo("b", "https://b.git", "repos/b")
        # r1を有効化
        resp = api_client.post(f"/api/dev-stream/repos/{r1['id']}/toggle", json={"active": True})
        assert resp.json()["ok"] is True
        assert test_db.get_dev_repo(r1["id"])["active"] == 1
        # r2を有効化 → r1は無効化される
        resp = api_client.post(f"/api/dev-stream/repos/{r2['id']}/toggle", json={"active": True})
        assert resp.json()["ok"] is True
        assert test_db.get_dev_repo(r2["id"])["active"] == 1
        assert test_db.get_dev_repo(r1["id"])["active"] == 0

    def test_deactivate(self, api_client, test_db):
        repo = test_db.add_dev_repo("o/r", "https://o.git", "repos/r")
        api_client.post(f"/api/dev-stream/repos/{repo['id']}/toggle", json={"active": True})
        resp = api_client.post(f"/api/dev-stream/repos/{repo['id']}/toggle", json={"active": False})
        assert resp.json()["ok"] is True
        assert test_db.get_dev_repo(repo["id"])["active"] == 0


class TestCheckRepo:
    def test_no_commits(self, api_client):
        resp = api_client.post("/api/dev-stream/repos/1/check")
        assert resp.json()["ok"] is True
        assert resp.json()["commits"] == 0


class TestStatus:
    def test_status(self, api_client):
        resp = api_client.get("/api/dev-stream/status")
        assert resp.status_code == 200
        assert "running" in resp.json()
        assert "active_repos" in resp.json()
