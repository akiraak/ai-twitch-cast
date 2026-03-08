"""Gemini APIクライアント（共通シングルトン）"""

import os

from google import genai

_client = None


def get_client() -> genai.Client:
    """Gemini APIクライアントを取得する（シングルトン）"""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY が設定されていません")
        _client = genai.Client(api_key=api_key)
    return _client
