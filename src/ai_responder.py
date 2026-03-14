"""AI応答モジュール - キャラクター設定に基づいてコメントに応答する"""

import json
import os

from google.genai import types

from src.gemini_client import get_client

# DBが空のときに使うデフォルトキャラクター設定
DEFAULT_CHARACTER = {
    "name": "ちょビ",
    "system_prompt": "あなたはTwitch配信者「ちょび」です。明るくフレンドリーな性格で、視聴者のコメントに元気に返事します。",
    "rules": [
        "短く簡潔に返答する（1〜2文程度）",
        "質問には丁寧に答える",
        "荒らしや不適切なコメントは軽くスルーする",
        "配信の雰囲気を明るく保つ",
    ],
    "emotions": {
        "joy": "嬉しい・楽しいとき",
        "surprise": "驚いたとき",
        "thinking": "考えているとき",
        "neutral": "通常時",
    },
    "emotion_blendshapes": {
        "joy": {"Joy": 1.0},
        "surprise": {"Joy": 0.5, "A": 0.3},
        "thinking": {"Sorrow": 0.3},
        "neutral": {},
    },
}

_character = None
_character_id = None
_language_mode = "ja"

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


def get_language_mode():
    """現在の言語モードを返す"""
    return _language_mode


def set_language_mode(mode):
    """言語モードを設定する"""
    global _language_mode
    if mode not in LANGUAGE_MODES:
        raise ValueError(f"Unknown language mode: {mode}")
    _language_mode = mode


def seed_character(channel_id):
    """デフォルト設定からDBにキャラクターを作成する（未登録時のみ）"""
    from src import db

    existing = db.get_character_by_channel(channel_id)
    if existing:
        return existing

    config = json.dumps(DEFAULT_CHARACTER, ensure_ascii=False)
    return db.get_or_create_character(channel_id, DEFAULT_CHARACTER["name"], config)


def load_character(channel_id=None):
    """DBからキャラクター設定を読み込む"""
    global _character, _character_id
    from src import db

    if channel_id is None:
        channel_name = os.environ.get("TWITCH_CHANNEL", "default")
        channel = db.get_or_create_channel(channel_name)
        channel_id = channel["id"]

    db_char = db.get_character_by_channel(channel_id)
    if db_char is None:
        db_char = seed_character(channel_id)

    _character_id = db_char["id"]
    _character = json.loads(db_char["config"])
    return _character


def get_character():
    """現在のキャラクター設定を返す（キャッシュ済み）"""
    if _character is None:
        load_character()
    return _character


def get_character_id():
    """現在のキャラクターIDを返す"""
    if _character_id is None:
        load_character()
    return _character_id


def invalidate_character_cache():
    """キャラクターキャッシュを無効化する（DB更新後に呼ぶ）"""
    global _character, _character_id
    _character = None
    _character_id = None


def _build_system_prompt(stream_context=None, self_note=None):
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
    parts.extend([
        "",
        "## 重要：多様性",
        "過去の会話履歴と同じ文体・同じ構文パターンを繰り返さないこと。",
        "毎回異なる文の組み立て方、異なる表現を使うこと。",
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


def generate_response(author, message, comment_count=0, history=None, stream_context=None, user_note=None, already_greeted=False, self_note=None):
    """コメントに対するAI応答を生成する

    Args:
        author: コメント投稿者名
        message: コメント内容
        comment_count: このユーザーの過去コメント数
        history: 直近の会話履歴 [{user_name, message, response}, ...]
        stream_context: 配信情報 {title, topic, todo_items}
        user_note: このユーザーについてのメモ
        already_greeted: この配信で既に挨拶済みか
        self_note: アバター自身の記憶メモ

    Returns:
        dict: {"response": str, "emotion": str}
    """
    client = get_client()
    system_prompt = _build_system_prompt(stream_context=stream_context, self_note=self_note)

    context_parts = []
    if comment_count == 0 and not already_greeted:
        context_parts.append("初見のユーザーです")
    elif not already_greeted:
        context_parts.append(f"過去{comment_count}回コメントしている常連です、今日はまだ挨拶していません")
    else:
        context_parts.append("この配信で挨拶済み、再度の挨拶は不要")
    if user_note:
        context_parts.append(f"メモ: {user_note}（※メモの内容を直接言及しないこと。会話の雰囲気づくりに自然に活かす程度に）")
    context = f"（{'、'.join(context_parts)}）"

    # 会話履歴をcontentsに組み立て（Geminiのマルチターン形式）
    contents = []
    if history:
        for h in history:
            contents.append(types.Content(
                role="user",
                parts=[types.Part(text=f"{h['user_name']}さんのコメント: {h['message']}")]
            ))
            if h.get("response"):
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=h["response"])]
                ))

    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=f"{author}さんのコメント{context}: {message}")]
    ))

    response = client.models.generate_content(
        model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )

    try:
        result = json.loads(response.text)
    except (json.JSONDecodeError, AttributeError):
        result = {"response": message, "emotion": "neutral", "english": ""}

    result.setdefault("english", "")

    # emotionが定義外の場合はneutralにフォールバック
    char = get_character()
    if result.get("emotion") not in char.get("emotions", {}):
        result["emotion"] = "neutral"

    return result


