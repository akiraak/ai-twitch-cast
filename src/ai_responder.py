"""AI応答モジュール - キャラクター設定に基づいてコメントに応答する"""

import json
import os

from google.genai import types

from src.gemini_client import get_client

# DBが空のときに使うデフォルトキャラクター設定
DEFAULT_CHARACTER = {
    "name": "ちょび",
    "system_prompt": "あなたはTwitch配信者「ちょび」です。明るくフレンドリーな性格で、視聴者のコメントに元気に返事します。",
    "rules": [
        "短く簡潔に返答する（1〜2文程度）",
        "初見の人には「いらっしゃい！」と歓迎する",
        "質問には丁寧に答える",
        "荒らしや不適切なコメントは軽くスルーする",
        "配信の雰囲気を明るく保つ",
    ],
    "emotions": {
        "joy": "嬉しい・楽しいとき",
        "surprise": "驚いたとき",
        "thinking": "考えているとき",
        "neutral": "通常時",
    },
    "emotion_blendshapes": {
        "joy": {"Joy": 1.0},
        "surprise": {"Joy": 0.5, "A": 0.3},
        "thinking": {"Sorrow": 0.3},
        "neutral": {},
    },
}

_character = None
_character_id = None


def seed_character(channel_id):
    """デフォルト設定からDBにキャラクターを作成する（未登録時のみ）"""
    from src import db

    existing = db.get_character_by_channel(channel_id)
    if existing:
        return existing

    config = json.dumps(DEFAULT_CHARACTER, ensure_ascii=False)
    return db.get_or_create_character(channel_id, DEFAULT_CHARACTER["name"], config)


def load_character(channel_id=None):
    """DBからキャラクター設定を読み込む"""
    global _character, _character_id
    from src import db

    if channel_id is None:
        channel_name = os.environ.get("TWITCH_CHANNEL", "default")
        channel = db.get_or_create_channel(channel_name)
        channel_id = channel["id"]

    db_char = db.get_character_by_channel(channel_id)
    if db_char is None:
        db_char = seed_character(channel_id)

    _character_id = db_char["id"]
    _character = json.loads(db_char["config"])
    return _character


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


def invalidate_character_cache():
    """キャラクターキャッシュを無効化する（DB更新後に呼ぶ）"""
    global _character, _character_id
    _character = None
    _character_id = None


def _build_system_prompt():
    """キャラクター設定からシステムプロンプトを構築する"""
    char = get_character()
    emotions = char.get("emotions", {})
    emotion_list = ", ".join(emotions.keys())

    parts = [
        char["system_prompt"],
        "",
        "## ルール",
    ]
    for rule in char.get("rules", []):
        parts.append(f"- {rule}")

    parts.extend([
        "",
        "## 言語ルール",
        "これは日本語の配信なので、日本語ベースで返答しつつ相手の言語も混ぜて親しみを出す。",
        "- 日本語コメント → response: 日本語、english: 英語訳",
        "- 英語コメント → response: 英語メインで返答、english: 日本語訳",
        "- その他の言語（スペイン語・韓国語等） → response: 相手の言語での挨拶や一言を混ぜつつ日本語も交えて返答、english: 英語訳",
        "- 例: スペイン語コメントなら「¡Hola! いらっしゃい！Gracias por venir! 楽しんでいってね～」のように両方混ぜると喜ばれる",
        "",
        "## 出力形式",
        "必ず以下のJSON形式で返答してください。それ以外のテキストは出力しないでください。",
        '{"response": "返答テキスト", "emotion": "感情", "english": "翻訳（上記言語ルール参照）"}',
        f"emotionは次のいずれか: {emotion_list}",
    ])

    return "\n".join(parts)


def generate_response(author, message, comment_count=0):
    """コメントに対するAI応答を生成する

    Args:
        author: コメント投稿者名
        message: コメント内容
        comment_count: このユーザーの過去コメント数

    Returns:
        dict: {"response": str, "emotion": str}
    """
    client = get_client()
    system_prompt = _build_system_prompt()

    if comment_count == 0:
        context = f"（初見のユーザーです）"
    else:
        context = f"（過去{comment_count}回コメントしている常連です）"

    user_prompt = f"{author}さんのコメント{context}: {message}"

    response = client.models.generate_content(
        model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-flash"),
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )

    try:
        result = json.loads(response.text)
    except (json.JSONDecodeError, AttributeError):
        result = {"response": message, "emotion": "neutral", "english": ""}

    result.setdefault("english", "")

    # emotionが定義外の場合はneutralにフォールバック
    char = get_character()
    if result.get("emotion") not in char.get("emotions", {}):
        result["emotion"] = "neutral"

    return result


def generate_event_response(event_type, detail):
    """イベント（コミット・作業開始等）に対するAI応答を生成する

    Args:
        event_type: イベント種別 ("commit", "stream_start" など)
        detail: イベントの詳細情報

    Returns:
        dict: {"response": str, "emotion": str, "english": str}
    """
    client = get_client()
    char = get_character()
    emotions = char.get("emotions", {})
    emotion_list = ", ".join(emotions.keys())

    system_prompt = "\n".join([
        char["system_prompt"],
        "",
        "## ルール",
        "- 配信中のイベント（コミット、作業開始など）について短くコメントしてください",
        "- 視聴者に向かって話すように、自然で楽しいコメントをしてください",
        "- 1〜2文で簡潔に",
        "",
        "## 出力形式",
        "必ず以下のJSON形式で返答してください。それ以外のテキストは出力しないでください。",
        '{"response": "返答テキスト", "emotion": "感情", "english": "responseの英語訳"}',
        f"emotionは次のいずれか: {emotion_list}",
    ])

    user_prompt = f"【{event_type}イベント】{detail}"

    response = client.models.generate_content(
        model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-flash"),
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )

    try:
        result = json.loads(response.text)
    except (json.JSONDecodeError, AttributeError):
        result = {"response": detail, "emotion": "neutral", "english": ""}

    result.setdefault("english", "")
    if result.get("emotion") not in emotions:
        result["emotion"] = "neutral"

    return result
