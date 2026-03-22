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


# --- 三者視点プラン生成 ---

def _build_image_parts(source_images: list[str] | None) -> list:
    """画像をGemini用のPartリストに変換する"""
    parts = []
    if source_images:
        for img_path in source_images:
            p = Path(img_path)
            if p.exists():
                data = p.read_bytes()
                mime = _guess_mime(p.suffix)
                parts.append(types.Part(inline_data=types.Blob(mime_type=mime, data=data)))
    return parts


def generate_lesson_plan(lesson_name: str, extracted_text: str, source_images: list[str] = None) -> dict:
    """三者視点で授業プランを生成する（3回のLLM呼び出し）

    Returns:
        dict: {knowledge: str, entertainment: str, plan_sections: list[dict]}
            plan_sections: [{section_type, title, summary, emotion, has_question}, ...]
    """
    client = get_client()
    image_parts = _build_image_parts(source_images)

    user_text = f"# 授業タイトル: {lesson_name}\n\n# 教材テキスト:\n{extracted_text}"

    # --- 呼び出し1: 知識先生 ---
    knowledge_prompt = """あなたは「知識先生」です。教科主任として、教材を分析し授業で教えるべき内容を整理してください。

## あなたの役割
- 教材の核心を正確に把握し、教えるべき要点を洗い出す
- 学習者にとって最適な順序（前提知識→核心→応用）を設計する
- よくある誤解や注意すべきポイントを指摘する
- 教材に含まれる重要な事実・数値・概念を漏らさない

## 出力形式
以下の構成でテキストを出力してください:

### 教えるべき要点
（重要度順にリスト）

### 推奨する学習順序
（前提→本題→発展の流れ）

### 注意すべき誤解・難所
（学習者がつまずきやすいポイント）

### 推奨セクション構成
（各セクションで扱うべき内容の概要）"""

    parts1 = image_parts + [types.Part(text=user_text)]
    resp1 = client.models.generate_content(
        model=_get_model(),
        contents=[types.Content(parts=parts1)],
        config=types.GenerateContentConfig(
            system_instruction=knowledge_prompt,
            temperature=0.5,
            max_output_tokens=4096,
        ),
    )
    knowledge_text = resp1.text.strip()
    logger.info("知識先生の分析完了（%d文字）", len(knowledge_text))

    # --- 呼び出し2: エンタメ先生 ---
    entertainment_prompt = """あなたは「エンタメ先生」です。Twitch配信で視聴者を楽しませる人気講師として、授業を起承転結で構成してください。

## あなたの役割
- 知識先生の分析を踏まえつつ、**起承転結**の物語構造で授業を再構成する
- 視聴者が最後まで見たくなる構成を設計する

## 起承転結の設計指針

### 【起】導入・フック
- 視聴者の興味を一瞬で掴む問いかけや意外な事実
- 「え、そうなの？」と思わせる入り口

### 【承】展開・積み上げ
- 知識を段階的に積み上げる
- 伏線を張る（後の「転」で回収するネタを仕込む）
- 身近な例え話で理解を助ける

### 【転】転換・驚き
- 常識を覆す展開、意外な事実
- 「実はこうだった！」「でもここが落とし穴で…」
- 承で張った伏線の回収

### 【結】オチ・締め
- 学んだことが全部繋がる瞬間。「なるほど！」と腹落ちする締め
- 「だから○○なんです！」という一言でまとまるオチ
- 視聴者が誰かに話したくなるような余韻

## その他の演出
- クイズや問いかけの最適な配置
- 感情の起伏（どこで盛り上げ、どこで考えさせるか）
- ユーモアや例え話のアイデア

## 出力形式
以下の構成でテキストを出力してください:

### 起承転結の構成
（各パートの概要と演出意図）

### オチの設計
（最後に視聴者に届けたい「なるほど！」は何か）

### 演出ポイント
（クイズ・例え話・感情の起伏の配置）"""

    parts2 = [types.Part(text=f"{user_text}\n\n---\n\n# 知識先生の分析:\n{knowledge_text}")]
    resp2 = client.models.generate_content(
        model=_get_model(),
        contents=[types.Content(parts=parts2)],
        config=types.GenerateContentConfig(
            system_instruction=entertainment_prompt,
            temperature=0.8,
            max_output_tokens=4096,
        ),
    )
    entertainment_text = resp2.text.strip()
    logger.info("エンタメ先生の構成完了（%d文字）", len(entertainment_text))

    # --- 呼び出し3: 監督 ---
    director_prompt = """あなたは「監督」です。知識先生とエンタメ先生の提案を統合し、最終的な授業プランを決定してください。

## あなたの役割

### 全体のバランス調整
- 知識先生の正確性・網羅性とエンタメ先生の起承転結・演出を両立させる
- 詰め込みすぎを防ぎ、適切なセクション数（3〜15）に調整する
- 知識の正確性を損なわない範囲でエンタメ要素を採用する

### 矛盾・分かりにくさの修正
- セクション間の流れに矛盾がないかチェックする
- 前のセクションで説明していない用語を使っていないか確認する
- 分かりにくい構成があれば順序を入れ替える

### 「間」（ま）の設計
各セクションに適切な **wait_seconds**（セクション終了後の間）を設定してください。
間は授業のリズムを作る重要な要素です。

- **自然な会話・説明**: 1〜2秒（テンポよく次へ）
- **重要なポイントの後**: 3〜4秒（視聴者に考える時間を与える）
- **驚きの事実・転換の後**: 4〜5秒（余韻を残す）
- **問いかけ（question）**: 8〜15秒（視聴者が考える・チャットで答える時間）
- **最後のまとめ・オチ**: 2〜3秒（締めの余韻）

## 出力形式（JSON配列）
```json
[
  {
    "section_type": "introduction",
    "title": "セクションの短いタイトル",
    "summary": "このセクションで扱う内容の概要（2〜3文）",
    "emotion": "excited",
    "has_question": false,
    "wait_seconds": 2
  }
]
```

### section_type の選択肢
- introduction: 導入（起）
- explanation: 説明（承）
- example: 具体例・例え話
- question: 視聴者への問いかけ
- summary: まとめ・締め（結）

### emotion の選択肢
- joy, excited, surprise, thinking, sad, embarrassed, neutral

JSON配列のみを出力してください。"""

    parts3 = [types.Part(text=(
        f"# 知識先生の分析:\n{knowledge_text}\n\n"
        f"---\n\n# エンタメ先生の構成:\n{entertainment_text}"
    ))]
    resp3 = client.models.generate_content(
        model=_get_model(),
        contents=[types.Content(parts=parts3)],
        config=types.GenerateContentConfig(
            system_instruction=director_prompt,
            response_mime_type="application/json",
            temperature=0.5,
            max_output_tokens=4096,
        ),
    )

    # JSONパース
    plan_text = resp3.text.strip()
    plan_text = re.sub(r'^```(?:json)?\s*\n?', '', plan_text)
    plan_text = re.sub(r'\n?\s*```$', '', plan_text)
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', plan_text, re.DOTALL)
    if m:
        plan_text = m.group(1).strip()

    try:
        plan_sections = json.loads(plan_text)
    except json.JSONDecodeError as e:
        logger.error("監督のプランJSONパース失敗 (pos=%s): %s...", e.pos, plan_text[:500])
        raise ValueError("プラン生成のJSONパースに失敗しました。再度お試しください。")

    if not isinstance(plan_sections, list):
        raise ValueError("プラン生成結果が配列ではありません")

    # 必須フィールド補完
    valid_types = {"introduction", "explanation", "example", "question", "summary"}
    for s in plan_sections:
        if s.get("section_type") not in valid_types:
            s["section_type"] = "explanation"
        s.setdefault("title", "")
        s.setdefault("summary", "")
        s.setdefault("emotion", "neutral")
        s.setdefault("has_question", s.get("section_type") == "question")
        # 間のデフォルト: questionは10秒、それ以外は2秒
        default_wait = 10 if s.get("section_type") == "question" else 2
        s.setdefault("wait_seconds", default_wait)

    logger.info("監督の最終プラン完了（%dセクション）", len(plan_sections))

    return {
        "knowledge": knowledge_text,
        "entertainment": entertainment_text,
        "plan_sections": plan_sections,
    }


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

    parts = _build_image_parts(source_images)

    user_text = f"# 授業タイトル: {lesson_name}\n\n# 教材テキスト:\n{extracted_text}"
    parts.append(types.Part(text=user_text))

    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
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
            last_error = e
            logger.warning("スクリプト生成のJSONパースに失敗 (attempt=%d, pos=%s): %s...（全%d文字）",
                           attempt + 1, e.pos, text[:500], len(text))
            continue

        if not isinstance(sections, list):
            last_error = ValueError("スクリプト生成結果が配列ではありません")
            logger.warning("スクリプト生成結果が配列ではありません (attempt=%d)", attempt + 1)
            continue

        # パース成功
        break
    else:
        # 全リトライ失敗
        if isinstance(last_error, json.JSONDecodeError):
            raise ValueError(f"スクリプト生成のJSONパースに{max_retries}回失敗しました。再度お試しください。")
        raise ValueError(str(last_error))

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


