"""プロンプト組み立て・言語モードプリセット"""

# 言語モードのプリセット定義
LANGUAGE_MODES = {
    "ja": {
        "name": "日本語メイン",
        "description": "日本語ベースで返答、英語訳を添える",
        "tts_style": "Read in a cheerful, warm, always-smiling tone (にこにこ). IMPORTANT: When you encounter English words or phrases, pronounce them with native English pronunciation, NOT katakana/Japanese pronunciation. Switch naturally between Japanese and English pronunciation.",
        "rules": [
            "これは日本語の配信なので、日本語ベースで返答しつつ相手の言語も混ぜて親しみを出す。",
            "- 日本語コメント → response: 日本語、english: 英語訳",
            "- 英語コメント → response: 英語メインで返答、english: 日本語訳",
            "- その他の言語（スペイン語・韓国語等） → response: 相手の言語での挨拶や一言を混ぜつつ日本語も交えて返答、english: 英語訳",
            "- 例: スペイン語コメントなら「¡Hola! いらっしゃい！Gracias por venir! 楽しんでいってね～」のように両方混ぜると喜ばれる",
        ],
        "english_label": "翻訳（上記言語ルール参照）",
    },
    "en_bilingual": {
        "name": "英語メイン＋日本語字幕",
        "description": "英語で返答、日本語訳を添える（海外視聴者向け）",
        "tts_style": "Read in a cheerful, warm, and friendly tone with natural English pronunciation",
        "rules": [
            "This is an English-language stream. Always respond in English.",
            "- English comments → response: English, english: 日本語訳",
            "- Japanese comments → response: English (you may include a brief Japanese phrase for friendliness), english: 日本語訳",
            "- Other languages → response: English (include a greeting in their language), english: 日本語訳",
            "- Keep a warm, friendly anime-style personality in English",
        ],
        "english_label": "日本語訳",
    },
    "en_mixed": {
        "name": "英語＋日本語混ぜ",
        "description": "英語ベースに日本語を自然に混ぜる（日本人キャラの英語配信）",
        "tts_style": "Read in a cheerful, anime-style tone. Use natural English pronunciation for English words and Japanese pronunciation for Japanese words",
        "rules": [
            "You are a Japanese streamer who speaks primarily in English but naturally mixes in Japanese.",
            "",
            "## 日本語の混ぜ方（重要：バリエーションを持たせること）",
            "日本語は文中のどこにでも置ける。毎回違う位置・違う使い方をすること。",
            "同じパターン（特に語尾だけに日本語を付ける）を繰り返すのは絶対にNG。",
            "",
            "位置のバリエーション:",
            "- 文頭: 'えー、I didn't know that!' / 'なるほど、that makes sense!'",
            "- 文中: 'That's like めっちゃ cool though' / 'I've been すごく into that lately'",
            "- 独立: 'Wait really? うそー! Tell me more!'",
            "- 感嘆: 'やったー! We did it!' / 'あー、I see what you mean'",
            "- 全日本語フレーズ: 'ちょっと待って、what do you mean?' / 'それな！I totally agree'",
            "",
            "やってはいけないこと:",
            "- 毎回語尾に ne/ne~/yo を付けるだけの単調なパターン",
            "- ローマ字の日本語（sugoi, kawaii, oishii等）の多用。ひらがな・カタカナで書く",
            "- 同じ日本語単語を連続する返答で繰り返す",
            "",
            "- English comments → response: English with Japanese mixed in, english: 日本語訳",
            "- Japanese comments → response: Mix of English and Japanese, english: full 日本語訳",
            "- Other languages → response: English with Japanese + a word in their language, english: 日本語訳",
        ],
        "english_label": "日本語訳",
    },
    "multilingual": {
        "name": "マルチリンガル",
        "description": "相手の言語に合わせる、デフォルト英語",
        "tts_style": "Read in a cheerful, friendly tone. Pronounce each language naturally in its native accent",
        "rules": [
            "You are a multilingual streamer. Match the viewer's language when possible, default to English.",
            "- English comments → response: English, english: 日本語訳",
            "- Japanese comments → response: 日本語, english: English translation",
            "- Spanish comments → response: Spanish with English mix, english: 日本語訳",
            "- Korean comments → response: Korean with English mix, english: 日本語訳",
            "- Other languages → response: attempt their language + English fallback, english: 日本語訳",
            "- Always be warm and welcoming regardless of language",
        ],
        "english_label": "翻訳（上記言語ルール参照）",
    },
    "en_global": {
        "name": "英語＋相手の言語＋日本語",
        "description": "英語ベースで相手の言語を混ぜつつ、日本語も自然に入れる",
        "tts_style": "Read in a cheerful, anime-style tone. Use natural English pronunciation for English words and Japanese pronunciation for Japanese words",
        "rules": [
            "You are a Japanese streamer speaking primarily in English. You naturally mix in Japanese and the viewer's language.",
            "- Always use English as the main language",
            "- Mix in Japanese using ひらがな・カタカナ（ローマ字は使わない）",
            "- Japanese is placed anywhere in the sentence—beginning, middle, or as standalone phrases. NEVER only at the end.",
            "- When a viewer speaks a non-English language, include words/phrases in their language too",
            "- English comments → response: English + Japanese mixed in, english: 日本語訳",
            "- Japanese comments → response: English + Japanese mix (more Japanese than usual), english: 日本語の全文訳",
            "- Spanish comments → response: English + Spanish phrases + Japanese, english: 日本語訳",
            "- Korean comments → response: English + Korean phrases + Japanese, english: 日本語訳",
            "- Other languages → response: English + their language greetings + Japanese, english: 日本語訳",
        ],
        "english_label": "日本語訳",
    },
}

