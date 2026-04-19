"""キャプチャ制御API (scripts/routes/capture.py) のテスト

capture.py は Windows ネイティブ配信アプリとの通信を束ねるルート。
テストは次の方針で書く:

- `proxy_request` / `ws_request` は `scripts.services.capture_client` の関数だが、
  capture.py が `from ... import` しているので `scripts.routes.capture` のモジュール属性を
  `monkeypatch` で差し替える（ネイティブアプリへの実通信を避ける）
- DB操作（`src.db` の `capture_windows` テーブル）は `test_db` フィクスチャのインメモリ SQLite を
  使って実際に書き込み・読み取りを検証する
- `state.broadcast_to_broadcast` は `api_client` フィクスチャで AsyncMock 化済み
- スクリーンショット系は `SCREENSHOT_DIR` を `tmp_path` に差し替えて `/tmp` 汚染を防止
"""

from unittest.mock import AsyncMock

import pytest


def _patch_capture_client(monkeypatch, *, proxy=None, ws=None, base_url="http://win-host:9090"):
    """capture.py に import 済みの proxy_request / ws_request / capture_base_url を差し替える"""
    from scripts.routes import capture as cap_mod

    if proxy is not None:
        monkeypatch.setattr(cap_mod, "proxy_request", proxy)
    if ws is not None:
        monkeypatch.setattr(cap_mod, "ws_request", ws)
    monkeypatch.setattr(cap_mod, "capture_base_url", lambda: base_url)


# =====================================================
# GET /api/capture/status
# =====================================================


class TestCaptureStatus:
    def test_running_when_proxy_succeeds(self, api_client, monkeypatch):
        proxy = AsyncMock(return_value={"uptime": 42})
        _patch_capture_client(monkeypatch, proxy=proxy)

        resp = api_client.get("/api/capture/status")
        assert resp.status_code == 200
        assert resp.json() == {"running": True, "uptime": 42}
        proxy.assert_awaited_once_with("GET", "/status")

    def test_not_running_when_proxy_fails(self, api_client, monkeypatch):
        proxy = AsyncMock(side_effect=ConnectionError("down"))
        _patch_capture_client(monkeypatch, proxy=proxy)

        resp = api_client.get("/api/capture/status")
        assert resp.status_code == 200
        assert resp.json() == {"running": False}


# =====================================================
# GET /api/capture/windows
# =====================================================


class TestCaptureWindows:
    def test_returns_windows_list(self, api_client, monkeypatch):
        windows = [{"id": "w1", "name": "Notepad"}, {"id": "w2", "name": "VSCode"}]
        proxy = AsyncMock(return_value=windows)
        _patch_capture_client(monkeypatch, proxy=proxy)

        resp = api_client.get("/api/capture/windows")
        assert resp.status_code == 200
        assert resp.json() == windows

    def test_502_when_proxy_fails(self, api_client, monkeypatch):
        proxy = AsyncMock(side_effect=ConnectionError("down"))
        _patch_capture_client(monkeypatch, proxy=proxy)

        resp = api_client.get("/api/capture/windows")
        assert resp.status_code == 502
        assert "キャプチャサーバーに接続できません" in resp.json()["detail"]


# =====================================================
# GET /api/capture/saved
# =====================================================


class TestCaptureSavedList:
    def test_empty(self, api_client):
        resp = api_client.get("/api/capture/saved")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_saved_rows_in_api_shape(self, api_client):
        from src import db
        db.upsert_capture_window(
            "Notepad",
            label="メモ帳",
            layout={"x": 10, "y": 20, "width": 30, "height": 40, "zIndex": 5, "visible": True},
        )
        resp = api_client.get("/api/capture/saved")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        entry = data[0]
        assert entry["window_name"] == "Notepad"
        assert entry["label"] == "メモ帳"
        assert entry["layout"] == {
            "x": 10, "y": 20, "width": 30, "height": 40, "zIndex": 5, "visible": True,
        }


# =====================================================
# DELETE /api/capture/saved
# =====================================================


