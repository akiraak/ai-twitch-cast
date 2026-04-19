"""素材ファイル管理API (scripts/routes/files.py) のテスト

方針:
- CATEGORIES 各カテゴリの dir を tmp_path に差し替えて resources/ 配下への副作用を防ぐ
- scene_config.CONFIG_PATH も tmp_path の空JSONに差し替え、scenes.json フォールバックの混入を防ぐ
- アバターVRM系は characters テーブル経由なので test_db で実行し、
  get_or_create_character + update_character_config_field の実体を使って検証
- state.broadcast_to_broadcast は api_client で AsyncMock 化済み
"""

import io
import json


def _patch_categories(tmp_path, monkeypatch):
    """CATEGORIES 4種の dir を tmp_path 配下に差し替え、4つの Path を返す"""
    import scripts.routes.files as files_mod
    import src.scene_config as sc

    vrm = tmp_path / "vrm"
    bg = tmp_path / "backgrounds"
    teaching = tmp_path / "teaching"
    vrm.mkdir()
    bg.mkdir()
    teaching.mkdir()

    # CATEGORIES dict 自体を差し替え（avatar/avatar2 は同じディレクトリを指す）
    new_cats = {
        "avatar": {"dir": vrm, "extensions": {".vrm"}},
        "avatar2": {"dir": vrm, "extensions": {".vrm"}},
        "background": {
            "dir": bg,
            "extensions": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
            "config_key": "files.active_background",
        },
        "teaching": {
            "dir": teaching,
            "extensions": {".png", ".jpg", ".jpeg", ".webp"},
            "config_key": "files.active_teaching",
        },
    }
    monkeypatch.setattr(files_mod, "CATEGORIES", new_cats)

    # scenes.json フォールバックを無効化
    empty_config = tmp_path / "scenes.json"
    empty_config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sc, "CONFIG_PATH", empty_config)
    return vrm, bg, teaching


def _seed_character(test_db, role):
    """role=teacher/student のキャラをDBに作成し、character row を返す"""
    import os
    channel_name = os.environ.get("TWITCH_CHANNEL", "default")
    channel = test_db.get_or_create_channel(channel_name)
    config = json.dumps({"role": role}, ensure_ascii=False)
    name = "ちょビ" if role == "teacher" else "なるこ"
    return test_db.get_or_create_character(channel["id"], name, config)


