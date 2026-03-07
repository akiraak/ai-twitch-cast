"""AI応答モジュール - キャラクター設定に基づいてコメントに応答する"""

import json
import os
from pathlib import Path

from google import genai
from google.genai import types

_PROJECT_DIR = Path(__file__).resolve().parent.parent
CHARACTER_PATH = _PROJECT_DIR / "character.json"

_client = None
_character = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY が設定されていません")
        _client = genai.Client(api_key=api_key)
    return _client


def load_character():
    """character.json を読み込む"""
    global _character
    with open(CHARACTER_PATH, encoding="utf-8") as f:
        _character = json.load(f)
    return _character


def get_character():
    """現在のキャラクター設定を返す"""
    global _character
    if _character is None:
        load_character()
    return _character


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
        '{"response": "返答テキスト", "emotion": "感情"}',
        f"emotionは次のいずれか: {emotion_list}",
    ])

    return "\n".join(parts)


def generate_response(author, message):
    """コメントに対するAI応答を生成する

    Args:
        author: コメント投稿者名
        message: コメント内容

    Returns:
        dict: {"response": str, "emotion": str}
    """
    client = _get_client()
    system_prompt = _build_system_prompt()

    user_prompt = f"{author}さんのコメント: {message}"

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
        result = {"response": message, "emotion": "neutral"}

    # emotionが定義外の場合はneutralにフォールバック
    char = get_character()
    if result.get("emotion") not in char.get("emotions", {}):
        result["emotion"] = "neutral"

    return result
