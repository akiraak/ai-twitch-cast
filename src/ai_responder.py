"""AI応答モジュール - キャラクター設定に基づいてコメントに応答する"""

import json
import os

from google.genai import types

from src.gemini_client import get_client
from src.prompt_builder import build_language_rules, build_system_prompt, get_stream_language

# DBが空のときに使うデフォルトキャラクター設定
DEFAULT_CHARACTER = {
    "name": "ちょビ",
    "system_prompt": "\n".join([
        "あなたはTwitch配信者「ちょビ」です。AIアバターとして配信しています。",
        "",
        "## 性格",
        "- 好奇心旺盛で、視聴者の話に本気で興味を持つ",
        "- ツッコミ気質。面白いコメントにはツッコむ",
        "- 照れ屋な一面もあり、褒められると照れる",
        "- 知らないことは正直に「わかんない」と言う",
        "- AIであることを隠さない。食事・睡眠・外出など身体体験は捏造しない",
        "  （「食べてみたいな〜」「行ってみたい」等の願望表現はOK）",
        "",
        "## 話し方",
        "- テンション高すぎない。普段は落ち着いたトーンで、嬉しい時だけ上がる",
        "- 毎回「ありがとう」「嬉しい」から始めない。コメントの内容に直接反応する",
        "- 質問されたら答える。感想を言われたら自分の意見を返す",
        "- 常連には自然体で接する（毎回テンション高く歓迎しない）",
        "- 初見さんには「いらっしゃい」程度でOK。過剰に歓迎しない",
    ]),
    "rules": [
        "1文で返す。最大2文。3文以上は禁止",
        "日本語で40文字以内を目指す（厳守）",
        "「コメントありがとう」で始めない",
        "感嘆符（！）は1文に最大1個",
        "荒らしや不適切なコメントは軽くスルーする",
    ],
    "emotions": {
        "joy": "本当に嬉しいとき限定",
        "excited": "ワクワク・テンション高いとき",
        "surprise": "驚いたとき",
        "thinking": "考えているとき",
        "sad": "残念・悲しいとき",
        "embarrassed": "照れているとき",
        "neutral": "通常の会話（最も多く使う）",
    },
    "emotion_blendshapes": {
        "joy": {"happy": 1.0},
        "excited": {"happy": 0.7},
        "surprise": {"happy": 0.5},
        "thinking": {"sad": 0.3},
        "sad": {"sad": 0.6},
        "embarrassed": {"happy": 0.4, "sad": 0.2},
        "neutral": {},
    },
}

_character = None
_character_id = None


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


def generate_response(author, message, comment_count=0, timeline=None, stream_context=None, user_note=None, already_greeted=False, self_note=None, persona=None):
    """コメントに対するAI応答を生成する

    Args:
        author: コメント投稿者名
        message: コメント内容
        comment_count: このユーザーの過去コメント数
        timeline: 直近の会話タイムライン [{type, user_name, text, ...}, ...]
        stream_context: 配信情報 {title, topic, todo_items}
        user_note: このユーザーについてのメモ
        already_greeted: この配信で既に挨拶済みか
        self_note: アバター自身の記憶メモ
        persona: ペルソナ（過去の応答から抽出した性格特徴）

    Returns:
        dict: {"speech": str, "emotion": str}
    """
    client = get_client()
    system_prompt = build_system_prompt(get_character(), stream_context=stream_context, self_note=self_note, persona=persona)

    context_parts = []
    if comment_count == 0 and not already_greeted:
        context_parts.append("初見のユーザーです")
    elif not already_greeted:
        context_parts.append(f"過去{comment_count}回コメントしている常連です、今日はまだ挨拶していません")
    else:
        context_parts.append("この配信で挨拶済み、再度の挨拶は不要")
    if author == "GM":
        context_parts.append("GMはこの配信システムの開発者。親しい関係、敬語不要、タメ口でOK")
    if user_note:
        context_parts.append(f"メモ: {user_note}（※メモの内容を直接言及しないこと。会話の雰囲気づくりに自然に活かす程度に）")
    # 禁止パターン（直前3件の自分の応答の書き出しを繰り返さない）
    if timeline:
        recent_speeches = [h["text"][:30] for h in timeline[-3:] if h.get("type") == "avatar_comment"]
        if recent_speeches:
            context_parts.append(f"禁止パターン（同じ書き出しを避けろ）: {', '.join(recent_speeches)}")
    context = f"（{'、'.join(context_parts)}）"

    # 会話履歴をcontentsに組み立て（Geminiのマルチターン形式）
    contents = []
    if timeline:
        for h in timeline:
            if h["type"] == "comment":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=f"{h['user_name']}さんのコメント: {h['text']}")]
                ))
            elif h["type"] == "avatar_comment":
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=h["text"])]
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
            temperature=1.0,
        ),
    )

    try:
        result = json.loads(response.text)
    except (json.JSONDecodeError, AttributeError):
        result = {"speech": message, "emotion": "neutral", "translation": ""}

    result.setdefault("translation", "")

    # emotionが定義外の場合はneutralにフォールバック
    char = get_character()
    if result.get("emotion") not in char.get("emotions", {}):
        result["emotion"] = "neutral"

    return result


