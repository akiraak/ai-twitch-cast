"""アバター制御API (scripts/routes/avatar.py) のテスト

avatar.py は発話・TTSテスト・会話デモ・Claude Watcher制御・チャット履歴など、
アバターに関するAPIを広くまとめたモジュール。テストは以下の方針で書く:

- `asyncio.create_task(reader.speak_event(...))` の経路は、AsyncMock の呼び出し記録が
  create_task に渡した時点で発生する性質を利用し、`assert_called_once()` で入口を検証する
- SSEやファイルI/O（会話デモ）は `_CONV_DEMO_DIR` を tmp_path に差し替えて副作用を隔離
- `state.ensure_reader` は呼び出す経路では AsyncMock 化して本番起動を回避
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestAvatarSpeak:
    """POST /api/avatar/speak"""

    def test_broadcasts_overlay_and_triggers_speak_event(self, api_client):
        import scripts.state as st
        st.reader.speak_event = AsyncMock()
        resp = api_client.post("/api/avatar/speak", json={"detail": "テスト作業"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # overlayへ current_task を通知
        st.broadcast_overlay.assert_called_once()
        event = st.broadcast_overlay.call_args.args[0]
        assert event == {"type": "current_task", "task": "テスト作業"}

        # reader.speak_event が呼び出される（AsyncMockは呼び出し時点で記録される）
        st.reader.speak_event.assert_called_once()
        args, kwargs = st.reader.speak_event.call_args
        assert args[0] == "手動"  # デフォルトevent_type
        assert args[1] == "テスト作業"
        assert kwargs.get("voice") is None

    def test_accepts_custom_event_type_and_voice(self, api_client):
        import scripts.state as st
        st.reader.speak_event = AsyncMock()
        resp = api_client.post(
            "/api/avatar/speak",
            json={"event_type": "通知", "detail": "やあ", "voice": "Leda"},
        )
        assert resp.status_code == 200
        args, kwargs = st.reader.speak_event.call_args
        assert args[0] == "通知"
        assert args[1] == "やあ"
        assert kwargs.get("voice") == "Leda"


class TestTtsTest:
    """POST /api/tts/test"""

    def test_known_pattern_uses_mapped_prompt(self, api_client):
        import scripts.state as st
        st.reader.speak_event = AsyncMock()
        resp = api_client.post("/api/tts/test", json={"pattern": "greeting"})
        assert resp.status_code == 200
        st.reader.speak_event.assert_called_once()
        args, kwargs = st.reader.speak_event.call_args
        assert args[0] == "TTSテスト"
        # デフォルト lang 設定（primary=ja, sub=en）から 日本語/English 指示が付くはず
        detail = args[1]
        assert "greeting" in detail or "short" in detail
        assert "日本語" in detail and "English" in detail
        assert kwargs.get("multi") is False

    def test_unknown_pattern_falls_back_to_random(self, api_client):
        import scripts.state as st
        st.reader.speak_event = AsyncMock()
        resp = api_client.post("/api/tts/test", json={"pattern": "unknown-pattern"})
        assert resp.status_code == 200
        # 未知patternは _TTS_PATTERNS からランダム選択
        st.reader.speak_event.assert_called_once()

    def test_sub_language_none_uses_primary_only(self, api_client, monkeypatch):
        import scripts.state as st
        import src.prompt_builder as pb
        st.reader.speak_event = AsyncMock()
        monkeypatch.setattr(pb, "_stream_lang", {"primary": "ja", "sub": "none", "mix": "low"})
        resp = api_client.post("/api/tts/test", json={"pattern": "greeting"})
        assert resp.status_code == 200
        detail = st.reader.speak_event.call_args.args[1]
        assert "Speak in 日本語" in detail
        assert "Mix" not in detail


class TestTtsTestEmotion:
    """POST /api/tts/test-emotion"""

    def test_uses_character_emotion_description(self, api_client, monkeypatch):
        import scripts.state as st
        import src.ai_responder as ar
        st.reader.speak_event = AsyncMock()
        monkeypatch.setattr(
            ar, "get_character",
            lambda: {"emotions": {"happy": "にこにこ嬉しそうに"}},
        )
        resp = api_client.post("/api/tts/test-emotion", json={"emotion": "happy"})
        assert resp.status_code == 200
        st.reader.speak_event.assert_called_once()
        args, kwargs = st.reader.speak_event.call_args
        assert args[0] == "感情テスト"
        assert "にこにこ嬉しそうに" in args[1]
        assert "happy" in args[1]
        assert kwargs.get("multi") is False

    def test_unknown_emotion_uses_emotion_name_as_description(self, api_client, monkeypatch):
        import scripts.state as st
        import src.ai_responder as ar
        st.reader.speak_event = AsyncMock()
        monkeypatch.setattr(ar, "get_character", lambda: {"emotions": {}})
        resp = api_client.post("/api/tts/test-emotion", json={"emotion": "mystery"})
        assert resp.status_code == 200
        detail = st.reader.speak_event.call_args.args[1]
        assert "mystery" in detail


class TestTtsVoiceSample:
    """POST /api/tts/voice-sample"""

    def test_calls_ensure_reader_and_passes_voice_style(self, api_client, monkeypatch):
        import scripts.state as st
        st.reader.speak_event = AsyncMock()
        st.ensure_reader = AsyncMock()
        resp = api_client.post(
            "/api/tts/voice-sample",
            json={"voice": "Leda", "style": "soft", "avatar_id": "student"},
        )
        assert resp.status_code == 200
        st.ensure_reader.assert_called_once()
        st.reader.speak_event.assert_called_once()
        args, kwargs = st.reader.speak_event.call_args
        assert args[0] == "ボイスサンプル"
        assert kwargs.get("voice") == "Leda"
        assert kwargs.get("style") == "soft"
        assert kwargs.get("avatar_id") == "student"
        assert kwargs.get("multi") is False

    def test_empty_voice_treated_as_none(self, api_client):
        import scripts.state as st
        st.reader.speak_event = AsyncMock()
        st.ensure_reader = AsyncMock()
        resp = api_client.post(
            "/api/tts/voice-sample",
            json={"voice": "", "style": "", "avatar_id": "teacher"},
        )
        assert resp.status_code == 200
        kwargs = st.reader.speak_event.call_args.kwargs
        assert kwargs.get("voice") is None
        assert kwargs.get("style") is None


class TestTtsTestMulti:
    """POST /api/tts/test-multi"""

    def test_splits_response_into_segments(self, api_client, monkeypatch):
        import scripts.state as st
        import src.ai_responder as ar
        st.reader._speak_segment = AsyncMock()
        st.reader._segment_queue = []
        st.ensure_reader = AsyncMock()

        # split_sentencesは30文字超のみ分割するので、長めの日本語を用意
        long_text = (
            "今日は配信を見にきてくれてありがとう。"
            "最近プログラミングにハマっているよ。"
            "みんなも何か夢中になっていることがあれば教えて。"
        )
        monkeypatch.setattr(ar, "generate_event_response", lambda *a, **kw: {
            "speech": long_text,
            "tts_text": long_text,
            "emotion": "happy",
            "translation": "",
        })
        resp = api_client.post("/api/tts/test-multi")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        # 全角「。」で複数セグメントに分割される
        assert data["count"] >= 2
        assert len(data["segments"]) == data["count"]
        assert "ありがとう" in data["segments"][0]


class TestClaudeWatcherStatus:
    """GET /api/claude-watcher/status"""

    def test_returns_watcher_status(self, api_client):
        import scripts.state as st
        st.reader.claude_watcher.status = {
            "running": True,
            "active": False,
            "transcript_path": "/tmp/foo.jsonl",
            "start_time": 1700000000,
            "elapsed_seconds": 120,
            "last_conversation": None,
            "interval": 480,
            "min_actions": 3,
            "max_utterances": 4,
        }
        resp = api_client.get("/api/claude-watcher/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["interval"] == 480


class TestClaudeWatcherConfig:
    """POST /api/claude-watcher/config"""

    def test_updates_interval_with_minimum_clamp(self, api_client):
        import scripts.state as st
        watcher = st.reader.claude_watcher
        watcher._running = False
        watcher.INTERVAL = 480
        watcher.MIN_ACTIONS = 3
        watcher.MAX_UTTERANCES = 4
        watcher.status = {"interval": 0, "min_actions": 0, "max_utterances": 0}

        resp = api_client.post("/api/claude-watcher/config", json={"interval_seconds": 30})
        assert resp.status_code == 200
        # 最小60秒にクランプされる
        assert watcher.INTERVAL == 60

    def test_updates_all_numeric_fields(self, api_client):
        import scripts.state as st
        watcher = st.reader.claude_watcher
        watcher._running = False
        watcher.status = {}

        resp = api_client.post("/api/claude-watcher/config", json={
            "interval_seconds": 600,
            "min_actions": 5,
            "max_utterances": 6,
        })
        assert resp.status_code == 200
        assert watcher.INTERVAL == 600
        assert watcher.MIN_ACTIONS == 5
        assert watcher.MAX_UTTERANCES == 6

    def test_max_utterances_clamped_to_upper_bound(self, api_client):
        import scripts.state as st
        watcher = st.reader.claude_watcher
        watcher._running = False
        watcher.status = {}
        resp = api_client.post("/api/claude-watcher/config", json={"max_utterances": 100})
        assert resp.status_code == 200
        assert watcher.MAX_UTTERANCES == 8  # 上限8

    def test_enable_starts_watcher_when_stopped(self, api_client):
        import scripts.state as st
        watcher = st.reader.claude_watcher
        watcher._running = False
        watcher.start = AsyncMock()
        watcher.stop = AsyncMock()
        watcher.status = {}

        resp = api_client.post("/api/claude-watcher/config", json={"enabled": True})
        assert resp.status_code == 200
        watcher.start.assert_called_once()
        watcher.stop.assert_not_called()

    def test_disable_stops_watcher_when_running(self, api_client):
        import scripts.state as st
        watcher = st.reader.claude_watcher
        watcher._running = True
        watcher.start = AsyncMock()
        watcher.stop = AsyncMock()
        watcher.status = {}

        resp = api_client.post("/api/claude-watcher/config", json={"enabled": False})
        assert resp.status_code == 200
        watcher.stop.assert_called_once()
        watcher.start.assert_not_called()


class TestChatSend:
    """POST /api/chat/send"""

    def test_sends_message_via_twitch_chat(self, api_client):
        import scripts.state as st
        st.reader._chat.send_message = AsyncMock()
        resp = api_client.post("/api/chat/send", json={"message": "hi"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        st.reader._chat.send_message.assert_called_once_with("hi")


class TestChatHistory:
    """GET /api/chat/history"""

    def test_empty_db_returns_zero(self, api_client):
        resp = api_client.get("/api/chat/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["comments"] == []
        assert data["offset"] == 0
        assert data["limit"] == 50

    def test_pagination_params_echoed(self, api_client):
        resp = api_client.get("/api/chat/history?limit=10&offset=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 5

    def test_includes_avatar_comments(self, api_client):
        from src import db
        # コメント + アバター発話を両方作成
        channel = db.get_or_create_channel("test-ch")
        show = db.get_or_create_show(channel["id"], "デフォルト")
        char = db.get_or_create_character(channel["id"], "ちょビ", "{}")
        episode = db.start_episode(show["id"], char["id"])
        db.save_avatar_comment(episode["id"], "event", "トリガー", "アバター発話", "neutral")

        resp = api_client.get("/api/chat/history")
        data = resp.json()
        assert data["total"] == 1
        assert len(data["comments"]) == 1
        assert data["comments"][0]["type"] == "avatar_comment"
        assert data["comments"][0]["speech"] == "アバター発話"


class TestTtsAudio:
    """GET /api/tts/audio"""

    def test_no_audio_returns_error(self, api_client):
        import scripts.state as st
        st.reader._current_audio = None
        resp = api_client.get("/api/tts/audio")
        assert resp.status_code == 200
        assert resp.json() == {"error": "no audio"}

    def test_returns_file_when_audio_exists(self, api_client, tmp_path):
        import scripts.state as st
        wav = tmp_path / "tts.wav"
        wav.write_bytes(b"RIFFxxxx")
        st.reader._current_audio = wav
        resp = api_client.get("/api/tts/audio")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert resp.content == b"RIFFxxxx"
        # キャッシュ無効ヘッダが付与される
        assert "no-cache" in resp.headers.get("cache-control", "")


class TestConversationDemoStatus:
    """GET /api/debug/conversation-demo/status"""

    def test_no_meta_returns_has_data_false(self, api_client, tmp_path, monkeypatch):
        from scripts.routes import avatar as avatar_mod
        monkeypatch.setattr(avatar_mod, "_CONV_DEMO_DIR", tmp_path / "no_conv")
        resp = api_client.get("/api/debug/conversation-demo/status")
        assert resp.status_code == 200
        assert resp.json() == {"has_data": False}

    def test_with_meta_returns_dialogues(self, api_client, tmp_path, monkeypatch):
        from scripts.routes import avatar as avatar_mod
        conv_dir = tmp_path / "conv_demo"
        conv_dir.mkdir()
        (conv_dir / "00.wav").write_bytes(b"WAV")
        meta = {
            "topic": "AIの未来",
            "dialogues": [
                {"speaker": "teacher", "content": "先生の話", "emotion": "neutral"},
                {"speaker": "student", "content": "生徒の反応", "emotion": "happy"},
            ],
            "wav_paths": [str(conv_dir / "00.wav"), None],
            "teacher_cfg": {"name": "ちょビ"},
            "student_cfg": {"name": "なるこ"},
        }
        (conv_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
        monkeypatch.setattr(avatar_mod, "_CONV_DEMO_DIR", conv_dir)

        resp = api_client.get("/api/debug/conversation-demo/status")
        data = resp.json()
        assert data["has_data"] is True
        assert data["topic"] == "AIの未来"
        assert data["dialogues_count"] == 2
        assert data["dialogues"][0]["speaker"] == "ちょビ"
        assert data["dialogues"][0]["wav_url"] == "/resources/audio/conv_demo/00.wav"
        assert data["dialogues"][1]["speaker"] == "なるこ"
        assert data["dialogues"][1]["wav_url"] is None


class TestConversationDemoPlay:
    """POST /api/debug/conversation-demo/play"""

    def test_no_meta_returns_error(self, api_client, tmp_path, monkeypatch):
        from scripts.routes import avatar as avatar_mod
        monkeypatch.setattr(avatar_mod, "_CONV_DEMO_DIR", tmp_path / "empty")
        resp = api_client.post("/api/debug/conversation-demo/play")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "生成済みの会話がありません" in data["error"]

    def test_with_meta_schedules_playback(self, api_client, tmp_path, monkeypatch):
        from scripts.routes import avatar as avatar_mod
        import scripts.state as st
        conv_dir = tmp_path / "conv_demo"
        conv_dir.mkdir()
        meta = {
            "topic": "雑談",
            "dialogues": [
                {"speaker": "teacher", "content": "やあ", "emotion": "neutral", "tts_text": "やあ"},
            ],
            "wav_paths": [None],
            "teacher_cfg": {"name": "ちょビ", "tts_voice": "Leda"},
            "student_cfg": {"name": "なるこ"},
        }
        (conv_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
        monkeypatch.setattr(avatar_mod, "_CONV_DEMO_DIR", conv_dir)

        st.ensure_reader = AsyncMock()
        st.reader._speech.apply_emotion = MagicMock()
        st.reader._speech.speak = AsyncMock()
        st.reader._speech.notify_overlay_end = AsyncMock()

        resp = api_client.post("/api/debug/conversation-demo/play")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["dialogues_count"] == 1


class TestConversationDemoGenerate:
    """POST /api/debug/conversation-demo/generate

    フル生成フローは複雑（Gemini + TTS + ファイルI/O）なので、
    エラー経路のみ検証する（先生・生徒キャラ未登録時）。
    """

    def test_returns_error_when_characters_missing(self, api_client, monkeypatch):
        # 関数内で `from src.lesson_generator import get_lesson_characters` しているので
        # モジュール側の属性を差し替える
        import src.lesson_generator as lg
        monkeypatch.setattr(
            lg, "get_lesson_characters",
            lambda: {"teacher": None, "student": None},
        )
        resp = api_client.post(
            "/api/debug/conversation-demo/generate", json={"topic": "AI"},
        )
        assert resp.status_code == 200
        # SSEレスポンス内に "ok": False と「キャラクター未登録」エラーが含まれる
        assert '"ok": false' in resp.text
        assert "先生・生徒キャラがDBに登録されていません" in resp.text
