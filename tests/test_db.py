"""db.py のテスト（インメモリSQLite使用）"""

import json


class TestSchema:
    """テーブル作成・マイグレーションのテスト"""

    def test_tables_created(self, test_db):
        conn = test_db.get_connection()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in rows}
        expected = {
            "channels", "characters", "shows", "episodes",
            "users", "comments", "actions", "settings",
            "bgm_tracks", "se_tracks",
            "custom_texts", "character_memory",
            "lessons", "lesson_sources", "lesson_sections",
        }
        assert expected.issubset(names)

    def test_wal_mode_enabled(self, test_db):
        conn = test_db.get_connection()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_foreign_keys_enabled(self, test_db):
        conn = test_db.get_connection()
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

    def test_users_has_migration_columns(self, test_db):
        conn = test_db.get_connection()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        assert "display_name" in cols
        assert "note" in cols
        assert "last_seen" in cols

    def test_characters_has_updated_at(self, test_db):
        conn = test_db.get_connection()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(characters)").fetchall()}
        assert "updated_at" in cols


class TestChannels:
    def test_create_and_get(self, test_db):
        ch = test_db.get_or_create_channel("test_ch")
        assert ch["name"] == "test_ch"
        assert ch["id"] is not None

    def test_idempotent(self, test_db):
        ch1 = test_db.get_or_create_channel("ch")
        ch2 = test_db.get_or_create_channel("ch")
        assert ch1["id"] == ch2["id"]


class TestCharacters:
    def test_create_and_get(self, test_db):
        ch = test_db.get_or_create_channel("ch")
        char = test_db.get_or_create_character(ch["id"], "ちょビ", '{"name":"ちょビ"}')
        assert char["name"] == "ちょビ"
        assert char["channel_id"] == ch["id"]

    def test_idempotent(self, test_db):
        ch = test_db.get_or_create_channel("ch")
        c1 = test_db.get_or_create_character(ch["id"], "name")
        c2 = test_db.get_or_create_character(ch["id"], "name")
        assert c1["id"] == c2["id"]

    def test_get_by_channel(self, test_db):
        ch = test_db.get_or_create_channel("ch")
        test_db.get_or_create_character(ch["id"], "char1")
        result = test_db.get_character_by_channel(ch["id"])
        assert result["name"] == "char1"

    def test_get_by_channel_empty(self, test_db):
        assert test_db.get_character_by_channel(999) is None

    def test_update_name(self, test_db):
        ch = test_db.get_or_create_channel("ch")
        char = test_db.get_or_create_character(ch["id"], "old_name")
        test_db.update_character(char["id"], name="new_name")
        updated = test_db.get_character_by_channel(ch["id"])
        assert updated["name"] == "new_name"

    def test_update_config(self, test_db):
        ch = test_db.get_or_create_channel("ch")
        char = test_db.get_or_create_character(ch["id"], "char")
        new_config = json.dumps({"key": "value"})
        test_db.update_character(char["id"], config=new_config)
        updated = test_db.get_character_by_channel(ch["id"])
        assert json.loads(updated["config"]) == {"key": "value"}

    def test_update_nothing(self, test_db):
        """引数なしでupdate_characterを呼んでもエラーにならない"""
        ch = test_db.get_or_create_channel("ch")
        char = test_db.get_or_create_character(ch["id"], "char")
        test_db.update_character(char["id"])  # no-op


class TestShows:
    def test_create_and_get(self, test_db):
        ch = test_db.get_or_create_channel("ch")
        show = test_db.get_or_create_show(ch["id"], "show1", "desc")
        assert show["name"] == "show1"
        assert show["description"] == "desc"

    def test_idempotent(self, test_db):
        ch = test_db.get_or_create_channel("ch")
        s1 = test_db.get_or_create_show(ch["id"], "show")
        s2 = test_db.get_or_create_show(ch["id"], "show")
        assert s1["id"] == s2["id"]


