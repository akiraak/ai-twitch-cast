"""ブラウザテスト用フィクスチャ — テストサーバー自動起動"""

import os
import subprocess
import time

import pytest
import requests


@pytest.fixture(scope="session")
def browser_server():
    """テスト用Webサーバーを起動（セッション全体で1回）"""
    port = 18080
    env = {
        **os.environ,
        "WEB_PORT": str(port),
        "GEMINI_API_KEY": "test-key",
        "TWITCH_TOKEN": "test-token",
        "TWITCH_CLIENT_ID": "test-client-id",
        "TWITCH_CHANNEL": "test-channel",
    }
    proc = subprocess.Popen(
        [
            "python3", "-m", "uvicorn", "scripts.web:app",
            "--host", "127.0.0.1", "--port", str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # サーバー起動待ち
    url = f"http://127.0.0.1:{port}/api/status"
    for _ in range(60):
        try:
            resp = requests.get(url, timeout=1)
            if resp.ok:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError(f"テストサーバーが起動しません: {url}")

    yield f"http://127.0.0.1:{port}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def base_url(browser_server):
    """テストサーバーのベースURL（pytest-base-url互換）"""
    return browser_server
