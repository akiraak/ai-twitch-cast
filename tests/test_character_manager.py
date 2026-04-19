"""character_manager のテスト（キャラクターDB操作・キャッシュ・マイグレーション）

対象: src/character_manager.py
"""

import json

from src.character_manager import (
    DEFAULT_CHARACTER,
    DEFAULT_CHARACTER_NAME,
    DEFAULT_STUDENT_CHARACTER,
    DEFAULT_STUDENT_CHARACTER_NAME,
    build_all_character_contexts,
    build_character_context,
    get_all_characters,
    get_channel_id,
    get_character,
    get_character_id,
    get_chat_characters,
    get_tts_config,
    invalidate_character_cache,
    load_character,
    seed_all_characters,
    seed_character,
)
from src.prompt_builder import set_stream_language


class TestDefaultConstants:
    """モジュール定数の整合性確認（DBとは無関係）"""

    def test_default_character_has_required_fields(self):
        required = {
            "role", "tts_voice", "tts_style",
            "system_prompt", "emotions", "emotion_blendshapes",
        }
        assert required.issubset(DEFAULT_CHARACTER.keys())
        assert DEFAULT_CHARACTER["role"] == "teacher"

    def test_default_student_character_has_required_fields(self):
        required = {
            "role", "tts_voice", "tts_style",
            "system_prompt", "emotions",
        }
        assert required.issubset(DEFAULT_STUDENT_CHARACTER.keys())
        assert DEFAULT_STUDENT_CHARACTER["role"] == "student"

    def test_teacher_and_student_use_different_voices(self):
        # 同じ声だと判別できないので異なることを保証
        assert DEFAULT_CHARACTER["tts_voice"] != DEFAULT_STUDENT_CHARACTER["tts_voice"]


class TestGetChannelId:
    def test_uses_twitch_channel_env(self, test_db, mock_env, monkeypatch):
        monkeypatch.setenv("TWITCH_CHANNEL", "my_channel_xyz")
        cid = get_channel_id()
        # 同名チャンネルを直接 DB から引いて一致を確認
        row = test_db.get_or_create_channel("my_channel_xyz")
        assert cid == row["id"]

    def test_defaults_when_env_missing(self, test_db, monkeypatch):
        monkeypatch.delenv("TWITCH_CHANNEL", raising=False)
        cid = get_channel_id()
        row = test_db.get_or_create_channel("default")
        assert cid == row["id"]


class TestSeedCharacter:
    def setup_method(self):
        invalidate_character_cache()

    def test_seed_character_creates(self, test_db):
        ch = test_db.get_or_create_channel("ch_a")
        char = seed_character(ch["id"])
        assert char["name"] == DEFAULT_CHARACTER_NAME
        # configに emotions が入っている
        cfg = json.loads(char["config"])
        assert "emotions" in cfg

    def test_seed_character_idempotent(self, test_db):
        ch = test_db.get_or_create_channel("ch_a")
        c1 = seed_character(ch["id"])
        c2 = seed_character(ch["id"])
        assert c1["id"] == c2["id"]

    def test_seed_character_returns_existing_only_if_same_channel(self, test_db):
        """他チャンネル由来のフォールバック行は採用しない（同じchannel_idに改めて seed する）"""
        ch_a = test_db.get_or_create_channel("ch_a")
        ch_b = test_db.get_or_create_channel("ch_b")
        # ch_a にシード
        c_a = seed_character(ch_a["id"])
        assert c_a["channel_id"] == ch_a["id"]
        # ch_b でシード呼び出し — get_character_by_channel は ch_a 行をフォールバックするが、
        # channel_id が一致しないので、get_or_create_character が改めて name ベースで検索し
        # 既存の「ちょビ」を返す（name は UNIQUE）。
        c_b = seed_character(ch_b["id"])
        # name は同じ（「ちょビ」は UNIQUE）なので既存行が返る
        assert c_b["name"] == DEFAULT_CHARACTER_NAME