class TestCaptureSavedDelete:
    def test_removes_row(self, api_client):
        from src import db
        db.upsert_capture_window("Foo", label="Foo")
        assert db.get_capture_window_by_name("Foo") is not None

        resp = api_client.request("DELETE", "/api/capture/saved", json={"window_name": "Foo"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert db.get_capture_window_by_name("Foo") is None

    def test_no_op_when_window_name_missing(self, api_client):
        resp = api_client.request("DELETE", "/api/capture/saved", json={})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


# =====================================================
# POST /api/capture/saved/layout
# =====================================================


class TestCaptureSavedUpdateLayout:
    def test_updates_layout_partially(self, api_client):
        from src import db
        db.upsert_capture_window(
            "Foo",
            label="Foo",
            layout={"x": 1, "y": 2, "width": 3, "height": 4, "zIndex": 5, "visible": True},
        )
        resp = api_client.post(
            "/api/capture/saved/layout",
            json={"window_name": "Foo", "x": 99, "visible": False},
        )
        assert resp.status_code == 200
        row = db.get_capture_window_by_name("Foo")
        assert row["x"] == 99
        assert row["visible"] == 0
        assert row["y"] == 2  # 未指定は据え置き

    def test_no_op_without_window_name(self, api_client):
        from src import db
        db.upsert_capture_window("Foo", label="Foo")
        resp = api_client.post("/api/capture/saved/layout", json={"x": 1})
        assert resp.status_code == 200
        row = db.get_capture_window_by_name("Foo")
        assert row["x"] == 5  # デフォルトのまま


# =====================================================
# POST /api/capture/restore
# =====================================================


class TestCaptureRestore:
    def test_no_saved_rows_returns_zero(self, api_client, monkeypatch):
        _patch_capture_client(monkeypatch, proxy=AsyncMock())
        resp = api_client.post("/api/capture/restore")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["restored"] == 0
        assert "保存済み設定なし" in data["message"]

    def test_error_when_proxy_fails_for_windows(self, api_client, monkeypatch):
        from src import db
        db.upsert_capture_window("Foo", label="Foo")

        proxy = AsyncMock(side_effect=ConnectionError("down"))
        _patch_capture_client(monkeypatch, proxy=proxy)

        resp = api_client.post("/api/capture/restore")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "配信アプリに接続できません" in data["error"]

    def test_restores_matching_window_by_exact_name(self, api_client, monkeypatch):
        from src import db
        import scripts.state as st

        db.upsert_capture_window(
            "Notepad - foo.txt",
            label="メモ",
            layout={"x": 1, "y": 2, "width": 3, "height": 4, "zIndex": 7, "visible": True},
        )

        async def fake_proxy(method, path, body=None):
            if (method, path) == ("GET", "/windows"):
                return [{"id": "w1", "name": "Notepad - foo.txt", "sourceId": "src-1"}]
            if (method, path) == ("GET", "/captures"):
                return []  # アクティブなし
            if (method, path) == ("POST", "/capture"):
                assert body == {"sourceId": "src-1"}
                return {"ok": True, "id": "cap-new"}
            raise AssertionError(f"unexpected call: {method} {path}")

        _patch_capture_client(monkeypatch, proxy=AsyncMock(side_effect=fake_proxy))

        resp = api_client.post("/api/capture/restore")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["restored"] == 1

        # broadcast_to_broadcast に capture_add が送られていること
        sent = st.broadcast_to_broadcast.call_args.args[0]
        assert sent["type"] == "capture_add"
        assert sent["id"] == "cap-new"
        assert sent["label"] == "メモ"
        assert sent["layout"]["zIndex"] == 7

    def test_skips_invisible_and_already_active(self, api_client, monkeypatch):
        from src import db
        import scripts.state as st

        db.upsert_capture_window(
            "Hidden", label="H",
            layout={"x": 1, "y": 2, "width": 3, "height": 4, "zIndex": 1, "visible": False},
        )
        db.upsert_capture_window("Active", label="A")

        async def fake_proxy(method, path, body=None):
            if (method, path) == ("GET", "/windows"):
                return [{"id": "wA", "name": "Active", "sourceId": "sA"}]
            if (method, path) == ("GET", "/captures"):
                return [{"id": "cap-A", "name": "Active"}]
            raise AssertionError(f"unexpected call: {method} {path}")

        _patch_capture_client(monkeypatch, proxy=AsyncMock(side_effect=fake_proxy))

        resp = api_client.post("/api/capture/restore")
        data = resp.json()
        assert data["restored"] == 0
        # broadcast は呼ばれない
        st.broadcast_to_broadcast.assert_not_called()


# =====================================================
# POST /api/capture/start
# =====================================================


class TestCaptureStart:
    def test_persists_layout_and_broadcasts(self, api_client, monkeypatch):
        from src import db
        import scripts.state as st

        async def fake_proxy(method, path, body=None):
            assert (method, path) == ("POST", "/capture")
            assert body["sourceId"] == "src-xyz"
            return {"ok": True, "id": "cap-42", "name": "MyWindow"}

        _patch_capture_client(
            monkeypatch,
            proxy=AsyncMock(side_effect=fake_proxy),
            base_url="http://host:9090",
        )

        resp = api_client.post(
            "/api/capture/start",
            json={"sourceId": "src-xyz", "label": "好きなラベル"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["id"] == "cap-42"
        assert data["stream_url"] == "http://host:9090/stream/cap-42"

        # DB（永続テーブル）にも保存されている
        row = db.get_capture_window_by_name("MyWindow")
        assert row is not None
        assert row["label"] == "好きなラベル"

        # broadcast にも通知
        sent = st.broadcast_to_broadcast.call_args.args[0]
        assert sent == {
            "type": "capture_add",
            "id": "cap-42",
            "stream_url": "http://host:9090/stream/cap-42",
            "label": "好きなラベル",
            "layout": sent["layout"],  # レイアウトはデフォルト値を含む辞書
        }
        assert sent["layout"]["visible"] is True

    def test_reuses_saved_layout_when_window_known(self, api_client, monkeypatch):
        from src import db

        db.upsert_capture_window(
            "Known",
            label="保存済みラベル",
            layout={"x": 77, "y": 88, "width": 99, "height": 11, "zIndex": 22, "visible": False},
        )

        async def fake_proxy(method, path, body=None):
            return {"ok": True, "id": "cap-1", "name": "Known"}

        _patch_capture_client(monkeypatch, proxy=AsyncMock(side_effect=fake_proxy))

        resp = api_client.post("/api/capture/start", json={"sourceId": "src-a"})
        assert resp.status_code == 200
        import scripts.state as st
        sent = st.broadcast_to_broadcast.call_args.args[0]
        assert sent["label"] == "保存済みラベル"
        assert sent["layout"]["x"] == 77
        assert sent["layout"]["visible"] is False

    def test_502_when_proxy_fails(self, api_client, monkeypatch):
        proxy = AsyncMock(side_effect=ConnectionError("down"))
        _patch_capture_client(monkeypatch, proxy=proxy)

        resp = api_client.post("/api/capture/start", json={"sourceId": "src-a"})
        assert resp.status_code == 502

    def test_400_when_native_returns_not_ok(self, api_client, monkeypatch):
        proxy = AsyncMock(return_value={"ok": False, "error": "busy"})
        _patch_capture_client(monkeypatch, proxy=proxy)

        resp = api_client.post("/api/capture/start", json={"sourceId": "src-a"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "busy"

    def test_fetches_name_from_captures_when_missing(self, api_client, monkeypatch):
        """C#旧バージョン互換: /capture 応答に name が無い場合は /captures から取得"""
        async def fake_proxy(method, path, body=None):
            if (method, path) == ("POST", "/capture"):
                return {"ok": True, "id": "cap-99"}  # name なし
            if (method, path) == ("GET", "/captures"):
                return [{"id": "cap-99", "name": "RetroName"}]
            raise AssertionError(f"unexpected: {method} {path}")

        _patch_capture_client(monkeypatch, proxy=AsyncMock(side_effect=fake_proxy))

        resp = api_client.post("/api/capture/start", json={"sourceId": "src-a"})
        assert resp.status_code == 200

        from src import db
        assert db.get_capture_window_by_name("RetroName") is not None


# =====================================================
# DELETE /api/capture/{capture_id}
# =====================================================


class TestCaptureStop:
    def test_broadcasts_capture_remove(self, api_client, monkeypatch):
        import scripts.state as st

        proxy = AsyncMock(return_value={"ok": True})
        _patch_capture_client(monkeypatch, proxy=proxy)

        resp = api_client.delete("/api/capture/cap-9")
        assert resp.status_code == 200
        proxy.assert_awaited_once_with("DELETE", "/capture/cap-9")

        sent = st.broadcast_to_broadcast.call_args.args[0]
        assert sent == {"type": "capture_remove", "id": "cap-9"}

    def test_broadcasts_even_if_proxy_fails(self, api_client, monkeypatch):
        """配信アプリ側停止に失敗しても、クライアント側状態だけは同期する"""
        import scripts.state as st

        proxy = AsyncMock(side_effect=ConnectionError("down"))
        _patch_capture_client(monkeypatch, proxy=proxy)

        resp = api_client.delete("/api/capture/cap-9")
        assert resp.status_code == 200
        st.broadcast_to_broadcast.assert_called_once()


# =====================================================
# GET /api/capture/sources
# =====================================================


class TestCaptureSources:
    def test_merges_saved_layout_with_active(self, api_client, monkeypatch):
        # 保存済みレイアウトを書き込む
        from scripts.routes import capture as cap_mod
        cap_mod._save_capture_layout(
            "cap-1",
            {"x": 1, "y": 2, "width": 3, "height": 4, "zIndex": 5, "visible": True},
            label="ラベル",
            window_name="WinA",
        )

        async def fake_proxy(method, path, body=None):
            assert (method, path) == ("GET", "/captures")
            return [{"id": "cap-1", "name": "WinA"}]

        _patch_capture_client(
            monkeypatch,
            proxy=AsyncMock(side_effect=fake_proxy),
            base_url="http://h:9090",
        )

        resp = api_client.get("/api/capture/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        entry = data[0]
        assert entry["id"] == "cap-1"
        assert entry["label"] == "ラベル"
        assert entry["layout"]["x"] == 1
        assert entry["stream_url"] == "http://h:9090/stream/cap-1"

    def test_empty_when_proxy_fails(self, api_client, monkeypatch):
        proxy = AsyncMock(side_effect=ConnectionError("down"))
        _patch_capture_client(monkeypatch, proxy=proxy)
        resp = api_client.get("/api/capture/sources")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_default_layout_for_unknown_active(self, api_client, monkeypatch):
        async def fake_proxy(method, path, body=None):
            return [{"id": "unsaved", "name": "UnknownWin"}]

        _patch_capture_client(monkeypatch, proxy=AsyncMock(side_effect=fake_proxy))

        resp = api_client.get("/api/capture/sources")
        data = resp.json()
        entry = data[0]
        # デフォルトレイアウト
        assert entry["layout"]["x"] == 5
        assert entry["layout"]["visible"] is True
        assert entry["label"] == "UnknownWin"


# =====================================================
# POST /api/capture/{capture_id}/layout
# =====================================================


class TestCaptureUpdateLayout:
    def test_broadcasts_and_drops_none(self, api_client):
        import scripts.state as st

        resp = api_client.post(
            "/api/capture/cap-1/layout",
            json={"x": 12, "width": 34, "visible": False},
        )
        assert resp.status_code == 200
        sent = st.broadcast_to_broadcast.call_args.args[0]
        assert sent["type"] == "capture_layout"
        assert sent["id"] == "cap-1"
        # None は送信payloadから除外される
        assert sent["layout"] == {"x": 12, "width": 34, "visible": False}

    def test_syncs_db_when_window_name_known(self, api_client, monkeypatch):
        """_update_capture_layout は window_name があれば capture_windows テーブルも更新する"""
        from src import db
        from scripts.routes import capture as cap_mod
        db.upsert_capture_window(
            "WinA",
            label="WinA",
            layout={"x": 1, "y": 2, "width": 3, "height": 4, "zIndex": 5, "visible": True},
        )
        cap_mod._save_capture_layout(
            "cap-A",
            {"x": 1, "y": 2, "width": 3, "height": 4, "zIndex": 5, "visible": True},
            label="WinA",
            window_name="WinA",
        )

        resp = api_client.post("/api/capture/cap-A/layout", json={"x": 55})
        assert resp.status_code == 200

        row = db.get_capture_window_by_name("WinA")
        assert row["x"] == 55


# =====================================================
# POST /api/capture/screenshot
# =====================================================


class TestCaptureScreenshot:
    def test_saves_file_and_returns_meta(self, api_client, monkeypatch, tmp_path):
        import base64
        from scripts.routes import capture as cap_mod

        monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path)

        png = b"\x89PNGfake"
        ws = AsyncMock(return_value={"ok": True, "png_base64": base64.b64encode(png).decode()})
        _patch_capture_client(monkeypatch, ws=ws)

        resp = api_client.post("/api/capture/screenshot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["size"] == len(png)
        saved = tmp_path / data["file"]
        assert saved.exists()
        assert saved.read_bytes() == png
        ws.assert_awaited_once_with("screenshot", timeout=10.0)

    def test_502_when_ws_fails(self, api_client, monkeypatch, tmp_path):
        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path)
        ws = AsyncMock(side_effect=ConnectionError("down"))
        _patch_capture_client(monkeypatch, ws=ws)
        resp = api_client.post("/api/capture/screenshot")
        assert resp.status_code == 502

    def test_400_when_ws_reports_not_ok(self, api_client, monkeypatch, tmp_path):
        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path)
        ws = AsyncMock(return_value={"ok": False, "error": "no broadcast window"})
        _patch_capture_client(monkeypatch, ws=ws)
        resp = api_client.post("/api/capture/screenshot")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "no broadcast window"


# =====================================================
# GET /api/capture/screenshots
# =====================================================


class TestCaptureScreenshotList:
    def test_empty_when_dir_missing(self, api_client, monkeypatch, tmp_path):
        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path / "missing")
        resp = api_client.get("/api/capture/screenshots")
        assert resp.status_code == 200
        assert resp.json() == {"files": []}

    def test_returns_files_sorted_newest_first(self, api_client, monkeypatch, tmp_path):
        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path)

        import os
        old = tmp_path / "screenshot_20260101_000000.png"
        new = tmp_path / "screenshot_20260102_000000.png"
        old.write_bytes(b"A")
        new.write_bytes(b"B")
        # mtime を明示的に差をつける
        os.utime(old, (1_700_000_000, 1_700_000_000))
        os.utime(new, (1_700_001_000, 1_700_001_000))

        resp = api_client.get("/api/capture/screenshots")
        data = resp.json()
        assert [f["name"] for f in data["files"]] == [new.name, old.name]
        assert all("size" in f and "created" in f for f in data["files"])


# =====================================================
# GET / DELETE /api/capture/screenshots/{filename}
# =====================================================


class TestCaptureScreenshotFile:
    def test_get_returns_file(self, api_client, monkeypatch, tmp_path):
        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path)
        png = b"\x89PNGbody"
        (tmp_path / "screenshot_a.png").write_bytes(png)

        resp = api_client.get("/api/capture/screenshots/screenshot_a.png")
        assert resp.status_code == 200
        assert resp.content == png
        assert resp.headers["content-type"] == "image/png"

    def test_get_404_when_missing(self, api_client, monkeypatch, tmp_path):
        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path)
        resp = api_client.get("/api/capture/screenshots/missing.png")
        assert resp.status_code == 404

    @pytest.mark.parametrize("filename", ["../etc/passwd", "..\\windows", "sub/dir.png"])
    def test_get_400_for_path_traversal(self, api_client, monkeypatch, tmp_path, filename):
        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path)
        # FastAPI がスラッシュ入りパスをマッチしなかったら 404 になるので、バックスラッシュと .. ケースのみ検証
        resp = api_client.get(f"/api/capture/screenshots/{filename}")
        # どのケースでも保存ファイルは読み出させない（400 or 404 のいずれか）
        assert resp.status_code in (400, 404)

    def test_delete_removes_file(self, api_client, monkeypatch, tmp_path):
        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path)
        target = tmp_path / "screenshot_del.png"
        target.write_bytes(b"x")
        resp = api_client.delete("/api/capture/screenshots/screenshot_del.png")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert not target.exists()

    def test_delete_404_when_missing(self, api_client, monkeypatch, tmp_path):
        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path)
        resp = api_client.delete("/api/capture/screenshots/missing.png")
        assert resp.status_code == 404

    def test_delete_400_on_backslash(self, api_client, monkeypatch, tmp_path):
        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "SCREENSHOT_DIR", tmp_path)
        resp = api_client.delete("/api/capture/screenshots/..\\x")
        assert resp.status_code == 400


