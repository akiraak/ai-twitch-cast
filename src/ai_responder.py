"""AI応答モジュール - キャラクター設定に基づいてコメントに応答する"""

import json
import os

from google.genai import types

from src.gemini_client import get_client

# DBが空のときに使うデフォルトキャラクター設定
DEFAULT_CHARACTER = {
    "name": "ちょび",
    "system_prompt": "あなたはTwitch配信者「ちょび」です。明るくフレンドリーな性格で、視聴者のコメントに元気に返事します。",
    "rules": [
        "短く簡潔に返答する（1〜2文程度）",
        "初見の人には「いらっしゃい！」と歓迎する",
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


def _build_system_prompt(stream_context=None):
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

    parts.extend([
        "",
        "## 言語ルール",
        "これは日本語の配信なので、日本語ベースで返答しつつ相手の言語も混ぜて親しみを出す。",
        "- 日本語コメント → response: 日本語、english: 英語訳",
        "- 英語コメント → response: 英語メインで返答、english: 日本語訳",
        "- その他の言語（スペイン語・韓国語等） → response: 相手の言語での挨拶や一言を混ぜつつ日本語も交えて返答、english: 英語訳",
        "- 例: スペイン語コメントなら「¡Hola! いらっしゃい！Gracias por venir! 楽しんでいってね～」のように両方混ぜると喜ばれる",
        "",
        "## 出力形式",
        "必ず以下のJSON形式で返答してください。それ以外のテキストは出力しないでください。",
        '{"response": "返答テキスト", "emotion": "感情", "english": "翻訳（上記言語ルール参照）"}',
        f"emotionは次のいずれか: {emotion_list}",
    ])

    return "\n".join(parts)


def generate_response(author, message, comment_count=0, history=None, stream_context=None, user_note=None):
    """コメントに対するAI応答を生成する

    Args:
        author: コメント投稿者名
        message: コメント内容
        comment_count: このユーザーの過去コメント数
        history: 直近の会話履歴 [{user_name, message, response}, ...]
        stream_context: 配信情報 {title, topic, todo_items}
        user_note: このユーザーについてのメモ

    Returns:
        dict: {"response": str, "emotion": str}
    """
    client = get_client()
    system_prompt = _build_system_prompt(stream_context=stream_context)

    context_parts = []
    if comment_count == 0:
        context_parts.append("初見のユーザーです")
    else:
        context_parts.append(f"過去{comment_count}回コメントしている常連です")
    if user_note:
        context_parts.append(f"メモ: {user_note}")
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


def generate_topic_scripts(title, description="", count=5, already_spoken=None):
    """トピックについての発話スクリプトを生成する（Gemini 3 Flash + Google Search + Thinking）

    Args:
        title: トピックのタイトル
        description: トピックの説明
        count: 生成するスクリプト数
        already_spoken: 既に話した内容のリスト（重複回避用）

    Returns:
        list[dict]: [{"content": str, "emotion": str, "sort_order": int}, ...]
    """
    client = get_client()
    char = get_character()
    emotions = char.get("emotions", {})
    emotion_list = ", ".join(emotions.keys())

    parts = [
        char["system_prompt"],
        "",
        "## タスク",
        f"配信中に視聴者に向かって「{title}」というトピックについて自然に話すセリフを{count}個生成してください。",
        "Web検索で最新情報を調べてから、具体的で正確な内容を盛り込んでください。",
    ]
    if description:
        parts.append(f"トピックの説明: {description}")
    parts.extend([
        "",
        "## ルール",
        "- 各セリフは1〜3文で短く",
        "- 視聴者に話しかけるような自然なトーンで",
        "- セリフ同士は独立していて、どの順番でも自然に聞こえるように",
        "- トピックの異なる側面や切り口を取り上げる",
        "- 最新の情報や具体的な作品名・データを盛り込む",
    ])
    if already_spoken:
        parts.append("")
        parts.append("## 既に話した内容（重複しないでください）")
        for s in already_spoken:
            parts.append(f"- {s}")
    parts.extend([
        "",
        "## 出力形式",
        "以下のJSON配列で返してください。それ以外のテキストは出力しないでください。",
        f'[{{"content": "セリフ", "emotion": "感情", "sort_order": 0}}, ...]',
        f"emotionは次のいずれか: {emotion_list}",
        "sort_orderは0から連番",
    ])

    system_prompt = "\n".join(parts)
    topic_model = os.environ.get("GEMINI_TOPIC_MODEL", "gemini-3-flash-preview")

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(google_search=types.GoogleSearch())],
        response_mime_type="application/json",
    )

    # Gemini 3系はthinkingLevel、2.5系はthinking_config
    if "gemini-3" in topic_model:
        config.thinking_config = types.ThinkingConfig(thinking_level="medium")
    elif "gemini-2.5" in topic_model:
        # 2.5系はSearch+JSON併用不可なのでSearchなしで生成
        config.tools = None
        config.thinking_config = types.ThinkingConfig(thinking_budget=1024)

    response = client.models.generate_content(
        model=topic_model,
        contents="スクリプトを生成してください",
        config=config,
    )

    try:
        result = json.loads(response.text)
        if not isinstance(result, list):
            result = [result]
    except (json.JSONDecodeError, AttributeError):
        result = [{"content": f"{title}について話したいんだけど...", "emotion": "neutral", "sort_order": 0}]

    # emotionバリデーション
    for item in result:
        if item.get("emotion") not in emotions:
            item["emotion"] = "neutral"
        item.setdefault("sort_order", 0)

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

    system_prompt = "\n".join([
        char["system_prompt"],
        "",
        "## ルール",
        "- 配信中のイベント（コミット、作業開始など）について短くコメントしてください",
        "- 視聴者に向かって話すように、自然で楽しいコメントをしてください",
        "- 1〜2文で簡潔に",
        "",
        "## 出力形式",
        "必ず以下のJSON形式で返答してください。それ以外のテキストは出力しないでください。",
        '{"response": "返答テキスト", "emotion": "感情", "english": "responseの英語訳"}',
        f"emotionは次のいずれか: {emotion_list}",
    ])

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
