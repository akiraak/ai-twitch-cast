"""ドキュメント閲覧APIのテスト"""

from pathlib import Path

import pytest

from scripts.routes import docs_viewer


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


@pytest.fixture
def temp_plans_root(tmp_path, monkeypatch):
    """docs_viewer の PROJECT_ROOT を差し替えて plans/ を隔離する"""
    monkeypatch.setattr(docs_viewer, "PROJECT_ROOT", tmp_path)
    plans = tmp_path / "plans"
    plans.mkdir()
    return plans


class TestArchivePlan:
    """POST /api/docs/archive-plan のテスト"""

    def test_archive_success(self, api_client, temp_plans_root):
        """plans/foo.md → plans/archive/foo.md に移動できる"""
        (temp_plans_root / "foo.md").write_text("# foo\n", encoding="utf-8")
        res = api_client.post("/api/docs/archive-plan?name=foo.md")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["moved_to"] == "archive/foo.md"
        assert not (temp_plans_root / "foo.md").exists()
        assert (temp_plans_root / "archive" / "foo.md").exists()

    def test_creates_archive_dir_if_missing(self, api_client, temp_plans_root):
        """archive/ が無ければ作る"""
        (temp_plans_root / "bar.md").write_text("# bar\n", encoding="utf-8")
        assert not (temp_plans_root / "archive").exists()
        res = api_client.post("/api/docs/archive-plan?name=bar.md")
        assert res.status_code == 200
        assert (temp_plans_root / "archive").is_dir()

    def test_slash_rejected(self, api_client, temp_plans_root):
        """name に / を含むと400"""
        res = api_client.post("/api/docs/archive-plan?name=sub/foo.md")
        assert res.status_code == 400
        assert res.json()["ok"] is False

    def test_parent_traversal_rejected(self, api_client, temp_plans_root):
        """name に .. を含むと400"""
        res = api_client.post("/api/docs/archive-plan?name=..%2Ffoo.md")
        assert res.status_code == 400

    def test_non_md_file_rejected(self, api_client, temp_plans_root):
        """存在する .md 以外のファイルは400"""
        (temp_plans_root / "foo.txt").write_text("x", encoding="utf-8")
        res = api_client.post("/api/docs/archive-plan?name=foo.txt")
        assert res.status_code == 400
        # 移動されていない
        assert (temp_plans_root / "foo.txt").exists()

    def test_empty_name_rejected(self, api_client, temp_plans_root):
        """空のファイル名は400"""
        res = api_client.post("/api/docs/archive-plan?name=")
        assert res.status_code == 400

    def test_missing_file(self, api_client, temp_plans_root):
        """存在しないファイルは404"""
        res = api_client.post("/api/docs/archive-plan?name=nope.md")
        assert res.status_code == 404
        assert res.json()["ok"] is False

    def test_conflict_on_existing_archive(self, api_client, temp_plans_root):
        """archive に同名ファイルが既にある場合は409で上書きしない"""
        (temp_plans_root / "dup.md").write_text("new\n", encoding="utf-8")
        archive = temp_plans_root / "archive"
        archive.mkdir()
        (archive / "dup.md").write_text("old\n", encoding="utf-8")
        res = api_client.post("/api/docs/archive-plan?name=dup.md")
        assert res.status_code == 409
        assert res.json()["ok"] is False
        # 元ファイルも archive も変更されていない
        assert (temp_plans_root / "dup.md").exists()
        assert (archive / "dup.md").read_text(encoding="utf-8") == "old\n"

    def test_archive_directory(self, api_client, temp_plans_root):
        """plans/<dir>/ → plans/archive/<dir>/ に移動できる"""
        feature_dir = temp_plans_root / "my-feature"
        feature_dir.mkdir()
        (feature_dir / "README.md").write_text("# readme\n", encoding="utf-8")
        (feature_dir / "step1.md").write_text("step1\n", encoding="utf-8")

        res = api_client.post("/api/docs/archive-plan?name=my-feature")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["moved_to"] == "archive/my-feature"

        # ディレクトリごと移動しており、中身が保持されている
        assert not feature_dir.exists()
        moved = temp_plans_root / "archive" / "my-feature"
        assert moved.is_dir()
        assert (moved / "README.md").read_text(encoding="utf-8") == "# readme\n"
        assert (moved / "step1.md").read_text(encoding="utf-8") == "step1\n"

    def test_archive_itself_rejected(self, api_client, temp_plans_root):
        """archive 自身は移動できない"""
        (temp_plans_root / "archive").mkdir()
        res = api_client.post("/api/docs/archive-plan?name=archive")
        assert res.status_code == 400
        assert res.json()["ok"] is False
        # archive はそのまま残っている
        assert (temp_plans_root / "archive").is_dir()

    def test_conflict_on_existing_archive_dir(self, api_client, temp_plans_root):
        """archive に同名ディレクトリが既にある場合は409で上書きしない"""
        src = temp_plans_root / "dup-dir"
        src.mkdir()
        (src / "a.md").write_text("new\n", encoding="utf-8")
        archive = temp_plans_root / "archive" / "dup-dir"
        archive.mkdir(parents=True)
        (archive / "a.md").write_text("old\n", encoding="utf-8")

        res = api_client.post("/api/docs/archive-plan?name=dup-dir")
        assert res.status_code == 409
        # 元ディレクトリも archive も変更されていない
        assert src.is_dir()
        assert (archive / "a.md").read_text(encoding="utf-8") == "old\n"
