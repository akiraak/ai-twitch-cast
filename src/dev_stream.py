"""外部Gitリポジトリの管理・監視・開発実況"""

import asyncio
import logging
import re
import shutil
import subprocess
from pathlib import Path

from src import db

logger = logging.getLogger(__name__)

_PROJECT_DIR = Path(__file__).resolve().parent.parent
_REPOS_DIR = _PROJECT_DIR / "repos"
_MAX_REPOS = 10
_MAX_DIFF_CHARS = 500


def _parse_repo_name(url: str) -> str:
    """URLからowner/repo形式の名前を抽出する"""
    # https://github.com/owner/repo.git or git@github.com:owner/repo.git
    m = re.search(r"[/:]([^/:]+/[^/:]+?)(?:\.git)?$", url)
    if m:
        return m.group(1)
    raise ValueError(f"リポジトリ名を抽出できません: {url}")


def _run_git(args: list[str], cwd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """git コマンドを実行する"""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class DevStreamManager:
    """外部Gitリポジトリの管理・監視・実況"""

    def __init__(self, on_event=None):
        """
        Args:
            on_event: async def(repo_name, commits_info) — コミット検知コールバック
        """
        self._on_event = on_event
        self._running = False
        self._task = None
        self._poll_interval = 60  # 秒

    async def add_repo(self, url: str, branch: str = "main") -> dict:
        """リポジトリをcloneしてDBに登録する

        Returns:
            dict: 登録されたリポジトリ情報
        Raises:
            ValueError: URL不正、上限超過、clone失敗
        """
        # リポジトリ数上限チェック
        existing = db.get_dev_repos()
        if len(existing) >= _MAX_REPOS:
            raise ValueError(f"リポジトリ数の上限（{_MAX_REPOS}）に達しています")

        name = _parse_repo_name(url)
        local_path = str(_REPOS_DIR / name.replace("/", "-"))

        # clone（shallow）
        _REPOS_DIR.mkdir(parents=True, exist_ok=True)
        result = await asyncio.to_thread(
            _run_git,
            ["clone", "--depth", "100", "--branch", branch, url, local_path],
            cwd=str(_PROJECT_DIR),
            timeout=120,
        )
        if result.returncode != 0:
            raise ValueError(f"git clone 失敗: {result.stderr.strip()}")

        # 最新コミットハッシュを取得
        head = await asyncio.to_thread(
            _run_git, ["rev-parse", "HEAD"], cwd=local_path
        )
        last_hash = head.stdout.strip() if head.returncode == 0 else None

        # DB登録
        repo = db.add_dev_repo(name, url, local_path, branch)
        if last_hash:
            db.update_dev_repo_commit(repo["id"], last_hash)
            repo["last_commit_hash"] = last_hash

        logger.info("リポジトリ追加: %s (%s)", name, last_hash[:8] if last_hash else "none")
        return repo

    async def remove_repo(self, repo_id: int):
        """リポジトリを削除する（ローカルファイルも削除）"""
        repo = db.get_dev_repo(repo_id)
        if not repo:
            return
        # ローカルファイル削除
        local_path = Path(repo["local_path"])
        if local_path.exists():
            await asyncio.to_thread(shutil.rmtree, str(local_path), True)
            logger.info("ローカルリポジトリ削除: %s", local_path)
        db.delete_dev_repo(repo_id)
        logger.info("リポジトリ削除: %s (id=%d)", repo["name"], repo_id)

    async def check_repo(self, repo_id: int) -> list[dict]:
        """指定リポジトリを手動チェックし、新コミットがあれば返す"""
        repo = db.get_dev_repo(repo_id)
        if not repo:
            return []
        return await self._fetch_and_check(repo)

    async def start(self):
        """全activeリポジトリの監視を開始する"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("開発リポジトリ監視を開始 (間隔: %d秒)", self._poll_interval)

    async def stop(self):
        """監視を停止する"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("開発リポジトリ監視を停止")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _watch_loop(self):
        """定期的にfetchして新コミットを検出する"""
        try:
            while self._running:
                await asyncio.sleep(self._poll_interval)
                repos = db.get_active_dev_repos()
                for repo in repos:
                    try:
                        commits = await self._fetch_and_check(repo)
                        if commits and self._on_event:
                            try:
                                await self._on_event(repo["name"], commits)
                            except Exception as e:
                                logger.error("コールバック失敗 (%s): %s", repo["name"], e)
                    except Exception as e:
                        logger.warning("リポジトリチェック失敗 (%s): %s", repo["name"], e)
        except asyncio.CancelledError:
            pass

    async def _fetch_and_check(self, repo: dict) -> list[dict]:
        """リポジトリをfetchし、新コミットを検出・分析する"""
        local_path = repo["local_path"]
        branch = repo["branch"]

        if not Path(local_path).exists():
            logger.warning("ローカルパスが存在しません: %s", local_path)
            return []

        # git fetch
        fetch_result = await asyncio.to_thread(
            _run_git, ["fetch", "origin"], cwd=local_path
        )
        if fetch_result.returncode != 0:
            logger.warning("git fetch 失敗 (%s): %s", repo["name"], fetch_result.stderr.strip())
            return []

        # 新コミット検出
        old_hash = repo["last_commit_hash"]
        new_ref = f"origin/{branch}"

        if old_hash:
            log_range = f"{old_hash}..{new_ref}"
        else:
            # 初回は最新1件だけ
            log_range = f"{new_ref} -1"

        commits = await asyncio.to_thread(
            self._get_new_commits, local_path, log_range
        )

        if not commits:
            return []

        # ローカルをff-mergeで更新
        await asyncio.to_thread(
            _run_git, ["merge", "--ff-only", new_ref], cwd=local_path
        )

        # diff情報を付与
        for commit in commits:
            commit["diff_summary"] = await asyncio.to_thread(
                self._get_diff_summary, local_path, commit["hash"]
            )

        # DBのlast_commit_hashを更新
        newest_hash = commits[-1]["hash"]
        db.update_dev_repo_commit(repo["id"], newest_hash)

        logger.info("新コミット検出 (%s): %d件", repo["name"], len(commits))
        return commits

    def _get_new_commits(self, repo_path: str, log_range: str) -> list[dict]:
        """git logで新コミット一覧を取得する"""
        result = _run_git(
            ["log", log_range, "--format=%H\t%s\t%an"],
            cwd=repo_path,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            parts = line.split("\t", 2)
            if len(parts) >= 2:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "author": parts[2] if len(parts) > 2 else "",
                })
        # 古い順に並べる
        commits.reverse()
        return commits

    def _get_diff_summary(self, repo_path: str, commit_hash: str) -> str:
        """コミットの変更内容サマリを取得する"""
        # --stat でファイル一覧+統計
        stat_result = _run_git(
            ["show", "--stat", "--format=", commit_hash],
            cwd=repo_path,
        )
        stat_text = stat_result.stdout.strip() if stat_result.returncode == 0 else ""

        # diff本体（大きすぎる場合は切り詰め）
        diff_result = _run_git(
            ["diff", f"{commit_hash}~1..{commit_hash}", "--no-color"],
            cwd=repo_path,
        )
        diff_text = ""
        if diff_result.returncode == 0:
            diff_text = diff_result.stdout
            if len(diff_text) > _MAX_DIFF_CHARS:
                diff_text = diff_text[:_MAX_DIFF_CHARS] + "\n... (以下省略)"

        parts = []
        if stat_text:
            parts.append(stat_text)
        if diff_text:
            parts.append(diff_text)
        return "\n".join(parts)