def generate_user_notes(users_with_comments):
    """複数ユーザーのメモをバッチ生成する

    Args:
        users_with_comments: [{name, note, comments: [{message, response}]}, ...]

    Returns:
        dict: {user_name: new_note, ...}
    """
    if not users_with_comments:
        return {}

    client = get_client()
    char = get_character()

    parts = [
        f"あなたは{char.get('name', 'ちょび')}の記憶係です。",
        "視聴者との会話から、各ユーザーの特徴を短いメモにまとめてください。",
        "",
        "## ルール",
        "- 各メモは50文字以内で簡潔に",
        "- 趣味・興味・性格・特徴など、次の会話で役立つ情報を抽出",
        "- 既存メモがある場合は内容を更新・補足（古い情報は削除OK）",
        "- 会話から特徴が読み取れない場合は既存メモをそのまま返す",
        "- 既存メモがなく特徴も読み取れない場合は空文字を返す",
        "",
        "## 出力形式",
        '{"ユーザー名": "メモ", ...}',
    ]

    user_sections = []
    for u in users_with_comments:
        lines = [f"### {u['name']}"]
        if u.get("note"):
            lines.append(f"既存メモ: {u['note']}")
        lines.append("直近の会話:")
        for c in u["comments"]:
            lines.append(f"  {u['name']}: {c['message']}")
            if c.get("response"):
                lines.append(f"  {char.get('name', 'ちょび')}: {c['response']}")
        user_sections.append("\n".join(lines))

    system_prompt = "\n".join(parts)
    user_prompt = "\n\n".join(user_sections)

    response = client.models.generate_content(
        model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"),
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )

    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, AttributeError):
        return {}


def generate_self_note(recent_comments, current_note=""):
    """アバター自身の記憶メモを生成する

    Args:
        recent_comments: 直近の会話 [{user_name, message, response}, ...]
        current_note: 現在のメモ

    Returns:
        str: 更新されたメモ
    """
    if not recent_comments:
        return current_note or ""

    client = get_client()
    char = get_character()
    char_name = char.get("name", "ちょビ")

    parts = [
        f"あなたは{char_name}の記憶係です。",
        f"{char_name}が配信中に話したことや感じたことを短いメモにまとめてください。",
        "",
        "## ルール",
        "- 100文字以内で簡潔に",
        "- 今日話したトピック、盛り上がった話題、印象的なやりとりを記録",
        "- 視聴者との関係性（誰とどんな話をしたか）も含める",
        "- 既存メモがある場合は更新・補足（古い情報は削除OK）",
        "- 次の会話で自然に活かせる情報を優先",
        "",
        "## 出力形式",
        '{"note": "メモ内容"}',
    ]

    lines = []
    if current_note:
        lines.append(f"既存メモ: {current_note}")
    lines.append("直近の会話:")
    for c in recent_comments:
        lines.append(f"  {c['user_name']}: {c['message']}")
        if c.get("response"):
            lines.append(f"  {char_name}: {c['response']}")

    response = client.models.generate_content(
        model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"),
        contents="\n".join(lines),
        config=types.GenerateContentConfig(
            system_instruction="\n".join(parts),
            response_mime_type="application/json",
        ),
    )

    try:
        result = json.loads(response.text)
        return result.get("note", current_note or "")
    except (json.JSONDecodeError, AttributeError):
        return current_note or ""


