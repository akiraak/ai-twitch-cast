"""Gitコミット監視 - 新しいコミットを検知してコールバックを呼び出す"""

import asyncio
import logging
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_DIR = Path(__file__).resolve().parent.parent

# クールダウン後にまとめて通知するまでの待機時間（秒）
_BATCH_WAIT = 30
# クールダウン時間（秒）- 最後の通知からこの時間は新たな通知をしない
_COOLDOWN = 60


class GitWatcher:
    """リポジトリの新規コミットを監視する"""

    def __init__(self, on_commit, repo_dir=None, interval=10):
        """
        Args:
            on_commit: コミット検知時のコールバック async def(hash, message)
            repo_dir: 監視対象のリポジトリパス
            interval: ポーリング間隔（秒）
        """
        self._on_commit = on_commit
        self._repo_dir = str(repo_dir or _PROJECT_DIR)
        self._interval = interval
        self._last_hash = None
        self._task = None
        self._running = False
        self._last_notify_time = 0.0
        self._pending_commits = []
        self._batch_task = None

    def _get_latest_commit(self):
        """最新コミットのハッシュとメッセージを取得する"""
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%H\t%s"],
                cwd=self._repo_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("\t", 1)
                return parts[0], parts[1] if len(parts) > 1 else ""
        except Exception as e:
            logger.warning("git log 取得失敗: %s", e)
        return None, None

    async def start(self):
        """監視を開始する"""
        if self._running:
            return
        # 初期ハッシュを記録（起動時のコミットは通知しない）
        self._last_hash, _ = await asyncio.to_thread(self._get_latest_commit)
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("Git監視を開始しました (最新: %s)", self._last_hash[:8] if self._last_hash else "none")

    async def stop(self):
        """監視を停止する"""
        self._running = False
        if self._batch_task:
            self._batch_task.cancel()
            self._batch_task = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        self._pending_commits.clear()
        logger.info("Git監視を停止しました")

    async def _watch_loop(self):
        """定期的にコミットをチェックする"""
        try:
            while self._running:
                await asyncio.sleep(self._interval)
                commit_hash, message = await asyncio.to_thread(self._get_latest_commit)
                if commit_hash and commit_hash != self._last_hash:
                    self._last_hash = commit_hash
                    logger.info("新規コミット検知: %s %s", commit_hash[:8], message)
                    self._pending_commits.append((commit_hash[:8], message))
                    # バッチ通知タスクがなければ起動
                    if self._batch_task is None or self._batch_task.done():
                        self._batch_task = asyncio.create_task(self._batch_notify())
        except asyncio.CancelledError:
            pass

    async def _batch_notify(self):
        """クールダウンを待ってから溜まったコミットをまとめて通知する"""
        try:
            # クールダウン中なら残り時間を待つ
            elapsed = time.monotonic() - self._last_notify_time
            if elapsed < _COOLDOWN:
                await asyncio.sleep(_COOLDOWN - elapsed)

            # さらに少し待って連続コミットをまとめる
            await asyncio.sleep(_BATCH_WAIT)

            if not self._pending_commits:
                return

            commits = list(self._pending_commits)
            self._pending_commits.clear()
            self._last_notify_time = time.monotonic()

            if len(commits) == 1:
                hash_, msg = commits[0]
                detail = f"{hash_}: {msg}"
            else:
                lines = [f"- {h}: {m}" for h, m in commits]
                detail = f"{len(commits)}件のコミット\n" + "\n".join(lines)

            logger.info("コミット通知: %d件まとめて", len(commits))
            try:
                await self._on_commit(commits[-1][0], detail)
            except Exception as e:
                logger.error("コミット通知コールバック失敗: %s", e)
        except asyncio.CancelledError:
            pass