class TestEpisodes:
    def _setup_episode(self, test_db):
        ch = test_db.get_or_create_channel("ch")
        char = test_db.get_or_create_character(ch["id"], "char")
        show = test_db.get_or_create_show(ch["id"], "show")
        return show["id"], char["id"]

    def test_start_episode(self, test_db):
        show_id, char_id = self._setup_episode(test_db)
        ep = test_db.start_episode(show_id, char_id, "テスト配信")
        assert ep["title"] == "テスト配信"
        assert ep["started_at"] is not None
        assert ep["ended_at"] is None

    def test_end_episode(self, test_db):
        show_id, char_id = self._setup_episode(test_db)
        ep = test_db.start_episode(show_id, char_id)
        test_db.end_episode(ep["id"])
        conn = test_db.get_connection()
        row = conn.execute("SELECT * FROM episodes WHERE id = ?", (ep["id"],)).fetchone()
        assert row["ended_at"] is not None


class TestUsers:
    def test_create_and_get(self, test_db):
        user = test_db.get_or_create_user("testuser")
        assert user["name"] == "testuser"
        assert user["comment_count"] == 0

    def test_idempotent(self, test_db):
        u1 = test_db.get_or_create_user("user")
        u2 = test_db.get_or_create_user("user")
        assert u1["id"] == u2["id"]

    def test_increment_comment_count(self, test_db):
        user = test_db.get_or_create_user("user")
        test_db.increment_comment_count(user["id"])
        test_db.increment_comment_count(user["id"])
        count = test_db.get_user_comment_count("user")
        assert count == 2

    def test_comment_count_unknown_user(self, test_db):
        assert test_db.get_user_comment_count("nobody") == 0

    def test_update_note(self, test_db):
        user = test_db.get_or_create_user("user")
        test_db.update_user_note(user["id"], "テストメモ")
        conn = test_db.get_connection()
        row = conn.execute("SELECT note FROM users WHERE id = ?", (user["id"],)).fetchone()
        assert row["note"] == "テストメモ"

    def test_update_last_seen(self, test_db):
        user = test_db.get_or_create_user("user")
        test_db.update_user_last_seen(user["id"])
        conn = test_db.get_connection()
        row = conn.execute("SELECT last_seen FROM users WHERE id = ?", (user["id"],)).fetchone()
        assert row["last_seen"] is not None