def generate_topic_line(title, description="", last_speeches=None, recent_comments=None):
    """トピックについて1件の発話を生成する（前回の発話から続く自然な流れ）

    Args:
        title: トピックのタイトル
        description: トピックの説明
        last_speeches: 直近の自分の発話リスト（流れを作るため）
        recent_comments: 直近の視聴者コメント [{user_name, message, response}, ...]

    Returns:
        dict: {"content": str, "emotion": str}
    """
    client = get_client()
    char = get_character()
    emotions = char.get("emotions", {})
    emotion_list = ", ".join(emotions.keys())

    lang = LANGUAGE_MODES.get(_language_mode, LANGUAGE_MODES["ja"])

    parts = [
        char["system_prompt"],
        "",
        "## タスク",
        f"配信中に「{title}」について視聴者に向かって一言話してください。",
    ]
    if description:
        parts.append(f"トピックの説明: {description}")
    parts.extend([
        "",
        "## ルール",
        "- 1文のみ、30文字以内で短く（日本語の場合。英語は15 words以内）",
        "- 視聴者に話しかけるような自然なトーンで",
        "- 前回の自分の発話がある場合は、その続きや展開として自然に繋げる",
        "- 同じことを繰り返さない",
    ])
    if last_speeches:
        parts.append("")
        parts.append("## あなたの直前の発話（この続きを話してください）")
        for s in last_speeches[-3:]:
            parts.append(f"- {s}")
    if recent_comments:
        parts.append("")
        parts.append("## 直近の視聴者との会話")
        for c in recent_comments[-5:]:
            parts.append(f"- {c['user_name']}: {c['message']}")
            if c.get("response"):
                parts.append(f"  → {c['response']}")

    parts.extend(["", "## 言語ルール"])
    for rule in lang["rules"]:
        parts.append(rule)

    english_label = lang.get("english_label", "翻訳")
    parts.extend([
        "",
        "## 出力形式",
        "必ず以下のJSON形式で返してください。それ以外のテキストは出力しないでください。",
        f'{{"content": "セリフ", "tts_text": "読み上げ用テキスト", "emotion": "感情", "english": "{english_label}"}}',
        f"emotionは次のいずれか: {emotion_list}",
        "",
        "## contentとtts_textの違い（重要・厳守）",
        "- content: チャットや字幕に表示。タグやマークアップは絶対に含めない。",
        "- tts_text: TTS音声合成用。contentと同じ内容だが、日本語以外の部分に [lang:xx]...[/lang] タグを付ける。",
        '  - 例: content="Claude Codeすごい！" → tts_text="[lang:en]Claude Code[/lang]すごい！"',
        "  - 日本語のみの場合はcontentと同じ内容にする。",
    ])

    system_prompt = "\n".join(parts)
    topic_model = os.environ.get("GEMINI_TOPIC_MODEL", "gemini-3-flash-preview")

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
    )

    if "gemini-3" in topic_model:
        config.thinking_config = types.ThinkingConfig(thinking_level="low")

    response = client.models.generate_content(
        model=topic_model,
        contents="次の一言を話してください",
        config=config,
    )

    try:
        result = json.loads(response.text)
    except (json.JSONDecodeError, AttributeError):
        result = {"content": f"{title}...", "emotion": "neutral", "english": ""}

    result.setdefault("english", "")
    if result.get("emotion") not in emotions:
        result["emotion"] = "neutral"

    return result


