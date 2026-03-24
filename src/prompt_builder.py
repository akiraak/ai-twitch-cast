"""プロンプト組み立て・配信言語設定"""

# 対応言語一覧
SUPPORTED_LANGUAGES = {
    "ja": "日本語",
    "en": "English",
    "ko": "한국어",
    "es": "Español",
    "zh": "中文",
    "fr": "Français",
    "pt": "Português",
    "de": "Deutsch",
}

# 混ぜ具合レベル
MIX_LEVELS = ("low", "medium", "high")

# デフォルト配信言語設定
_stream_lang = {"primary": "ja", "sub": "en", "mix": "low"}


def get_stream_language():
    """現在の配信言語設定を返す"""
    return dict(_stream_lang)


def set_stream_language(primary, sub="none", mix="low"):
    """配信言語を設定する

    Args:
        primary: 基本言語コード（例: "ja", "en"）
        sub: サブ言語コード（例: "en", "ja", "none"）
        mix: 混ぜ具合（"low", "medium", "high"）
    """
    if primary not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unknown primary language: {primary}")
    if sub != "none" and sub not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unknown sub language: {sub}")
    if mix not in MIX_LEVELS:
        raise ValueError(f"Unknown mix level: {mix}")
    if sub != "none" and primary == sub:
        raise ValueError("Primary and sub language must be different")
    global _stream_lang
    _stream_lang = {"primary": primary, "sub": sub, "mix": mix}


def _lang_name(code):
    """言語コードから言語名を返す"""
    return SUPPORTED_LANGUAGES.get(code, code)


def build_language_rules():
    """現在の配信言語設定から言語ルールテキストを生成する

    Returns:
        list[str]: プロンプトに注入する言語ルール行のリスト
    """
    primary = _stream_lang["primary"]
    sub = _stream_lang["sub"]
    mix = _stream_lang["mix"]
    p_name = _lang_name(primary)
    rules = []

    if sub == "none":
        # サブ言語なし: 基本言語のみ
        if primary != "ja":
            rules.append(f"Respond in {p_name}.")
            rules.append(f"- If a comment is in another language → respond in that language, mixing in {p_name} naturally")
            rules.append("- Put Japanese translation in the translation field")
        else:
            rules.append(f"{p_name}で返答する。")
            rules.append(f"- コメントが別の言語の場合 → その言語で返答し、{p_name}も自然に混ぜる")
            rules.append(f"- translationには{p_name}訳を入れる（コメントが{p_name}の場合はEnglish訳）")
        return rules

    s_name = _lang_name(sub)

    if primary != "ja":
        # 英語等ベースのバイリンガルモード
        rules.append(f"Speak mainly in {p_name}, mixing in {s_name}.")

        if mix == "low":
            rules.append(f"- Limit {s_name} to greetings, exclamations, and single words")
        elif mix == "medium":
            rules.append(f"- Mix {s_name} naturally at phrase level. Can appear anywhere in a sentence (beginning, middle, standalone)")
            rules.append("- Vary placement — don't always put it in the same position")
        else:  # high
            rules.append(f"- Use {s_name} actively at sentence level. Mix both languages roughly equally")
            rules.append("- Create sentences in both languages within a single response")

        if sub == "ja":
            rules.append("- Write Japanese in hiragana/katakana. Never use romaji (sugoi, kawaii, etc.)")

        rules.append(f"- If a comment is in neither {p_name} nor {s_name} → respond in that language, naturally mixing in {p_name} and {s_name}")
        rules.append(f"- Put {s_name} translation in the translation field")
    else:
        # 日本語ベースのバイリンガルモード
        rules.append(f"{p_name}をメインで話し、{s_name}を混ぜる。")

        if mix == "low":
            rules.append(f"- {s_name}は挨拶・感嘆詞・一単語程度にとどめる")
        elif mix == "medium":
            rules.append(f"- {s_name}をフレーズ単位で自然に混ぜる。文のどの位置にも置ける（文頭・文中・独立）")
            rules.append(f"- 毎回同じ位置（語尾だけ等）にならないようにする")
        else:  # high
            rules.append(f"- {s_name}を文単位で積極的に使う。両言語ほぼ均等に混ぜる")
            rules.append(f"- 1つの返答の中で両方の言語で文を作る")

        if sub == "ja":
            rules.append("- 日本語はひらがな・カタカナで書く。ローマ字（sugoi, kawaii等）は使わない")

        rules.append(f"- コメントが{p_name}でも{s_name}でもない言語の場合 → その言語で返答する。{p_name}と{s_name}も自然に混ぜる")
        rules.append(f"- translationには{s_name}訳を入れる")

    return rules