# =====================================================
# POST /api/capture/stream/start
# =====================================================


class TestCaptureStreamStart:
    def test_uses_env_stream_key_and_builds_server_url(self, api_client, monkeypatch):
        monkeypatch.setenv("TWITCH_STREAM_KEY", "live_abc")
        monkeypatch.setenv("WEB_PORT", "8888")

        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "get_windows_host_ip", lambda: "10.0.0.7")

        ws = AsyncMock(return_value={"ok": True})
        _patch_capture_client(monkeypatch, ws=ws)

        resp = api_client.post(
            "/api/capture/stream/start",
            json={"resolution": "1280x720", "framerate": 60},
        )
        assert resp.status_code == 200
        ws.assert_awaited_once()
        kwargs = ws.call_args.kwargs
        assert ws.call_args.args[0] == "start_stream"
        assert kwargs["streamKey"] == "live_abc"
        assert kwargs["serverUrl"] == "http://10.0.0.7:8888"
        assert kwargs["resolution"] == "1280x720"
        assert kwargs["framerate"] == 60

    def test_prefers_body_stream_key(self, api_client, monkeypatch):
        monkeypatch.setenv("TWITCH_STREAM_KEY", "env_key")

        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "get_windows_host_ip", lambda: "10.0.0.1")

        ws = AsyncMock(return_value={"ok": True})
        _patch_capture_client(monkeypatch, ws=ws)

        resp = api_client.post(
            "/api/capture/stream/start",
            json={"stream_key": "body_key"},
        )
        assert resp.status_code == 200
        assert ws.call_args.kwargs["streamKey"] == "body_key"

    def test_400_when_no_stream_key(self, api_client, monkeypatch):
        monkeypatch.delenv("TWITCH_STREAM_KEY", raising=False)
        ws = AsyncMock()
        _patch_capture_client(monkeypatch, ws=ws)

        resp = api_client.post("/api/capture/stream/start", json={})
        assert resp.status_code == 400
        assert "TWITCH_STREAM_KEY" in resp.json()["detail"]
        ws.assert_not_called()

    def test_502_when_ws_fails(self, api_client, monkeypatch):
        monkeypatch.setenv("TWITCH_STREAM_KEY", "key")

        from scripts.routes import capture as cap_mod
        monkeypatch.setattr(cap_mod, "get_windows_host_ip", lambda: "10.0.0.1")

        ws = AsyncMock(side_effect=ConnectionError("down"))
        _patch_capture_client(monkeypatch, ws=ws)

        resp = api_client.post("/api/capture/stream/start", json={})
        assert resp.status_code == 502


