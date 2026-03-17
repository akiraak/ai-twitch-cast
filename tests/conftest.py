"""テスト共通設定 - 未インストール外部モジュールのスタブ + 共通フィクスチャ"""

import sys
from unittest.mock import MagicMock

import pytest

# twitchio等の外部モジュールがインストールされていない環境でも
# scripts.state → src.comment_reader → src.twitch_chat のインポートチェーンが通るようにする
_STUB_MODULES = [
    "twitchio",
    "aiohttp",
]

for mod_name in _STUB_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """隔離されたテスト用SQLite DB

    db.pyのシングルトン接続をリセットし、tmp_pathにDBを作成する。
    テスト終了後に接続を閉じてクリーンアップ。
    """
    import src.db as db_mod

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    monkeypatch.setattr(db_mod, "_conn", None)

    conn = db_mod.get_connection()
    yield db_mod

    conn.close()
    monkeypatch.setattr(db_mod, "_conn", None)


@pytest.fixture
def mock_gemini(monkeypatch):
    """Gemini APIモッククライアント

    get_clientをfrom importしているモジュールすべてにパッチする。
    """
    client = MagicMock()
    client.models.generate_content.return_value.text = '{"response": "テスト応答", "emotion": "neutral", "english": "test"}'

    getter = lambda: client
    import src.gemini_client as gc
    monkeypatch.setattr(gc, "get_client", getter)
    # from ... import get_client しているモジュールにもパッチ
    import src.ai_responder as ar
    monkeypatch.setattr(ar, "get_client", getter)
    import src.tts as tts_mod
    monkeypatch.setattr(tts_mod, "get_client", getter)
    return client


@pytest.fixture
def mock_env(monkeypatch):
    """テスト用環境変数"""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("TWITCH_TOKEN", "test-token")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("TWITCH_CHANNEL", "test-channel")
    monkeypatch.setenv("WEB_PORT", "8888")
