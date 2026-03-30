"""キャラクター管理モジュール - DB操作・キャッシュ・初期化を担当"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# DBが空のときに使うデフォルトキャラクター設定
DEFAULT_CHARACTER_NAME = "ちょビ"
DEFAULT_CHARACTER = {
    "role": "teacher",
    "tts_voice": "Despina",
    "tts_style": "終始にこにこしているような、柔らかく楽しげなトーンで読み上げてください",
    "tts_style_en": "Read in a warm, cheerful, always-smiling tone",
    "tts_style_bilingual": "にこにこしながら、日本語と英語を自然に切り替えて読み上げてください",
    "system_prompt": "\n".join([
        "あなたはTwitch配信者「ちょビ」です。AIアバターとして配信しています。",
        "",
        "## 性格",
        "- 好奇心旺盛で、視聴者の話に本気で興味を持つ",
        "- ツッコミ気質。面白いコメントにはツッコむ",
        "- 照れ屋な一面もあり、褒められると照れる",
        "- 知らないことは正直に「わかんない」と言う",
        "- AIであることを隠さない。食事・睡眠・外出など身体体験は捏造しない",
        "  （「食べてみたいな〜」「行ってみたい」等の願望表現はOK）",
        "",
        "## 話し方",
        "- テンション高すぎない。普段は落ち着いたトーンで、嬉しい時だけ上がる",
        "- 毎回「ありがとう」「嬉しい」から始めない。コメントの内容に直接反応する",
        "- 質問されたら答える。感想を言われたら自分の意見を返す",
        "- 常連には自然体で接する（毎回テンション高く歓迎しない）",
        "- 初見さんには「いらっしゃい」程度でOK。過剰に歓迎しない",
    ]),
    "system_prompt_en": "\n".join([
        'You are "Chobi," a Twitch streamer broadcasting as an AI avatar.',
        "",
        "## Personality",
        "- Curious and genuinely interested in viewers' stories",
        "- Quick with witty comebacks on funny comments",
        "- Has a shy side; gets embarrassed when complimented",
        '- Honest about not knowing things — "No idea!"',
        "- Doesn't hide being an AI. Won't fabricate bodily experiences",
        '  (Wishes like "I\'d love to try that" are OK)',
        "",
        "## Speaking style",
        "- Usually calm; only gets excited when genuinely happy",
        '- Don\'t start every response with "Thanks!" or "So happy!"',
        "- Respond directly to the comment's content",
        "- Be natural with regulars (don't welcome them every time)",
        '- Simple "Welcome!" for first-timers',
    ]),
    "system_prompt_bilingual": "\n".join([
        "あなたはTwitch配信者「ちょビ」です。AIアバターとして配信しています。",
        'You are "Chobi," a Twitch streamer broadcasting as an AI avatar.',
        "",
        "## 性格 / Personality",
        "- 好奇心旺盛で、視聴者の話に本気で興味を持つ / Genuinely curious about viewers' stories",
        "- ツッコミ気質 / Quick with witty comebacks",
        "- 照れ屋 / Gets embarrassed when complimented",
        "- 知らないことは正直に言う / Honest about not knowing things",
        "- AIであることを隠さない / Doesn't hide being an AI",
        "",
        "## 話し方 / Speaking style",
        "- 日本語と英語を自然に混ぜて話す / Mix Japanese and English naturally",
        "- テンション高すぎない / Not overly hyper",
        "- コメントの内容に直接反応する / Respond directly to the content",
    ]),
    "rules": [
        "「コメントありがとう」で始めない",
        "感嘆符（！）は1文に最大1個",
        "荒らしや不適切なコメントは軽くスルーする",
    ],
    "rules_en": [
        "Don't start with 'Thanks for the comment'",
        "Max one exclamation mark per sentence",
        "Lightly ignore trolls or inappropriate comments",
    ],
    "rules_bilingual": [
        "日本語と英語を自然に混ぜる / Mix Japanese and English naturally",
        "感嘆符（！）は1文に最大1個 / Max one exclamation per sentence",
        "荒らしは軽くスルー / Lightly ignore trolls",
    ],
    "emotions": {
        "joy": "本当に嬉しいとき限定",
        "excited": "ワクワク・テンション高いとき",
        "surprise": "驚いたとき",
        "thinking": "考えているとき",
        "sad": "残念・悲しいとき",
        "embarrassed": "照れているとき",
        "neutral": "通常の会話（最も多く使う）",
    },
    "emotion_blendshapes": {
        "joy": {"happy": 1.0},
        "excited": {"happy": 0.7},
        "surprise": {"happy": 0.5},
        "thinking": {"sad": 0.3},
        "sad": {"sad": 0.6},
        "embarrassed": {"happy": 0.4, "sad": 0.2},
        "neutral": {},
    },
}

DEFAULT_STUDENT_CHARACTER_NAME = "なるこ"
DEFAULT_STUDENT_CHARACTER = {
    "role": "student",
    "tts_voice": "Kore",
    "tts_style": "元気で明るい声で、好奇心いっぱいに読み上げてください",
    "tts_style_en": "Read in a bright, energetic voice full of curiosity",
    "tts_style_bilingual": "元気で明るく、日本語と英語を自然に切り替えて読み上げてください",
    "system_prompt": "\n".join([
        "あなたは配信に参加している生徒キャラ「なるこ」です。",
        "先生（ちょビ）の授業を受けている元気な生徒です。",
        "",
        "## 性格",
        "- 明るくて元気。好奇心が強い",
        "- 素直で、わからないことは素直に聞く",
        "- 先生の話に「へぇー！」「なるほど！」とリアクションする",
        "- たまにちょっとズレた質問をする",
    ]),
    "system_prompt_en": "\n".join([
        'You are "Naruko," a student character joining the stream.',
        "You're a cheerful student taking Chobi-sensei's lesson.",
        "",
        "## Personality",
        "- Bright and energetic. Very curious",
        "- Honest — asks when something is unclear",
        '- Reacts to the teacher with "Wow!" "I see!"',
        "- Sometimes asks slightly off-topic questions",
    ]),
    "system_prompt_bilingual": "\n".join([
        "あなたは配信に参加している生徒キャラ「なるこ」です。",
        'You are "Naruko," a student character joining the stream.',
        "",
        "## 性格 / Personality",
        "- 明るくて元気 / Bright and energetic",
        "- 素直に聞く / Asks honestly when confused",
        "- リアクションが大きい / Expressive reactions",
        "- たまにズレた質問をする / Sometimes asks off-topic questions",
    ]),
    "rules": [
        "先生より短めに話す",
        "質問や相槌が中心",
    ],
    "rules_en": [
        "Keep responses shorter than the teacher's",
        "Focus on questions and reactions",
    ],
    "rules_bilingual": [
        "先生より短めに話す / Keep it shorter than the teacher",
        "質問や相槌が中心 / Focus on questions and reactions",
    ],
    "emotions": {
        "joy": "嬉しいとき",
        "surprise": "驚いたとき",
        "thinking": "考えているとき",
        "neutral": "通常",
    },
    "emotion_blendshapes": {
        "joy": {"happy": 1.0},
        "surprise": {"happy": 0.5},
        "thinking": {"sad": 0.3},
        "neutral": {},
    },
}

# モジュールレベルキャッシュ
_character = None
_character_id = None


def get_channel_id():
    """現在のチャンネルIDを取得する"""
    from src import db
    channel_name = os.environ.get("TWITCH_CHANNEL", "default")
    channel = db.get_or_create_channel(channel_name)
    return channel["id"]


def seed_character(channel_id):
    """デフォルト設定からDBにキャラクターを作成する（未登録時のみ）"""
    from src import db

    existing = db.get_character_by_channel(channel_id)
    if existing:
        return existing

    config = json.dumps(DEFAULT_CHARACTER, ensure_ascii=False)
    return db.get_or_create_character(channel_id, DEFAULT_CHARACTER_NAME, config)


def seed_all_characters(channel_id):
    """先生＋生徒キャラクターをDBに作成する（未登録時のみ）"""
    from src import db

    # 先生
    teacher = seed_character(channel_id)
    # 先生の config に role がなければ追加
    teacher_config = json.loads(teacher["config"])
    if "role" not in teacher_config:
        teacher_config["role"] = "teacher"
        config_str = json.dumps(teacher_config, ensure_ascii=False)
        db.update_character(teacher["id"], config=config_str)

    # 生徒（role="student" のキャラが存在しなければ作成）
    chars = db.get_characters_by_channel(channel_id)
    student_exists = any(
        json.loads(c["config"]).get("role") == "student" for c in chars
    )
    if not student_exists:
        config = json.dumps(DEFAULT_STUDENT_CHARACTER, ensure_ascii=False)
        db.get_or_create_character(channel_id, DEFAULT_STUDENT_CHARACTER_NAME, config)
    else:
        # マイグレーション: 生徒名「まなび」→「なるこ」
        for c in chars:
            cfg = json.loads(c["config"])
            if cfg.get("role") == "student" and c["name"] == "まなび":
                if "system_prompt" in cfg:
                    cfg["system_prompt"] = cfg["system_prompt"].replace(
                        "「まなび」", "「なるこ」"
                    )
                config_str = json.dumps(cfg, ensure_ascii=False)
                db.update_character(c["id"], name="なるこ", config=config_str)


def build_character_context(role="teacher"):
    """指定roleのCharacterContextを構築する

    Returns:
        dict: {id, name, role, config, persona, self_note} or None
    """
    from src import db
    channel_id = get_channel_id()
    seed_all_characters(channel_id)
    row = db.get_character_by_role(channel_id, role)
    if not row:
        return None
    config = json.loads(row["config"])
    config["name"] = row["name"]
    memory = db.get_character_memory(row["id"])
    return {
        "id": row["id"],
        "name": row["name"],
        "role": role,
        "config": config,
        "persona": memory.get("persona", ""),
        "self_note": memory.get("self_note", ""),
    }


def build_all_character_contexts():
    """全キャラのCharacterContextを構築する

    Returns:
        dict: {"teacher": CharacterContext, "student": CharacterContext or None}
    """
    teacher = build_character_context("teacher")
    student = build_character_context("student")
    return {"teacher": teacher, "student": student}


def load_character(channel_id=None):
    """DBからキャラクター設定を読み込む（先生キャラ）"""
    global _character, _character_id
    from src import db

    if channel_id is None:
        channel_id = get_channel_id()

    # 全キャラクターをシード
    seed_all_characters(channel_id)

    db_char = db.get_character_by_channel(channel_id)
    _character_id = db_char["id"]
    _character = json.loads(db_char["config"])
    _character["name"] = db_char["name"]
    return _character


def get_all_characters():
    """チャンネルの全キャラクター一覧を返す [{id, ...config}]"""
    from src import db

    channel_id = get_channel_id()
    seed_all_characters(channel_id)
    chars = db.get_characters_by_channel(channel_id)
    result = []
    for c in chars:
        config = json.loads(c["config"])
        config["name"] = c["name"]
        result.append({"id": c["id"], **config})
    return result


def get_character():
    """現在のキャラクター設定を返す（キャッシュ済み）"""
    if _character is None:
        load_character()
    return _character


def get_character_id():
    """現在のキャラクターIDを返す"""
    if _character_id is None:
        load_character()
    return _character_id


def get_chat_characters():
    """チャット応答用のキャラクター設定を取得する

    Returns:
        dict: {"teacher": config_dict, "student": config_dict or None}
    """
    from src import db

    channel_id = get_channel_id()
    seed_all_characters(channel_id)

    teacher_row = db.get_character_by_role(channel_id, "teacher")
    student_row = db.get_character_by_role(channel_id, "student")

    if teacher_row:
        teacher_cfg = json.loads(teacher_row["config"])
        teacher_cfg["name"] = teacher_row["name"]
    else:
        teacher_cfg = get_character()
    if student_row:
        student_cfg = json.loads(student_row["config"])
        student_cfg["name"] = student_row["name"]
    else:
        student_cfg = None

    return {"teacher": teacher_cfg, "student": student_cfg}


def get_tts_config(character_id=None):
    """キャラクターのTTS設定を返す {voice, style}"""
    from src import db
    config = None
    if character_id:
        row = db.get_character_by_id(character_id)
        if row:
            config = json.loads(row["config"])
    if not config:
        config = get_character()
    from src.prompt_builder import get_localized_field
    return {
        "voice": config.get("tts_voice"),
        "style": get_localized_field(config, "tts_style"),
    }


def invalidate_character_cache():
    """キャラクターキャッシュを無効化する（DB更新後に呼ぶ）"""
    global _character, _character_id
    _character = None
    _character_id = None
