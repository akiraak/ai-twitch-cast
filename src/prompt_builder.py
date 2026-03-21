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
        rules.append(f"{p_name}で返答する。")
        rules.append(f"- コメントが別の言語の場合 → その言語で返答し、{p_name}も自然に混ぜる")
        rules.append(f"- translationには{p_name}訳を入れる（コメントが{p_name}の場合はEnglish訳）")
        return rules

    s_name = _lang_name(sub)

    rules.append(f"{p_name}をメインで話し、{s_name}を混ぜる。")

    # 混ぜ具合に応じた指示
    if mix == "low":
        rules.append(f"- {s_name}は挨拶・感嘆詞・一単語程度にとどめる")
    elif mix == "medium":
        rules.append(f"- {s_name}をフレーズ単位で自然に混ぜる。文のどの位置にも置ける（文頭・文中・独立）")
        rules.append(f"- 毎回同じ位置（語尾だけ等）にならないようにする")
    else:  # high
        rules.append(f"- {s_name}を文単位で積極的に使う。両言語ほぼ均等に混ぜる")
        rules.append(f"- 1つの返答の中で両方の言語で文を作る")

    # サブ言語がローマ字表記可能な場合の注意
    if sub == "ja":
        rules.append("- 日本語はひらがな・カタカナで書く。ローマ字（sugoi, kawaii等）は使わない")
    elif primary == "ja":
        pass  # 基本言語が日本語ならローマ字問題なし

    # 他言語コメントへの対応（固定ルール）
    rules.append(f"- コメントが{p_name}でも{s_name}でもない言語の場合 → その言語で返答する。{p_name}と{s_name}も自然に混ぜる")

    # 翻訳欄の指示
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

    parts = [
        char["system_prompt"],
        "",
        "## ルール",
    ]
    for rule in char.get("rules", []):
        parts.append(f"- {rule}")

    # 自分の記憶メモ
    if self_note:
        parts.extend([
            "",
            "## あなたの記憶メモ（今日の配信で話したこと・感じたこと）",
            self_note,
        ])

    # ペルソナ（過去の応答から抽出した性格特徴）
    if persona:
        parts.extend([
            "",
            "## あなた自身の性格（過去の会話から抽出）",
            persona,
        ])

    # 配信コンテキスト
    if stream_context:
        parts.extend(["", "## 現在の配信情報"])
        if stream_context.get("title"):
            parts.append(f"- 配信タイトル: {stream_context['title']}")
        if stream_context.get("topic"):
            parts.append(f"- 話題のトピック: {stream_context['topic']}")
        if stream_context.get("todo_items"):
            parts.append("- 作業中のタスク:")
            for item in stream_context["todo_items"]:
                parts.append(f"  - {item}")

    lang_rules = build_language_rules()
    parts.extend(["", "## 言語ルール"])
    for rule in lang_rules:
        parts.append(rule)

    # 感情分布ガイド
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

    parts.extend([
        "",
        "## 重要：多様性",
        "過去の会話履歴と同じ文体・同じ構文パターンを繰り返さないこと。",
        "毎回異なる文の組み立て方、異なる表現を使うこと。",
        "直前の自分の返答と同じ書き出し・同じ感情を使わない。",
        "",
        "## 出力形式",
        "必ず以下のJSON形式で返答してください。それ以外のテキストは出力しないでください。",
        '{"speech": "返答テキスト", "tts_text": "読み上げ用テキスト", "emotion": "感情", "translation": "翻訳テキスト"}',
        f"emotionは次のいずれか: {emotion_list}",
        "",
        "## speechとtts_textの違い（重要・厳守）",
        "- speech: チャットや字幕に表示するテキスト。タグやマークアップは絶対に含めないこと。そのまま人に見せるテキスト。",
        "- tts_text: TTS音声合成に送信するテキスト。speechと同じ内容だが、日本語以外の言語部分に [lang:xx]...[/lang] タグを付ける。",
        '  - xx = en, es, ko, fr, zh 等の言語コード',
        '  - 例: speech="今日はClaude Codeで開発してるよ！" → tts_text="今日は[lang:en]Claude Code[/lang]で開発してるよ！"',
        '  - 例: speech="¡Hola!いらっしゃい！Welcome！" → tts_text="[lang:es]¡Hola![/lang]いらっしゃい！[lang:en]Welcome[/lang]！"',
        "  - 日本語のみの場合はタグ不要（responseと同じ内容にする）",
    ])

    return "\n".join(parts)
