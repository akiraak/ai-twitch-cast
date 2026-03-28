"""ドキュメント閲覧APIのテスト"""

import pytest


class TestListDocFiles:
    """GET /api/docs/files のテスト"""

    def test_list_plans(self, api_client):
        """plansディレクトリのファイル一覧が返る"""
        res = api_client.get("/api/docs/files?dir=plans")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert isinstance(data["files"], list)
        assert len(data["files"]) > 0
        # 各ファイルにname, size, modifiedがある
        f = data["files"][0]
        assert "name" in f
        assert "size" in f
        assert "modified" in f
        # .mdファイルのみ
        for f in data["files"]:
            assert f["name"].endswith(".md")

    def test_list_docs(self, api_client):
        """docsディレクトリのファイル一覧が返る"""
        res = api_client.get("/api/docs/files?dir=docs")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert len(data["files"]) > 0

    def test_invalid_dir(self, api_client):
        """許可されていないディレクトリは拒否"""
        res = api_client.get("/api/docs/files?dir=src")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False
        assert "許可されていない" in data["error"]


class TestGetDocFile:
    """GET /api/docs/file のテスト"""

    def test_get_existing_file(self, api_client):
        """存在するファイルの内容が返る"""
        res = api_client.get("/api/docs/file?dir=docs&name=versioning.md")
        assert res.status_code == 200
        assert "バージョニング" in res.text

    def test_file_not_found(self, api_client):
        """存在しないファイルは404"""
        res = api_client.get("/api/docs/file?dir=docs&name=nonexistent.md")
        assert res.status_code == 404

    def test_path_traversal_rejected(self, api_client):
        """パストラバーサルは400"""
        res = api_client.get("/api/docs/file?dir=plans&name=../server.sh")
        assert res.status_code == 400

    def test_invalid_dir(self, api_client):
        """許可されていないディレクトリは400"""
        res = api_client.get("/api/docs/file?dir=src&name=db.py")
        assert res.status_code == 400

    def test_non_md_extension_rejected(self, api_client):
        """md以外の拡張子は400"""
        res = api_client.get("/api/docs/file?dir=plans&name=test.txt")
        assert res.status_code == 400

    def test_empty_name_rejected(self, api_client):
        """空のファイル名は400"""
        res = api_client.get("/api/docs/file?dir=plans&name=")
        assert res.status_code == 400