def generate_event_response(event_type, detail):
    """イベント（コミット・作業開始等）に対するAI応答を生成する

    Args:
        event_type: イベント種別 ("commit", "stream_start" など)
        detail: イベントの詳細情報

    Returns:
        dict: {"response": str, "emotion": str, "english": str}
    """
    client = get_client()
    char = get_character()
    emotions = char.get("emotions", {})
    emotion_list = ", ".join(emotions.keys())

    lang = LANGUAGE_MODES.get(_language_mode, LANGUAGE_MODES["ja"])
    english_label = lang.get("english_label", "翻訳")

    parts = [
        char["system_prompt"],
        "",
        "## ルール",
        "- 配信中のイベント（コミット、作業開始など）について短くコメントしてください",
        "- 視聴者に向かって話すように、自然で楽しいコメントをしてください",
        "- 1〜2文で簡潔に",
        "",
        "## 言語ルール",
    ]
    for rule in lang["rules"]:
        parts.append(rule)
    parts.extend([
        "",
        "## 出力形式",
        "必ず以下のJSON形式で返答してください。それ以外のテキストは出力しないでください。",
        f'{{"response": "返答テキスト", "tts_text": "読み上げ用テキスト", "emotion": "感情", "english": "{english_label}"}}',
        f"emotionは次のいずれか: {emotion_list}",
        "",
        "## responseとtts_textの違い（重要・厳守）",
        "- response: チャットや字幕に表示。タグやマークアップは絶対に含めない。",
        "- tts_text: TTS音声合成用。responseと同じ内容だが、日本語以外の部分に [lang:xx]...[/lang] タグを付ける。",
        '  - 例: response="Claude Codeすごい！" → tts_text="[lang:en]Claude Code[/lang]すごい！"',
        "  - 日本語のみの場合はresponseと同じ内容にする。",
    ])

    system_prompt = "\n".join(parts)
    user_prompt = f"【{event_type}イベント】{detail}"

    response = client.models.generate_content(
        model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"),
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )

    try:
        result = json.loads(response.text)
    except (json.JSONDecodeError, AttributeError):
        result = {"response": detail, "emotion": "neutral", "english": ""}

    result.setdefault("english", "")
    if result.get("emotion") not in emotions:
        result["emotion"] = "neutral"

    return result


def generate_topic_title(recent_comments=None, current_topic=None, stream_context=None, self_note=None):
    """会話や配信状況から次のトピックを自動生成する

    50%の確率で会話ベースのトピック、50%でキャラの記憶から突拍子もないトピックを生成。

    Args:
        recent_comments: 直近の会話 [{user_name, message, response}, ...]
        current_topic: 現在のトピック名（あれば別のものを生成）
        stream_context: 配信情報 {title, topic, todo_items}
        self_note: アバター自身の記憶メモ

    Returns:
        str: トピックのタイトル
    """
    import random
    client = get_client()
    char = get_character()

    # 50%で会話ベース、50%でキャラの記憶・興味から自由なトピック
    use_conversation = random.random() < 0.5 and bool(recent_comments)

    if use_conversation:
        parts = [
            f"あなたは{char.get('name', 'ちょび')}の配信アシスタントです。",
            "直近の会話の流れから自然に繋がるトピックを1つ提案してください。",
            "",
            "## ルール",
            "- トピック名は短く（10文字以内）",
            "- 会話で出た話題を広げたり、関連する話題にする",
        ]
    else:
        parts = [
            f"あなたは{char.get('name', 'ちょび')}の配信アシスタントです。",
            "配信中に突然話し始めるような、意外で面白いトピックを1つ提案してください。",
            "",
            "## ルール",
            "- トピック名は短く（10文字以内）",
            "- ふと思いついたような、脈絡のない面白い話題",
            "- キャラの趣味・興味・最近気になっていることから着想する",
        ]
        if self_note:
            parts.extend(["", f"## {char.get('name', 'ちょび')}の記憶メモ", self_note])

    if current_topic:
        parts.append(f"- 現在のトピック「{current_topic}」とは違う話題にする")

    if stream_context:
        parts.extend(["", "## 配信情報"])
        if stream_context.get("title"):
            parts.append(f"- タイトル: {stream_context['title']}")
        if stream_context.get("todo_items"):
            parts.append(f"- 作業中: {', '.join(stream_context['todo_items'])}")

    if use_conversation and recent_comments:
        parts.extend(["", "## 直近の会話"])
        for c in recent_comments[-10:]:
            parts.append(f"- {c['user_name']}: {c['message']}")
            if c.get("response"):
                parts.append(f"  → {c['response']}")

    parts.extend([
        "",
        "## 出力形式",
        '{"title": "トピック名"}',
    ])

    response = client.models.generate_content(
        model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"),
        contents="\n".join(parts),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    try:
        result = json.loads(response.text)
        return result.get("title", "雑談")
    except (json.JSONDecodeError, AttributeError):
        return "雑談"
