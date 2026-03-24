"""AI応答モジュール - キャラクター設定に基づいてコメントに応答する"""

import json
import logging
import os
from pathlib import Path

from google.genai import types

from src.gemini_client import get_client
from src.prompt_builder import build_language_rules, build_system_prompt, get_stream_language

logger = logging.getLogger(__name__)

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
    lang = get_stream_language()
    en = lang["primary"] != "ja"
    system_prompt = build_system_prompt(get_character(), stream_context=stream_context, self_note=self_note, persona=persona)

    context_parts = []
    if en:
        if comment_count == 0 and not already_greeted:
            context_parts.append("First-time viewer")
        elif not already_greeted:
            context_parts.append(f"Regular viewer with {comment_count} past comments, hasn't been greeted today yet")
        else:
            context_parts.append("Already greeted this stream, no need to greet again")
        if author == "GM":
            context_parts.append("GM is the developer of this stream system. Close relationship, casual tone OK")
        if user_note:
            context_parts.append(f"Note: {user_note} (*Don't mention the note directly. Use it subtly to shape the conversation)")
        if timeline:
            recent_speeches = [h["text"][:30] for h in timeline[-3:] if h.get("type") == "avatar_comment"]
            if recent_speeches:
                context_parts.append(f"Forbidden patterns (avoid same openings): {', '.join(recent_speeches)}")
        context = f" ({', '.join(context_parts)})"
    else:
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
                if en:
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part(text=f"{h['user_name']}'s comment: {h['text']}")]
                    ))
                else:
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part(text=f"{h['user_name']}さんのコメント: {h['text']}")]
                    ))
            elif h["type"] == "avatar_comment":
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=h["text"])]
                ))

    if en:
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=f"{author}'s comment{context}: {message}")]
        ))
    else:
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

    lang = get_stream_language()
    is_en = lang["primary"] != "ja"
    lang_rules = build_language_rules()

    if is_en:
        parts = [
            char["system_prompt"],
            "",
            "## Rules",
            "- Comment briefly on stream events (commits, work updates, etc.)",
            "- Speak naturally and cheerfully to viewers",
            "- Keep it to 1 sentence, about 10 words",
            "- Vary your reactions — don't repeat the same expressions",
        ]
        if last_event_responses:
            parts.append("")
            parts.append("## Recent event responses (avoid repeating)")
            for r in last_event_responses[-3:]:
                parts.append(f"- {r}")
        parts.extend(["", "## Language rules"])
        for rule in lang_rules:
            parts.append(rule)
        parts.extend([
            "",
            "## Output format",
            "Reply ONLY in the following JSON format. No other text.",
            '{"speech": "response text", "tts_text": "TTS text", "emotion": "emotion", "translation": "translation text"}',
            f"emotion must be one of: {emotion_list}",
            "",
            "## speech vs tts_text (important)",
            "- speech: Displayed in chat/subtitles. No tags or markup.",
            "- tts_text: Sent to TTS. Same as speech, but add [lang:xx]...[/lang] tags for non-English parts.",
            '  - Example: speech="Great commit! すごい!" → tts_text="Great commit! [lang:ja]すごい[/lang]!"',
            "  - If English only, same as speech.",
        ])
        user_prompt = f"[{event_type} event] {detail}"
    else:
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
        parts.extend(["", "## 言語ルール"])
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
        user_prompt = f"【{event_type}イベント】{detail}"

    system_prompt = "\n".join(parts)

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


