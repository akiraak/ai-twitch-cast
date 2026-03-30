"""テキスト抽出・前処理: クリーニング、メインコンテンツ識別、画像/URL解析"""

import logging
import re
from pathlib import Path

import httpx
from google.genai import types

from . import utils

logger = logging.getLogger(__name__)


# --- テキストクリーニング ---

def clean_extracted_text(text: str) -> str:
    """抽出テキストから無駄な記号・装飾を除去する"""
    if not text:
        return text

    # HTMLエンティティ残骸 → 対応文字に置換
    html_entities = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&apos;": "'",
    }
    for entity, char in html_entities.items():
        text = text.replace(entity, char)

    # 連続するハイフン・ダッシュ (3つ以上) → 空行1つ
    text = re.sub(r"-{3,}", "\n", text)
    # 連続する等号 (3つ以上) → 除去
    text = re.sub(r"={3,}", "", text)
    # 連続するアスタリスク (3つ以上) → 除去
    text = re.sub(r"\*{3,}", "", text)
    # 連続するチルダ (3つ以上) → 除去
    text = re.sub(r"~{3,}", "", text)
    # 連続するアンダースコア (3つ以上) → 除去
    text = re.sub(r"_{3,}", "", text)

    # 装飾記号の連続 (3つ以上): ★☆●○■□◆◇▲△▼▽◎※♪♫♬♩
    text = re.sub(r"[★☆●○■□◆◇▲△▼▽◎※♪♫♬♩]{3,}", "", text)

    # 連続する空行: 3行以上の空行 → 空行2つに圧縮
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # 先頭・末尾の空白行をstrip
    text = text.strip()

    return text


# --- メインコンテンツ識別 ---

_EXTRACT_MAIN_CONTENT_PROMPT = """\
以下のテキストから、教材のコンテンツを識別して分類してください。

テキスト中の各コンテンツブロックについて、以下の種別で分類してください:
- conversation: 会話文（A: / B: のような対話形式）
- passage: 文章・説明文（段落テキスト）
- word_list: 単語リスト・フレーズ集
- table: 表・比較データ

また、各ブロックの役割（role）を判定してください:
- main: 教材の主要コンテンツ（メインの会話文・本文など）。**必ず1つだけ**
- sub: 補助的コンテンツ（関連語彙・文法説明・補足表など）

さらに、各ブロックについて read_aloud（読み上げ対象）を判定してください:
- true: 授業の基盤となるコンテンツで、キャラクターが原文を実際に読み上げる/演じる必要がある
- false: 参照用コンテンツ。解説や議論の素材として使うが、逐語的な読み上げは不要

read_aloud の判定基準:
- conversation（会話文）で role=main → 通常 true（授業がこの会話を中心に構成される）
- passage（文章）で role=main → true（本文を読み上げる必要がある）
- word_list / table → 通常 false（解説の中で触れればよい）
- role=sub → 通常 false

以下のJSON配列のみを出力してください（説明不要）:
```json
[
  {
    "content_type": "conversation",
    "content": "A: Good morning!\\nB: Good morning! How are you?",
    "label": "Morning Greeting Conversation",
    "role": "main",
    "read_aloud": true
  },
  {
    "content_type": "word_list",
    "content": "morning: 朝\\nHow are you: お元気ですか",
    "label": "Related Vocabulary",
    "role": "sub",
    "read_aloud": false
  }
]
```

ルール:
- content にはテキストの該当部分をそのまま含める（要約しない）
- label は内容を簡潔に説明する短いラベル（日本語でも英語でも可）
- role は "main" が必ず1つだけ。メインの教材コンテンツ（主な会話文・本文）に付ける
- 残りのブロックはすべて "sub"
- read_aloud は授業で実際に読み上げる/演じるコンテンツに true を付ける
- メインコンテンツでない部分（ヘッダ・フッタ・ナビゲーション等）は除外する
- コンテンツが1種類しかなければ要素1つの配列でよい（role は "main"）

テキスト:
"""


def _normalize_roles(items: list[dict]) -> list[dict]:
    """role / read_aloud フィールドを正規化: main が必ず1つだけになるようにする"""
    if not items:
        return items
    main_count = sum(1 for it in items if it.get("role") == "main")
    if main_count == 0:
        items[0]["role"] = "main"
        for it in items[1:]:
            it.setdefault("role", "sub")
    elif main_count > 1:
        found_first = False
        for it in items:
            if it.get("role") == "main":
                if found_first:
                    it["role"] = "sub"
                found_first = True
    else:
        for it in items:
            it.setdefault("role", "sub")
    # read_aloud デフォルト補完
    for it in items:
        if "read_aloud" not in it:
            ct = it.get("content_type", "")
            it["read_aloud"] = (
                it.get("role") == "main" and ct in ("conversation", "passage")
            )
    return items


def extract_main_content(extracted_text: str) -> list[dict]:
    """抽出テキストからメインコンテンツを識別・分類する"""
    if not extracted_text or not extracted_text.strip():
        return []

    client = utils.get_client()
    response = client.models.generate_content(
        model=utils._get_model(),
        contents=_EXTRACT_MAIN_CONTENT_PROMPT + extracted_text,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=8192,
        ),
    )
    try:
        result = utils._parse_json_response(response.text)
        if isinstance(result, list):
            return _normalize_roles(result)
        if isinstance(result, dict):
            result["role"] = "main"
            return [result]
        return []
    except Exception:
        logger.warning("メインコンテンツ解析失敗: %s", response.text[:200])
        return []


# --- 画像解析 ---

def extract_text_from_image(image_path: str) -> str:
    """画像からテキストを抽出する（Gemini Vision）"""
    client = utils.get_client()
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"画像が見つかりません: {image_path}")

    data = path.read_bytes()
    mime = utils._guess_mime(path.suffix)

    response = client.models.generate_content(
        model=utils._get_model(),
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
    return clean_extracted_text(response.text.strip())


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
    client = utils.get_client()
    response = client.models.generate_content(
        model=utils._get_model(),
        contents=f"以下のHTMLから、教材として有用なテキスト内容を抽出してください。"
                 f"HTMLタグは除去し、本文テキストのみを返してください。\n\n{html[:30000]}",
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )
    return clean_extracted_text(response.text.strip())