class TestSeedAllCharacters:
    def setup_method(self):
        invalidate_character_cache()

    def test_creates_teacher_and_student(self, test_db):
        ch = test_db.get_or_create_channel("ch_a")
        seed_all_characters(ch["id"])
        chars = test_db.get_characters_by_channel(ch["id"])
        roles = {json.loads(c["config"]).get("role") for c in chars}
        assert "teacher" in roles
        assert "student" in roles

    def test_idempotent(self, test_db):
        ch = test_db.get_or_create_channel("ch_a")
        seed_all_characters(ch["id"])
        seed_all_characters(ch["id"])
        chars = test_db.get_characters_by_channel(ch["id"])
        # 先生＋生徒の2件のみ
        assert len(chars) == 2

    def test_adds_missing_teacher_role(self, test_db):
        """既存teacherの config に role が無ければ補う"""
        ch = test_db.get_or_create_channel("ch_a")
        # role を含まない config で先生キャラを手動作成
        cfg = {"tts_voice": "Leda", "system_prompt": "test"}
        test_db.get_or_create_character(
            ch["id"], DEFAULT_CHARACTER_NAME, json.dumps(cfg)
        )
        seed_all_characters(ch["id"])
        teacher = test_db.get_character_by_channel(ch["id"])
        teacher_cfg = json.loads(teacher["config"])
        assert teacher_cfg["role"] == "teacher"

    def test_migrates_manabi_to_naruko(self, test_db):
        """既存生徒「まなび」が存在すれば「なるこ」に rename + system_prompt も置換"""
        ch = test_db.get_or_create_channel("ch_a")
        # 先生を先に作る（seed_character 相当）
        test_db.get_or_create_character(
            ch["id"], DEFAULT_CHARACTER_NAME,
            json.dumps(DEFAULT_CHARACTER, ensure_ascii=False),
        )
        # 古い生徒「まなび」を作る
        old_cfg = dict(DEFAULT_STUDENT_CHARACTER)
        old_cfg["system_prompt"] = "あなたは生徒キャラ「まなび」です。"
        test_db.get_or_create_character(
            ch["id"], "まなび", json.dumps(old_cfg, ensure_ascii=False),
        )

        seed_all_characters(ch["id"])

        chars = test_db.get_characters_by_channel(ch["id"])
        names = {c["name"] for c in chars}
        assert "なるこ" in names
        assert "まなび" not in names
        # system_prompt も置換されている
        student = next(
            c for c in chars if json.loads(c["config"]).get("role") == "student"
        )
        assert "「なるこ」" in json.loads(student["config"])["system_prompt"]
        assert "「まなび」" not in json.loads(student["config"])["system_prompt"]

    def test_no_extra_student_when_student_exists(self, test_db):
        """生徒が既にいれば追加作成しない"""
        ch = test_db.get_or_create_channel("ch_a")
        seed_all_characters(ch["id"])
        before = test_db.get_characters_by_channel(ch["id"])
        seed_all_characters(ch["id"])
        after = test_db.get_characters_by_channel(ch["id"])
        assert len(before) == len(after)


class TestLoadCharacter:
    def setup_method(self):
        invalidate_character_cache()

    def test_loads_from_db(self, test_db, mock_env):
        result = load_character()
        assert result["name"] == DEFAULT_CHARACTER_NAME
        assert "system_prompt" in result

    def test_load_populates_cache(self, test_db, mock_env):
        load_character()
        # キャッシュにより load_character を再呼び出しせず同じ instance が返る
        cached = get_character()
        assert cached["name"] == DEFAULT_CHARACTER_NAME

    def test_get_character_lazy_loads(self, test_db, mock_env):
        # キャッシュが空 → get_character が内部で load_character を呼ぶ
        invalidate_character_cache()
        char = get_character()
        assert char["name"] == DEFAULT_CHARACTER_NAME

    def test_get_character_id_lazy_loads(self, test_db, mock_env):
        invalidate_character_cache()
        cid = get_character_id()
        assert isinstance(cid, int)
        # DBに実在
        assert test_db.get_character_by_id(cid) is not None

    def test_invalidate_cache_reloads(self, test_db, mock_env):
        load_character()
        invalidate_character_cache()
        # 再度 load できる
        char = get_character()
        assert char is not None


