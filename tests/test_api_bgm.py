"""BGM ルート (scripts/routes/bgm.py) のテスト

方針:
- BGM_DIR を tmp_path に差し替えて resources/audio/bgm への副作用を防ぐ
- state.broadcast_bgm は api_client フィクスチャで AsyncMock 化済み
- subprocess.run（yt-dlp）はモック化（外部プロセスを呼ばない）
- DB は conftest の test_db（インメモリSQLite）を使用
"""

import re
import subprocess
from unittest.mock import MagicMock, patch


def _make_bgm_dir(tmp_path, monkeypatch):
    """BGM_DIR を tmp_path/bgm に差し替え、scenes.json も空にして Path を返す

    bgm.track は scenes.json にデフォルト値があるので、DB空 → scenes.json
    フォールバックの挙動がテストに混入する。設定系のアサーションを安定させる
    ため CONFIG_PATH も tmp_path の空JSONに差し替える。
    """
    import scripts.routes.bgm as bgm_mod
    import src.scene_config as sc
    bgm_dir = tmp_path / "bgm"
    bgm_dir.mkdir()
    monkeypatch.setattr(bgm_mod, "BGM_DIR", bgm_dir)
    empty_config = tmp_path / "scenes.json"
    empty_config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sc, "CONFIG_PATH", empty_config)
    return bgm_dir


