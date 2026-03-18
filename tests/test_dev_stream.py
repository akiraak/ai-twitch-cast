"""dev_stream.py のテスト（DevStreamManager）"""

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.dev_stream import DevStreamManager, _parse_repo_name, _run_git


class TestParseRepoName:
    def test_https_url(self):
        assert _parse_repo_name("https://github.com/owner/repo.git") == "owner/repo"

    def test_https_url_no_dotgit(self):
        assert _parse_repo_name("https://github.com/owner/repo") == "owner/repo"

    def test_ssh_url(self):
        assert _parse_repo_name("git@github.com:owner/repo.git") == "owner/repo"

    def test_gitlab_url(self):
        assert _parse_repo_name("https://gitlab.com/org/project.git") == "org/project"

    def test_invalid_url(self):
        with pytest.raises(ValueError):
            _parse_repo_name("not-a-url")


class TestAddRepo:
    @pytest.mark.asyncio
    async def test_add_success(self, test_db, tmp_path):
        """clone成功時にDBに登録される"""
        manager = DevStreamManager()

        def mock_run_git(args, cwd, timeout=30):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc123def456\n"
            result.stderr = ""
            # clone時にディレクトリを作る
            if args[0] == "clone":
                Path(args[-1]).mkdir(parents=True, exist_ok=True)
            return result

        with patch("src.dev_stream._run_git", side_effect=mock_run_git), \
             patch("src.dev_stream._REPOS_DIR", tmp_path / "repos"):
            repo = await manager.add_repo("https://github.com/test/repo.git")

        assert repo["name"] == "test/repo"
        assert repo["branch"] == "main"
        assert repo["last_commit_hash"] == "abc123def456"
        # DBにも保存されている
        assert test_db.get_dev_repo(repo["id"]) is not None

    @pytest.mark.asyncio
    async def test_add_clone_failure(self, test_db, tmp_path):
        """clone失敗時にValueError"""
        manager = DevStreamManager()

        def mock_run_git(args, cwd, timeout=30):
            result = MagicMock()
            result.returncode = 128
            result.stdout = ""
            result.stderr = "fatal: repository not found"
            return result

        with patch("src.dev_stream._run_git", side_effect=mock_run_git), \
             patch("src.dev_stream._REPOS_DIR", tmp_path / "repos"):
            with pytest.raises(ValueError, match="git clone 失敗"):
                await manager.add_repo("https://github.com/bad/repo.git")

    @pytest.mark.asyncio
    async def test_add_max_repos(self, test_db, tmp_path):
        """上限超過時にValueError"""
        manager = DevStreamManager()
        # 10個のリポジトリをDBに直接追加
        for i in range(10):
            test_db.add_dev_repo(f"r{i}", f"https://r{i}.git", f"repos/r{i}")

        with patch("src.dev_stream._REPOS_DIR", tmp_path / "repos"):
            with pytest.raises(ValueError, match="上限"):
                await manager.add_repo("https://github.com/extra/repo.git")

    @pytest.mark.asyncio
    async def test_add_custom_branch(self, test_db, tmp_path):
        """ブランチ指定"""
        manager = DevStreamManager()

        def mock_run_git(args, cwd, timeout=30):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc123\n"
            result.stderr = ""
            if args[0] == "clone":
                Path(args[-1]).mkdir(parents=True, exist_ok=True)
            return result

        with patch("src.dev_stream._run_git", side_effect=mock_run_git), \
             patch("src.dev_stream._REPOS_DIR", tmp_path / "repos"):
            repo = await manager.add_repo("https://github.com/t/r.git", branch="develop")

        assert repo["branch"] == "develop"


class TestRemoveRepo:
    @pytest.mark.asyncio
    async def test_remove_with_files(self, test_db, tmp_path):
        """ローカルファイルとDBレコードの両方を削除"""
        local_path = tmp_path / "repo"
        local_path.mkdir()
        (local_path / "file.txt").write_text("test")
        repo = test_db.add_dev_repo("o/r", "https://o.git", str(local_path))

        manager = DevStreamManager()
        await manager.remove_repo(repo["id"])

        assert not local_path.exists()
        assert test_db.get_dev_repo(repo["id"]) is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, test_db):
        """存在しないIDでもエラーにならない"""
        manager = DevStreamManager()
        await manager.remove_repo(999)  # no error