class TestComments:
    def _setup(self, test_db):
        ch = test_db.get_or_create_channel("ch")
        char = test_db.get_or_create_character(ch["id"], "char")
        show = test_db.get_or_create_show(ch["id"], "show")
        ep = test_db.start_episode(show["id"], char["id"])
        user = test_db.get_or_create_user("viewer")
        return ep["id"], user["id"]

    def test_save_comment(self, test_db):
        ep_id, user_id = self._setup(test_db)
        cid = test_db.save_comment(ep_id, user_id, "こんにちは")
        assert cid is not None

    def test_get_recent_comments(self, test_db):
        ep_id, user_id = self._setup(test_db)
        test_db.save_comment(ep_id, user_id, "msg1")
        test_db.save_comment(ep_id, user_id, "msg2")
        recent = test_db.get_recent_comments(limit=10)
        assert len(recent) == 2
        # 時系列順（古い→新しい）
        assert recent[0]["text"] == "msg1"
        assert recent[1]["text"] == "msg2"

    def test_recent_comments_limit(self, test_db):
        ep_id, user_id = self._setup(test_db)
        for i in range(5):
            test_db.save_comment(ep_id, user_id, f"msg{i}")
        recent = test_db.get_recent_comments(limit=3)
        assert len(recent) == 3

    def test_count_user_comments_in_episode(self, test_db):
        ep_id, user_id = self._setup(test_db)
        assert test_db.count_user_comments_in_episode(ep_id, user_id) == 0
        test_db.save_comment(ep_id, user_id, "a")
        test_db.save_comment(ep_id, user_id, "b")
        assert test_db.count_user_comments_in_episode(ep_id, user_id) == 2

    def test_get_user_recent_comments(self, test_db):
        ep_id, user_id = self._setup(test_db)
        test_db.save_comment(ep_id, user_id, "hello")
        results = test_db.get_user_recent_comments("viewer")
        assert len(results) == 1
        assert results[0]["text"] == "hello"

    def test_save_avatar_comment(self, test_db):
        ep_id, _ = self._setup(test_db)
        cid = test_db.save_avatar_comment(ep_id, "comment", "aliceさんのコメント: hi", "やほー！", "joy")
        assert cid is not None

    def test_get_recent_avatar_comments(self, test_db):
        ep_id, _ = self._setup(test_db)
        test_db.save_avatar_comment(ep_id, "comment", "trigger1", "speech1")
        test_db.save_avatar_comment(ep_id, "event", "trigger2", "speech2")
        all_ac = test_db.get_recent_avatar_comments(limit=10)
        assert len(all_ac) == 2
        # trigger_typeフィルタ
        events = test_db.get_recent_avatar_comments(limit=10, trigger_type="event")
        assert len(events) == 1
        assert events[0]["text"] == "speech2"

    def test_get_recent_timeline(self, test_db):
        ep_id, user_id = self._setup(test_db)
        test_db.save_comment(ep_id, user_id, "hello")
        test_db.save_avatar_comment(ep_id, "comment", "viewerさんのコメント: hello", "hi!")
        timeline = test_db.get_recent_timeline(limit=10)
        assert len(timeline) == 2
        assert timeline[0]["type"] == "comment"
        assert timeline[0]["text"] == "hello"
        assert timeline[1]["type"] == "avatar_comment"
        assert timeline[1]["text"] == "hi!"


    def test_clear_comments(self, test_db):
        ep_id, user_id = self._setup(test_db)
        test_db.save_comment(ep_id, user_id, "msg1")
        test_db.save_comment(ep_id, user_id, "msg2")
        assert len(test_db.get_recent_comments(limit=10)) == 2
        test_db.clear_comments()
        assert len(test_db.get_recent_comments(limit=10)) == 0

    def test_clear_avatar_comments(self, test_db):
        ep_id, _ = self._setup(test_db)
        test_db.save_avatar_comment(ep_id, "comment", "trigger", "speech1")
        test_db.save_avatar_comment(ep_id, "event", "trigger2", "speech2")
        assert len(test_db.get_recent_avatar_comments(limit=10)) == 2
        test_db.clear_avatar_comments()
        assert len(test_db.get_recent_avatar_comments(limit=10)) == 0


class TestSettings:
    def test_set_and_get(self, test_db):
        test_db.set_setting("key1", "value1")
        assert test_db.get_setting("key1") == "value1"

    def test_get_default(self, test_db):
        assert test_db.get_setting("nonexistent") is None
        assert test_db.get_setting("nonexistent", "default") == "default"

    def test_upsert(self, test_db):
        test_db.set_setting("key", "old")
        test_db.set_setting("key", "new")
        assert test_db.get_setting("key") == "new"

    def test_get_by_prefix(self, test_db):
        test_db.set_setting("volume.master", "0.8")
        test_db.set_setting("volume.tts", "0.5")
        test_db.set_setting("other.key", "val")
        result = test_db.get_settings_by_prefix("volume.")
        assert result == {"volume.master": "0.8", "volume.tts": "0.5"}

    def test_stores_as_string(self, test_db):
        test_db.set_setting("num", 42)
        assert test_db.get_setting("num") == "42"