def build_tts_style():
    """現在の配信言語設定からTTSスタイル指示を生成する

    Returns:
        str: Gemini TTSに渡すスタイル指示テキスト
    """
    primary = _stream_lang["primary"]
    sub = _stream_lang["sub"]
    p_name = _lang_name(primary)

    if primary != "ja":
        parts = ["Read in a cheerful, warm, always-smiling tone."]
    else:
        parts = ["Read in a cheerful, warm, always-smiling tone (にこにこ)."]

    if sub != "none":
        s_name = _lang_name(sub)
        parts.append(f"IMPORTANT: When you encounter {s_name} words, pronounce them with native {s_name} pronunciation.")
        parts.append(f"Switch naturally between {p_name} and {s_name} pronunciation.")
    else:
        if primary != "ja":
            parts.append(f"Use natural {p_name} pronunciation.")

    parts.append("When you encounter other languages, pronounce them as naturally as possible.")

    return " ".join(parts)


def build_system_prompt(char, stream_context=None, self_note=None, persona=None):
    """キャラクター設定からシステムプロンプトを構築する

    Args:
        char: キャラクター設定dict（get_character()の戻り値）
        stream_context: 配信情報 {title, topic, todo_items}
        self_note: アバター自身の記憶メモ
        persona: ペルソナ（過去の応答から抽出した性格特徴）
    """
    emotions = char.get("emotions", {})
    emotion_list = ", ".join(emotions.keys())

    from src import db
    primary = _stream_lang["primary"]
    max_chars = int(db.get_setting("speech.max_chars", "100"))

    if primary != "ja":
        word_count = max(10, max_chars // 5)
        if word_count <= 15:
            sentence_guide = "1-2 sentences"
        elif word_count <= 25:
            sentence_guide = "1-3 sentences"
        else:
            sentence_guide = "2-4 sentences"
        length_rule = f"- Aim for about {word_count} words in {sentence_guide}"
    else:
        if max_chars <= 50:
            sentence_guide = "1〜2文"
        elif max_chars <= 100:
            sentence_guide = "1〜3文"
        else:
            sentence_guide = "2〜4文"
        length_rule = f"- {sentence_guide}、日本語で{max_chars}文字以内を目指す"

    en = primary != "ja"
    p_name = _lang_name(primary)

    parts = [
        char["system_prompt"],
        "",
        "## Rules" if en else "## ルール",
        length_rule,
    ]
    for rule in char.get("rules", []):
        parts.append(f"- {rule}")

    # 自分の記憶メモ
    if self_note:
        parts.extend([
            "",
            "## Your memory notes (what you talked about and felt during today's stream)" if en else "## あなたの記憶メモ（今日の配信で話したこと・感じたこと）",
            self_note,
        ])

    # ペルソナ（過去の応答から抽出した性格特徴）
    if persona:
        parts.extend([
            "",
            "## Your personality (extracted from past conversations)" if en else "## あなた自身の性格（過去の会話から抽出）",
            persona,
        ])

    # 配信コンテキスト
    if stream_context:
        parts.extend(["", "## Current stream info" if en else "## 現在の配信情報"])
        if stream_context.get("title"):
            parts.append(f"- Stream title: {stream_context['title']}" if en else f"- 配信タイトル: {stream_context['title']}")
        if stream_context.get("todo_items"):
            parts.append("- Current tasks:" if en else "- 作業中のタスク:")
            for item in stream_context["todo_items"]:
                parts.append(f"  - {item}")
        if stream_context.get("lesson"):
            lesson = stream_context["lesson"]
            if en:
                parts.extend([
                    "",
                    "## Current lesson (teacher mode active)",
                    f"- Lesson name: {lesson.get('lesson_name', '')}",
                ])
                if lesson.get("current_section"):
                    parts.append(f"- Current section ({lesson.get('section_type', '')}): {lesson['current_section']}")
                parts.extend([
                    "- Answer viewer questions briefly, relating them to the lesson content. Don't derail the lesson",
                    "- You may answer off-topic questions too, but keep it short and get back to the lesson",
                ])
            else:
                parts.extend([
                    "",
                    "## 現在の授業（教師モード実行中）",
                    f"- 授業名: {lesson.get('lesson_name', '')}",
                ])
                if lesson.get("current_section"):
                    parts.append(f"- 現在のセクション（{lesson.get('section_type', '')}）: {lesson['current_section']}")
                parts.extend([
                    "- 視聴者からの質問には授業内容に関連づけて簡潔に回答し、授業を脱線させない",
                    "- 授業と無関係な質問にも答えてOKだが、手短にして授業に戻る意識を持つ",
                ])

    lang_rules = build_language_rules()
    parts.extend(["", "## Language rules" if en else "## 言語ルール"])
    for rule in lang_rules:
        parts.append(rule)

    # 感情分布ガイド
    if en:
        parts.extend([
            "",
            "## Emotion usage (important — follow strictly)",
            "- neutral: Normal conversation, small talk, information exchange → Use this for 50%+ of responses",
            "- joy: Only when genuinely happy (big achievements, compliments). Don't overuse",
            "- excited: Exciting topics, looking forward to something, high energy",
            "- surprise: Unexpected information, surprising facts",
            "- thinking: Answering questions, pondering topics, thinking things through",
            "- sad: Bad news, things not going well",
            "- embarrassed: When complimented and feeling shy",
            "- When in doubt, use neutral. joy is for special moments only",
        ])
    else:
        parts.extend([
            "",
            "## 感情の使い分け（重要・厳守）",
            "- neutral: 普通の会話、相槌、情報交換、雑談 → 全体の50%以上はこれを使え",
            "- joy: 本当に嬉しいとき限定（大きな成果、褒められた時）。乱用禁止",
            "- excited: ワクワクする話題、楽しみなこと、テンション上がるとき",
            "- surprise: 予想外の情報、意外な事実を聞いたとき",
            "- thinking: 質問への回答、考え込む話題、悩む系の話題",
            "- sad: 残念なニュース、うまくいかなかったとき",
            "- embarrassed: 褒められて照れるとき、恥ずかしいとき",
            "- 迷ったらneutralを選べ。joyは特別なときだけ",
        ])

    # SE（効果音）セクション
    from src.se_resolver import get_available_categories
    se_categories = get_available_categories()
    if se_categories:
        if en:
            parts.extend([
                "",
                "## Sound effects (optional)",
                "Choose a sound effect that matches the conversation. However:",
                "- Not every response needs an SE. Only use for special moments (greetings, surprises, good news, etc.)",
                "- About 1 in 5 responses is enough. Don't overuse",
                "- Don't use the same SE consecutively",
                "",
                "Available SE categories:",
            ])
        else:
            parts.extend([
                "",
                "## SE（効果音）選択（任意）",
                "会話の内容に合った効果音を選んでください。ただし：",
                "- 全ての返答にSEは不要。特別な瞬間（挨拶・驚き・嬉しいニュース等）にのみ使う",
                "- 5回に1回程度の頻度で十分。使いすぎ注意",
                "- 同じSEを連続で使わない",
                "",
                "使用可能なSEカテゴリ:",
            ])
        for cat in se_categories:
            desc = f" — {cat['description']}" if cat["description"] else ""
            parts.append(f"- {cat['name']}{desc}")
        parts.append("")
        if en:
            parts.append('If no SE is appropriate, set "se" to null.')
        else:
            parts.append('SEが不要な場合は "se" を null にしてください。')

    if en:
        parts.extend([
            "",
            "## Important: Variety",
            "Don't repeat the same sentence structure or phrasing as previous responses.",
            "Use different sentence constructions and expressions each time.",
            "Don't start the same way or use the same emotion as your previous response.",
            "",
            "## Output format",
            "Reply ONLY in the following JSON format. No other text.",
            '{"speech": "response text", "tts_text": "TTS text", "emotion": "emotion", "translation": "translation", "se": "category or null"}',
            f"emotion must be one of: {emotion_list}",
            "",
            "## speech vs tts_text (important — follow strictly)",
            "- speech: Displayed in chat and subtitles. Never include any tags or markup. Plain text for viewers.",
            f"- tts_text: Sent to TTS. Same as speech, but add [lang:xx]...[/lang] tags for non-{p_name} parts.",
            '  - xx = ja, es, ko, fr, zh etc.',
            f'  - Example: speech="Let\'s learn こんにちは today!" → tts_text="Let\'s learn [lang:ja]こんにちは[/lang] today!"',
            f"  - If {p_name} only, no tags needed (same as speech)",
        ])
    else:
        parts.extend([
            "",
            "## 重要：多様性",
            "過去の会話履歴と同じ文体・同じ構文パターンを繰り返さないこと。",
            "毎回異なる文の組み立て方、異なる表現を使うこと。",
            "直前の自分の返答と同じ書き出し・同じ感情を使わない。",
            "",
            "## 出力形式",
            "必ず以下のJSON形式で返答してください。それ以外のテキストは出力しないでください。",
            '{"speech": "返答テキスト", "tts_text": "読み上げ用テキスト", "emotion": "感情", "translation": "翻訳テキスト", "se": "カテゴリ名 or null"}',
            f"emotionは次のいずれか: {emotion_list}",
            "",
            "## speechとtts_textの違い（重要・厳守）",
            "- speech: チャットや字幕に表示するテキスト。タグやマークアップは絶対に含めないこと。そのまま人に見せるテキスト。",
            "- tts_text: TTS音声合成に送信するテキスト。speechと同じ内容だが、日本語以外の言語部分に [lang:xx]...[/lang] タグを付ける。",
            '  - xx = en, es, ko, fr, zh 等の言語コード',
            '  - 例: speech="今日はClaude Codeで開発してるよ！" → tts_text="今日は[lang:en]Claude Code[/lang]で開発してるよ！"',
            '  - 例: speech="¡Hola!いらっしゃい！Welcome！" → tts_text="[lang:es]¡Hola![/lang]いらっしゃい！[lang:en]Welcome[/lang]！"',
            "  - 日本語のみの場合はタグ不要（speechと同じ内容にする）",
        ])

    return "\n".join(parts)