class TestFetchAndCheck:
    @pytest.mark.asyncio
    async def test_new_commits_detected(self, test_db, tmp_path):
        """新コミットを検知してdiff付きで返す"""
        local_path = tmp_path / "repo"
        local_path.mkdir()
        repo = test_db.add_dev_repo("o/r", "https://o.git", str(local_path))
        test_db.update_dev_repo_commit(repo["id"], "old111")
        repo["last_commit_hash"] = "old111"

        def mock_run_git(args, cwd, timeout=30):
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            if args[0] == "fetch":
                result.stdout = ""
            elif args[0] == "log":
                result.stdout = "new222\t新機能追加\tAuthor1\n"
            elif args[0] == "merge":
                result.stdout = ""
            elif args[0] == "show":
                result.stdout = " file.py | 10 ++++\n 1 file changed\n"
            elif args[0] == "diff":
                result.stdout = "+added line"
            else:
                result.stdout = ""
            return result

        manager = DevStreamManager()
        with patch("src.dev_stream._run_git", side_effect=mock_run_git):
            commits = await manager._fetch_and_check(repo)

        assert len(commits) == 1
        assert commits[0]["hash"] == "new222"
        assert commits[0]["message"] == "新機能追加"
        assert commits[0]["author"] == "Author1"
        assert "file.py" in commits[0]["diff_summary"]
        # DB更新されている
        updated = test_db.get_dev_repo(repo["id"])
        assert updated["last_commit_hash"] == "new222"

    @pytest.mark.asyncio
    async def test_no_new_commits(self, test_db, tmp_path):
        """新コミットがない場合は空リスト"""
        local_path = tmp_path / "repo"
        local_path.mkdir()
        repo = test_db.add_dev_repo("o/r", "https://o.git", str(local_path))
        test_db.update_dev_repo_commit(repo["id"], "current")
        repo["last_commit_hash"] = "current"

        def mock_run_git(args, cwd, timeout=30):
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            result.stdout = ""
            return result

        manager = DevStreamManager()
        with patch("src.dev_stream._run_git", side_effect=mock_run_git):
            commits = await manager._fetch_and_check(repo)

        assert commits == []

    @pytest.mark.asyncio
    async def test_missing_local_path(self, test_db):
        """ローカルパスが存在しない場合は空リスト"""
        repo = test_db.add_dev_repo("o/r", "https://o.git", "/nonexistent/path")
        manager = DevStreamManager()
        commits = await manager._fetch_and_check(repo)
        assert commits == []


class TestWatchLoop:
    @pytest.mark.asyncio
    async def test_calls_on_event(self, test_db, tmp_path):
        """新コミット検知時にon_eventが呼ばれる"""
        local_path = tmp_path / "repo"
        local_path.mkdir()
        repo = test_db.add_dev_repo("o/r", "https://o.git", str(local_path))
        test_db.update_dev_repo_commit(repo["id"], "old111")

        on_event = AsyncMock()
        manager = DevStreamManager(on_event=on_event)
        manager._poll_interval = 0.1  # テスト用に短く

        def mock_run_git(args, cwd, timeout=30):
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            if args[0] == "fetch":
                result.stdout = ""
            elif args[0] == "log":
                result.stdout = "new222\tfix bug\tDev\n"
            elif args[0] == "merge":
                result.stdout = ""
            elif args[0] == "show":
                result.stdout = " a.py | 1 +\n"
            elif args[0] == "diff":
                result.stdout = "+fix"
            else:
                result.stdout = ""
            return result

        with patch("src.dev_stream._run_git", side_effect=mock_run_git):
            await manager.start()
            # 1回ループが回るのを待つ
            await asyncio.sleep(0.3)
            await manager.stop()

        on_event.assert_called()
        call_args = on_event.call_args
        assert call_args[0][0] == "o/r"
        assert call_args[0][1][0]["hash"] == "new222"


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        """start/stopでis_runningが変わる"""
        manager = DevStreamManager()
        assert not manager.is_running
        await manager.start()
        assert manager.is_running
        await manager.stop()
        assert not manager.is_running

    @pytest.mark.asyncio
    async def test_double_start(self):
        """二重startは無視"""
        manager = DevStreamManager()
        await manager.start()
        await manager.start()  # no error
        assert manager.is_running
        await manager.stop()


class TestGetDiffSummary:
    def test_truncates_large_diff(self, tmp_path):
        """大きなdiffは切り詰められる"""
        manager = DevStreamManager()

        def mock_run_git(args, cwd, timeout=30):
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            if args[0] == "show":
                result.stdout = "stat line"
            elif args[0] == "diff":
                result.stdout = "x" * 1000
            else:
                result.stdout = ""
            return result

        with patch("src.dev_stream._run_git", side_effect=mock_run_git):
            summary = manager._get_diff_summary(str(tmp_path), "abc123")

        assert "以下省略" in summary
        # 500文字 + 省略メッセージ以内
        assert len(summary) < 600