class TestBgmList:
    """GET /api/bgm/list"""

    def test_empty_directory(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        resp = api_client.get("/api/bgm/list")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tracks"] == []
        assert body["track"] == ""

    def test_includes_supported_extensions_only(self, api_client, test_db, tmp_path, monkeypatch):
        bgm_dir = _make_bgm_dir(tmp_path, monkeypatch)
        (bgm_dir / "song.mp3").write_bytes(b"x")
        (bgm_dir / "song.wav").write_bytes(b"x")
        (bgm_dir / "song.ogg").write_bytes(b"x")
        (bgm_dir / "song.m4a").write_bytes(b"x")
        (bgm_dir / "readme.txt").write_text("skip me")
        (bgm_dir / "cover.png").write_bytes(b"x")

        resp = api_client.get("/api/bgm/list")
        files = [t["file"] for t in resp.json()["tracks"]]
        assert set(files) == {"song.mp3", "song.wav", "song.ogg", "song.m4a"}

    def test_merges_db_volume_and_source_url(self, api_client, test_db, tmp_path, monkeypatch):
        bgm_dir = _make_bgm_dir(tmp_path, monkeypatch)
        (bgm_dir / "a.mp3").write_bytes(b"x")
        (bgm_dir / "b.mp3").write_bytes(b"x")
        test_db.set_bgm_track_volume("a.mp3", 0.42)
        test_db.set_bgm_track_source_url("a.mp3", "https://youtu.be/abc")

        resp = api_client.get("/api/bgm/list")
        tracks = {t["file"]: t for t in resp.json()["tracks"]}
        assert tracks["a.mp3"]["volume"] == 0.42
        assert tracks["a.mp3"]["source_url"] == "https://youtu.be/abc"
        assert tracks["a.mp3"]["name"] == "a"
        # 未登録はデフォルト
        assert tracks["b.mp3"]["volume"] == 1.0
        assert tracks["b.mp3"]["source_url"] is None

    def test_includes_current_track_from_settings(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        from src.scene_config import save_config_value
        save_config_value("bgm.track", "current.mp3")
        resp = api_client.get("/api/bgm/list")
        assert resp.json()["track"] == "current.mp3"

    def test_creates_directory_if_missing(self, api_client, test_db, tmp_path, monkeypatch):
        """BGM_DIR が無い場合は自動作成する"""
        import scripts.routes.bgm as bgm_mod
        bgm_dir = tmp_path / "missing_bgm"
        assert not bgm_dir.exists()
        monkeypatch.setattr(bgm_mod, "BGM_DIR", bgm_dir)
        resp = api_client.get("/api/bgm/list")
        assert resp.status_code == 200
        assert bgm_dir.exists()


class TestBgmControl:
    """POST /api/bgm"""

    def test_play_broadcasts_bgm_play_and_saves_track(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        test_db.set_bgm_track_volume("song.mp3", 0.75)
        import scripts.state as st

        resp = api_client.post("/api/bgm", json={"action": "play", "track": "song.mp3"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        # bgm_play が正しい url/volume で broadcast される
        st.broadcast_bgm.assert_called_once()
        event = st.broadcast_bgm.call_args.args[0]
        assert event == {"type": "bgm_play", "url": "/bgm/song.mp3", "volume": 0.75}

        # settings に track が保存されている
        from src.scene_config import load_config_value
        assert load_config_value("bgm.track") == "song.mp3"

    def test_play_uses_default_volume_when_not_set(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        import scripts.state as st

        resp = api_client.post("/api/bgm", json={"action": "play", "track": "new.mp3"})
        assert resp.status_code == 200
        event = st.broadcast_bgm.call_args.args[0]
        assert event["volume"] == 1.0

    def test_stop_broadcasts_bgm_stop_and_clears_track(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        from src.scene_config import save_config_value, load_config_value
        save_config_value("bgm.track", "playing.mp3")
        import scripts.state as st

        resp = api_client.post("/api/bgm", json={"action": "stop"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        st.broadcast_bgm.assert_called_once_with({"type": "bgm_stop"})
        assert load_config_value("bgm.track") == ""

    def test_unknown_action_returns_error(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        import scripts.state as st

        resp = api_client.post("/api/bgm", json={"action": "pause"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "不明なアクション" in body["error"]
        st.broadcast_bgm.assert_not_called()


class TestBgmTrackVolume:
    """POST /api/bgm/track-volume"""

    def test_sets_volume_in_db(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        resp = api_client.post(
            "/api/bgm/track-volume",
            json={"file": "song.mp3", "volume": 0.3},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert test_db.get_bgm_track_volume("song.mp3") == 0.3

    def test_broadcasts_volume_when_track_is_playing(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        from src.scene_config import save_config_value
        save_config_value("bgm.track", "song.mp3")
        import scripts.state as st

        resp = api_client.post(
            "/api/bgm/track-volume",
            json={"file": "song.mp3", "volume": 0.55},
        )
        assert resp.status_code == 200
        st.broadcast_bgm.assert_called_once()
        event = st.broadcast_bgm.call_args.args[0]
        assert event == {"type": "bgm_volume", "source": "track", "volume": 0.55}

    def test_does_not_broadcast_when_not_playing(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        from src.scene_config import save_config_value
        save_config_value("bgm.track", "other.mp3")
        import scripts.state as st

        resp = api_client.post(
            "/api/bgm/track-volume",
            json={"file": "song.mp3", "volume": 0.2},
        )
        assert resp.status_code == 200
        # 再生中ではないので broadcast されない
        st.broadcast_bgm.assert_not_called()
        # DBには保存される
        assert test_db.get_bgm_track_volume("song.mp3") == 0.2


class TestBgmTrackDelete:
    """DELETE /api/bgm/track"""

    def test_deletes_file_and_db_record(self, api_client, test_db, tmp_path, monkeypatch):
        bgm_dir = _make_bgm_dir(tmp_path, monkeypatch)
        target = bgm_dir / "old.mp3"
        target.write_bytes(b"x")
        test_db.set_bgm_track_volume("old.mp3", 0.5)

        resp = api_client.delete("/api/bgm/track?file=old.mp3")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert not target.exists()
        # DBレコードも削除されている（デフォルトの1.0に戻る）
        assert test_db.get_bgm_track_volume("old.mp3") == 1.0

    def test_stops_playback_before_delete(self, api_client, test_db, tmp_path, monkeypatch):
        bgm_dir = _make_bgm_dir(tmp_path, monkeypatch)
        target = bgm_dir / "playing.mp3"
        target.write_bytes(b"x")
        from src.scene_config import save_config_value, load_config_value
        save_config_value("bgm.track", "playing.mp3")
        import scripts.state as st

        resp = api_client.delete("/api/bgm/track?file=playing.mp3")
        assert resp.status_code == 200
        st.broadcast_bgm.assert_called_once_with({"type": "bgm_stop"})
        assert load_config_value("bgm.track") == ""
        assert not target.exists()

    def test_missing_file_returns_error(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        import scripts.state as st

        resp = api_client.delete("/api/bgm/track?file=ghost.mp3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "見つかりません" in body["error"]
        # 何も broadcast されない
        st.broadcast_bgm.assert_not_called()


class TestBgmYoutube:
    """POST /api/bgm/youtube"""

    def test_empty_url_returns_error(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        resp = api_client.post("/api/bgm/youtube", json={"url": "   "})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "URLが空" in body["error"]

    def test_downloads_and_saves_source_url(self, api_client, test_db, tmp_path, monkeypatch):
        bgm_dir = _make_bgm_dir(tmp_path, monkeypatch)
        import scripts.routes.bgm as bgm_mod

        def fake_title(url):
            return "My Song / Live"

        def fake_download(url, output_path):
            # yt-dlp がMP3を書き出す挙動を模擬
            from pathlib import Path
            Path(output_path).write_bytes(b"fake-mp3-data")

        monkeypatch.setattr(bgm_mod, "_get_youtube_title", fake_title)
        monkeypatch.setattr(bgm_mod, "_download_youtube_audio", fake_download)

        resp = api_client.post(
            "/api/bgm/youtube",
            json={"url": "https://youtu.be/abc123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["title"] == "My Song / Live"
        # / は sanitize で除去される
        assert body["file"] == "My Song  Live.mp3"
        assert (bgm_dir / "My Song  Live.mp3").exists()
        # ソースURLがDBに保存されている
        tracks = test_db.get_all_bgm_tracks()
        assert tracks["My Song  Live.mp3"]["source_url"] == "https://youtu.be/abc123"

    def test_existing_file_skips_download_but_updates_url(self, api_client, test_db, tmp_path, monkeypatch):
        bgm_dir = _make_bgm_dir(tmp_path, monkeypatch)
        import scripts.routes.bgm as bgm_mod
        # 既存ファイル
        (bgm_dir / "Existing.mp3").write_bytes(b"old")

        monkeypatch.setattr(bgm_mod, "_get_youtube_title", lambda url: "Existing")
        # ダウンロードが呼ばれたら失敗させる（呼ばれないはず）
        called = []
        monkeypatch.setattr(
            bgm_mod,
            "_download_youtube_audio",
            lambda url, path: called.append(path),
        )

        resp = api_client.post(
            "/api/bgm/youtube",
            json={"url": "https://youtu.be/xyz"},
        )
        body = resp.json()
        assert body["ok"] is True
        assert body["file"] == "Existing.mp3"
        assert "既にダウンロード済み" in body["message"]
        assert called == []  # ダウンロードはスキップされた
        # 既存ファイルへのURL補完は行われる
        tracks = test_db.get_all_bgm_tracks()
        assert tracks["Existing.mp3"]["source_url"] == "https://youtu.be/xyz"

    def test_download_failure_returns_error(self, api_client, test_db, tmp_path, monkeypatch):
        _make_bgm_dir(tmp_path, monkeypatch)
        import scripts.routes.bgm as bgm_mod

        def failing_title(url):
            raise RuntimeError("yt-dlp: Video unavailable")

        monkeypatch.setattr(bgm_mod, "_get_youtube_title", failing_title)

        resp = api_client.post(
            "/api/bgm/youtube",
            json={"url": "https://youtu.be/bad"},
        )
        body = resp.json()
        assert body["ok"] is False
        assert "Video unavailable" in body["error"]

    def test_download_returns_false_when_file_missing_after_dl(self, api_client, test_db, tmp_path, monkeypatch):
        """ダウンロード完了なのにファイルが存在しないケース"""
        _make_bgm_dir(tmp_path, monkeypatch)
        import scripts.routes.bgm as bgm_mod

        monkeypatch.setattr(bgm_mod, "_get_youtube_title", lambda url: "NoFile")
        # ダウンロードしたふりをして何も書かない
        monkeypatch.setattr(bgm_mod, "_download_youtube_audio", lambda url, path: None)

        resp = api_client.post(
            "/api/bgm/youtube",
            json={"url": "https://youtu.be/nop"},
        )
        body = resp.json()
        assert body["ok"] is False
        assert "ダウンロード" in body["error"]


class TestGetYoutubeTitle:
    """_get_youtube_title（ヘルパー）"""

    def test_returns_stripped_title_on_success(self, monkeypatch):
        import scripts.routes.bgm as bgm_mod

        fake_result = MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = "Awesome Title\n"
        fake_result.stderr = ""

        with patch.object(bgm_mod.subprocess, "run", return_value=fake_result) as mock_run:
            title = bgm_mod._get_youtube_title("https://youtu.be/abc")
        assert title == "Awesome Title"
        args = mock_run.call_args.args[0]
        assert args[0] == "yt-dlp"
        assert "--get-title" in args
        assert args[-1] == "https://youtu.be/abc"

    def test_raises_on_nonzero_exit(self, monkeypatch):
        import scripts.routes.bgm as bgm_mod

        fake_result = MagicMock()
        fake_result.returncode = 1
        fake_result.stdout = ""
        fake_result.stderr = "Video not found"

        with patch.object(bgm_mod.subprocess, "run", return_value=fake_result):
            try:
                bgm_mod._get_youtube_title("https://youtu.be/bad")
                assert False, "should raise"
            except RuntimeError as e:
                assert "Video not found" in str(e)


class TestDownloadYoutubeAudio:
    """_download_youtube_audio（ヘルパー）"""

    def test_builds_yt_dlp_command_correctly(self, monkeypatch):
        import scripts.routes.bgm as bgm_mod

        fake_result = MagicMock(returncode=0, stderr="")

        with patch.object(bgm_mod.subprocess, "run", return_value=fake_result) as mock_run:
            bgm_mod._download_youtube_audio("https://youtu.be/abc", "/tmp/out.mp3")
        args = mock_run.call_args.args[0]
        assert args[0] == "yt-dlp"
        assert "-x" in args
        assert "mp3" in args
        assert "192K" in args
        assert "--no-playlist" in args
        assert "/tmp/out.mp3" in args
        assert args[-1] == "https://youtu.be/abc"

    def test_raises_on_yt_dlp_failure(self):
        import scripts.routes.bgm as bgm_mod

        fake_result = MagicMock(returncode=1, stderr="no network")

        with patch.object(bgm_mod.subprocess, "run", return_value=fake_result):
            try:
                bgm_mod._download_youtube_audio("https://youtu.be/x", "/tmp/y.mp3")
                assert False, "should raise"
            except RuntimeError as e:
                assert "no network" in str(e)


class TestSanitizeFilename:
    """_sanitize_filename（ヘルパー）"""

    def test_removes_forbidden_chars(self):
        import scripts.routes.bgm as bgm_mod
        assert bgm_mod._sanitize_filename('hello/<world>?*:"|') == "helloworld"

    def test_strips_leading_trailing_dots_and_spaces(self):
        import scripts.routes.bgm as bgm_mod
        assert bgm_mod._sanitize_filename(" . hello . ") == "hello"

    def test_empty_becomes_untitled(self):
        import scripts.routes.bgm as bgm_mod
        assert bgm_mod._sanitize_filename("") == "untitled"
        assert bgm_mod._sanitize_filename("...   ") == "untitled"
        assert bgm_mod._sanitize_filename('\\/:*?"<>|') == "untitled"

    def test_truncates_to_100_chars(self):
        import scripts.routes.bgm as bgm_mod
        long_name = "a" * 200
        result = bgm_mod._sanitize_filename(long_name)
        assert len(result) == 100
        assert result == "a" * 100

    def test_preserves_unicode(self):
        import scripts.routes.bgm as bgm_mod
        assert bgm_mod._sanitize_filename("日本語タイトル") == "日本語タイトル"


class TestLoadBgmSettings:
    """load_bgm_settings（ヘルパー）"""

    def test_returns_empty_track_when_unset(self, test_db, tmp_path, monkeypatch):
        import scripts.routes.bgm as bgm_mod
        import src.scene_config as sc
        empty_config = tmp_path / "scenes.json"
        empty_config.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sc, "CONFIG_PATH", empty_config)
        assert bgm_mod.load_bgm_settings() == {"track": ""}

    def test_returns_track_from_db(self, test_db):
        import scripts.routes.bgm as bgm_mod
        from src.scene_config import save_config_value
        save_config_value("bgm.track", "saved.mp3")
        assert bgm_mod.load_bgm_settings() == {"track": "saved.mp3"}


class TestSaveBgm:
    """_save_bgm（ヘルパー）"""

    def test_saves_track_to_db(self, test_db):
        import scripts.routes.bgm as bgm_mod
        from src.db import get_setting
        bgm_mod._save_bgm(track="new.mp3")
        assert get_setting("bgm.track") == "new.mp3"

    def test_none_track_is_noop(self, test_db):
        import scripts.routes.bgm as bgm_mod
        from src.scene_config import save_config_value
        from src.db import get_setting
        save_config_value("bgm.track", "existing.mp3")
        bgm_mod._save_bgm(track=None)
        # DB上書きされない
        assert get_setting("bgm.track") == "existing.mp3"
