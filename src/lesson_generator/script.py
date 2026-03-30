"""スクリプト生成: v1（直接生成）+ from_plan（プランベース生成）"""

import json
import logging

from google.genai import types

from . import utils
from .dialogue import (
    get_lesson_characters,
    _build_dialogue_prompt,
    _build_dialogue_output_example,
    _build_section_from_dialogues,
)

logger = logging.getLogger(__name__)


def generate_lesson_script(lesson_name: str, extracted_text: str, source_images: list[str] = None,
                           on_progress=None, student_config: dict = None) -> list[dict]:
    """教材テキスト（+ 画像）から授業スクリプトを生成する

    Args:
        lesson_name: 授業コンテンツ名
        extracted_text: 抽出済みテキスト
        source_images: 画像ファイルパスのリスト（Gemini Vision用）
        on_progress: コールバック(step, total, message) で進捗を通知
        student_config: 生徒キャラ設定（Noneなら従来の一人語り形式）

    Returns:
        list[dict]: セクション一覧
            [{section_type, content, tts_text, display_text, emotion,
              question, answer, wait_seconds, dialogues}, ...]
    """
    def _progress(step, total, msg):
        if on_progress:
            on_progress(step, total, msg)

    en = utils._is_english_mode()
    if en:
        _progress(1, 2, "Generating script with LLM...")
    else:
        _progress(1, 2, "LLMでスクリプト生成中...")
    client = utils.get_client()

    if en:
        system_prompt = """You are a lesson script generation AI.
Based on the source text (and images), generate a Twitch stream lesson script.

## Important: Viewer environment
- **Viewers do NOT have the source material**. They can only see the stream screen
- The only text viewers see is display_text shown on screen
- NEVER use phrases like "look at the text" or "open page X of the material"
- Any content you want viewers to reference (examples, diagrams, terms) MUST be in display_text, and say "check the screen" or "I'll put it on screen"
- The speech (content/tts_text) alone should convey the full meaning. display_text is supplementary visual support

## Rules
- Teach faithfully based on the source material, making it easy to understand
- Teach entirely in English
- AI determines section count based on content (roughly 3-15)
- Each section has a type: introduction, explanation, example, question, summary
- Each section has an emotion: joy, excited, surprise, thinking, sad, embarrassed, neutral
- Question sections include a question and answer
- Must include introduction and conclusion

## content vs tts_text (important)
- content: Text shown in subtitles. NO tags or markup ever
- tts_text: Text sent to TTS. Same as content, but add [lang:xx]...[/lang] tags for **non-English** language parts
  - xx = ja, es, ko, fr, zh etc.
  - Example: content="Let's learn こんにちは today" → tts_text="Let's learn [lang:ja]こんにちは[/lang] today"
  - If English only, no tags needed (same as content)

## display_text (very important)
- display_text is the ONLY visual information viewers see on the stream screen
- It must contain **actual content**, NOT just a title or section name
- Good: "Formal: Good morning / Good afternoon\nInformal: Hi / Hey / What's up?"
- Good: "Q: Your friend says 'What's up?' — what do you reply?\nA) Good morning  B) Not much!  C) How do you do?"
- Bad: "Formal Greetings" (too short, just a title)
- Bad: "Matching Your Responses" (meaningless without content)
- Include key vocabulary, example sentences, comparison tables, quiz choices, etc.
- Use line breaks (\n) to organize content clearly

## Output format (JSON array)
```json
[
  {
    "section_type": "introduction",
    "content": "Speech text (what the host says. No tags)",
    "tts_text": "TTS text (with [lang:xx] tags for non-English parts)",
    "display_text": "Today's Topic: English Greetings\n\nFormal vs Informal — when to use which?",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  },
  {
    "section_type": "explanation",
    "content": "Speech explaining formal greetings",
    "tts_text": "TTS text",
    "display_text": "Formal Greetings:\n• Good morning / afternoon / evening\n• How do you do? (first meeting only)\n• It is a pleasure to meet you.",
    "emotion": "neutral",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  },
  {
    "section_type": "question",
    "content": "Speech for posing the question",
    "tts_text": "TTS text",
    "display_text": "Q: You meet your new boss. What do you say?\nA) Hey!  B) What's up?  C) Good morning",
    "emotion": "thinking",
    "question": "Question for viewers",
    "answer": "Correct answer and explanation",
    "wait_seconds": 8
  }
]
```

Output ONLY the JSON array. No other text."""
    else:
        system_prompt = """あなたは授業スクリプト生成AIです。
教材のテキスト（と画像）をもとに、Twitch配信の授業スクリプトを生成してください。

## 重要: 視聴者の環境
- **視聴者は教材テキストを持っていない**。配信画面しか見えない
- 視聴者が見られるのは配信画面に表示される display_text のみ
- 「テキストを見てください」「教材の○ページを開いて」等の表現は**絶対に使わない**
- 参照してほしい内容（例文・図表・用語）は必ず display_text に含め、「画面を見てください」「画面に出しますね」と言う
- 発話（content/tts_text）だけで内容が伝わるようにする。display_text は補足・視覚的サポート

## ルール
- 教材の内容に忠実に、わかりやすく教える授業スクリプトを作る
- バイリンガル（日本語と英語を自然に混ぜる）で教える
- セクション数はAIが内容に応じて自動調整する（3〜15程度）
- 各セクションにはtypeを付ける: introduction, explanation, example, question, summary
- 感情（emotion）を各セクションに付ける: joy, excited, surprise, thinking, sad, embarrassed, neutral
- questionセクションには問いかけ(question)と回答(answer)を含める
- 導入と締めくくりを必ず含める

## contentとtts_textの違い（重要・厳守）
- content: 字幕に表示するテキスト。タグやマークアップは絶対に含めない
- tts_text: TTS音声合成に送信するテキスト。contentと同じ内容だが、**日本語以外の言語部分に [lang:xx]...[/lang] タグを付ける**
  - xx = en, es, ko, fr, zh 等の言語コード
  - 例: content="Helloは挨拶だよ" → tts_text="[lang:en]Hello[/lang]は挨拶だよ"
  - 例: content="How are you?って聞かれたら..." → tts_text="[lang:en]How are you?[/lang]って聞かれたら..."
  - 例: content="appleはりんごのことだね" → tts_text="[lang:en]apple[/lang]はりんごのことだね"
  - 日本語のみの場合はタグ不要（contentと同じ内容にする）
  - **英語の単語1つでも必ずタグを付ける**。タグがないと日本語アクセントで読まれてしまう

## 英語発音のルール
- 英語の単語・フレーズ・例文はネイティブ英語の発音で読み上げさせる
- tts_textで英語部分を必ず [lang:en]...[/lang] で囲むことが最重要
- 英語の例文を紹介するときは、contentでも自然な導入をする（「画面に出しますね」等）

## display_text（非常に重要）
- display_textは視聴者が配信画面で見る**唯一の視覚情報**
- **実際の内容**を書くこと。タイトルやセクション名だけはNG
- 良い例: "フォーマル: Good morning / Good afternoon\nカジュアル: Hi / Hey / What's up?"
- 良い例: "Q: 上司に初めて会う場面。何と言う？\nA) Hey!  B) What's up?  C) Good morning"
- 悪い例: "フォーマルな挨拶"（短すぎ、タイトルだけ）
- 悪い例: "挨拶の使い分け"（内容がない）
- キーワード、例文、比較表、クイズの選択肢などを含める
- 改行(\n)で見やすく整理する

## 出力形式（JSON配列）
```json
[
  {
    "section_type": "introduction",
    "content": "発話テキスト（ちょビが話す内容。タグなし）",
    "tts_text": "TTS用テキスト（英語部分に[lang:en]タグ付き）",
    "display_text": "今日のテーマ: 英語の挨拶\n\nフォーマル vs カジュアル — 使い分けを学ぼう！",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  },
  {
    "section_type": "explanation",
    "content": "フォーマルな挨拶の説明",
    "tts_text": "TTS用テキスト",
    "display_text": "フォーマルな挨拶:\n• Good morning / afternoon / evening\n• How do you do?（初対面のみ）\n• It is a pleasure to meet you.",
    "emotion": "neutral",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  },
  {
    "section_type": "question",
    "content": "問題を出す発話テキスト",
    "tts_text": "TTS用テキスト",
    "display_text": "Q: 新しい上司に会う場面。何と言う？\nA) Hey!  B) What's up?  C) Good morning",
    "emotion": "thinking",
    "question": "視聴者への問いかけ",
    "answer": "正解と解説",
    "wait_seconds": 8
  }
]
```

JSON配列のみを出力してください。他のテキストは不要です。"""

    # 対話モード: 生徒キャラがいればdialogues指示を追加
    dialogue_mode = False
    if student_config:
        characters = get_lesson_characters()
        teacher_cfg = characters.get("teacher")
        if teacher_cfg:
            dialogue_mode = True
            # 出力形式セクションを対話版に差し替え
            if en:
                system_prompt = system_prompt.rsplit("## Output format", 1)[0]
            else:
                system_prompt = system_prompt.rsplit("## 出力形式", 1)[0]
            system_prompt += _build_dialogue_prompt(teacher_cfg, student_config, en)
            system_prompt += _build_dialogue_output_example(en)

    parts = utils._build_image_parts(source_images)

    if en:
        user_text = f"# Lesson title: {lesson_name}\n\n# Source text:\n{extracted_text}"
    else:
        user_text = f"# 授業タイトル: {lesson_name}\n\n# 教材テキスト:\n{extracted_text}"
    parts.append(types.Part(text=user_text))

    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
        if attempt > 0:
            if en:
                _progress(1, 2, f"Retrying script generation ({attempt + 1}/{max_retries})...")
            else:
                _progress(1, 2, f"LLMでスクリプト再生成中（リトライ {attempt + 1}/{max_retries}）...")
        response = client.models.generate_content(
            model=utils._get_model(),
            contents=[types.Content(parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )

        _progress(2, 2, "JSONパース・セクション整理中...")

        try:
            sections = utils._parse_json_response(response.text)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning("スクリプト生成のJSONパースに失敗 (attempt=%d): %s", attempt + 1, e)
            continue

        if not isinstance(sections, list):
            last_error = ValueError("スクリプト生成結果が配列ではありません")
            logger.warning("スクリプト生成結果が配列ではありません (attempt=%d)", attempt + 1)
            continue

        break
    else:
        if isinstance(last_error, json.JSONDecodeError):
            raise ValueError(f"スクリプト生成のJSONパースに{max_retries}回失敗しました。再度お試しください。")
        raise ValueError(str(last_error))

    # 必須フィールドの補完（プランなし — titleなし）
    valid_types = {"introduction", "explanation", "example", "question", "summary"}
    result = []
    for s in sections:
        dialogues_raw = s.get("dialogues", [])

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
        # 対話モードならdialoguesからcontent/tts_text/emotionを自動構築
        if dialogue_mode and dialogues_raw:
            section["dialogues"] = dialogues_raw  # リストのまま渡す
            section = _build_section_from_dialogues(section)
        # dialoguesをJSON文字列に変換してDB保存用にする
        section["dialogues"] = json.dumps(dialogues_raw, ensure_ascii=False) if dialogues_raw else ""
        if section["section_type"] not in valid_types:
            section["section_type"] = "explanation"
        result.append(section)

    return result


def generate_lesson_script_from_plan(
    lesson_name: str,
    extracted_text: str,
    plan_sections: list[dict],
    source_images: list[str] = None,
    on_progress=None,
    student_config: dict = None,
) -> list[dict]:
    """プランに基づいて授業スクリプトを生成する

    Args:
        lesson_name: 授業コンテンツ名
        extracted_text: 抽出済みテキスト
        plan_sections: 監督の最終プラン
        source_images: 画像ファイルパスのリスト
        on_progress: コールバック(step, total, message) で進捗を通知
        student_config: 生徒キャラ設定（Noneなら従来の一人語り形式）

    Returns:
        list[dict]: セクション一覧（generate_lesson_scriptと同じ形式）
    """
    def _progress(step, total, msg):
        if on_progress:
            on_progress(step, total, msg)

    en = utils._is_english_mode()
    if en:
        _progress(1, 2, "Generating script from plan...")
    else:
        _progress(1, 2, "プランに基づいてスクリプト生成中...")
    client = utils.get_client()

    # プランを読みやすいテキストに変換
    if en:
        plan_text = "\n".join(
            f"{i+1}. [{s.get('section_type', 'explanation')}] {s.get('title', '')} — {s.get('summary', '')} (emotion: {s.get('emotion', 'neutral')}, pause: {s.get('wait_seconds', 2)}s)"
            + (" *has question" if s.get("has_question") else "")
            for i, s in enumerate(plan_sections)
        )
    else:
        plan_text = "\n".join(
            f"{i+1}. [{s.get('section_type', 'explanation')}] {s.get('title', '')} — {s.get('summary', '')} (感情: {s.get('emotion', 'neutral')}, 間: {s.get('wait_seconds', 2)}秒)"
            + (f" ※問いかけあり" if s.get("has_question") else "")
            for i, s in enumerate(plan_sections)
        )

    if en:
        system_prompt = f"""You are a lesson script generation AI.
Follow the lesson plan below **strictly** to generate a Twitch stream lesson script.

## Lesson plan (follow this structure)
{plan_text}

## Important: Viewer environment
- **Viewers do NOT have the source material**. They can only see the stream screen
- The only text viewers see is display_text shown on screen
- NEVER use phrases like "look at the text" or "open page X"
- Any content you want viewers to reference MUST be in display_text, and say "check the screen"
- The speech (content/tts_text) alone should convey the full meaning. display_text is supplementary

## Rules
- Strictly follow the plan's section count, order, type, emotion, and wait_seconds
- Expand each section's summary into speech text
- Teach entirely in English
- Sections with has_question=true must include question and answer
- Stay faithful to the source material
- Use wait_seconds values from the plan as-is

## content vs tts_text (important)
- content: Text shown in subtitles. NO tags or markup ever
- tts_text: Text sent to TTS. Same as content, but add [lang:xx]...[/lang] tags for **non-English** parts
  - xx = ja, es, ko, fr, zh etc.
  - Example: content="Let's learn こんにちは today" → tts_text="Let's learn [lang:ja]こんにちは[/lang] today"
  - If English only, no tags needed (same as content)

## display_text (very important)
- display_text is the ONLY visual information viewers see on the stream screen
- It must contain **actual content**, NOT just a title or section name
- Good: "Formal: Good morning / Good afternoon\\nInformal: Hi / Hey / What's up?"
- Good: "Q: Your friend says 'What's up?' — what do you reply?\\nA) Good morning  B) Not much!  C) How do you do?"
- Bad: "Formal Greetings" (too short, just a title)
- Bad: "Matching Your Responses" (meaningless without content)
- Include key vocabulary, example sentences, comparison tables, quiz choices, etc.
- Use line breaks (\\n) to organize content clearly

## Output format (JSON array)
```json
[
  {{
    "section_type": "introduction",
    "content": "Speech text (what the host says. No tags)",
    "tts_text": "TTS text (with [lang:xx] tags for non-English parts)",
    "display_text": "Today's Topic: English Greetings\\n\\nFormal vs Informal — when to use which?",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  }}
]
```

Output ONLY the JSON array."""
    else:
        system_prompt = f"""あなたは授業スクリプト生成AIです。
以下の授業プランに**忠実に従って**、Twitch配信の授業スクリプトを生成してください。

## 授業プラン（この構成に従うこと）
{plan_text}

## 重要: 視聴者の環境
- **視聴者は教材テキストを持っていない**。配信画面しか見えない
- 視聴者が見られるのは配信画面に表示される display_text のみ
- 「テキストを見てください」「教材の○ページを開いて」等の表現は**絶対に使わない**
- 参照してほしい内容（例文・図表・用語）は必ず display_text に含め、「画面を見てください」「画面に出しますね」と言う
- 発話（content/tts_text）だけで内容が伝わるようにする。display_text は補足・視覚的サポート

## ルール
- プランのセクション数・順序・type・感情・wait_secondsを厳守する
- 各セクションの概要（summary）に沿った内容を発話テキストとして展開する
- バイリンガル（日本語と英語を自然に混ぜる）で教える
- has_question=trueのセクションには問いかけ(question)と回答(answer)を含める
- 教材テキストの内容に忠実に
- wait_secondsはプランの値をそのまま使う（セクション終了後の間）

## contentとtts_textの違い（重要・厳守）
- content: 字幕に表示するテキスト。タグやマークアップは絶対に含めない
- tts_text: TTS音声合成に送信するテキスト。contentと同じ内容だが、**日本語以外の言語部分に [lang:xx]...[/lang] タグを付ける**
  - xx = en, es, ko, fr, zh 等の言語コード
  - 例: content="Helloは挨拶だよ" → tts_text="[lang:en]Hello[/lang]は挨拶だよ"
  - 例: content="How are you?って聞かれたら..." → tts_text="[lang:en]How are you?[/lang]って聞かれたら..."
  - 例: content="appleはりんごのことだね" → tts_text="[lang:en]apple[/lang]はりんごのことだね"
  - 日本語のみの場合はタグ不要（contentと同じ内容にする）
  - **英語の単語1つでも必ずタグを付ける**。タグがないと日本語アクセントで読まれてしまう

## 英語発音のルール
- 英語の単語・フレーズ・例文はネイティブ英語の発音で読み上げさせる
- tts_textで英語部分を必ず [lang:en]...[/lang] で囲むことが最重要
- 英語の例文を紹介するときは、contentでも自然な導入をする（「画面に出しますね」等）

## display_text（非常に重要）
- display_textは視聴者が配信画面で見る**唯一の視覚情報**
- **実際の内容**を書くこと。タイトルやセクション名だけはNG
- 良い例: "フォーマル: Good morning / Good afternoon\\nカジュアル: Hi / Hey / What's up?"
- 良い例: "Q: 上司に初めて会う場面。何と言う？\\nA) Hey!  B) What's up?  C) Good morning"
- 悪い例: "フォーマルな挨拶"（短すぎ、タイトルだけ）
- 悪い例: "挨拶の使い分け"（内容がない）
- キーワード、例文、比較表、クイズの選択肢などを含める
- 改行(\\n)で見やすく整理する

## 出力形式（JSON配列）
```json
[
  {{
    "section_type": "introduction",
    "content": "発話テキスト（ちょビが話す内容。タグなし）",
    "tts_text": "TTS用テキスト（英語部分に[lang:en]タグ付き）",
    "display_text": "今日のテーマ: 英語の挨拶\\n\\nフォーマル vs カジュアル — 使い分けを学ぼう！",
    "emotion": "excited",
    "question": "",
    "answer": "",
    "wait_seconds": 0
  }}
]
```

JSON配列のみを出力してください。"""

    # 対話モード: 生徒キャラがいればdialogues指示を追加
    dialogue_mode = False
    if student_config:
        characters = get_lesson_characters()
        teacher_cfg = characters.get("teacher")
        if teacher_cfg:
            dialogue_mode = True
            if en:
                system_prompt = system_prompt.rsplit("## Output format", 1)[0]
            else:
                system_prompt = system_prompt.rsplit("## 出力形式", 1)[0]
            system_prompt += _build_dialogue_prompt(teacher_cfg, student_config, en)
            system_prompt += _build_dialogue_output_example(en)

    parts = utils._build_image_parts(source_images)
    if en:
        user_text = f"# Lesson title: {lesson_name}\n\n# Source text:\n{extracted_text}"
    else:
        user_text = f"# 授業タイトル: {lesson_name}\n\n# 教材テキスト:\n{extracted_text}"
    parts.append(types.Part(text=user_text))

    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
        if attempt > 0:
            if en:
                _progress(1, 2, f"Retrying plan-based script generation ({attempt + 1}/{max_retries})...")
            else:
                _progress(1, 2, f"プランベーススクリプト再生成中（リトライ {attempt + 1}/{max_retries}）...")
        response = client.models.generate_content(
            model=utils._get_model(),
            contents=[types.Content(parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )

        _progress(2, 2, "JSONパース・セクション整理中...")

        try:
            sections = utils._parse_json_response(response.text)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning("プランベーススクリプト生成のJSONパース失敗 (attempt=%d): %s", attempt + 1, e)
            continue

        if not isinstance(sections, list):
            last_error = ValueError("スクリプト生成結果が配列ではありません")
            continue

        break
    else:
        if isinstance(last_error, json.JSONDecodeError):
            raise ValueError(f"スクリプト生成のJSONパースに{max_retries}回失敗しました。再度お試しください。")
        raise ValueError(str(last_error))

    # 必須フィールドの補完 + プランのtitleをマージ
    valid_types = {"introduction", "explanation", "example", "question", "summary"}
    result = []
    for i, s in enumerate(sections):
        plan_title = plan_sections[i].get("title", "") if i < len(plan_sections) else ""
        dialogues_raw = s.get("dialogues", [])

        section = {
            "section_type": s.get("section_type", "explanation"),
            "title": plan_title,
            "content": s.get("content", ""),
            "tts_text": s.get("tts_text", s.get("content", "")),
            "display_text": s.get("display_text", ""),
            "emotion": s.get("emotion", "neutral"),
            "question": s.get("question", ""),
            "answer": s.get("answer", ""),
            "wait_seconds": int(s.get("wait_seconds", 0)),
        }
        if dialogue_mode and dialogues_raw:
            section["dialogues"] = dialogues_raw
            section = _build_section_from_dialogues(section)
        section["dialogues"] = json.dumps(dialogues_raw, ensure_ascii=False) if dialogues_raw else ""
        if section["section_type"] not in valid_types:
            section["section_type"] = "explanation"
        result.append(section)

    return result
