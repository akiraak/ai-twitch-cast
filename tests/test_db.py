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
            "bgm_tracks", "topics", "topic_scripts",
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
        cid = test_db.save_comment(ep_id, user_id, "こんにちは", "やほー！", "joy")
        assert cid is not None

    def test_get_recent_comments(self, test_db):
        ep_id, user_id = self._setup(test_db)
        test_db.save_comment(ep_id, user_id, "msg1", "res1")
        test_db.save_comment(ep_id, user_id, "msg2", "res2")
        recent = test_db.get_recent_comments(limit=10)
        assert len(recent) == 2
        # 時系列順（古い→新しい）
        assert recent[0]["message"] == "msg1"
        assert recent[1]["message"] == "msg2"

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
        test_db.save_comment(ep_id, user_id, "hello", "hi!")
        results = test_db.get_user_recent_comments("viewer")
        assert len(results) == 1
        assert results[0]["message"] == "hello"
        assert results[0]["response"] == "hi!"


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


class TestTopics:
    def test_create_topic(self, test_db):
        topic = test_db.create_topic("Python", "Pythonについて話す")
        assert topic["title"] == "Python"
        assert topic["status"] == "active"

    def test_get_active_topic(self, test_db):
        test_db.create_topic("topic1")
        test_db.create_topic("topic2")
        active = test_db.get_active_topic()
        # 最新のアクティブトピック
        assert active["title"] == "topic2"

    def test_get_active_topic_none(self, test_db):
        assert test_db.get_active_topic() is None

    def test_deactivate_topic(self, test_db):
        topic = test_db.create_topic("topic")
        test_db.deactivate_topic(topic["id"])
        assert test_db.get_active_topic() is None

    def test_deactivate_all(self, test_db):
        test_db.create_topic("t1")
        test_db.create_topic("t2")
        test_db.deactivate_all_topics()
        assert test_db.get_active_topic() is None


class TestTopicScripts:
    def test_add_and_get_scripts(self, test_db):
        topic = test_db.create_topic("topic")
        scripts = [
            {"content": "セリフ1", "emotion": "joy", "sort_order": 0},
            {"content": "セリフ2", "emotion": "neutral", "sort_order": 1},
        ]
        test_db.add_topic_scripts(topic["id"], scripts)
        all_scripts = test_db.get_all_scripts(topic["id"])
        assert len(all_scripts) == 2
        assert all_scripts[0]["content"] == "セリフ1"
        assert all_scripts[1]["content"] == "セリフ2"

    def test_next_unspoken(self, test_db):
        topic = test_db.create_topic("topic")
        test_db.add_topic_scripts(topic["id"], [
            {"content": "first", "sort_order": 0},
            {"content": "second", "sort_order": 1},
        ])
        script = test_db.get_next_unspoken_script(topic["id"])
        assert script["content"] == "first"

    def test_mark_spoken(self, test_db):
        topic = test_db.create_topic("topic")
        test_db.add_topic_scripts(topic["id"], [
            {"content": "line1", "sort_order": 0},
            {"content": "line2", "sort_order": 1},
        ])
        first = test_db.get_next_unspoken_script(topic["id"])
        test_db.mark_script_spoken(first["id"])
        next_script = test_db.get_next_unspoken_script(topic["id"])
        assert next_script["content"] == "line2"

    def test_count_unspoken(self, test_db):
        topic = test_db.create_topic("topic")
        test_db.add_topic_scripts(topic["id"], [
            {"content": "a", "sort_order": 0},
            {"content": "b", "sort_order": 1},
        ])
        assert test_db.count_unspoken_scripts(topic["id"]) == 2
        first = test_db.get_next_unspoken_script(topic["id"])
        test_db.mark_script_spoken(first["id"])
        assert test_db.count_unspoken_scripts(topic["id"]) == 1

    def test_get_spoken_scripts(self, test_db):
        topic = test_db.create_topic("topic")
        test_db.add_topic_scripts(topic["id"], [
            {"content": "a", "sort_order": 0},
        ])
        assert test_db.get_spoken_scripts(topic["id"]) == []
        script = test_db.get_next_unspoken_script(topic["id"])
        test_db.mark_script_spoken(script["id"])
        spoken = test_db.get_spoken_scripts(topic["id"])
        assert len(spoken) == 1
        assert spoken[0]["content"] == "a"

    def test_no_unspoken_returns_none(self, test_db):
        topic = test_db.create_topic("topic")
        assert test_db.get_next_unspoken_script(topic["id"]) is None

    def test_default_emotion(self, test_db):
        topic = test_db.create_topic("topic")
        test_db.add_topic_scripts(topic["id"], [{"content": "text"}])
        script = test_db.get_next_unspoken_script(topic["id"])
        assert script["emotion"] == "neutral"
