"""教師モード — 画像/URL解析 + 授業スクリプト生成"""

import base64
import json
import logging
import os
import re
from pathlib import Path

import httpx
from google.genai import types

from src.gemini_client import get_client

logger = logging.getLogger(__name__)

_CHAT_MODEL = None


def _get_model():
    global _CHAT_MODEL
    if _CHAT_MODEL is None:
        _CHAT_MODEL = os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview")
    return _CHAT_MODEL


# --- 画像解析 ---

def extract_text_from_image(image_path: str) -> str:
    """画像からテキストを抽出する（Gemini Vision）"""
    client = get_client()
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"画像が見つかりません: {image_path}")

    data = path.read_bytes()
    mime = _guess_mime(path.suffix)

    response = client.models.generate_content(
        model=_get_model(),
        contents=[
            types.Content(parts=[
                types.Part(inline_data=types.Blob(mime_type=mime, data=data)),
                types.Part(text="この画像に含まれるテキストをすべて正確に抽出してください。"
                           "レイアウトを保ちつつ、テキストのみを出力してください。"),
            ]),
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )
    return response.text.strip()


def _guess_mime(ext: str) -> str:
    ext = ext.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")


# --- URL解析 ---

async def extract_text_from_url(url: str) -> str:
    """URLからテキストを取得する"""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        resp = await http.get(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; AI-Twitch-Cast/1.0)"
        })
        resp.raise_for_status()
        html = resp.text

    # HTMLからテキストを抽出（簡易）
    client = get_client()
    response = client.models.generate_content(
        model=_get_model(),
        contents=f"以下のHTMLから、教材として有用なテキスト内容を抽出してください。"
                 f"HTMLタグは除去し、本文テキストのみを返してください。\n\n{html[:30000]}",
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )
    return response.text.strip()


# --- スクリプト生成 ---

def generate_lesson_script(lesson_name: str, extracted_text: str, source_images: list[str] = None) -> list[dict]:
    """教材テキスト（+ 画像）から授業スクリプトを生成する

    Args:
        lesson_name: 授業コンテンツ名
        extracted_text: 抽出済みテキスト
        source_images: 画像ファイルパスのリスト（Gemini Vision用）

    Returns:
        list[dict]: セクション一覧
            [{section_type, content, tts_text, display_text, emotion,
              question, answer, wait_seconds}, ...]
    """
    client = get_client()

    system_prompt = """あなたは授業スクリプト生成AIです。
教材のテキスト（と画像）をもとに、Twitch配信の授業スクリプトを生成してください。

## ルール
- 教材の内容に忠実に、わかりやすく教える授業スクリプトを作る
- バイリンガル（日本語と英語を自然に混ぜる）で教える
- セクション数はAIが内容に応じて自動調整する（3〜15程度）
- 各セクションにはtypeを付ける: introduction, explanation, example, question, summary
- 感情（emotion）を各セクションに付ける: joy, excited, surprise, thinking, sad, embarrassed, neutral
- questionセクションには問いかけ(question)と回答(answer)を含める
- 導入と締めくくりを必ず含める

## 出力形式（JSON配列）
```json
[
  {
    "section_type": "introduction",
    "content": "発話テキスト（ちょビが話す内容）",
    "tts_text": "TTS用テキスト（発音指示・言語タグ付き）",
    "display_text": "画面に表示するテキスト（要点・例文など自由形式）",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  },
  {
    "section_type": "question",
    "content": "問題を出す発話テキスト",
    "tts_text": "TTS用テキスト",
    "display_text": "画面に表示する問題文",
    "emotion": "thinking",
    "question": "視聴者への問いかけ",
    "answer": "正解と解説",
    "wait_seconds": 8
  }
]
```

JSON配列のみを出力してください。他のテキストは不要です。"""

    parts = []

    # 画像があれば添付
    if source_images:
        for img_path in source_images:
            p = Path(img_path)
            if p.exists():
                data = p.read_bytes()
                mime = _guess_mime(p.suffix)
                parts.append(types.Part(inline_data=types.Blob(mime_type=mime, data=data)))

    user_text = f"# 授業タイトル: {lesson_name}\n\n# 教材テキスト:\n{extracted_text}"
    parts.append(types.Part(text=user_text))

    response = client.models.generate_content(
        model=_get_model(),
        contents=[types.Content(parts=parts)],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.7,
            max_output_tokens=8192,
        ),
    )

    # JSONパース
    text = response.text.strip()
    # ```json ... ``` を除去（マルチライン対応）
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    # 先頭/末尾の ``` だけ残っている場合も除去
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?\s*```$', '', text)

    try:
        sections = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("スクリプト生成のJSONパースに失敗 (pos=%s): %s...（全%d文字）", e.pos, text[:1000], len(text))
        raise ValueError(f"スクリプト生成のJSONパースに失敗しました（位置{e.pos}）。再度お試しください。")

    if not isinstance(sections, list):
        raise ValueError("スクリプト生成結果が配列ではありません")

    # 必須フィールドの補完
    valid_types = {"introduction", "explanation", "example", "question", "summary"}
    result = []
    for s in sections:
        section = {
            "section_type": s.get("section_type", "explanation"),
            "content": s.get("content", ""),
            "tts_text": s.get("tts_text", s.get("content", "")),
            "display_text": s.get("display_text", ""),
            "emotion": s.get("emotion", "neutral"),
            "question": s.get("question", ""),
            "answer": s.get("answer", ""),
            "wait_seconds": int(s.get("wait_seconds", 0)),
        }
        if section["section_type"] not in valid_types:
            section["section_type"] = "explanation"
        result.append(section)

    return result
