"""ウィンドウキャプチャルート - Windows側Electronアプリの管理"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scripts import state
from src import db
from src.wsl_path import get_windows_host_ip, to_windows_path, is_wsl

logger = logging.getLogger(__name__)
router = APIRouter()

CAPTURE_PORT = 9090
_capture_proc = None

# Electronアプリのパス
_APP_DIR = Path(__file__).resolve().parent.parent.parent / "win-capture-app"
_EXE_PATH = _APP_DIR / "dist" / "win-unpacked" / "win-capture-app.exe"

# ソースファイル（これらが更新されたらasar再パック）
_SOURCE_FILES = ["main.js", "preload.js", "capture.html", "capture-renderer.js", "package.json"]
_ASAR_PATH = _EXE_PATH.parent / "resources" / "app.asar" if _EXE_PATH.parent.exists() else _APP_DIR / "dist" / "win-unpacked" / "resources" / "app.asar"

# ビルド状態
_build_state = {
    "status": "idle",  # idle, building, done, error
    "message": "",
    "progress": 0,  # 0-100
}
_build_lock = threading.Lock()


def _needs_build():
    """exeが存在しない、またはpackage.jsonが変更された場合はフルビルドが必要"""
    if not _EXE_PATH.exists():
        return True
    pkg = _APP_DIR / "package.json"
    if not pkg.exists():
        return False
    current_hash = hashlib.md5(pkg.read_bytes()).hexdigest()
    saved_hash = db.get_setting("capture_build_hash")
    return saved_hash != current_hash


def _save_build_hash():
    """ビルド成功時にpackage.jsonのハッシュをDBに保存"""
    pkg = _APP_DIR / "package.json"
    if pkg.exists():
        current_hash = hashlib.md5(pkg.read_bytes()).hexdigest()
        db.set_setting("capture_build_hash", current_hash)


def _fix_dist_permissions():
    """dist/内のroot所有ファイルをubuntu:ubuntuに修正"""
    dist_dir = _APP_DIR / "dist"
    if not dist_dir.exists():
        return
    try:
        result = subprocess.run(
            ["find", str(dist_dir), "-user", "root", "-exec", "chown", "ubuntu:ubuntu", "{}", "+"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.warning("dist権限修正失敗: %s", result.stderr[:200])
        else:
            logger.info("dist権限修正完了")
    except Exception as e:
        logger.warning("dist権限修正エラー: %s", e)


def _needs_asar_update():
    """ソースファイルがasarより新しいかチェック"""
    asar = _EXE_PATH.parent / "resources" / "app.asar"
    if not asar.exists():
        return _EXE_PATH.exists()  # exeはあるがasarがない
    asar_mtime = asar.stat().st_mtime
    for name in _SOURCE_FILES:
        src = _APP_DIR / name
        if src.exists() and src.stat().st_mtime > asar_mtime:
            logger.info("ソース更新検知: %s", name)
            return True
    return False


def _update_asar():
    """ソースファイルをasarに再パックする（フルビルド不要）"""
    global _build_state
    if not _build_lock.acquire(blocking=False):
        return
    try:
        _build_state = {"status": "building", "message": "asar更新中...", "progress": 30}
        logger.info("asar再パック開始")

        # 権限修正: root所有ならubuntuに変更
        _fix_dist_permissions()

        import tempfile
        asar_path = _EXE_PATH.parent / "resources" / "app.asar"

        # 更新前のmtimeを記録
        old_mtime = asar_path.stat().st_mtime if asar_path.exists() else 0

        with tempfile.TemporaryDirectory() as tmp:
            # 展開
            result = subprocess.run(
                ["npx", "asar", "extract", str(asar_path), tmp],
                cwd=str(_APP_DIR),
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                _build_state = {"status": "error", "message": f"asar展開失敗: {result.stderr[:200]}", "progress": 0}
                return

            _build_state = {"status": "building", "message": "ソース更新中...", "progress": 60}

            # ソースファイルを上書き
            for name in _SOURCE_FILES:
                src = _APP_DIR / name
                if src.exists():
                    shutil.copy2(str(src), os.path.join(tmp, name))

            _build_state = {"status": "building", "message": "asar再パック中...", "progress": 80}

            # 再パック
            result = subprocess.run(
                ["npx", "asar", "pack", tmp, str(asar_path)],
                cwd=str(_APP_DIR),
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                _build_state = {"status": "error", "message": f"asarパック失敗: {result.stderr[:200]}", "progress": 0}
                return

        # 検証: ファイルが実際に更新されたか
        new_mtime = asar_path.stat().st_mtime if asar_path.exists() else 0
        if new_mtime <= old_mtime:
            _build_state = {"status": "error", "message": "asar再パック失敗: ファイルが更新されませんでした（権限問題の可能性）", "progress": 0}
            logger.error("asar再パック失敗: mtime未変更 (old=%s, new=%s)", old_mtime, new_mtime)
            return

        _build_state = {"status": "done", "message": "更新完了", "progress": 100}
        logger.info("asar再パック完了 (size=%d)", asar_path.stat().st_size)
    except Exception as e:
        _build_state = {"status": "error", "message": str(e)[:200], "progress": 0}
        logger.error("asar更新エラー: %s", e)
    finally:
        _build_lock.release()


def _run_build():
    """バックグラウンドでElectronアプリをフルビルド"""
    global _build_state
    if not _build_lock.acquire(blocking=False):
        return
    try:
        _build_state = {"status": "building", "message": "npm install ...", "progress": 10}
        logger.info("Electronアプリフルビルド開始")

        result = subprocess.run(
            ["npm", "install"],
            cwd=str(_APP_DIR),
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            _build_state = {"status": "error", "message": f"npm install失敗: {result.stderr[:200]}", "progress": 0}
            logger.error("npm install失敗: %s", result.stderr[:500])
            return

        _build_state = {"status": "building", "message": "electron-builder ...", "progress": 50}

        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(_APP_DIR),
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0 and not _EXE_PATH.exists():
            err_detail = (result.stderr or result.stdout or "")[:200]
            _build_state = {"status": "error", "message": f"ビルド失敗: {err_detail}", "progress": 0}
            logger.error("electron-builder失敗: %s", err_detail)
            return
        if result.returncode != 0:
            logger.warning("electron-builder警告（exe生成済み）: %s", (result.stderr or result.stdout or "")[:200])

        _fix_dist_permissions()
        _save_build_hash()
        _build_state = {"status": "done", "message": "ビルド完了", "progress": 100}
        logger.info("Electronアプリビルド完了")
    except subprocess.TimeoutExpired:
        _build_state = {"status": "error", "message": "ビルドタイムアウト", "progress": 0}
    except Exception as e:
        _build_state = {"status": "error", "message": str(e)[:200], "progress": 0}
        logger.error("ビルドエラー: %s", e)
    finally:
        _build_lock.release()


def _capture_base_url():
    """キャプチャサーバーのベースURLを返す"""
    try:
        host = get_windows_host_ip()
    except Exception:
        host = "localhost"
    return f"http://{host}:{CAPTURE_PORT}"


async def _proxy_request(method, path, body=None):
    """キャプチャサーバーへHTTPリクエストをプロキシする"""
    import httpx

    url = f"{_capture_base_url()}{path}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        if method == "GET":
            resp = await client.get(url)
        elif method == "POST":
            resp = await client.post(url, json=body)
        elif method == "DELETE":
            resp = await client.delete(url)
        else:
            raise ValueError(f"Unknown method: {method}")
        return resp.json()


# =====================================================
# サーバー管理
# =====================================================


@router.get("/api/capture/status")
async def capture_status():
    """キャプチャサーバーの状態を返す（ビルド状態含む）"""
    result = {"build": dict(_build_state)}
    try:
        data = await _proxy_request("GET", "/status")
        result.update({"running": True, **data})
    except Exception:
        result["running"] = False
    return result


@router.post("/api/capture/build")
async def capture_build():
    """Electronアプリのビルドを手動トリガー"""
    if _build_state["status"] == "building":
        return {"ok": True, "message": "既にビルド中", "build": dict(_build_state)}
    if not _APP_DIR.exists():
        raise HTTPException(status_code=404, detail=f"win-capture-appディレクトリが見つかりません: {_APP_DIR}")
    threading.Thread(target=_run_build, daemon=True).start()
    return {"ok": True, "message": "ビルド開始", "build": dict(_build_state)}


def _deploy_to_windows():
    """Windowsローカルディスクにデプロイ（WSL環境用）。デプロイしたexeのパスを返す"""
    win_deploy_dir = Path("/mnt/c/Users") / os.environ.get("WIN_USER", "akira") / "AppData" / "Local" / "ai-twitch-cast-capture"
    dst_exe = win_deploy_dir / "win-capture-app.exe"
    src_asar = _EXE_PATH.parent / "resources" / "app.asar"
    dst_asar = win_deploy_dir / "resources" / "app.asar"

    if not dst_exe.exists():
        # 初回: 全ファイルコピー
        logger.info("Electronアプリを初回デプロイ中...")
        win_deploy_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(_EXE_PATH.parent), str(win_deploy_dir), dirs_exist_ok=True)
        if not dst_asar.exists():
            raise RuntimeError(f"デプロイ後にasarが見つかりません: {dst_asar}")
        logger.info("初回デプロイ完了: %s", win_deploy_dir)
    elif src_asar.exists():
        # 更新: asarファイルを毎回コピー（mtime比較なし＝確実にデプロイ）
        logger.info("asarデプロイ中...")
        dst_asar.parent.mkdir(parents=True, exist_ok=True)
        # WSL2→Windowsでは既存ファイルへの上書きがPermissionErrorになる場合がある
        # 削除してからコピーすることで回避
        if dst_asar.exists():
            dst_asar.unlink()
        shutil.copy(str(src_asar), str(dst_asar))
        logger.info("asarデプロイ完了 (size=%d)", dst_asar.stat().st_size)

    return dst_exe


def _launch_electron():
    """Electronアプリを起動してプロセスを返す"""
    global _capture_proc
    if is_wsl():
        dst_exe = _deploy_to_windows()
        win_exe = to_windows_path(str(dst_exe))
        _capture_proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{win_exe}'"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        _capture_proc = subprocess.Popen(
            [str(_EXE_PATH)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return _capture_proc


async def _wait_for_server(timeout=10):
    """キャプチャサーバーの応答を待つ。成功ならTrue"""
    for _ in range(timeout * 2):
        await asyncio.sleep(0.5)
        try:
            st = await capture_status()
            if st.get("running"):
                return True
        except Exception:
            pass
    return False


@router.post("/api/capture/launch")
async def capture_launch():
    """Electronキャプチャアプリを起動する（必要ならビルドも実行）"""
    # 既に起動中か確認
    st = await capture_status()
    if st.get("running"):
        return {"ok": True, "message": "既に起動中"}

    # フルビルドが必要か確認
    if _needs_build():
        if _build_state["status"] == "building":
            return {"ok": False, "error": "ビルド中です。完了後に再度起動してください。", "build": dict(_build_state)}
        threading.Thread(target=_run_build, daemon=True).start()
        return {"ok": False, "error": "ビルドを開始しました。完了後に再度起動してください。", "build": dict(_build_state)}

    # ソース更新時はasar再パック（高速なので同期実行）
    if _needs_asar_update():
        _update_asar()
        if _build_state["status"] == "error":
            return {"ok": False, "error": _build_state["message"], "build": dict(_build_state)}

    if not _EXE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"ビルド済みexeが見つかりません: {_EXE_PATH}",
        )

    try:
        _launch_electron()

        if await _wait_for_server(timeout=10):
            logger.info("キャプチャサーバー起動成功")
            return {"ok": True}

        return {"ok": False, "error": "起動タイムアウト"}
    except Exception as e:
        logger.error("キャプチャサーバー起動失敗: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/capture/shutdown")
async def capture_shutdown():
    """キャプチャサーバーを停止する"""
    global _capture_proc
    if _capture_proc:
        try:
            _capture_proc.terminate()
        except Exception:
            pass
        _capture_proc = None
    return {"ok": True}


# =====================================================
# ワンクリックプレビュー
# =====================================================

_oneclick_state = {
    "status": "idle",       # idle | running | done | error
    "stage": "",
    "message": "",
    "progress": 0,
    "stages_done": [],
    "stages_skipped": [],
}
_oneclick_lock = threading.Lock()


def _update_oneclick(stage, message, progress, done=None, skipped=None):
    """ワンクリック状態を更新"""
    global _oneclick_state
    _oneclick_state = {
        "status": "running",
        "stage": stage,
        "message": message,
        "progress": progress,
        "stages_done": (done or [])[:],
        "stages_skipped": (skipped or [])[:],
    }


def _run_preview_oneclick():
    """ワンクリックプレビューをバックグラウンドで実行"""
    global _oneclick_state
    if not _oneclick_lock.acquire(blocking=False):
        return
    try:
        done = []
        skipped = []

        # ---- Stage: check_build ----
        _update_oneclick("check_build", "ビルド状態を確認中...", 5, done, skipped)
        if _needs_build():
            # ---- Stage: npm_install ----
            _update_oneclick("npm_install", "npm install ...", 10, done, skipped)
            result = subprocess.run(
                ["npm", "install"], cwd=str(_APP_DIR),
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                _oneclick_state = {"status": "error", "stage": "npm_install",
                    "message": f"npm install失敗: {result.stderr[:200]}",
                    "progress": 0, "stages_done": done, "stages_skipped": skipped}
                return
            done.append("npm_install")

            # ---- Stage: build ----
            _update_oneclick("build", "electron-builder ...", 20, done, skipped)
            result = subprocess.run(
                ["npm", "run", "build"], cwd=str(_APP_DIR),
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0 and not _EXE_PATH.exists():
                err_detail = (result.stderr or result.stdout or "")[:200]
                _oneclick_state = {"status": "error", "stage": "build",
                    "message": f"ビルド失敗: {err_detail}",
                    "progress": 0, "stages_done": done, "stages_skipped": skipped}
                return
            if result.returncode != 0:
                logger.warning("electron-builder警告（exe生成済み）: %s", (result.stderr or result.stdout or "")[:200])
            _fix_dist_permissions()
            _save_build_hash()
            done.append("build")
        else:
            skipped.append("npm_install")
            skipped.append("build")
        done.append("check_build")

        # ---- Stage: update_asar（毎回実行） ----
        _update_oneclick("update_asar", "asar更新中...", 50, done, skipped)
        _update_asar()
        if _build_state["status"] == "error":
            _oneclick_state = {"status": "error", "stage": "update_asar",
                "message": _build_state["message"],
                "progress": 0, "stages_done": done, "stages_skipped": skipped}
            return
        if _build_state["status"] != "done":
            # ロック競合等でasar更新がスキップされた場合
            _oneclick_state = {"status": "error", "stage": "update_asar",
                "message": "asar更新がスキップされました（別プロセスがビルド中の可能性）",
                "progress": 0, "stages_done": done, "stages_skipped": skipped}
            return
        done.append("update_asar")

        if not _EXE_PATH.exists():
            _oneclick_state = {"status": "error", "stage": "check_build",
                "message": f"exeが見つかりません: {_EXE_PATH}",
                "progress": 0, "stages_done": done, "stages_skipped": skipped}
            return

        # ---- Stage: stop（起動中なら停止） ----
        import httpx
        server_running = False
        try:
            resp = httpx.get(f"{_capture_base_url()}/status", timeout=2.0)
            server_running = resp.status_code == 200
        except Exception:
            pass

        if server_running:
            _update_oneclick("stop", "アプリ停止中...", 58, done, skipped)
            try:
                httpx.post(f"{_capture_base_url()}/quit", timeout=3.0)
                time.sleep(2)
            except Exception:
                pass
            global _capture_proc
            if _capture_proc:
                try:
                    _capture_proc.terminate()
                except Exception:
                    pass
                _capture_proc = None
            if is_wsl():
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command",
                     "Stop-Process -Name 'win-capture-app' -Force -ErrorAction SilentlyContinue"],
                    capture_output=True, timeout=5,
                )
            for _ in range(10):
                time.sleep(0.5)
                try:
                    httpx.get(f"{_capture_base_url()}/status", timeout=1.0)
                except Exception:
                    break
            done.append("stop")
        else:
            skipped.append("stop")

        # ---- Stage: deploy（毎回実行） ----
        _update_oneclick("deploy", "Windowsにデプロイ中...", 65, done, skipped)
        try:
            if is_wsl():
                _deploy_to_windows()
            else:
                skipped.append("deploy")
            done.append("deploy")
        except Exception as e:
            _oneclick_state = {"status": "error", "stage": "deploy",
                "message": f"デプロイ失敗: {e}",
                "progress": 0, "stages_done": done, "stages_skipped": skipped}
            return

        # ---- Stage: launch ----
        _update_oneclick("launch", "Electronアプリ起動中...", 75, done, skipped)
        try:
            _launch_electron()
            done.append("launch")
        except Exception as e:
            _oneclick_state = {"status": "error", "stage": "launch",
                "message": f"起動失敗: {e}",
                "progress": 0, "stages_done": done, "stages_skipped": skipped}
            return

        # ---- Stage: wait_server ----
        _update_oneclick("wait_server", "サーバー応答待ち...", 80, done, skipped)
        server_running = False
        for i in range(30):  # 15秒
            time.sleep(0.5)
            try:
                resp = httpx.get(f"{_capture_base_url()}/status", timeout=2.0)
                if resp.status_code == 200:
                    server_running = True
                    break
            except Exception:
                pass
            _update_oneclick("wait_server", f"サーバー応答待ち... ({i+1}/30)", 80 + i * 0.3, done, skipped)

        if not server_running:
            _oneclick_state = {"status": "error", "stage": "wait_server",
                "message": "サーバー起動タイムアウト",
                "progress": 0, "stages_done": done, "stages_skipped": skipped}
            return
        done.append("wait_server")

        # ---- Stage: open_preview ----
        _update_oneclick("open_preview", "プレビューを開いています...", 92, done, skipped)
        try:
            web_port = os.environ.get("WEB_PORT", "8080")
            from src.wsl_path import get_wsl_ip
            wsl_ip = get_wsl_ip()
            server_url = f"http://{wsl_ip}:{web_port}"
            resp = httpx.post(
                f"{_capture_base_url()}/preview/open",
                json={"serverUrl": server_url},
                timeout=5.0,
            )
            if resp.status_code != 200:
                _oneclick_state = {"status": "error", "stage": "open_preview",
                    "message": f"プレビューを開けません: HTTP {resp.status_code}",
                    "progress": 0, "stages_done": done, "stages_skipped": skipped}
                return
            done.append("open_preview")
        except Exception as e:
            _oneclick_state = {"status": "error", "stage": "open_preview",
                "message": f"プレビューを開けません: {e}",
                "progress": 0, "stages_done": done, "stages_skipped": skipped}
            return

        # ---- 完了 ----
        _oneclick_state = {
            "status": "done",
            "stage": "done",
            "message": "プレビュー起動完了",
            "progress": 100,
            "stages_done": done,
            "stages_skipped": skipped,
        }
        logger.info("ワンクリックプレビュー完了: done=%s, skipped=%s", done, skipped)

    except Exception as e:
        _oneclick_state = {"status": "error", "stage": _oneclick_state.get("stage", ""),
            "message": str(e)[:200], "progress": 0,
            "stages_done": _oneclick_state.get("stages_done", []),
            "stages_skipped": _oneclick_state.get("stages_skipped", [])}
        logger.error("ワンクリックプレビューエラー: %s", e)
    finally:
        _oneclick_lock.release()


@router.post("/api/capture/preview-oneclick")
async def capture_preview_oneclick():
    """ワンクリックでビルド→デプロイ→起動→プレビューを実行"""
    global _oneclick_state
    if _oneclick_state.get("status") == "running":
        return {"ok": False, "message": "既に実行中", "state": dict(_oneclick_state)}
    _oneclick_state = {"status": "running", "stage": "", "message": "開始...", "progress": 0, "stages_done": [], "stages_skipped": []}
    threading.Thread(target=_run_preview_oneclick, daemon=True).start()
    return {"ok": True, "message": "プレビュー起動開始"}


@router.get("/api/capture/preview-oneclick/status")
async def capture_preview_oneclick_status():
    """ワンクリックプレビューの進捗状態を返す"""
    return dict(_oneclick_state)


# =====================================================
# プレビューウィンドウ
# =====================================================


@router.get("/api/capture/preview/status")
async def capture_preview_status():
    """プレビューウィンドウの開閉状態を返す"""
    try:
        data = await _proxy_request("GET", "/preview/status")
        return data
    except Exception:
        return {"open": False}


@router.post("/api/capture/preview")
async def capture_preview_open():
    """Electronアプリで配信プレビュー+レイアウト編集ウィンドウを開く"""
    from src.wsl_path import get_wsl_ip
    web_port = os.environ.get("WEB_PORT", "8080")
    wsl_ip = get_wsl_ip()
    server_url = f"http://{wsl_ip}:{web_port}"
    try:
        data = await _proxy_request("POST", "/preview/open", {"serverUrl": server_url})
        return {"ok": True, **data}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Electronアプリに接続できません: {e}")


@router.post("/api/capture/preview/close")
async def capture_preview_close():
    """プレビューウィンドウを閉じる"""
    try:
        await _proxy_request("POST", "/preview/close")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# =====================================================
# ウィンドウ操作
# =====================================================


@router.get("/api/capture/windows")
async def capture_windows():
    """Windows側のウィンドウ一覧を取得"""
    try:
        return await _proxy_request("GET", "/windows")
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"キャプチャサーバーに接続できません: {e}"
        )


# =====================================================
# キャプチャ操作
# =====================================================


class CaptureStartRequest(BaseModel):
    sourceId: str
    id: str | None = None
    label: str | None = None
    fps: int | None = None
    quality: float | None = None


@router.post("/api/capture/start")
async def capture_start(body: CaptureStartRequest):
    """ウィンドウキャプチャを開始"""
    try:
        req_body = {"sourceId": body.sourceId}
        if body.id:
            req_body["id"] = body.id
        if body.fps:
            req_body["fps"] = body.fps
        if body.quality:
            req_body["quality"] = body.quality
        data = await _proxy_request("POST", "/capture", req_body)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not data.get("ok"):
        raise HTTPException(status_code=400, detail=data.get("error", "unknown"))

    cid = data["id"]
    stream_url = f"{_capture_base_url()}/stream/{cid}"
    layout = {
        "x": 5,
        "y": 10,
        "width": 40,
        "height": 50,
        "zIndex": 10,
        "visible": True,
    }

    label = body.label or data.get("name", "")

    # DBにレイアウト保存
    _save_capture_layout(cid, layout, label)

    # broadcast.htmlに通知
    await state.broadcast_to_broadcast(
        {
            "type": "capture_add",
            "id": cid,
            "stream_url": stream_url,
            "label": label,
            "layout": layout,
        }
    )

    return {"ok": True, "id": cid, "stream_url": stream_url}


@router.delete("/api/capture/{capture_id}")
async def capture_stop(capture_id: str):
    """キャプチャを停止"""
    try:
        await _proxy_request("DELETE", f"/capture/{capture_id}")
    except Exception:
        pass

    _remove_capture_layout(capture_id)

    await state.broadcast_to_broadcast(
        {"type": "capture_remove", "id": capture_id}
    )
    return {"ok": True}


@router.get("/api/capture/sources")
async def capture_sources():
    """アクティブなキャプチャソース一覧（レイアウト情報付き）"""
    try:
        captures = await _proxy_request("GET", "/captures")
    except Exception:
        captures = []

    # DB保存のレイアウト情報をマージ
    saved = {s["id"]: s for s in _load_capture_sources()}

    result = []
    for c in captures:
        cid = c["id"]
        info = saved.get(cid, {})
        layout = info.get(
            "layout",
            {
                "x": 5,
                "y": 10,
                "width": 40,
                "height": 50,
                "zIndex": 10,
                "visible": True,
            },
        )
        result.append(
            {
                **c,
                "label": info.get("label", c.get("name", cid)),
                "stream_url": f"{_capture_base_url()}/stream/{cid}",
                "layout": layout,
            }
        )
    return result


class CaptureLayoutRequest(BaseModel):
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    zIndex: int | None = None
    visible: bool | None = None


@router.post("/api/capture/{capture_id}/layout")
async def capture_update_layout(capture_id: str, body: CaptureLayoutRequest):
    """キャプチャのレイアウトを更新"""
    layout_update = {k: v for k, v in body.model_dump().items() if v is not None}

    _update_capture_layout(capture_id, layout_update)

    await state.broadcast_to_broadcast(
        {"type": "capture_layout", "id": capture_id, "layout": layout_update}
    )
    return {"ok": True}


# =====================================================
# DB管理（キャプチャレイアウト）
# =====================================================


def _load_capture_sources():
    raw = db.get_setting("capture.sources")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return []


def _save_capture_sources(sources):
    db.set_setting("capture.sources", json.dumps(sources, ensure_ascii=False))


def _save_capture_layout(capture_id, layout, label=""):
    sources = _load_capture_sources()
    for s in sources:
        if s["id"] == capture_id:
            s["layout"] = layout
            s["label"] = label
            _save_capture_sources(sources)
            return
    sources.append({"id": capture_id, "label": label, "layout": layout})
    _save_capture_sources(sources)


def _update_capture_layout(capture_id, layout_update):
    sources = _load_capture_sources()
    for s in sources:
        if s["id"] == capture_id:
            s.setdefault("layout", {}).update(layout_update)
            _save_capture_sources(sources)
            return


def _remove_capture_layout(capture_id):
    sources = _load_capture_sources()
    sources = [s for s in sources if s["id"] != capture_id]
    _save_capture_sources(sources)
