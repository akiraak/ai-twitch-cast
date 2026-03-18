"""開発配信（外部リポジトリ監視）ルート"""

from fastapi import APIRouter

from scripts import state
from src import db

router = APIRouter()


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
    await state.dev_stream_manager.remove_repo(repo_id)
    return {"ok": True}


@router.post("/api/dev-stream/repos/{repo_id}/toggle")
async def toggle_repo(repo_id: int, body: dict):
    """監視ON/OFF切り替え"""
    active = body.get("active", True)
    db.toggle_dev_repo(repo_id, active)
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


@router.post("/api/dev-stream/start")
async def start_watching():
    """監視開始"""
    await state.dev_stream_manager.start()
    return {"ok": True}


@router.post("/api/dev-stream/stop")
async def stop_watching():
    """監視停止"""
    await state.dev_stream_manager.stop()
    return {"ok": True}