class TestFilesList:
    """GET /api/files/{category}/list"""

    def test_unknown_category_returns_error(self, api_client, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        resp = api_client.get("/api/files/unknown/list")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "不明なカテゴリ" in body["error"]

    def test_background_list_empty(self, api_client, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        resp = api_client.get("/api/files/background/list")
        body = resp.json()
        assert body["ok"] is True
        assert body["files"] == []
        assert body["active"] == ""

    def test_background_list_filters_by_extension(self, api_client, test_db, tmp_path, monkeypatch):
        _, bg, _ = _patch_categories(tmp_path, monkeypatch)
        (bg / "a.png").write_bytes(b"x")
        (bg / "b.jpg").write_bytes(b"x")
        (bg / "c.webp").write_bytes(b"x")
        (bg / "d.gif").write_bytes(b"x")
        (bg / "ignore.txt").write_text("skip")
        (bg / "ignore.vrm").write_bytes(b"x")

        resp = api_client.get("/api/files/background/list")
        body = resp.json()
        assert body["ok"] is True
        names = {f["file"] for f in body["files"]}
        assert names == {"a.png", "b.jpg", "c.webp", "d.gif"}

    def test_background_marks_active(self, api_client, test_db, tmp_path, monkeypatch):
        _, bg, _ = _patch_categories(tmp_path, monkeypatch)
        (bg / "active.png").write_bytes(b"x")
        (bg / "other.png").write_bytes(b"x")
        from src.scene_config import save_config_value
        save_config_value("files.active_background", "active.png")

        resp = api_client.get("/api/files/background/list")
        body = resp.json()
        files = {f["file"]: f for f in body["files"]}
        assert files["active.png"]["active"] is True
        assert files["other.png"]["active"] is False
        assert body["active"] == "active.png"

    def test_avatar_list_reads_vrm_from_character(self, api_client, test_db, tmp_path, monkeypatch):
        vrm, _, _ = _patch_categories(tmp_path, monkeypatch)
        (vrm / "teacher.vrm").write_bytes(b"x")
        (vrm / "student.vrm").write_bytes(b"x")

        char = _seed_character(test_db, "teacher")
        test_db.update_character_config_field(char["id"], "vrm", "teacher.vrm")

        resp = api_client.get("/api/files/avatar/list")
        body = resp.json()
        assert body["ok"] is True
        assert body["active"] == "teacher.vrm"
        files = {f["file"]: f for f in body["files"]}
        assert files["teacher.vrm"]["active"] is True
        assert files["student.vrm"]["active"] is False

    def test_avatar_list_falls_back_to_settings_key(self, api_client, test_db, tmp_path, monkeypatch):
        """characters に vrm 未設定なら files.active_avatar フォールバック"""
        vrm, _, _ = _patch_categories(tmp_path, monkeypatch)
        (vrm / "fallback.vrm").write_bytes(b"x")
        # teacher キャラは作成するが vrm フィールドは入れない
        _seed_character(test_db, "teacher")
        from src.scene_config import save_config_value
        save_config_value("files.active_avatar", "fallback.vrm")

        resp = api_client.get("/api/files/avatar/list")
        body = resp.json()
        assert body["active"] == "fallback.vrm"

    def test_creates_directory_if_missing(self, api_client, test_db, tmp_path, monkeypatch):
        """dir が無くても自動作成される"""
        import scripts.routes.files as files_mod
        import src.scene_config as sc

        missing = tmp_path / "not_yet"
        assert not missing.exists()
        monkeypatch.setattr(files_mod, "CATEGORIES", {
            "background": {
                "dir": missing,
                "extensions": {".png"},
                "config_key": "files.active_background",
            },
        })
        empty_config = tmp_path / "scenes.json"
        empty_config.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sc, "CONFIG_PATH", empty_config)

        resp = api_client.get("/api/files/background/list")
        assert resp.status_code == 200
        assert missing.exists()


class TestFilesUpload:
    """POST /api/files/{category}/upload"""

    def test_unknown_category(self, api_client, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        files = {"file": ("a.png", io.BytesIO(b"x"), "image/png")}
        resp = api_client.post("/api/files/unknown/upload", files=files)
        body = resp.json()
        assert body["ok"] is False
        assert "不明なカテゴリ" in body["error"]

    def test_unsupported_extension(self, api_client, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        files = {"file": ("evil.exe", io.BytesIO(b"x"), "application/octet-stream")}
        resp = api_client.post("/api/files/background/upload", files=files)
        body = resp.json()
        assert body["ok"] is False
        assert "対応していない" in body["error"]

    def test_saves_file_with_sanitized_name(self, api_client, test_db, tmp_path, monkeypatch):
        _, bg, _ = _patch_categories(tmp_path, monkeypatch)
        data = b"image-bytes"
        # Path.stem が先にディレクトリを剥がすので `/` はここでは試せない。
        # 代わりに `?` `*` `|` など _sanitize_filename が除去する文字を含める
        files = {"file": ('name?*|x.png', io.BytesIO(data), "image/png")}
        resp = api_client.post("/api/files/background/upload", files=files)
        body = resp.json()
        assert body["ok"] is True
        # 不正文字（?, *, |）が除去されて "namex.png"
        assert body["file"] == "namex.png"
        assert body["size"] == len(data)
        assert (bg / "namex.png").read_bytes() == data

    def test_appends_counter_on_collision(self, api_client, test_db, tmp_path, monkeypatch):
        _, bg, _ = _patch_categories(tmp_path, monkeypatch)
        (bg / "img.png").write_bytes(b"old")
        files = {"file": ("img.png", io.BytesIO(b"new"), "image/png")}
        resp = api_client.post("/api/files/background/upload", files=files)
        body = resp.json()
        assert body["ok"] is True
        assert body["file"] == "img_1.png"
        # 既存ファイルは上書きされない
        assert (bg / "img.png").read_bytes() == b"old"
        assert (bg / "img_1.png").read_bytes() == b"new"

    def test_extension_is_lowercased(self, api_client, test_db, tmp_path, monkeypatch):
        """大文字拡張子も対応リストと照合される（保存時は lower）"""
        _, bg, _ = _patch_categories(tmp_path, monkeypatch)
        files = {"file": ("photo.JPG", io.BytesIO(b"x"), "image/jpeg")}
        resp = api_client.post("/api/files/background/upload", files=files)
        body = resp.json()
        assert body["ok"] is True
        assert body["file"] == "photo.jpg"
        assert (bg / "photo.jpg").exists()


class TestFilesSelect:
    """POST /api/files/{category}/select"""

    def test_unknown_category(self, api_client, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        resp = api_client.post("/api/files/unknown/select", json={"file": "a.png"})
        body = resp.json()
        assert body["ok"] is False

    def test_missing_file_returns_error(self, api_client, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        resp = api_client.post(
            "/api/files/background/select",
            json={"file": "ghost.png"},
        )
        body = resp.json()
        assert body["ok"] is False
        assert "見つかりません" in body["error"]

    def test_background_select_saves_and_broadcasts(self, api_client, test_db, tmp_path, monkeypatch):
        _, bg, _ = _patch_categories(tmp_path, monkeypatch)
        (bg / "sel.png").write_bytes(b"x")
        import scripts.state as st

        resp = api_client.post(
            "/api/files/background/select",
            json={"file": "sel.png"},
        )
        body = resp.json()
        assert body["ok"] is True

        from src.scene_config import load_config_value
        assert load_config_value("files.active_background") == "sel.png"

        st.broadcast_to_broadcast.assert_called_once()
        event = st.broadcast_to_broadcast.call_args.args[0]
        assert event == {
            "type": "background_change",
            "url": "/resources/images/backgrounds/sel.png",
        }

    def test_avatar_select_updates_character_and_broadcasts(self, api_client, test_db, tmp_path, monkeypatch):
        vrm, _, _ = _patch_categories(tmp_path, monkeypatch)
        (vrm / "new.vrm").write_bytes(b"x")
        char = _seed_character(test_db, "teacher")
        import scripts.state as st

        resp = api_client.post(
            "/api/files/avatar/select",
            json={"file": "new.vrm"},
        )
        assert resp.json()["ok"] is True

        # characters.config.vrm が更新される
        row = test_db.get_character_by_id(char["id"])
        cfg = json.loads(row["config"])
        assert cfg["vrm"] == "new.vrm"

        st.broadcast_to_broadcast.assert_called_once_with({
            "type": "avatar_vrm_change",
            "url": "/resources/vrm/new.vrm",
        })

    def test_avatar2_select_updates_student_and_broadcasts(self, api_client, test_db, tmp_path, monkeypatch):
        vrm, _, _ = _patch_categories(tmp_path, monkeypatch)
        (vrm / "student.vrm").write_bytes(b"x")
        char = _seed_character(test_db, "student")
        import scripts.state as st

        resp = api_client.post(
            "/api/files/avatar2/select",
            json={"file": "student.vrm"},
        )
        assert resp.json()["ok"] is True

        row = test_db.get_character_by_id(char["id"])
        cfg = json.loads(row["config"])
        assert cfg["vrm"] == "student.vrm"

        st.broadcast_to_broadcast.assert_called_once_with({
            "type": "avatar2_vrm_change",
            "url": "/resources/vrm/student.vrm",
        })

    def test_teaching_select_does_not_broadcast(self, api_client, test_db, tmp_path, monkeypatch):
        _, _, teaching = _patch_categories(tmp_path, monkeypatch)
        (teaching / "mat.png").write_bytes(b"x")
        import scripts.state as st

        resp = api_client.post(
            "/api/files/teaching/select",
            json={"file": "mat.png"},
        )
        assert resp.json()["ok"] is True
        # teaching はブロードキャスト対象外
        st.broadcast_to_broadcast.assert_not_called()
        from src.scene_config import load_config_value
        assert load_config_value("files.active_teaching") == "mat.png"


class TestFilesDelete:
    """DELETE /api/files/{category}?file=..."""

    def test_unknown_category(self, api_client, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        resp = api_client.delete("/api/files/unknown?file=a.png")
        body = resp.json()
        assert body["ok"] is False

    def test_missing_file_returns_error(self, api_client, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        resp = api_client.delete("/api/files/background?file=ghost.png")
        body = resp.json()
        assert body["ok"] is False
        assert "見つかりません" in body["error"]

    def test_deletes_file(self, api_client, test_db, tmp_path, monkeypatch):
        _, bg, _ = _patch_categories(tmp_path, monkeypatch)
        target = bg / "delete_me.png"
        target.write_bytes(b"x")

        resp = api_client.delete("/api/files/background?file=delete_me.png")
        assert resp.json()["ok"] is True
        assert not target.exists()

    def test_clears_active_when_deleting_active_file(self, api_client, test_db, tmp_path, monkeypatch):
        _, bg, _ = _patch_categories(tmp_path, monkeypatch)
        target = bg / "active.png"
        target.write_bytes(b"x")
        from src.scene_config import save_config_value, load_config_value
        save_config_value("files.active_background", "active.png")

        resp = api_client.delete("/api/files/background?file=active.png")
        assert resp.json()["ok"] is True
        assert load_config_value("files.active_background") == ""

    def test_deleting_avatar_clears_character_config(self, api_client, test_db, tmp_path, monkeypatch):
        vrm, _, _ = _patch_categories(tmp_path, monkeypatch)
        target = vrm / "avatar.vrm"
        target.write_bytes(b"x")
        char = _seed_character(test_db, "teacher")
        test_db.update_character_config_field(char["id"], "vrm", "avatar.vrm")

        resp = api_client.delete("/api/files/avatar?file=avatar.vrm")
        assert resp.json()["ok"] is True

        row = test_db.get_character_by_id(char["id"])
        cfg = json.loads(row["config"])
        assert cfg["vrm"] == ""


class TestSanitizeFilename:
    """_sanitize_filename（ヘルパー）"""

    def test_removes_forbidden_chars(self):
        import scripts.routes.files as files_mod
        assert files_mod._sanitize_filename('bad/<name>?*:"|') == "badname"

    def test_empty_becomes_untitled(self):
        import scripts.routes.files as files_mod
        assert files_mod._sanitize_filename("") == "untitled"
        assert files_mod._sanitize_filename("...   ") == "untitled"

    def test_strips_leading_trailing_dots(self):
        import scripts.routes.files as files_mod
        assert files_mod._sanitize_filename(" ..foo.. ") == "foo"

    def test_truncates_to_200_chars(self):
        import scripts.routes.files as files_mod
        long_name = "a" * 400
        result = files_mod._sanitize_filename(long_name)
        assert len(result) == 200


class TestGetActiveVrm:
    """_get_active_vrm（ヘルパー・characters優先 → settings フォールバック）"""

    def test_returns_vrm_from_character_config(self, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        import scripts.routes.files as files_mod
        char = _seed_character(test_db, "teacher")
        test_db.update_character_config_field(char["id"], "vrm", "from_char.vrm")

        assert files_mod._get_active_vrm("avatar") == "from_char.vrm"

    def test_falls_back_to_settings_when_no_character(self, test_db, tmp_path, monkeypatch):
        """character が無い場合 → files.active_avatar を返す"""
        _patch_categories(tmp_path, monkeypatch)
        import scripts.routes.files as files_mod
        from src.scene_config import save_config_value
        save_config_value("files.active_avatar", "fallback.vrm")

        assert files_mod._get_active_vrm("avatar") == "fallback.vrm"

    def test_returns_empty_for_unmapped_category(self, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        import scripts.routes.files as files_mod
        assert files_mod._get_active_vrm("background") == ""


class TestSetActiveVrm:
    """_set_active_vrm（ヘルパー）"""

    def test_updates_character_config(self, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        import scripts.routes.files as files_mod
        char = _seed_character(test_db, "teacher")

        files_mod._set_active_vrm("avatar", "my.vrm")

        row = test_db.get_character_by_id(char["id"])
        cfg = json.loads(row["config"])
        assert cfg["vrm"] == "my.vrm"

    def test_fallback_to_settings_when_no_character(self, test_db, tmp_path, monkeypatch):
        _patch_categories(tmp_path, monkeypatch)
        import scripts.routes.files as files_mod
        from src.db import get_setting

        files_mod._set_active_vrm("avatar", "settings.vrm")
        assert get_setting("files.active_avatar") == "settings.vrm"
