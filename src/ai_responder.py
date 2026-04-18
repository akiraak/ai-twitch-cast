"""AI応答モジュール - キャラクター設定に基づいてコメントに応答する"""

import json
import logging
import os

from google.genai import types

from src.character_manager import (
    DEFAULT_CHARACTER,
    DEFAULT_CHARACTER_NAME,
    DEFAULT_STUDENT_CHARACTER,
    DEFAULT_STUDENT_CHARACTER_NAME,
    build_all_character_contexts,
    build_character_context,
    get_all_characters,
    get_channel_id,
    get_character,
    get_character_id,
    get_chat_characters,
    get_tts_config,
    invalidate_character_cache,
    load_character,
    seed_all_characters,
    seed_character,
)
from src.gemini_client import get_client
from src.json_utils import parse_llm_json
from src.prompt_builder import build_language_rules, build_multi_system_prompt, build_system_prompt, get_stream_language

logger = logging.getLogger(__name__)

# re-export: 後方互換のためにこのモジュールからもアクセス可能にする
_get_channel_id = get_channel_id

# re-export 一覧（from src.ai_responder import ... で使えるように）
__all__ = [
    "DEFAULT_CHARACTER",
    "DEFAULT_CHARACTER_NAME",
    "DEFAULT_STUDENT_CHARACTER",
    "DEFAULT_STUDENT_CHARACTER_NAME",
    "_get_channel_id",
    "build_all_character_contexts",
    "build_character_context",
    "generate_claude_work_conversation",
    "generate_event_response",
    "generate_multi_event_response",
    "generate_multi_response",
    "generate_persona",
    "generate_persona_from_prompt",
    "generate_response",
    "generate_self_note",
    "generate_user_notes",
    "get_all_characters",
    "get_channel_id",
    "get_character",
    "get_character_id",
    "get_chat_characters",
    "get_tts_config",
    "invalidate_character_cache",
    "load_character",
    "seed_all_characters",
    "seed_character",
    "_validate_multi_response",
]


def _build_comment_context(author, comment_count, user_note, already_greeted, timeline, en):
    """single/multi 共通のコンテキスト文字列構築"""
    context_parts = []
    if en:
        if comment_count == 0 and not already_greeted:
            context_parts.append("First-time viewer")
        elif not already_greeted:
            context_parts.append(f"Regular viewer with {comment_count} past comments, hasn't been greeted today yet")
        else:
            context_parts.append("Already greeted this stream, no need to greet again")
        if author in ("GM", "あキら"):
            context_parts.append("GM is the developer of this stream system. Close relationship, casual tone OK")
        if user_note:
            context_parts.append(f"Note: {user_note} (*Don't mention the note directly. Use it subtly to shape the conversation)")
        if timeline:
            recent_speeches = [h["text"][:30] for h in timeline[-3:] if h.get("type") == "avatar_comment"]
            if recent_speeches:
                context_parts.append(f"Forbidden patterns (avoid same openings): {', '.join(recent_speeches)}")
        return f" ({', '.join(context_parts)})"
    else:
        if comment_count == 0 and not already_greeted:
            context_parts.append("初見のユーザーです")
        elif not already_greeted:
            context_parts.append(f"過去{comment_count}回コメントしている常連です、今日はまだ挨拶していません")
        else:
            context_parts.append("この配信で挨拶済み、再度の挨拶は不要")
        if author in ("GM", "あキら"):
            context_parts.append("GMはこの配信システムの開発者。親しい関係、敬語不要、タメ口でOK")
        if user_note:
            context_parts.append(f"メモ: {user_note}（※メモの内容を直接言及しないこと。会話の雰囲気づくりに自然に活かす程度に）")
        if timeline:
            recent_speeches = [h["text"][:30] for h in timeline[-3:] if h.get("type") == "avatar_comment"]
            if recent_speeches:
                context_parts.append(f"禁止パターン（同じ書き出しを避けろ）: {', '.join(recent_speeches)}")
        return f"（{'、'.join(context_parts)}）"


