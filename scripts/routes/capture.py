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
_SOURCE_FILES = ["main.js", "preload.js", "broadcast-preload.js", "capture.html", "capture-renderer.js", "package.json"]
_ASAR_PATH = _EXE_PATH.parent / "resources" / "app.asar" if _EXE_PATH.parent.exists() else _APP_DIR / "dist" / "win-unpacked" / "resources" / "app.asar"

# ビルド状態
_build_state = {
    "status": "idle",  # idle, building, done, error
    "message": "",
    "progress": 0,  # 0-100
}
_build_lock = threading.Lock()

# ビルドログファイル
_BUILD_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "build.log"


def _log_build(label, result):
    """subprocessの結果をビルドログファイルに追記する"""
    try:
        with open(_BUILD_LOG_PATH, "a", encoding="utf-8") as f:
            import datetime
            f.write(f"\n{'='*60}\n")
            f.write(f"[{datetime.datetime.now().isoformat()}] {label}\n")
            f.write(f"returncode: {result.returncode}\n")
            if result.stdout:
                f.write(f"--- stdout ---\n{result.stdout}\n")
            if result.stderr:
                f.write(f"--- stderr ---\n{result.stderr}\n")
    except Exception:
        pass


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
    """dist/内のroot所有ファイルを修正。chown不可ならPowerShellでdist削除"""
    dist_dir = _APP_DIR / "dist"
    if not dist_dir.exists():
        return
    try:
        # root所有ファイルがあるか確認
        result = subprocess.run(
            ["find", str(dist_dir), "-user", "root", "-maxdepth", "3", "-print", "-quit"],
            capture_output=True, text=True, timeout=10,
        )
        if not result.stdout.strip():
            return  # root所有ファイルなし

        # まずchownを試す
        result = subprocess.run(
            ["find", str(dist_dir), "-user", "root", "-exec", "chown", "ubuntu:ubuntu", "{}", "+"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            logger.info("dist権限修正完了（chown）")
            return

        # chown失敗 → WSL2ではPowerShellでdist削除
        logger.warning("chown失敗、PowerShellでdist削除を試行")
        if is_wsl():
            win_path = to_windows_path(str(dist_dir))
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command",
                 f"Remove-Item -Path '{win_path}' -Recurse -Force"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                logger.info("dist削除完了（PowerShell）")
            else:
                logger.error("dist削除失敗: %s", result.stderr[:200])
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
            _log_build("asar extract", result)
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
            _log_build("asar pack", result)
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

        # 権限修正（前回ビルドのroot所有ファイルを修正）
        _fix_dist_permissions()

        result = subprocess.run(
            ["npm", "install"],
            cwd=str(_APP_DIR),
            capture_output=True, text=True, timeout=120,
        )
        _log_build("npm install", result)
        if result.returncode != 0:
            _build_state = {"status": "error", "message": f"npm install失敗: {result.stderr[:200]}", "progress": 0}
            logger.error("npm install失敗: %s", result.stderr[:500])
            return

        _build_state = {"status": "building", "message": "FFmpegダウンロード中...", "progress": 30}
        result = subprocess.run(
            ["bash", "scripts/download-ffmpeg.sh"],
            cwd=str(_APP_DIR),
            capture_output=True, text=True, timeout=300,
        )
        _log_build("download-ffmpeg", result)
        if result.returncode != 0:
            logger.warning("FFmpegダウンロード失敗（配信機能なしで続行）: %s", result.stderr[:200])

        _build_state = {"status": "building", "message": "electron-builder ...", "progress": 50}

        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(_APP_DIR),
            capture_output=True, text=True, timeout=300,
        )
        _log_build("npm run build", result)
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


def _capture_ws_url():
    """キャプチャサーバーの制御WebSocket URLを返す"""
    try:
        host = get_windows_host_ip()
    except Exception:
        host = "localhost"
    return f"ws://{host}:{CAPTURE_PORT}/ws/control"


# WebSocketクライアント（Electron制御用）
_capture_ws = None
_capture_ws_lock = asyncio.Lock()
_pending_requests: dict[str, asyncio.Future] = {}
_ws_reader_task = None


async def _ensure_capture_ws():
    """Electronへの制御WebSocket接続を確保する"""
    global _capture_ws, _ws_reader_task
    import websockets

    if _capture_ws is not None:
        try:
            await _capture_ws.ping()
            return _capture_ws
        except Exception:
            _capture_ws = None

    url = _capture_ws_url()
    _capture_ws = await websockets.connect(url, close_timeout=2)
    _ws_reader_task = asyncio.create_task(_read_capture_ws())
    logger.info("Electron制御WebSocket接続: %s", url)
    return _capture_ws


async def _read_capture_ws():
    """WebSocketからのレスポンスを読み取り、pendingリクエストを解決する"""
    global _capture_ws
    try:
        async for msg in _capture_ws:
            data = json.loads(msg)
            rid = data.get("requestId")
            if rid and rid in _pending_requests:
                _pending_requests[rid].set_result(data)
    except Exception:
        pass
    finally:
        _capture_ws = None
        for fut in _pending_requests.values():
            if not fut.done():
                fut.set_exception(ConnectionError("WebSocket closed"))
        _pending_requests.clear()


async def _ws_request(action, timeout=5.0, **params):
    """WebSocket経由でElectronにコマンドを送信し、レスポンスを待つ"""
    async with _capture_ws_lock:
        ws = await _ensure_capture_ws()
    rid = hashlib.md5(f"{action}{time.time()}".encode()).hexdigest()[:8]
    fut = asyncio.get_event_loop().create_future()
    _pending_requests[rid] = fut
    try:
        await ws.send(json.dumps({"requestId": rid, "action": action, **params}))
        result = await asyncio.wait_for(fut, timeout=timeout)
        # 配列レスポンスは data フィールドに入る
        return result.get("data", result)
    finally:
        _pending_requests.pop(rid, None)


# HTTP method+path → WebSocket action マッピング
_PATH_TO_ACTION = {
    ("GET", "/status"): ("status", {}),
    ("GET", "/windows"): ("windows", {}),
    ("GET", "/captures"): ("captures", {}),
    ("GET", "/preview/status"): ("preview_status", {}),
    ("POST", "/preview/close"): ("preview_close", {}),
    ("POST", "/quit"): ("quit", {}),
    ("POST", "/stream/stop"): ("stop_stream", {}),
    ("GET", "/stream/status"): ("stream_status", {}),
    ("POST", "/broadcast/close"): ("broadcast_close", {}),
    ("GET", "/broadcast/status"): ("broadcast_status", {}),
}


async def _proxy_request(method, path, body=None):
    """キャプチャサーバーへリクエスト（WebSocket優先→HTTPフォールバック）"""
    # WebSocket経由を試行
    try:
        key = (method, path)
        if key in _PATH_TO_ACTION:
            action, _ = _PATH_TO_ACTION[key]
            return await _ws_request(action, **(body or {}))
        elif method == "POST" and path == "/capture":
            return await _ws_request("start_capture", **(body or {}))
        elif method == "DELETE" and path.startswith("/capture/"):
            cap_id = path.split("/capture/")[1]
            return await _ws_request("stop_capture", id=cap_id)
        elif method == "POST" and path == "/preview/open":
            return await _ws_request("preview_open", **(body or {}))
    except Exception as e:
        logger.debug("WebSocket制御失敗、HTTPフォールバック: %s", e)

    # HTTPフォールバック
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


@router.get("/api/capture/build-log")
async def capture_build_log():
    """ビルドログの末尾を返す（デバッグ用）"""
    if not _BUILD_LOG_PATH.exists():
        return {"log": "(ログなし)"}
    text = _BUILD_LOG_PATH.read_text(encoding="utf-8", errors="replace")
    # 末尾5000文字を返す
    return {"log": text[-5000:] if len(text) > 5000 else text}


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
        # WSL2→WindowsではPythonのshutil.copy/copy2/unlinkが
        # Operation not permittedになるため、PowerShellでコピーする
        if is_wsl():
            win_src = to_windows_path(str(src_asar))
            win_dst = to_windows_path(str(dst_asar))
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command",
                 f"Copy-Item -Path '{win_src}' -Destination '{win_dst}' -Force"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                raise RuntimeError(f"PowerShellコピー失敗: {result.stderr[:200]}")
        else:
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
            # 権限修正（前回ビルドのroot所有ファイルを修正）
            _fix_dist_permissions()

            # ---- Stage: npm_install ----
            _update_oneclick("npm_install", "npm install ...", 10, done, skipped)
            result = subprocess.run(
                ["npm", "install"], cwd=str(_APP_DIR),
                capture_output=True, text=True, timeout=120,
            )
            _log_build("oneclick: npm install", result)
            if result.returncode != 0:
                _oneclick_state = {"status": "error", "stage": "npm_install",
                    "message": f"npm install失敗: {result.stderr[:200]}",
                    "progress": 0, "stages_done": done, "stages_skipped": skipped}
                return
            done.append("npm_install")

            # ---- Stage: download_ffmpeg ----
            _update_oneclick("download_ffmpeg", "FFmpegダウンロード中...", 15, done, skipped)
            result = subprocess.run(
                ["bash", "scripts/download-ffmpeg.sh"], cwd=str(_APP_DIR),
                capture_output=True, text=True, timeout=300,
            )
            _log_build("oneclick: download-ffmpeg", result)
            if result.returncode != 0:
                logger.warning("FFmpegダウンロード失敗（配信機能なしで続行）: %s", result.stderr[:200])
            done.append("download_ffmpeg")

            # ---- Stage: build ----
            _update_oneclick("build", "electron-builder ...", 20, done, skipped)
            result = subprocess.run(
                ["npm", "run", "build"], cwd=str(_APP_DIR),
                capture_output=True, text=True, timeout=300,
            )
            _log_build("oneclick: npm run build", result)
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


# =====================================================
# Electron配信ストリーミング制御
# =====================================================


class StreamStartRequest(BaseModel):
    stream_key: str | None = None
    resolution: str = "1920x1080"
    framerate: int = 30
    video_bitrate: str = "3500k"
    audio_bitrate: str = "128k"
    preset: str = "ultrafast"


@router.post("/api/capture/stream/start")
async def capture_stream_start(body: StreamStartRequest):
    """Electron経由でTwitch配信を開始"""
    stream_key = body.stream_key or os.environ.get("TWITCH_STREAM_KEY", "")
    if not stream_key:
        raise HTTPException(
            status_code=400,
            detail="TWITCH_STREAM_KEY が設定されていません",
        )

    web_port = os.environ.get("WEB_PORT", "8080")
    server_url = f"http://{get_windows_host_ip()}:{web_port}"

    try:
        result = await _ws_request(
            "start_stream",
            streamKey=stream_key,
            serverUrl=server_url,
            resolution=body.resolution,
            framerate=body.framerate,
            videoBitrate=body.video_bitrate,
            audioBitrate=body.audio_bitrate,
            preset=body.preset,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/capture/stream/stop")
async def capture_stream_stop():
    """Electron経由の配信を停止"""
    try:
        result = await _ws_request("stop_stream")
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/capture/stream/status")
async def capture_stream_status():
    """Electron配信の状態を取得"""
    try:
        return await _ws_request("stream_status")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
