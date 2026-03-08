"""AI応答モジュール - キャラクター設定に基づいてコメントに応答する"""

import json
import os
from pathlib import Path

from google import genai
from google.genai import types

_PROJECT_DIR = Path(__file__).resolve().parent.parent
_CHARACTER_SEED_PATH = _PROJECT_DIR / "character.json"

_client = None
_character = None
_character_id = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY が設定されていません")
        _client = genai.Client(api_key=api_key)
    return _client


def seed_character(channel_id):
    """character.json から初期データをDBにインポートする（未登録時のみ）"""
    from src import db

    existing = db.get_character_by_channel(channel_id)
    if existing:
        return existing

    with open(_CHARACTER_SEED_PATH, encoding="utf-8") as f:
        char_data = json.load(f)

    config = json.dumps(char_data, ensure_ascii=False)
    return db.get_or_create_character(channel_id, char_data["name"], config)


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
        "## 出力形式",
        "必ず以下のJSON形式で返答してください。それ以外のテキストは出力しないでください。",
        '{"response": "返答テキスト", "emotion": "感情", "english": "responseの英語訳"}',
        f"emotionは次のいずれか: {emotion_list}",
        "englishにはresponseの自然な英語訳を含めてください。",
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
    client = _get_client()
    system_prompt = _build_system_prompt()

    if comment_count == 0:
        context = f"（初見のユーザーです）"
    else:
        context = f"（過去{comment_count}回コメントしている常連です）"

    user_prompt = f"{author}さんのコメント{context}: {message}"

    response = client.models.generate_content(
        model="gemini-2.5-flash",
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
