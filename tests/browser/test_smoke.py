"""Smoke Test — Playwright ブラウザテストの基本動作確認"""

import pytest


pytestmark = pytest.mark.browser


def test_index_loads(page, base_url):
    """管理画面が読み込める"""
    page.goto(f"{base_url}/")
    assert page.title() == "AI Twitch Cast"
    # タブUIが表示される
    page.wait_for_selector(".tabs", timeout=5000)


def test_broadcast_loads(page, base_url):
    """配信ページが読み込める（トークン認証経由）"""
    # broadcast.htmlはトークン認証必須
    token_resp = page.request.get(f"{base_url}/api/broadcast/token")
    token = token_resp.json()["token"]
    page.goto(f"{base_url}/broadcast?token={token}", wait_until="domcontentloaded")
    assert "Broadcast" in page.title()
    # 主要要素が存在する
    page.wait_for_selector("#todo-panel", timeout=5000)


def test_api_status(page, base_url):
    """APIが応答する"""
    resp = page.request.get(f"{base_url}/api/status")
    assert resp.ok
    data = resp.json()
    assert "version" in data