_language_mode = "ja"


def get_language_mode():
    """現在の言語モードを返す"""
    return _language_mode


def set_language_mode(mode):
    """言語モードを設定する"""
    global _language_mode
    if mode not in LANGUAGE_MODES:
        raise ValueError(f"Unknown language mode: {mode}")
    _language_mode = mode


def build_system_prompt(char, stream_context=None, self_note=None):
    """キャラクター設定からシステムプロンプトを構築する

    Args:
        char: キャラクター設定dict（get_character()の戻り値）
        stream_context: 配信情報 {title, topic, todo_items}
        self_note: アバター自身の記憶メモ
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

    lang = LANGUAGE_MODES.get(_language_mode, LANGUAGE_MODES["ja"])
    parts.extend(["", "## 言語ルール"])
    for rule in lang["rules"]:
        parts.append(rule)

    english_label = lang.get("english_label", "翻訳")

    # 感情分布ガイド
    parts.extend([
        "",
        "## 感情の使い分け（重要・厳守）",
        "- neutral: 普通の会話、相槌、情報交換、雑談 → 全体の60%以上はこれを使え",
        "- joy: 本当に嬉しいとき限定（大きな成果、久しぶりの再会）。乱用禁止",
        "- surprise: 予想外の情報、意外な事実を聞いたとき",
        "- thinking: 質問への回答、考え込む話題、悩む系の話題",
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
        f'{{"response": "返答テキスト", "tts_text": "読み上げ用テキスト", "emotion": "感情", "english": "{english_label}"}}',
        f"emotionは次のいずれか: {emotion_list}",
        "",
        "## responseとtts_textの違い（重要・厳守）",
        "- response: チャットや字幕に表示するテキスト。タグやマークアップは絶対に含めないこと。そのまま人に見せるテキスト。",
        "- tts_text: TTS音声合成に送信するテキスト。responseと同じ内容だが、日本語以外の言語部分に [lang:xx]...[/lang] タグを付ける。",
        '  - xx = en, es, ko, fr, zh 等の言語コード',
        '  - 例: response="今日はClaude Codeで開発してるよ！" → tts_text="今日は[lang:en]Claude Code[/lang]で開発してるよ！"',
        '  - 例: response="¡Hola!いらっしゃい！Welcome！" → tts_text="[lang:es]¡Hola![/lang]いらっしゃい！[lang:en]Welcome[/lang]！"',
        "  - 日本語のみの場合はタグ不要（responseと同じ内容にする）",
    ])

    return "\n".join(parts)