class TestBuildCharacterContext:
    def setup_method(self):
        invalidate_character_cache()

    def test_teacher_context(self, test_db, mock_env):
        ctx = build_character_context("teacher")
        assert ctx is not None
        assert ctx["role"] == "teacher"
        assert ctx["name"] == DEFAULT_CHARACTER_NAME
        assert "config" in ctx
        # persona / self_note は初期状態で空文字
        assert ctx["persona"] == ""
        assert ctx["self_note"] == ""

    def test_student_context(self, test_db, mock_env):
        ctx = build_character_context("student")
        assert ctx is not None
        assert ctx["role"] == "student"
        assert ctx["name"] == DEFAULT_STUDENT_CHARACTER_NAME

    def test_unknown_role_returns_none(self, test_db, mock_env):
        assert build_character_context("ghost") is None

    def test_loads_persona_and_self_note(self, test_db, mock_env):
        # まず context 取得してキャラIDを確定
        ctx = build_character_context("teacher")
        test_db.update_character_persona(ctx["id"], "好奇心旺盛でツッコミ気質")
        test_db.update_character_self_note(ctx["id"], "今日はPythonの話をした")
        # 再構築したら反映されている
        ctx2 = build_character_context("teacher")
        assert ctx2["persona"] == "好奇心旺盛でツッコミ気質"
        assert ctx2["self_note"] == "今日はPythonの話をした"

    def test_config_includes_name(self, test_db, mock_env):
        """config dict に name キーが注入されている"""
        ctx = build_character_context("teacher")
        assert ctx["config"]["name"] == DEFAULT_CHARACTER_NAME


class TestBuildAllCharacterContexts:
    def setup_method(self):
        invalidate_character_cache()

    def test_returns_teacher_and_student(self, test_db, mock_env):
        ctxs = build_all_character_contexts()
        assert ctxs["teacher"] is not None
        assert ctxs["student"] is not None
        assert ctxs["teacher"]["role"] == "teacher"
        assert ctxs["student"]["role"] == "student"


class TestGetAllCharacters:
    def setup_method(self):
        invalidate_character_cache()

    def test_returns_teacher_and_student(self, test_db, mock_env):
        chars = get_all_characters()
        assert len(chars) == 2
        names = {c["name"] for c in chars}
        assert DEFAULT_CHARACTER_NAME in names
        assert DEFAULT_STUDENT_CHARACTER_NAME in names

    def test_each_entry_has_id_and_config_merged(self, test_db, mock_env):
        chars = get_all_characters()
        for c in chars:
            assert "id" in c
            # config から展開されているキー
            assert "role" in c
            assert "system_prompt" in c


class TestGetChatCharacters:
    def setup_method(self):
        invalidate_character_cache()

    def test_returns_teacher_and_student(self, test_db, mock_env):
        result = get_chat_characters()
        assert result["teacher"] is not None
        assert result["teacher"]["name"] == DEFAULT_CHARACTER_NAME
        assert result["student"] is not None
        assert result["student"]["name"] == DEFAULT_STUDENT_CHARACTER_NAME


class TestGetTtsConfig:
    """get_tts_config の言語対応＋ID指定テスト"""

    def setup_method(self):
        set_stream_language("ja", "en", "low")
        invalidate_character_cache()

    def teardown_method(self):
        set_stream_language("ja", "en", "low")

    def test_ja_returns_default_style(self, test_db, mock_env):
        set_stream_language("ja", "none", "low")
        config = get_tts_config()
        assert isinstance(config["style"], str)
        assert config["voice"] == DEFAULT_CHARACTER["tts_voice"]

    def test_en_returns_en_style(self, test_db, mock_env):
        set_stream_language("en", "none", "low")
        config = get_tts_config()
        # 英語版tts_style_en がある前提
        assert config["style"] == DEFAULT_CHARACTER["tts_style_en"]

    def test_bilingual_returns_bilingual_style(self, test_db, mock_env):
        set_stream_language("ja", "en", "low")
        config = get_tts_config()
        assert config["style"] == DEFAULT_CHARACTER["tts_style_bilingual"]

    def test_with_character_id_returns_that_characters_style(self, test_db, mock_env):
        """character_id を渡すと、そのキャラの voice/style が返る"""
        set_stream_language("ja", "none", "low")
        # 生徒キャラを取り出して id 指定
        chars = get_all_characters()
        student = next(c for c in chars if c["role"] == "student")
        cfg = get_tts_config(student["id"])
        assert cfg["voice"] == DEFAULT_STUDENT_CHARACTER["tts_voice"]

    def test_unknown_character_id_falls_back_to_default(self, test_db, mock_env):
        """存在しないIDなら現行キャラ（先生）の設定にフォールバック"""
        set_stream_language("ja", "none", "low")
        cfg = get_tts_config(999999)
        assert cfg["voice"] == DEFAULT_CHARACTER["tts_voice"]