class TestSeTracks:
    def test_upsert_and_get_all(self, test_db):
        test_db.upsert_se_track("greeting.wav", category="greeting", description="挨拶", volume=0.8, duration=0.6)
        tracks = test_db.get_all_se_tracks()
        assert "greeting.wav" in tracks
        assert tracks["greeting.wav"]["category"] == "greeting"
        assert tracks["greeting.wav"]["volume"] == 0.8
        assert tracks["greeting.wav"]["duration"] == 0.6

    def test_get_by_category(self, test_db):
        test_db.upsert_se_track("a.wav", category="surprise", volume=1.0, duration=0.5)
        test_db.upsert_se_track("b.wav", category="surprise", volume=0.9, duration=0.7)
        test_db.upsert_se_track("c.wav", category="greeting", volume=1.0, duration=0.6)
        results = test_db.get_se_tracks_by_category("surprise")
        assert len(results) == 2
        filenames = {r["filename"] for r in results}
        assert filenames == {"a.wav", "b.wav"}

    def test_get_by_category_empty(self, test_db):
        assert test_db.get_se_tracks_by_category("nonexistent") == []

    def test_upsert_updates(self, test_db):
        test_db.upsert_se_track("test.wav", category="old", volume=0.5, duration=1.0)
        test_db.upsert_se_track("test.wav", category="new", volume=0.8, duration=1.5)
        tracks = test_db.get_all_se_tracks()
        assert tracks["test.wav"]["category"] == "new"
        assert tracks["test.wav"]["volume"] == 0.8
        assert tracks["test.wav"]["duration"] == 1.5

    def test_delete(self, test_db):
        test_db.upsert_se_track("del.wav", category="test")
        test_db.delete_se_track("del.wav")
        assert "del.wav" not in test_db.get_all_se_tracks()

    def test_delete_nonexistent(self, test_db):
        # エラーにならない
        test_db.delete_se_track("nonexistent.wav")

    def test_default_values(self, test_db):
        test_db.upsert_se_track("default.wav")
        tracks = test_db.get_all_se_tracks()
        assert tracks["default.wav"]["category"] == ""
        assert tracks["default.wav"]["description"] == ""
        assert tracks["default.wav"]["volume"] == 1.0
        assert tracks["default.wav"]["duration"] == 1.0


class TestBgmTracks:
    def test_default_volume(self, test_db):
        assert test_db.get_bgm_track_volume("unknown.mp3") == 1.0

    def test_set_and_get_volume(self, test_db):
        test_db.set_bgm_track_volume("song.mp3", 0.7)
        assert test_db.get_bgm_track_volume("song.mp3") == 0.7

    def test_upsert_volume(self, test_db):
        test_db.set_bgm_track_volume("song.mp3", 0.5)
        test_db.set_bgm_track_volume("song.mp3", 0.9)
        assert test_db.get_bgm_track_volume("song.mp3") == 0.9

    def test_get_all_volumes(self, test_db):
        test_db.set_bgm_track_volume("a.mp3", 0.3)
        test_db.set_bgm_track_volume("b.mp3", 0.8)
        result = test_db.get_all_bgm_track_volumes()
        assert result == {"a.mp3": 0.3, "b.mp3": 0.8}

    def test_delete_volume(self, test_db):
        test_db.set_bgm_track_volume("song.mp3", 0.5)
        test_db.delete_bgm_track_volume("song.mp3")
        assert test_db.get_bgm_track_volume("song.mp3") == 1.0


class TestActions:
    def test_save_action(self, test_db):
        ch = test_db.get_or_create_channel("ch")
        char = test_db.get_or_create_character(ch["id"], "char")
        show = test_db.get_or_create_show(ch["id"], "show")
        ep = test_db.start_episode(show["id"], char["id"])
        aid = test_db.save_action(ep["id"], "commit", "fix bug")
        assert aid is not None


class TestCustomTexts:
    """カスタムテキストのテスト"""

    def test_create_and_list(self, test_db):
        item = test_db.create_custom_text(label="test", content="hello")
        assert item["id"] is not None
        assert item["label"] == "test"
        assert item["content"] == "hello"
        assert item["layout"]["x"] == 5
        items = test_db.get_custom_texts()
        assert len(items) == 1
        assert items[0]["label"] == "test"

    def test_create_with_layout(self, test_db):
        item = test_db.create_custom_text(
            label="a", content="b",
            layout={"x": 30, "y": 40, "width": 25, "fontSize": 2.0},
        )
        assert item["layout"]["x"] == 30
        assert item["layout"]["y"] == 40
        assert item["layout"]["width"] == 25
        assert item["layout"]["fontSize"] == 2.0

    def test_update(self, test_db):
        item = test_db.create_custom_text(label="old", content="x")
        test_db.update_custom_text(item["id"], label="new", content="updated")
        items = test_db.get_custom_texts()
        assert items[0]["label"] == "new"
        assert items[0]["content"] == "updated"

    def test_update_layout(self, test_db):
        item = test_db.create_custom_text()
        test_db.update_custom_text_layout(item["id"], {"x": 50, "y": 60})
        items = test_db.get_custom_texts()
        assert items[0]["layout"]["x"] == 50
        assert items[0]["layout"]["y"] == 60

    def test_delete(self, test_db):
        item = test_db.create_custom_text(label="del")
        test_db.delete_custom_text(item["id"])
        assert test_db.get_custom_texts() == []

    def test_multiple_items(self, test_db):
        test_db.create_custom_text(label="a")
        test_db.create_custom_text(label="b")
        test_db.create_custom_text(label="c")
        assert len(test_db.get_custom_texts()) == 3