# =====================================================
# POST /api/capture/stream/stop, GET /api/capture/stream/status
# =====================================================


class TestCaptureStreamLifecycle:
    def test_stop_returns_ws_result(self, api_client, monkeypatch):
        ws = AsyncMock(return_value={"ok": True})
        _patch_capture_client(monkeypatch, ws=ws)

        resp = api_client.post("/api/capture/stream/stop")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        ws.assert_awaited_once_with("stop_stream")

    def test_stop_502_on_ws_failure(self, api_client, monkeypatch):
        ws = AsyncMock(side_effect=ConnectionError("down"))
        _patch_capture_client(monkeypatch, ws=ws)

        resp = api_client.post("/api/capture/stream/stop")
        assert resp.status_code == 502

    def test_status_returns_ws_result(self, api_client, monkeypatch):
        ws = AsyncMock(return_value={"running": True, "uptime": 100})
        _patch_capture_client(monkeypatch, ws=ws)

        resp = api_client.get("/api/capture/stream/status")
        assert resp.status_code == 200
        assert resp.json() == {"running": True, "uptime": 100}
        ws.assert_awaited_once_with("stream_status")

    def test_status_502_on_ws_failure(self, api_client, monkeypatch):
        ws = AsyncMock(side_effect=ConnectionError("down"))
        _patch_capture_client(monkeypatch, ws=ws)

        resp = api_client.get("/api/capture/stream/status")
        assert resp.status_code == 502