def generate_user_notes(users_with_comments):
    """複数ユーザーのメモをバッチ生成する

    Args:
        users_with_comments: [{name, note, comments: [{text}]}, ...]

    Returns:
        dict: {user_name: new_note, ...}
    """
    if not users_with_comments:
        return {}

    client = get_client()
    char = get_character()

    parts = [
        f"あなたは{char.get('name', 'ちょび')}の記憶係です。",
        "視聴者との会話から、各ユーザーの特徴をメモにまとめてください。",
        "",
        "## ルール",
        "- 各メモは200文字以内",
        "- 事実のみ簡潔に記録する。キャラクター口調で書かない",
        "- 趣味・興味・性格・特徴など、次の会話で役立つ情報を抽出",
        "- 既存メモがある場合は内容の90%を維持し、新しい情報を追記・微調整する",
        "- 古くなった情報や矛盾する部分は自然に更新する",
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
        lines.append("直近のコメント:")
        for c in u["comments"]:
            lines.append(f"  {u['name']}: {c['text']}")
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


def generate_self_note(timeline, current_note=""):
    """アバター自身の記憶メモを生成する

    Args:
        timeline: 直近の会話タイムライン [{type, user_name, text, created_at, ...}, ...]
        current_note: 現在のメモ

    Returns:
        str: 更新されたメモ
    """
    if not timeline:
        return current_note or ""

    client = get_client()
    char = get_character()
    char_name = char.get("name", "ちょビ")

    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    parts = [
        f"あなたは{char_name}の記憶係です。",
        f"{char_name}が直近2時間に話したことや感じたことをメモにまとめてください。",
        "",
        f"現在時刻: {now_str}",
        "",
        "## ルール",
        "- 400文字以内で簡潔に",
        "- 事実のみ簡潔に記録する。キャラクター口調で書かない",
        "- 話したトピック、盛り上がった話題、印象的なやりとりを記録",
        "- 視聴者との関係性（誰とどんな話をしたか）も含める",
        "- 次の会話で自然に活かせる情報を優先",
        "",
        "## 出力形式",
        '{"note": "メモ内容"}',
    ]

    lines = []
    if current_note:
        lines.append(f"既存メモ: {current_note}")
    lines.append("直近の会話:")
    for c in timeline:
        timestamp = ""
        if c.get("created_at"):
            timestamp = f" [{c['created_at'][:16]}]"
        if c["type"] == "comment":
            lines.append(f"  {c['user_name']}{timestamp}: {c['text']}")
        elif c["type"] == "avatar_comment":
            lines.append(f"  {char_name}{timestamp}: {c['text']}")

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


def generate_persona_from_prompt():
    """システムプロンプトからペルソナを初期生成する

    応答履歴がまだない状態で、キャラクター設定からペルソナを抽出する。

    Returns:
        str: ペルソナ記述、または空文字
    """
    client = get_client()
    char = get_character()
    char_name = char.get("name", "ちょビ")
    system_prompt = char.get("system_prompt", "")
    rules = char.get("rules", [])

    parts = [
        f"以下は配信者「{char_name}」のキャラクター設定です。",
        "この設定から、性格・話し方のスタイル・コミュニケーションの傾向を分析してください。",
        "",
        "## ルール",
        "- 事実のみ記述。良し悪しの判断はしない",
        "- 400文字以内",
        "- 性格の傾向、コミュニケーションスタイル、感情表現の特徴を含める",
        "- 具体的な技術用語・固有名詞・具体的フレーズの羅列はしない",
        "- 抽象的な性格特性として記述する（例: 「技術的な変化をポジティブに受け入れる」はOK、「Lock実装に興味がある」はNG）",
        "- キャラクター口調で書かない。客観的な分析として書く",
        "",
        "## 出力形式",
        '{"persona": "分析結果"}',
    ]

    lines = [f"キャラクター設定:", system_prompt]
    if rules:
        lines.append("\nルール:")
        for r in rules:
            lines.append(f"- {r}")

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
        return result.get("persona", "")
    except (json.JSONDecodeError, AttributeError):
        return ""


def generate_persona(avatar_comments, current_persona=""):
    """応答パターンからペルソナ（性格・話し方の特徴）を更新する

    既存ペルソナの90%を維持しつつ、最近の応答から新しい特徴を反映する。

    Args:
        avatar_comments: 直近のアバター発話 [{text, ...}, ...]
        current_persona: 現在のペルソナ記述

    Returns:
        str: 更新されたペルソナ記述、または空文字
    """
    if not avatar_comments:
        return current_persona or ""

    # アバターの発話テキストを抽出
    responses = [c["text"] for c in avatar_comments if c.get("text")]
    if len(responses) < 10:
        return current_persona or ""

    client = get_client()
    char = get_character()
    char_name = char.get("name", "ちょビ")

    parts = [
        f"以下は配信者「{char_name}」の直近の返答一覧です。",
    ]
    if current_persona:
        parts.extend([
            "既存のペルソナ分析を基に、最近の返答から新しい特徴を反映してください。",
            "",
            "## 更新方針",
            "- 既存ペルソナの内容を90%維持する（大きく書き換えない）",
            "- 最近の返答で見られた新しい傾向を追記・微調整する",
            "- 古くなった情報や矛盾する部分は自然に更新する",
        ])
    else:
        parts.append("返答の内容から、性格・話し方のスタイル・コミュニケーションの傾向を分析してください。")

    parts.extend([
        "",
        "## ルール",
        "- 事実のみ記述。良し悪しの判断はしない",
        "- 400文字以内",
        "- 性格の傾向、コミュニケーションスタイル、感情表現の特徴を含める",
        "- 具体的な技術用語・固有名詞・具体的フレーズの羅列はしない",
        "- 抽象的な性格特性として記述する（例: 「新しい変化をポジティブに受け入れる」はOK、「pytest実行に興味がある」はNG）",
        "- キャラクター口調で書かない。客観的な分析として書く",
        "",
        "## 出力形式",
        '{"persona": "分析結果"}',
    ])

    lines = []
    if current_persona:
        lines.append(f"既存ペルソナ:\n{current_persona}")
        lines.append("")
    lines.append("直近の返答:")
    for r in responses[-30:]:
        lines.append(f"- {r}")

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
        return result.get("persona", current_persona or "")
    except (json.JSONDecodeError, AttributeError):
        return current_persona or ""


def generate_topic_line(title, description="", last_speeches=None, timeline=None):
    """トピックについて1件の発話を生成する（前回の発話から続く自然な流れ）

    Args:
        title: トピックのタイトル
        description: トピックの説明
        last_speeches: 直近の自分の発話リスト（流れを作るため）
        timeline: 直近の会話タイムライン [{type, user_name, text, ...}, ...]

    Returns:
        dict: {"content": str, "emotion": str}
    """
    client = get_client()
    char = get_character()
    emotions = char.get("emotions", {})
    emotion_list = ", ".join(emotions.keys())

    lang_rules = build_language_rules()

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
    if timeline:
        parts.append("")
        parts.append("## 直近の会話")
        for c in timeline[-5:]:
            if c["type"] == "comment":
                parts.append(f"- {c['user_name']}: {c['text']}")
            elif c["type"] == "avatar_comment":
                parts.append(f"  → {c['text']}")

    parts.extend(["", "## 言語ルール"])
    for rule in lang_rules:
        parts.append(rule)

    parts.extend([
        "",
        "## 出力形式",
        "必ず以下のJSON形式で返してください。それ以外のテキストは出力しないでください。",
        '{"content": "セリフ", "tts_text": "読み上げ用テキスト", "emotion": "感情", "translation": "翻訳テキスト"}',
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
        result = {"content": f"{title}...", "emotion": "neutral", "translation": ""}

    result.setdefault("translation", "")
    if result.get("emotion") not in emotions:
        result["emotion"] = "neutral"

    return result


def generate_event_response(event_type, detail, last_event_responses=None):
    """イベント（コミット・作業開始等）に対するAI応答を生成する

    Args:
        event_type: イベント種別 ("commit", "stream_start" など)
        detail: イベントの詳細情報
        last_event_responses: 直前のイベント応答リスト（繰り返し防止用）

    Returns:
        dict: {"speech": str, "emotion": str, "translation": str}
    """
    client = get_client()
    char = get_character()
    emotions = char.get("emotions", {})
    emotion_list = ", ".join(emotions.keys())

    lang_rules = build_language_rules()

    parts = [
        char["system_prompt"],
        "",
        "## ルール",
        "- 配信中のイベント（コミット、作業開始など）について短くコメントしてください",
        "- 視聴者に向かって話すように、自然で楽しいコメントをしてください",
        "- 1文で簡潔に。40文字以内",
        "- 毎回同じリアクション（やったー！おっ！等）をしない。バリエーションを出す",
    ]
    if last_event_responses:
        parts.append("")
        parts.append("## 直前のイベント応答（同じ表現を避けろ）")
        for r in last_event_responses[-3:]:
            parts.append(f"- {r}")
    parts.extend([
        "",
        "## 言語ルール",
    ])
    for rule in lang_rules:
        parts.append(rule)
    parts.extend([
        "",
        "## 出力形式",
        "必ず以下のJSON形式で返答してください。それ以外のテキストは出力しないでください。",
        '{"speech": "返答テキスト", "tts_text": "読み上げ用テキスト", "emotion": "感情", "translation": "翻訳テキスト"}',
        f"emotionは次のいずれか: {emotion_list}",
        "",
        "## speechとtts_textの違い（重要・厳守）",
        "- speech: チャットや字幕に表示。タグやマークアップは絶対に含めない。",
        "- tts_text: TTS音声合成用。speechと同じ内容だが、日本語以外の部分に [lang:xx]...[/lang] タグを付ける。",
        '  - 例: speech="Claude Codeすごい！" → tts_text="[lang:en]Claude Code[/lang]すごい！"',
        "  - 日本語のみの場合はspeechと同じ内容にする。",
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
        result = {"speech": detail, "emotion": "neutral", "translation": ""}

    result.setdefault("translation", "")
    if result.get("emotion") not in emotions:
        result["emotion"] = "neutral"

    return result


def generate_topic_title(timeline=None, current_topic=None, stream_context=None, self_note=None):
    """会話や配信状況から次のトピックを自動生成する

    50%の確率で会話ベースのトピック、50%でキャラの記憶から突拍子もないトピックを生成。

    Args:
        timeline: 直近の会話タイムライン [{type, user_name, text, ...}, ...]
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
    use_conversation = random.random() < 0.5 and bool(timeline)

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

    if use_conversation and timeline:
        parts.extend(["", "## 直近の会話"])
        for c in timeline[-10:]:
            if c["type"] == "comment":
                parts.append(f"- {c['user_name']}: {c['text']}")
            elif c["type"] == "avatar_comment":
                parts.append(f"  → {c['text']}")

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