class TestChildPanels:
    """子パネルのCRUDテスト"""

    def _ensure_parent(self, test_db):
        """テスト用の親パネルを作成"""
        test_db.upsert_broadcast_item("avatar", "avatar", {
            "positionX": 46.5, "positionY": 24.3,
            "width": 53.5, "height": 75.7,
        })
        return "avatar"

    def test_create_child(self, test_db):
        parent_id = self._ensure_parent(test_db)
        child = test_db.create_child_item(parent_id, {
            "type": "child_text",
            "label": "バージョン",
            "content": "v1.0",
        })
        assert child is not None
        assert child["id"] == f"child:{parent_id}:1"
        assert child["type"] == "child_text"
        assert child["label"] == "バージョン"
        assert child["parentId"] == parent_id
        assert child.get("content") == "v1.0"

    def test_create_multiple_children(self, test_db):
        parent_id = self._ensure_parent(test_db)
        c1 = test_db.create_child_item(parent_id, {"label": "テスト1"})
        c2 = test_db.create_child_item(parent_id, {"label": "テスト2"})
        assert c1["id"] == f"child:{parent_id}:1"
        assert c2["id"] == f"child:{parent_id}:2"

    def test_get_child_items(self, test_db):
        parent_id = self._ensure_parent(test_db)
        test_db.create_child_item(parent_id, {"label": "子A"})
        test_db.create_child_item(parent_id, {"label": "子B"})
        children = test_db.get_child_items(parent_id)
        assert len(children) == 2
        assert children[0]["label"] == "子A"
        assert children[1]["label"] == "子B"

    def test_children_not_in_root_items(self, test_db):
        parent_id = self._ensure_parent(test_db)
        test_db.create_child_item(parent_id, {"label": "子パネル"})
        # get_broadcast_items()はルートアイテムのみ返す
        items = test_db.get_broadcast_items()
        child_items = [i for i in items if i["id"].startswith("child:")]
        assert len(child_items) == 0

    def test_children_in_all_items(self, test_db):
        parent_id = self._ensure_parent(test_db)
        test_db.create_child_item(parent_id, {"label": "子パネル"})
        items = test_db.get_all_broadcast_items()
        child_items = [i for i in items if i["id"].startswith("child:")]
        assert len(child_items) == 1

    def test_delete_child(self, test_db):
        parent_id = self._ensure_parent(test_db)
        child = test_db.create_child_item(parent_id, {"label": "削除対象"})
        test_db.delete_child_item(child["id"])
        assert test_db.get_child_items(parent_id) == []

    def test_cascade_delete(self, test_db):
        parent_id = self._ensure_parent(test_db)
        test_db.create_child_item(parent_id, {"label": "子1"})
        test_db.create_child_item(parent_id, {"label": "子2"})
        test_db.delete_broadcast_item_cascade(parent_id)
        assert test_db.get_child_items(parent_id) == []
        assert test_db.get_broadcast_item(parent_id) is None

    def test_create_child_nonexistent_parent(self, test_db):
        result = test_db.create_child_item("nonexistent", {"label": "テスト"})
        assert result is None

    def test_child_default_values(self, test_db):
        parent_id = self._ensure_parent(test_db)
        child = test_db.create_child_item(parent_id, {})
        assert child["positionX"] == 5
        assert child["positionY"] == 75
        assert child["width"] == 90
        assert child["height"] == 20
        assert child["fontSize"] == 0.8

    def test_child_custom_values(self, test_db):
        parent_id = self._ensure_parent(test_db)
        child = test_db.create_child_item(parent_id, {
            "positionX": 10,
            "positionY": 50,
            "width": 80,
            "height": 30,
            "fontSize": 1.2,
            "textColor": "#ff0000",
        })
        assert child["positionX"] == 10
        assert child["positionY"] == 50
        assert child["width"] == 80
        assert child["height"] == 30
        assert child["fontSize"] == 1.2
        assert child["textColor"] == "#ff0000"


