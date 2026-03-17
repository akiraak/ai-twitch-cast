"""git_watcher.py のテスト"""

from unittest.mock import MagicMock, AsyncMock, patch


class TestGetLatestCommit:
    """_get_latest_commit のテスト"""

    def test_parses_git_log_output(self):
        from src.git_watcher import GitWatcher

        watcher = GitWatcher(on_commit=AsyncMock())
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc1234def5678\tfix: バグ修正\n",
            )
            hash_, msg = watcher._get_latest_commit()
            assert hash_ == "abc1234def5678"
            assert msg == "fix: バグ修正"

    def test_empty_output(self):
        from src.git_watcher import GitWatcher

        watcher = GitWatcher(on_commit=AsyncMock())
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            hash_, msg = watcher._get_latest_commit()
            assert hash_ is None
            assert msg is None

    def test_git_failure(self):
        from src.git_watcher import GitWatcher

        watcher = GitWatcher(on_commit=AsyncMock())
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            hash_, msg = watcher._get_latest_commit()
            assert hash_ is None

    def test_exception_handled(self):
        from src.git_watcher import GitWatcher

        watcher = GitWatcher(on_commit=AsyncMock())
        with patch("subprocess.run", side_effect=OSError("not found")):
            hash_, msg = watcher._get_latest_commit()
            assert hash_ is None

    def test_no_tab_in_output(self):
        """メッセージなしのフォーマット"""
        from src.git_watcher import GitWatcher

        watcher = GitWatcher(on_commit=AsyncMock())
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc1234def5678\n",
            )
            hash_, msg = watcher._get_latest_commit()
            assert hash_ == "abc1234def5678"
            assert msg == ""


class TestBatchNotifyFormat:
    """_batch_notify のフォーマットロジックテスト"""

    async def test_single_commit_format(self):
        """1件のコミットは "hash: message" 形式"""
        from src.git_watcher import GitWatcher
        import src.git_watcher as gw

        callback = AsyncMock()
        watcher = GitWatcher(on_commit=callback)
        watcher._pending_commits = [("abc12345", "fix bug")]
        watcher._last_notify_time = 0.0

        with patch.object(gw, "_COOLDOWN", 0), patch.object(gw, "_BATCH_WAIT", 0):
            await watcher._batch_notify()

        callback.assert_called_once()
        detail = callback.call_args[0][1]
        assert "abc12345: fix bug" in detail

    async def test_multiple_commits_format(self):
        """複数コミットは件数+リスト形式"""
        from src.git_watcher import GitWatcher
        import src.git_watcher as gw

        callback = AsyncMock()
        watcher = GitWatcher(on_commit=callback)
        watcher._pending_commits = [
            ("aaa11111", "first"),
            ("bbb22222", "second"),
        ]
        watcher._last_notify_time = 0.0

        with patch.object(gw, "_COOLDOWN", 0), patch.object(gw, "_BATCH_WAIT", 0):
            await watcher._batch_notify()

        callback.assert_called_once()
        # 最後のコミットのハッシュが第1引数
        assert callback.call_args[0][0] == "bbb22222"
        detail = callback.call_args[0][1]
        assert "2件のコミット" in detail
        assert "aaa11111" in detail
        assert "bbb22222" in detail

    async def test_empty_pending_no_callback(self):
        """保留コミットが空ならコールバックは呼ばない"""
        from src.git_watcher import GitWatcher
        import src.git_watcher as gw

        callback = AsyncMock()
        watcher = GitWatcher(on_commit=callback)
        watcher._pending_commits = []
        watcher._last_notify_time = 0.0

        with patch.object(gw, "_COOLDOWN", 0), patch.object(gw, "_BATCH_WAIT", 0):
            await watcher._batch_notify()

        callback.assert_not_called()


class TestLifecycle:
    async def test_start_records_initial_hash(self):
        from src.git_watcher import GitWatcher

        callback = AsyncMock()
        watcher = GitWatcher(on_commit=callback, interval=100)

        with patch.object(watcher, "_get_latest_commit", return_value=("initial123", "init")):
            await watcher.start()

        assert watcher._last_hash == "initial123"
        assert watcher._running is True
        await watcher.stop()

    async def test_stop_cleans_up(self):
        from src.git_watcher import GitWatcher

        callback = AsyncMock()
        watcher = GitWatcher(on_commit=callback, interval=100)

        with patch.object(watcher, "_get_latest_commit", return_value=("abc", "msg")):
            await watcher.start()

        await watcher.stop()
        assert watcher._running is False
        assert watcher._task is None
        assert watcher._pending_commits == []

    async def test_start_idempotent(self):
        from src.git_watcher import GitWatcher

        callback = AsyncMock()
        watcher = GitWatcher(on_commit=callback, interval=100)

        with patch.object(watcher, "_get_latest_commit", return_value=("abc", "msg")):
            await watcher.start()
            task1 = watcher._task
            await watcher.start()  # 二重起動しない
            assert watcher._task is task1

        await watcher.stop()