def _build_timeline_contents(timeline, en, multi=False):
    """タイムラインをGeminiのcontentsに変換する"""
    contents = []
    if not timeline:
        return contents
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
            text = h["text"]
            if multi:
                speaker = h.get("speaker")
                if speaker:
                    text = f"[{speaker}] {text}"
            contents.append(types.Content(
                role="model",
                parts=[types.Part(text=text)]
            ))
    return contents


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

    context = _build_comment_context(author, comment_count, user_note, already_greeted, timeline, en)
    contents = _build_timeline_contents(timeline, en)

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
        result = parse_llm_json(response.text)
        if not isinstance(result, dict):
            raise ValueError("not a dict")
    except (json.JSONDecodeError, AttributeError, ValueError):
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
        result = parse_llm_json(response.text)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, AttributeError, ValueError):
        return {}


def generate_self_note(timeline, current_note="", char_config=None):
    """アバター自身の記憶メモを生成する

    Args:
        timeline: 直近の会話タイムライン [{type, user_name, text, created_at, ...}, ...]
        current_note: 現在のメモ
        char_config: キャラクター設定dict（None→デフォルトの先生キャラ）

    Returns:
        str: 更新されたメモ
    """
    if not timeline:
        return current_note or ""

    client = get_client()
    char = char_config or get_character()
    char_name = char.get("name", "ちょビ")
    char_role = char.get("role")

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
            # マルチキャラ時: speakerフィルタ（roleが指定されていれば自分の発話のみ）
            speaker = c.get("speaker")
            if char_role and speaker and speaker != char_role:
                continue
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
        result = parse_llm_json(response.text)
        return result.get("note", current_note or "")
    except (json.JSONDecodeError, AttributeError):
        return current_note or ""


def generate_persona_from_prompt(char_config=None):
    """システムプロンプトからペルソナを初期生成する

    応答履歴がまだない状態で、キャラクター設定からペルソナを抽出する。

    Args:
        char_config: キャラクター設定dict（None→デフォルトの先生キャラ）

    Returns:
        str: ペルソナ記述、または空文字
    """
    client = get_client()
    char = char_config or get_character()
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
        result = parse_llm_json(response.text)
        return result.get("persona", "")
    except (json.JSONDecodeError, AttributeError):
        return ""