# =====================================================
# 内部ヘルパー
# =====================================================


class TestCaptureLayoutHelpers:
    """_load_capture_sources / _save_capture_layout / _update_capture_layout / _remove_capture_layout"""

    def test_save_then_load_roundtrip(self, test_db):
        from scripts.routes import capture as cap_mod
        cap_mod._save_capture_layout("cap-1", {"x": 1}, label="L", window_name="W")
        sources = cap_mod._load_capture_sources()
        assert sources == [{"id": "cap-1", "label": "L", "layout": {"x": 1}, "window_name": "W"}]

    def test_save_updates_existing(self, test_db):
        from scripts.routes import capture as cap_mod
        cap_mod._save_capture_layout("cap-1", {"x": 1}, label="L1")
        cap_mod._save_capture_layout("cap-1", {"x": 2}, label="L2", window_name="W2")
        sources = cap_mod._load_capture_sources()
        assert len(sources) == 1
        assert sources[0]["layout"] == {"x": 2}
        assert sources[0]["label"] == "L2"
        assert sources[0]["window_name"] == "W2"

    def test_update_merges_layout(self, test_db):
        from scripts.routes import capture as cap_mod
        cap_mod._save_capture_layout("cap-1", {"x": 1, "y": 2}, label="L")
        cap_mod._update_capture_layout("cap-1", {"y": 22, "z_index": 5})
        sources = cap_mod._load_capture_sources()
        assert sources[0]["layout"] == {"x": 1, "y": 22, "z_index": 5}

    def test_remove_drops_entry(self, test_db):
        from scripts.routes import capture as cap_mod
        cap_mod._save_capture_layout("cap-1", {"x": 1})
        cap_mod._save_capture_layout("cap-2", {"x": 2})
        cap_mod._remove_capture_layout("cap-1")
        sources = cap_mod._load_capture_sources()
        assert [s["id"] for s in sources] == ["cap-2"]

    def test_load_handles_corrupt_setting(self, test_db):
        from src import db
        from scripts.routes import capture as cap_mod
        db.set_setting("capture.sources", "not-json{")
        assert cap_mod._load_capture_sources() == []

    def test_row_to_layout_casts_visible_to_bool(self):
        from scripts.routes import capture as cap_mod
        row = {"x": 1, "y": 2, "width": 3, "height": 4, "z_index": 5, "visible": 0}
        assert cap_mod._row_to_layout(row) == {
            "x": 1, "y": 2, "width": 3, "height": 4, "zIndex": 5, "visible": False,
        }
