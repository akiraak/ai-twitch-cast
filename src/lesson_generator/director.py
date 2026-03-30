"""ディレクター評価: 生成済みセリフのレビューとフィードバック"""

import json
import logging

from google.genai import types

from . import utils
from .utils import _format_main_content_for_prompt

logger = logging.getLogger(__name__)


def _director_review(
    client,
    sections_with_dialogues: list[dict],
    extracted_text: str,
    lesson_name: str,
    en: bool,
    main_content: list[dict] | None = None,
) -> dict:
    """監督が生成済みセリフをレビューし、改善フィードバックを返す（Phase B-3）

    Returns:
        {
            "reviews": [
                {
                    "section_index": 0,
                    "approved": true/false,
                    "feedback": "改善点の具体的な指摘",
                    "revised_directions": [...]  # approved=falseの場合のみ
                },
                ...
            ],
            "overall_feedback": "全体を通してのコメント",
            "generation": { system_prompt, user_prompt, raw_output, model, temperature }
        }
    """
    if en:
        system_prompt = """You are the "Director" reviewing generated dialogue for a Twitch educational stream.
Review the character AI's generated lines and provide feedback.

## Review criteria

### 1. display_text coverage (MOST IMPORTANT)
- Check that the main content in each section's display_text (example sentences, conversation lines, key phrases) is actually read aloud in the dialogue
- If there is "content shown on screen but never spoken", mark as NOT approved
- Check that important items from tables and lists are mentioned in the dialogue

### 2. Naturalness & character consistency
- Do the teacher and student speak in character?
- Are there awkward or unnatural expressions?

### 3. Flow between sections
- Is there context continuity between sections?
- Does information flow naturally?

### 4. Accuracy & coverage
- Are key points from the source material covered?
- Are there factual errors?

## Output format (JSON)
```json
{
  "reviews": [
    {
      "section_index": 0,
      "approved": true,
      "feedback": "Good coverage of display_text content."
    },
    {
      "section_index": 1,
      "approved": false,
      "feedback": "The example sentence 'Good morning' from display_text is not read aloud.",
      "revised_directions": [
        {"speaker": "teacher", "direction": "...", "key_content": "..."},
        {"speaker": "student", "direction": "...", "key_content": "..."}
      ]
    }
  ],
  "overall_feedback": "Overall comment about the lesson quality"
}
```

### Rules for revised_directions
- Only include revised_directions when approved is false
- revised_directions replaces the original dialogue_directions entirely
- Each entry: speaker, direction (2-3 sentence instruction), key_content (specific content to mention)
- Fix the issues identified in feedback
- Keep the same general flow but ensure display_text content is covered

Output ONLY the JSON object."""

        # メインコンテンツ種別レビュー観点追加
        if main_content:
            system_prompt += """

## Content type review (additional criteria)
When pre-analyzed main content is provided, also check:
- conversation: Are roles split between teacher and student? If teacher reads ALL lines alone, mark NOT approved
- passage: Teacher should read and explain. Unnatural role-splitting is a problem
- word_list: Items should be read with explanation, student may repeat or ask
- table: Teacher should walk through entries, not skip important rows
- The reading style must match the content_type
- Items marked ★ PRIMARY must have complete coverage — any omission is grounds for rejection
- Supplementary items should be referenced where relevant but partial coverage is acceptable

## 🔊 Read-aloud content review (CRITICAL)
Items marked 🔊 READ ALOUD are core teaching material that characters MUST read aloud / perform in the dialogue.
- If 🔊 content is a conversation: characters must act it out with the original lines (teacher and student split roles)
- If 🔊 content is a passage: the teacher must read the original text aloud, then explain
- If 🔊 content is omitted, paraphrased beyond recognition, or only briefly mentioned → mark as NOT approved
- The original wording from 🔊 content must appear in the dialogue (verbatim or near-verbatim)

## 🔊 Read-aloud lead-in check (CRITICAL)
- If 🔊 content reading starts without any lead-in (no context-setting, no role assignment) → mark as NOT approved
- The turn immediately before the first 🔊 read-aloud line should set up what is about to be read
- For conversation: there must be a turn that introduces the conversation and assigns roles BEFORE the first line is read
- For passage: there must be a turn that explains what text will be read BEFORE the teacher starts reading"""

    else:
        system_prompt = """あなたは「監督」です。キャラクターAIが生成したセリフを監修し、ダメ出しを行ってください。

## レビュー観点

### 1. display_text カバー率（最重要）
- 各セクションの display_text に含まれるメインコンテンツ（例文・会話文・キーフレーズ）が
  セリフの中で実際に読み上げられているか確認する
- 「画面に表示されているのに読まれていない内容」があれば不合格
- 表・リストの重要項目もセリフ内で言及されているか

### 2. 自然さ・キャラらしさ
- 先生と生徒の口調がそれぞれのキャラクターに合っているか
- 不自然な言い回しやぎこちない表現がないか

### 3. セクション間の繋がり
- 前後のセクションとの文脈が途切れていないか
- 情報の流れが自然か

### 4. 情報の正確性・網羅性
- 教材の重要ポイントが漏れていないか
- 事実関係に誤りがないか

## 出力形式（JSON）
```json
{
  "reviews": [
    {
      "section_index": 0,
      "approved": true,
      "feedback": "display_text の内容が適切にカバーされています。"
    },
    {
      "section_index": 1,
      "approved": false,
      "feedback": "display_text の例文「Good morning」が読み上げられていません。",
      "revised_directions": [
        {"speaker": "teacher", "direction": "...", "key_content": "..."},
        {"speaker": "student", "direction": "...", "key_content": "..."}
      ]
    }
  ],
  "overall_feedback": "全体を通してのコメント"
}
```

### revised_directions のルール
- approved が false の場合のみ含める
- revised_directions は元の dialogue_directions を完全に置き換える
- 各エントリ: speaker, direction（2〜3文の演出指示）, key_content（必ず言及する内容）
- feedback で指摘した問題を修正する内容にする
- 全体の流れは維持しつつ、display_text の内容カバーを確保する

JSONオブジェクトのみを出力してください。"""

        # メインコンテンツ種別レビュー観点追加
        if main_content:
            system_prompt += """

## コンテンツ種別レビュー（追加観点）
事前分析済みメインコンテンツがある場合、以下も確認すること:
- conversation（会話文）: 先生と生徒で役割分担しているか？先生が一人で全部読んでいたら不合格
- passage（文章）: 先生が読み上げ・解説しているか？不自然な役割分担は問題
- word_list（単語集）: 各項目が読み上げ・説明されているか、生徒がリピートや質問しているか
- table（表）: 先生が重要行を解説しているか、重要項目をスキップしていないか
- 読み上げ方が content_type に合っていること
- ★ 主要 のアイテムは完全にカバーされていなければ不合格
- 補助アイテムは関連箇所で言及されていれば十分（部分的カバーでも可）

## 🔊 読み上げ対象コンテンツのレビュー（最重要）
🔊 読み上げ対象 のマークが付いたコンテンツは、キャラクターが必ず読み上げる/演じるべき核心教材です。
- conversation（会話文）の場合: 先生と生徒が原文のセリフを使って演じているか？
- passage（文章）の場合: 先生が原文を読み上げた上で解説しているか？
- 🔊コンテンツが省略されている、大幅に意訳されている、軽く触れただけの場合 → 不合格
- 🔊コンテンツの原文がセリフ内にそのまま（またはほぼそのまま）含まれていること

## 🔊 読み上げ導入チェック（最重要）
- 🔊コンテンツの読み上げが導入なしに始まっている場合（文脈説明なし、役割分担なし）→ 不合格
- 最初の🔊読み上げセリフの直前のターンで、これから何を読むか説明していること
- conversation の場合: 最初のセリフ読み上げの前に、会話の紹介と役割分担のターンがあること
- passage の場合: 先生が読み上げを始める前に、これからどんな文章を読むか説明するターンがあること"""

    # ユーザープロンプト: セクション一覧（display_text + 生成済みセリフ）
    if en:
        user_parts = [f"# Lesson: {lesson_name}\n"]
    else:
        user_parts = [f"# 授業: {lesson_name}\n"]

    for i, s in enumerate(sections_with_dialogues):
        display_text = s.get("display_text", "")
        dialogues = s.get("dialogues", [])

        if en:
            user_parts.append(f"## Section {i}: {s.get('section_type', '')} — {s.get('title', '')}")
            if display_text:
                user_parts.append(f"### display_text (shown on screen):\n{display_text}")
            user_parts.append("### Generated dialogue:")
        else:
            user_parts.append(f"## セクション {i}: {s.get('section_type', '')} — {s.get('title', '')}")
            if display_text:
                user_parts.append(f"### display_text（画面表示）:\n{display_text}")
            user_parts.append("### 生成されたセリフ:")

        for dlg in dialogues:
            speaker = dlg.get("speaker", "?")
            content = dlg.get("content", "")
            user_parts.append(f"  {speaker}: {content}")
        user_parts.append("")

    if main_content:
        if en:
            user_parts.append("# Pre-analyzed main content")
        else:
            user_parts.append("# メインコンテンツ（事前分析済み）")
        user_parts.append(_format_main_content_for_prompt(main_content, en))

    if extracted_text:
        if en:
            user_parts.append(f"# Source material (reference)\n{extracted_text[:3000]}")
        else:
            user_parts.append(f"# 教材テキスト（参考）\n{extracted_text[:3000]}")

    user_prompt = "\n".join(user_parts)
    model = utils._get_director_model()
    temperature = 1.0

    max_retries = 3
    last_error = None
    raw_output = ""
    for attempt in range(max_retries):
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=temperature,
                max_output_tokens=8192,
            ),
        )
        raw_output = response.text.strip()
        try:
            parsed = utils._parse_json_response(raw_output)
            if not isinstance(parsed, dict) or "reviews" not in parsed:
                raise ValueError("レビュー結果にreviews配列がありません")
            break
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning("監督レビューJSONパース失敗 (attempt=%d): %s", attempt + 1, e)
            continue
    else:
        raise ValueError(f"監督レビューのJSONパースに失敗: {last_error}")

    # 補完
    for r in parsed["reviews"]:
        r.setdefault("section_index", 0)
        r.setdefault("approved", True)
        r.setdefault("feedback", "")
        if not r["approved"]:
            r.setdefault("revised_directions", [])
            for dd in r.get("revised_directions", []):
                dd.setdefault("speaker", "teacher")
                dd.setdefault("direction", "")
                dd.setdefault("key_content", "")
    parsed.setdefault("overall_feedback", "")

    parsed["generation"] = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "raw_output": raw_output,
        "model": model,
        "temperature": temperature,
    }

    approved_count = sum(1 for r in parsed["reviews"] if r["approved"])
    total_count = len(parsed["reviews"])
    logger.info("監督レビュー完了: %d/%dセクション合格 (model=%s)", approved_count, total_count, model)

    return parsed
