"""開発配信（外部リポジトリ監視）ルート"""

from fastapi import APIRouter

from scripts import state
from src import db

router = APIRouter()


async def _activate_repo(repo_id: int):
    """リポジトリを有効化（排他: 他を全て無効化）→ 監視開始 → TODO切替"""
    import scripts.routes.overlay as ov

    # 他を全て無効化
    for repo in db.get_dev_repos():
        if repo["id"] != repo_id:
            db.toggle_dev_repo(repo["id"], False)
    db.toggle_dev_repo(repo_id, True)

    # 監視開始
    if not state.dev_stream_manager.is_running:
        await state.dev_stream_manager.start()

    # TODO切替
    ov._todo_source = f"dev:{repo_id}"
    ov._todo_last_mtime = 0.0
    await ov.broadcast_todo()


async def _deactivate_repo(repo_id: int):
    """リポジトリを無効化 → 監視停止 → TODO を自プロジェクトに戻す"""
    import scripts.routes.overlay as ov

    db.toggle_dev_repo(repo_id, False)

    # active なリポジトリがなければ監視停止
    if not db.get_active_dev_repos():
        await state.dev_stream_manager.stop()

    # TODO を自プロジェクトに戻す
    ov._todo_source = "self"
    ov._todo_last_mtime = 0.0
    await ov.broadcast_todo()


@router.get("/api/dev-stream/repos")
async def get_repos():
    """リポジトリ一覧"""
    repos = db.get_dev_repos()
    return {"repos": repos}


@router.post("/api/dev-stream/repos")
async def add_repo(body: dict):
    """リポジトリ追加（clone）"""
    url = body.get("url", "").strip()
    if not url:
        return {"ok": False, "error": "URLが必要です"}
    branch = body.get("branch", "main").strip() or "main"
    try:
        repo = await state.dev_stream_manager.add_repo(url, branch)
        return {"ok": True, "repo": repo}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.delete("/api/dev-stream/repos/{repo_id}")
async def delete_repo(repo_id: int):
    """リポジトリ削除"""
    repo = db.get_dev_repo(repo_id)
    if repo and repo["active"]:
        await _deactivate_repo(repo_id)
    await state.dev_stream_manager.remove_repo(repo_id)
    return {"ok": True}


@router.post("/api/dev-stream/repos/{repo_id}/toggle")
async def toggle_repo(repo_id: int, body: dict):
    """有効/無効切り替え（有効は排他: 1つだけ）"""
    active = body.get("active", True)
    if active:
        await _activate_repo(repo_id)
    else:
        await _deactivate_repo(repo_id)
    return {"ok": True}


@router.post("/api/dev-stream/repos/{repo_id}/check")
async def check_repo(repo_id: int):
    """手動でpull＆チェック"""
    try:
        commits = await state.dev_stream_manager.check_repo(repo_id)
        if commits and state.dev_stream_manager._on_event:
            repo = db.get_dev_repo(repo_id)
            if repo:
                await state.dev_stream_manager._on_event(repo["name"], commits)
        return {"ok": True, "commits": len(commits)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/api/dev-stream/status")
async def get_status():
    """監視状態"""
    return {
        "running": state.dev_stream_manager.is_running,
        "active_repos": len(db.get_active_dev_repos()),
    }
