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

    db パッケージ（src/db/）のシングルトン接続をリセットし、tmp_pathにDBを作成する。
    core モジュールの実体をパッチして、全サブモジュールが同じテスト接続を使うようにする。
    テスト終了後に接続を閉じてクリーンアップ。
    """
    import src.db as db_mod
    import src.db.core as db_core

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_core, "DB_PATH", db_path)
    monkeypatch.setattr(db_core, "_conn", None)

    conn = db_mod.get_connection()
    yield db_mod

    conn.close()
    monkeypatch.setattr(db_core, "_conn", None)


@pytest.fixture
def mock_gemini(monkeypatch):
    """Gemini APIモッククライアント

    get_clientをfrom importしているモジュールすべてにパッチする。
    """
    client = MagicMock()
    client.models.generate_content.return_value.text = '{"response": "テスト応答", "emotion": "neutral", "translation": "test"}'

    getter = lambda: client
    import src.gemini_client as gc
    monkeypatch.setattr(gc, "get_client", getter)
    # from ... import get_client しているモジュールにもパッチ
    import src.ai_responder as ar
    monkeypatch.setattr(ar, "get_client", getter)
    import src.tts as tts_mod
    monkeypatch.setattr(tts_mod, "get_client", getter)
    import src.lesson_generator as lg
    monkeypatch.setattr(lg, "get_client", getter)
    from src.lesson_generator import utils as _lg_utils
    monkeypatch.setattr(_lg_utils, "get_client", getter)
    from src.lesson_generator import improver as _lg_improver
    monkeypatch.setattr(_lg_improver, "get_client", getter)
    return client


@pytest.fixture
def mock_env(monkeypatch):
    """テスト用環境変数"""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("TWITCH_TOKEN", "test-token")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("TWITCH_CHANNEL", "test-channel")
    monkeypatch.setenv("WEB_PORT", "8888")


@pytest.fixture
def api_client(test_db, mock_env, mock_gemini, monkeypatch, tmp_path):
    """FastAPI TestClient（全外部依存をモック化）"""
    from unittest.mock import AsyncMock

    # 本番TTSキャッシュへの漏洩防止（api経由のclear_tts_cacheが本番dirをrmtreeするのを防ぐ）
    import src.lesson_runner as lr
    audio_dir = tmp_path / "audio_lessons"
    audio_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(lr, "LESSON_AUDIO_DIR", audio_dir)

    import scripts.state as st
    # stateのグローバルオブジェクトをモック化
    monkeypatch.setattr(st, "broadcast_overlay", AsyncMock())
    monkeypatch.setattr(st, "broadcast_tts", AsyncMock())
    monkeypatch.setattr(st, "broadcast_bgm", AsyncMock())
    monkeypatch.setattr(st, "broadcast_se", AsyncMock())
    monkeypatch.setattr(st, "broadcast_to_broadcast", AsyncMock())

    # reader/git_watcherはモック
    from src.lesson_runner import LessonRunner
    from src.speech_pipeline import SpeechPipeline
    mock_speech = MagicMock(spec=SpeechPipeline)
    mock_speech.speak = AsyncMock()
    mock_speech.notify_overlay_end = AsyncMock()
    mock_speech.apply_emotion = MagicMock()
    mock_speech.generate_tts = AsyncMock(return_value=None)
    mock_speech.split_sentences = SpeechPipeline.split_sentences
    mock_lesson_runner = LessonRunner(speech=mock_speech, on_overlay=AsyncMock())

    mock_reader = MagicMock()
    mock_reader.is_running = False
    mock_reader.queue_size = 0
    mock_reader.lesson_runner = mock_lesson_runner
    monkeypatch.setattr(st, "reader", mock_reader)

    mock_gw = MagicMock()
    mock_gw.start = AsyncMock()
    mock_gw.stop = AsyncMock()
    monkeypatch.setattr(st, "git_watcher", mock_gw)

    monkeypatch.setattr(st, "current_episode", None)

    from scripts.web import app
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)