class TestCharacterMemory:
    """character_memory テーブルのテスト"""

    def _make_char(self, test_db):
        ch = test_db.get_or_create_channel("ch")
        return test_db.get_or_create_character(ch["id"], "ちょビ", '{"name":"ちょビ"}')

    def test_get_creates_empty(self, test_db):
        char = self._make_char(test_db)
        mem = test_db.get_character_memory(char["id"])
        assert mem["persona"] == ""
        assert mem["self_note"] == ""
        assert "updated_at" in mem

    def test_update_persona(self, test_db):
        char = self._make_char(test_db)
        test_db.update_character_persona(char["id"], "明るい性格")
        mem = test_db.get_character_memory(char["id"])
        assert mem["persona"] == "明るい性格"
        assert mem["self_note"] == ""

    def test_update_self_note(self, test_db):
        char = self._make_char(test_db)
        test_db.update_character_self_note(char["id"], "今日はゲームの話で盛り上がった")
        mem = test_db.get_character_memory(char["id"])
        assert mem["self_note"] == "今日はゲームの話で盛り上がった"
        assert mem["persona"] == ""

    def test_upsert_preserves_other_field(self, test_db):
        char = self._make_char(test_db)
        test_db.update_character_persona(char["id"], "好奇心旺盛")
        test_db.update_character_self_note(char["id"], "AIの話をした")
        mem = test_db.get_character_memory(char["id"])
        assert mem["persona"] == "好奇心旺盛"
        assert mem["self_note"] == "AIの話をした"

    def test_character_id_unique(self, test_db):
        char = self._make_char(test_db)
        test_db.get_character_memory(char["id"])
        # 2回目の get でも1行のまま
        test_db.get_character_memory(char["id"])
        conn = test_db.get_connection()
        cnt = conn.execute(
            "SELECT COUNT(*) as c FROM character_memory WHERE character_id = ?",
            (char["id"],),
        ).fetchone()["c"]
        assert cnt == 1


class TestLessons:
    def test_create_and_get(self, test_db):
        lesson = test_db.create_lesson("English 1-1")
        assert lesson["name"] == "English 1-1"
        assert lesson["id"] is not None
        fetched = test_db.get_lesson(lesson["id"])
        assert fetched["name"] == "English 1-1"

    def test_get_all(self, test_db):
        test_db.create_lesson("A")
        test_db.create_lesson("B")
        all_lessons = test_db.get_all_lessons()
        assert len(all_lessons) == 2

    def test_update(self, test_db):
        lesson = test_db.create_lesson("Old")
        test_db.update_lesson(lesson["id"], name="New")
        fetched = test_db.get_lesson(lesson["id"])
        assert fetched["name"] == "New"

    def test_delete(self, test_db):
        lesson = test_db.create_lesson("ToDelete")
        test_db.delete_lesson(lesson["id"])
        assert test_db.get_lesson(lesson["id"]) is None

    def test_get_nonexistent(self, test_db):
        assert test_db.get_lesson(9999) is None