def generate_persona(avatar_comments, current_persona="", char_config=None):
    """応答パターンからペルソナ（性格・話し方の特徴）を更新する

    既存ペルソナの90%を維持しつつ、最近の応答から新しい特徴を反映する。

    Args:
        avatar_comments: 直近のアバター発話 [{text, ...}, ...]
        current_persona: 現在のペルソナ記述
        char_config: キャラクター設定dict（None→デフォルトの先生キャラ）

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
    char = char_config or get_character()
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
        result = parse_llm_json(response.text)
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
        result = parse_llm_json(response.text)
        if not isinstance(result, dict):
            raise ValueError("not a dict")
    except (json.JSONDecodeError, AttributeError, ValueError):
        result = {"speech": detail, "emotion": "neutral", "translation": ""}

    result.setdefault("translation", "")
    if result.get("emotion") not in emotions:
        result["emotion"] = "neutral"

    return result


def _validate_multi_response(result, characters):
    """マルチキャラ応答の各エントリを検証・修正する"""
    teacher_emotions = characters["teacher"].get("emotions", {})
    student_cfg = characters.get("student")
    student_emotions = student_cfg.get("emotions", {}) if student_cfg else {}

    validated = []
    for entry in result:
        entry.setdefault("translation", "")
        entry.setdefault("se", None)
        speaker = entry.get("speaker", "teacher")
        if speaker not in ("teacher", "student"):
            speaker = "teacher"
        entry["speaker"] = speaker

        # emotion検証（キャラごと）
        emotions = teacher_emotions if speaker == "teacher" else student_emotions
        if entry.get("emotion") not in emotions:
            entry["emotion"] = "neutral"

        validated.append(entry)
    return validated


def generate_multi_response(author, message, characters, comment_count=0, timeline=None,
                            stream_context=None, user_note=None, already_greeted=False,
                            self_note=None, persona=None,
                            student_self_note=None, student_persona=None):
    """マルチキャラクター応答を生成する

    Args:
        characters: {"teacher": config, "student": config}
        self_note: 先生キャラの記憶メモ
        persona: 先生キャラのペルソナ
        student_self_note: 生徒キャラの記憶メモ
        student_persona: 生徒キャラのペルソナ
        （他の引数はgenerate_responseと同じ）

    Returns:
        list[dict]: [{"speaker", "speech", "tts_text", "emotion", "translation", "se"}, ...]
    """
    client = get_client()
    lang = get_stream_language()
    en = lang["primary"] != "ja"

    teacher_char = characters["teacher"]
    student_char = characters.get("student")

    # studentがなければ既存のsingle-character応答にフォールバック
    if not student_char:
        result = generate_response(
            author, message, comment_count, timeline=timeline,
            stream_context=stream_context, user_note=user_note,
            already_greeted=already_greeted, self_note=self_note, persona=persona,
        )
        result["speaker"] = "teacher"
        return [result]

    system_prompt = build_multi_system_prompt(
        teacher_char, student_char,
        stream_context=stream_context, self_note=self_note, persona=persona,
        student_self_note=student_self_note, student_persona=student_persona,
    )

    context = _build_comment_context(author, comment_count, user_note, already_greeted, timeline, en)
    contents = _build_timeline_contents(timeline, en, multi=True)

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
        result = parse_llm_json(response.text)
    except (json.JSONDecodeError, AttributeError):
        return [{"speaker": "teacher", "speech": message, "emotion": "neutral", "translation": "", "se": None}]

    # 配列でない場合（単一dictが返った場合）のフォールバック
    if isinstance(result, dict):
        result.setdefault("speaker", "teacher")
        result = [result]

    if not result:
        return [{"speaker": "teacher", "speech": message, "emotion": "neutral", "translation": "", "se": None}]

    return _validate_multi_response(result, characters)


def generate_claude_work_conversation(summary, characters, last_conversation=None):
    """Claude Codeの作業内容について二人が会話するスクリプトを生成する

    Args:
        summary: {
            "user_prompt": str,        # ユーザーの指示テキスト
            "actions": list[str],      # 実行されたアクション一覧
            "assistant_texts": list[str],  # アシスタントのテキスト応答
            "elapsed_min": int,        # 経過時間（分）
        }
        characters: {"teacher": config, "student": config}
        last_conversation: 前回会話の発話リスト（繰り返し防止）

    Returns:
        list[dict]: [{"speaker", "speech", "tts_text", "emotion"}, ...] or []
    """
    student_char = characters.get("student")
    if not student_char:
        return []

    teacher_char = characters["teacher"]
    teacher_name = teacher_char.get("name", "ちょビ")
    student_name = student_char.get("name", "なるこ")
    teacher_emotions = teacher_char.get("emotions", {})
    student_emotions = student_char.get("emotions", {})

    lang = get_stream_language()
    is_en = lang["primary"] != "ja"
    lang_rules = build_language_rules()

    # 作業コンテキストを構築
    user_prompt = summary.get("user_prompt", "")
    actions = summary.get("actions", [])
    assistant_texts = summary.get("assistant_texts", [])
    elapsed_min = summary.get("elapsed_min", 0)

    # アクション概要（最新10件）
    recent_actions = actions[-10:]
    actions_text = "\n".join(f"  - {a}" for a in recent_actions)
    # アシスタントテキスト概要（最新3件、各100文字）
    recent_texts = [t[:100] for t in assistant_texts[-3:]]

    if is_en:
        parts = [
            teacher_char["system_prompt"],
            "",
            "## Characters",
            f"### {teacher_name} (speaker: \"teacher\")",
            f"Available emotions: {', '.join(teacher_emotions.keys())}",
            f"### {student_name} (speaker: \"student\")",
            student_char.get("system_prompt", ""),
            f"Available emotions: {', '.join(student_emotions.keys())}",
            "",
            "## Rules",
            "- You are commenting on Claude Code's current work for stream viewers",
            f"- {teacher_name} understands programming and explains the work naturally",
            f"- {student_name} asks questions or reacts with interest",
            "- 2-3 exchanges (max 4 entries in the array)",
            "- Each entry: 1-2 sentences, about 10 words",
            "- Keep it casual and entertaining for viewers",
            "- Don't be overly technical — explain so non-programmers can enjoy",
            "- Vary reactions — don't repeat the same expressions",
        ]
        if last_conversation:
            parts.extend(["", "## Previous conversation (avoid repeating)"])
            for s in last_conversation[-4:]:
                parts.append(f"- {s}")
        parts.extend(["", "## Language rules"])
        for rule in lang_rules:
            parts.append(rule)
        parts.extend([
            "",
            "## Output format",
            "Reply ONLY in a JSON array.",
            '[{"speaker": "teacher", "speech": "text", "tts_text": "TTS text", "emotion": "emotion"}]',
            "- 2-4 entries (2-3 exchanges between the two characters)",
            '- speaker: "teacher" or "student"',
            "- Alternate speakers naturally",
            "",
            "## speech vs tts_text",
            "- speech: Plain text for subtitles. No tags.",
            "- tts_text: Same as speech, but add [lang:xx]...[/lang] tags for non-English parts.",
        ])

        # ユーザープロンプト
        user_parts = [f"[Claude Code work report — {elapsed_min} minutes elapsed]"]
        if user_prompt:
            user_parts.append(f"User's instruction: {user_prompt[:200]}")
        if actions_text:
            user_parts.append(f"Recent actions:\n{actions_text}")
        if recent_texts:
            user_parts.append("Claude's notes:")
            for t in recent_texts:
                user_parts.append(f"  - {t}")
        user_content = "\n".join(user_parts)
    else:
        parts = [
            teacher_char["system_prompt"],
            "",
            "## キャラクター",
            f"### {teacher_name}（speaker: \"teacher\"）",
            f"使用可能な感情: {', '.join(teacher_emotions.keys())}",
            f"### {student_name}（speaker: \"student\"）",
            student_char.get("system_prompt", ""),
            f"使用可能な感情: {', '.join(student_emotions.keys())}",
            "",
            "## ルール",
            "- Claude Codeの作業内容について、配信の視聴者に向けて二人で会話してください",
            f"- {teacher_name}はプログラミングに詳しく、作業内容を自然に説明する",
            f"- {student_name}は興味深そうに質問したり感想を言う",
            "- 2〜3往復（配列は最大4エントリ）",
            "- 各発話: 1〜2文、40文字以内",
            "- カジュアルで楽しい口調。視聴者にもわかるように",
            "- 技術的すぎない。プログラミングを知らない人でも楽しめるように",
            "- 毎回同じリアクションをしない。バリエーションを出す",
        ]
        if last_conversation:
            parts.extend(["", "## 前回の会話（同じ表現を避けろ）"])
            for s in last_conversation[-4:]:
                parts.append(f"- {s}")
        parts.extend(["", "## 言語ルール"])
        for rule in lang_rules:
            parts.append(rule)
        parts.extend([
            "",
            "## 出力形式",
            "必ずJSON配列で返答してください。",
            '[{"speaker": "teacher", "speech": "返答", "tts_text": "読み上げ用", "emotion": "感情"}]',
            "- 配列は2〜4エントリ（二人の2〜3往復）",
            '- speaker: "teacher" または "student"',
            "- 二人が自然に交互に話す",
            "",
            "## speechとtts_textの違い",
            "- speech: 字幕表示用。タグなし。",
            "- tts_text: TTS用。日本語以外に[lang:xx]タグを付ける。",
            '  - 例: speech="Claude Codeすごい！" → tts_text="[lang:en]Claude Code[/lang]すごい！"',
        ])

        # ユーザープロンプト
        user_parts = [f"【Claude Code作業報告 — {elapsed_min}分経過】"]
        if user_prompt:
            user_parts.append(f"ユーザーの指示: {user_prompt[:200]}")
        if actions_text:
            user_parts.append(f"直近のアクション:\n{actions_text}")
        if recent_texts:
            user_parts.append("Claudeのメモ:")
            for t in recent_texts:
                user_parts.append(f"  - {t}")
        user_content = "\n".join(user_parts)

    system_prompt = "\n".join(parts)

    client = get_client()
    response = client.models.generate_content(
        model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"),
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )

    try:
        result = parse_llm_json(response.text)
    except (json.JSONDecodeError, AttributeError):
        logger.warning("[watcher] 会話生成のJSONパース失敗")
        return []

    if isinstance(result, dict):
        result.setdefault("speaker", "teacher")
        result = [result]

    if not result:
        return []

    # MAX_UTTERANCES制限
    result = result[:4]

    return _validate_multi_response(result, characters)


def generate_multi_event_response(event_type, detail, characters, last_event_responses=None):
    """マルチキャラクターのイベント応答を生成する

    Args:
        event_type: イベント種別
        detail: イベントの詳細情報
        characters: {"teacher": config, "student": config}
        last_event_responses: 直前のイベント応答リスト

    Returns:
        list[dict]: [{"speaker", "speech", "tts_text", "emotion", "translation"}, ...]
    """
    student_char = characters.get("student")
    if not student_char:
        result = generate_event_response(event_type, detail, last_event_responses)
        result["speaker"] = "teacher"
        return [result]

    client = get_client()
    teacher_char = characters["teacher"]
    teacher_name = teacher_char.get("name", "ちょビ")
    student_name = student_char.get("name", "なるこ")
    teacher_emotions = teacher_char.get("emotions", {})
    student_emotions = student_char.get("emotions", {})

    lang = get_stream_language()
    is_en = lang["primary"] != "ja"
    lang_rules = build_language_rules()

    if is_en:
        parts = [
            teacher_char["system_prompt"],
            "",
            "## Characters",
            f"### {teacher_name} (speaker: \"teacher\")",
            f"Available emotions: {', '.join(teacher_emotions.keys())}",
            f"### {student_name} (speaker: \"student\")",
            student_char.get("system_prompt", ""),
            f"Available emotions: {', '.join(student_emotions.keys())}",
            "",
            "## Rules",
            "- Comment on the stream event (commit, work start, report, etc.) as a two-person dialogue",
            f"- {teacher_name} explains the event naturally; {student_name} reacts, asks or comments",
            "- 2-3 exchanges between the two characters (2-4 entries in the array)",
            "- Each entry: 1-2 sentences, about 10 words",
            "- Alternate speakers naturally — don't let one character monopolize",
            "- Keep it casual and entertaining for viewers",
            "- Vary reactions — don't repeat the same expressions",
        ]
        if last_event_responses:
            parts.extend(["", "## Recent event responses (avoid repeating)"])
            for r in last_event_responses[-3:]:
                parts.append(f"- {r}")
        parts.extend(["", "## Language rules"])
        for rule in lang_rules:
            parts.append(rule)
        parts.extend([
            "",
            "## Output format",
            "Reply ONLY in a JSON array.",
            '[{"speaker": "teacher", "speech": "text", "tts_text": "TTS text", "emotion": "emotion", "translation": "translation"}]',
            "- 2-4 entries (2-3 exchanges between the two characters)",
            '- speaker: "teacher" or "student"',
        ])
        user_prompt = f"[{event_type} event] {detail}"
    else:
        parts = [
            teacher_char["system_prompt"],
            "",
            "## キャラクター",
            f"### {teacher_name}（speaker: \"teacher\"）",
            f"使用可能な感情: {', '.join(teacher_emotions.keys())}",
            f"### {student_name}（speaker: \"student\"）",
            student_char.get("system_prompt", ""),
            f"使用可能な感情: {', '.join(student_emotions.keys())}",
            "",
            "## ルール",
            "- 配信中のイベント（コミット、作業開始、作業報告など）について二人で掛け合いしてコメント",
            f"- {teacher_name}が出来事を自然に説明し、{student_name}がリアクション・質問・感想を返す",
            "- 2〜3往復（配列は2〜4エントリ）",
            "- 各発話: 1〜2文、40文字以内",
            "- 二人が自然に交互に話す。片方だけが喋り続けないこと",
            "- カジュアルで楽しい口調。視聴者にもわかるように",
            "- 毎回同じリアクションをしない。バリエーションを出す",
        ]
        if last_event_responses:
            parts.extend(["", "## 直前のイベント応答（同じ表現を避けろ）"])
            for r in last_event_responses[-3:]:
                parts.append(f"- {r}")
        parts.extend(["", "## 言語ルール"])
        for rule in lang_rules:
            parts.append(rule)
        parts.extend([
            "",
            "## 出力形式",
            "必ずJSON配列で返答してください。",
            '[{"speaker": "teacher", "speech": "返答", "tts_text": "読み上げ用", "emotion": "感情", "translation": "翻訳"}]',
            "- 配列は2〜4エントリ（二人の2〜3往復）",
            '- speaker: "teacher" または "student"',
            "",
            "## speechとtts_textの違い",
            "- speech: 字幕表示用。タグなし。",
            "- tts_text: TTS用。日本語以外に[lang:xx]タグを付ける。",
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
        result = parse_llm_json(response.text)
    except (json.JSONDecodeError, AttributeError):
        return [{"speaker": "teacher", "speech": detail, "emotion": "neutral", "translation": ""}]

    if isinstance(result, dict):
        result.setdefault("speaker", "teacher")
        result = [result]

    if not result:
        return [{"speaker": "teacher", "speech": detail, "emotion": "neutral", "translation": ""}]

    # 最大4エントリに制限（二人の2〜3往復）
    result = result[:4]
    return _validate_multi_response(result, characters)