def generate_lesson_script_from_plan(
    lesson_name: str,
    extracted_text: str,
    plan_sections: list[dict],
    source_images: list[str] = None,
) -> list[dict]:
    """プランに基づいて授業スクリプトを生成する

    Args:
        lesson_name: 授業コンテンツ名
        extracted_text: 抽出済みテキスト
        plan_sections: 監督の最終プラン
        source_images: 画像ファイルパスのリスト

    Returns:
        list[dict]: セクション一覧（generate_lesson_scriptと同じ形式）
    """
    client = get_client()

    # プランを読みやすいテキストに変換
    plan_text = "\n".join(
        f"{i+1}. [{s.get('section_type', 'explanation')}] {s.get('title', '')} — {s.get('summary', '')} (感情: {s.get('emotion', 'neutral')}, 間: {s.get('wait_seconds', 2)}秒)"
        + (f" ※問いかけあり" if s.get("has_question") else "")
        for i, s in enumerate(plan_sections)
    )

    system_prompt = f"""あなたは授業スクリプト生成AIです。
以下の授業プランに**忠実に従って**、Twitch配信の授業スクリプトを生成してください。

## 授業プラン（この構成に従うこと）
{plan_text}

## ルール
- プランのセクション数・順序・type・感情・wait_secondsを厳守する
- 各セクションの概要（summary）に沿った内容を発話テキストとして展開する
- バイリンガル（日本語と英語を自然に混ぜる）で教える
- has_question=trueのセクションには問いかけ(question)と回答(answer)を含める
- 教材テキストの内容に忠実に
- wait_secondsはプランの値をそのまま使う（セクション終了後の間）

## 出力形式（JSON配列）
```json
[
  {{
    "section_type": "introduction",
    "content": "発話テキスト（ちょビが話す内容）",
    "tts_text": "TTS用テキスト（発音指示・言語タグ付き）",
    "display_text": "画面に表示するテキスト（要点・例文など自由形式）",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  }}
]
```

JSON配列のみを出力してください。"""

    parts = _build_image_parts(source_images)
    user_text = f"# 授業タイトル: {lesson_name}\n\n# 教材テキスト:\n{extracted_text}"
    parts.append(types.Part(text=user_text))

    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
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

        text = response.text.strip()
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?\s*```$', '', text)

        try:
            sections = json.loads(text)
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning("プランベーススクリプト生成のJSONパース失敗 (attempt=%d, pos=%s)", attempt + 1, e.pos)
            continue

        if not isinstance(sections, list):
            last_error = ValueError("スクリプト生成結果が配列ではありません")
            continue

        break
    else:
        if isinstance(last_error, json.JSONDecodeError):
            raise ValueError(f"スクリプト生成のJSONパースに{max_retries}回失敗しました。再度お試しください。")
        raise ValueError(str(last_error))

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