class TestLessonSources:
    def test_add_and_get(self, test_db):
        lesson = test_db.create_lesson("SrcTest")
        src = test_db.add_lesson_source(
            lesson["id"], "image", file_path="resources/images/lessons/1/test.png",
            original_name="test.png",
        )
        assert src["source_type"] == "image"
        sources = test_db.get_lesson_sources(lesson["id"])
        assert len(sources) == 1

    def test_add_url_source(self, test_db):
        lesson = test_db.create_lesson("UrlTest")
        src = test_db.add_lesson_source(
            lesson["id"], "url", url="https://example.com",
        )
        assert src["source_type"] == "url"
        assert src["url"] == "https://example.com"

    def test_delete(self, test_db):
        lesson = test_db.create_lesson("DelSrc")
        src = test_db.add_lesson_source(lesson["id"], "image")
        test_db.delete_lesson_source(src["id"])
        assert len(test_db.get_lesson_sources(lesson["id"])) == 0

    def test_cascade_delete(self, test_db):
        lesson = test_db.create_lesson("Cascade")
        test_db.add_lesson_source(lesson["id"], "image")
        test_db.add_lesson_source(lesson["id"], "url")
        test_db.delete_lesson(lesson["id"])
        assert len(test_db.get_lesson_sources(lesson["id"])) == 0


class TestLessonSections:
    def test_add_and_get(self, test_db):
        lesson = test_db.create_lesson("SecTest")
        s = test_db.add_lesson_section(
            lesson["id"], 0, "introduction", "はじめに",
            tts_text="はじめにTTS", display_text="導入",
        )
        assert s["section_type"] == "introduction"
        assert s["content"] == "はじめに"
        sections = test_db.get_lesson_sections(lesson["id"])
        assert len(sections) == 1

    def test_order(self, test_db):
        lesson = test_db.create_lesson("OrderTest")
        test_db.add_lesson_section(lesson["id"], 1, "explanation", "説明")
        test_db.add_lesson_section(lesson["id"], 0, "introduction", "導入")
        sections = test_db.get_lesson_sections(lesson["id"])
        assert sections[0]["section_type"] == "introduction"
        assert sections[1]["section_type"] == "explanation"

    def test_update(self, test_db):
        lesson = test_db.create_lesson("UpdSec")
        s = test_db.add_lesson_section(lesson["id"], 0, "explanation", "元")
        test_db.update_lesson_section(s["id"], content="更新後", emotion="excited")
        sections = test_db.get_lesson_sections(lesson["id"])
        assert sections[0]["content"] == "更新後"
        assert sections[0]["emotion"] == "excited"

    def test_delete(self, test_db):
        lesson = test_db.create_lesson("DelSec")
        s = test_db.add_lesson_section(lesson["id"], 0, "explanation", "削除対象")
        test_db.delete_lesson_section(s["id"])
        assert len(test_db.get_lesson_sections(lesson["id"])) == 0

    def test_delete_all(self, test_db):
        lesson = test_db.create_lesson("DelAll")
        test_db.add_lesson_section(lesson["id"], 0, "introduction", "A")
        test_db.add_lesson_section(lesson["id"], 1, "explanation", "B")
        test_db.delete_lesson_sections(lesson["id"])
        assert len(test_db.get_lesson_sections(lesson["id"])) == 0

    def test_reorder(self, test_db):
        lesson = test_db.create_lesson("Reorder")
        s1 = test_db.add_lesson_section(lesson["id"], 0, "introduction", "A")
        s2 = test_db.add_lesson_section(lesson["id"], 1, "explanation", "B")
        s3 = test_db.add_lesson_section(lesson["id"], 2, "summary", "C")
        # 逆順
        test_db.reorder_lesson_sections(lesson["id"], [s3["id"], s2["id"], s1["id"]])
        sections = test_db.get_lesson_sections(lesson["id"])
        assert sections[0]["id"] == s3["id"]
        assert sections[1]["id"] == s2["id"]
        assert sections[2]["id"] == s1["id"]

    def test_question_fields(self, test_db):
        lesson = test_db.create_lesson("QTest")
        s = test_db.add_lesson_section(
            lesson["id"], 0, "question", "問題",
            question="What is 1+1?", answer="2", wait_seconds=10,
        )
        assert s["question"] == "What is 1+1?"
        assert s["answer"] == "2"
        assert s["wait_seconds"] == 10
