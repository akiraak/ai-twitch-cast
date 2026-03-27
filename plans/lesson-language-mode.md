# プラン: 英語モードのセリフを英語にする

ステータス: 未着手

## Context

教師モードのセリフ生成で、言語モードがセリフに反映されない問題を修正する。根本的な解決として、**キャラクター設定自体に3言語パターン（日本語/英語/バイリンガル）を持たせる**。

**現状の問題**:
- v2メソッドの `_generate_single_dialogue` のプロンプトが最小限（キャラsystem_prompt + rules + emotions のみ）
- 言語指示なし、self_note/persona 未使用
- キャラの `system_prompt` が日本語 → どのモードでも日本語セリフ

**設計原則**:
- 日本語生成 → プロンプト全体が日本語
- 英語生成 → プロンプト全体が英語
- バイリンガル → 両言語を記載

## 1. キャラクター config の拡張

`characters` テーブルの `config` JSON に以下のフィールドを追加:

```json
{
  "system_prompt": "日本語の性格設定（既存）",
  "system_prompt_en": "English personality setup",
  "system_prompt_bilingual": "日本語 + English の両方",
  "rules": ["日本語ルール（既存）"],
  "rules_en": ["English rules"],
  "rules_bilingual": ["Both languages rules"],
  "tts_style": "日本語TTSスタイル（既存）",
  "tts_style_en": "English TTS style",
  "tts_style_bilingual": "Bilingual TTS style",
  ...既存フィールドはそのまま...
}
```

**選択ロジック**:
- primary=ja, sub=none → `system_prompt`, `rules`, `tts_style`
- primary=en (or other non-ja), sub=none → `system_prompt_en`, `rules_en`, `tts_style_en`
- sub != none（バイリンガル）→ `system_prompt_bilingual`, `rules_bilingual`, `tts_style_bilingual`
- 未設定の場合は日本語版にフォールバック

ヘルパー関数（`src/prompt_builder.py` に追加）:
```python
def get_localized_field(config: dict, field: str) -> str | list:
    """言語モードに応じたフィールド値を返す（フォールバック付き）"""
    lang = get_stream_language()
    if lang["sub"] != "none":
        key = f"{field}_bilingual"
    elif lang["primary"] != "ja":
        key = f"{field}_en"
    else:
        key = field
    return config.get(key) or config.get(field, "" if isinstance(config.get(field, ""), str) else [])
```

### 変更ファイル: `src/ai_responder.py`

`DEFAULT_CHARACTER` と `DEFAULT_STUDENT_CHARACTER` に英語版・バイリンガル版を追加。

**ちょビ英語版 `system_prompt_en`** (例):
```
You are "Chobi," a Twitch streamer broadcasting as an AI avatar.

## Personality
- Curious and genuinely interested in viewers' stories
- Quick with witty comebacks on funny comments
- Has a shy side; gets embarrassed when complimented
- Honest about not knowing things — "No idea!"
- Doesn't hide being an AI. Won't fabricate bodily experiences
  (Wishes like "I'd love to try that" are OK)

## Speaking style
- Usually calm; only gets excited when genuinely happy
- Don't start every response with "Thanks!" or "So happy!"
- Respond directly to the comment's content
- Be natural with regulars (don't welcome them every time)
- Simple "Welcome!" for first-timers
```

**ちょビ バイリンガル版 `system_prompt_bilingual`** (例):
```
あなたはTwitch配信者「ちょビ」です。AIアバターとして配信しています。
You are "Chobi," a Twitch streamer broadcasting as an AI avatar.

## 性格 / Personality
- 好奇心旺盛で、視聴者の話に本気で興味を持つ / Genuinely curious about viewers' stories
- ツッコミ気質 / Quick with witty comebacks
- 照れ屋 / Gets embarrassed when complimented
- 知らないことは正直に言う / Honest about not knowing things
- AIであることを隠さない / Doesn't hide being an AI

## 話し方 / Speaking style
- 日本語と英語を自然に混ぜて話す / Mix Japanese and English naturally
- テンション高すぎない / Not overly hyper
```

**同様に** なるこ（student）にも英語版・バイリンガル版を追加。

**ルール例**:
```python
"rules_en": [
    "Don't start with 'Thanks for the comment'",
    "Max one exclamation mark per sentence",
    "Lightly ignore trolls or inappropriate comments",
],
"rules_bilingual": [
    "日本語と英語を自然に混ぜる / Mix Japanese and English naturally",
    "感嘆符（！）は1文に最大1個 / Max one exclamation per sentence",
    "荒らしは軽くスルー / Lightly ignore trolls",
],
```

**TTSスタイル例**:
```python
"tts_style_en": "Read in a warm, cheerful, always-smiling tone",
"tts_style_bilingual": "にこにこしながら、日本語と英語を自然に切り替えて読み上げてください",
```

## 2. キャラクター管理API の拡張

### 変更ファイル: `scripts/routes/character.py`

`CharacterUpdate` スキーマに新フィールドを追加:
```python
class CharacterUpdate(BaseModel):
    name: str
    system_prompt: str
    rules: list[str]
    # --- 英語版 ---
    system_prompt_en: str | None = None
    rules_en: list[str] | None = None
    tts_style_en: str | None = None
    # --- バイリンガル版 ---
    system_prompt_bilingual: str | None = None
    rules_bilingual: list[str] | None = None
    tts_style_bilingual: str | None = None
    # --- 既存 ---
    emotions: dict[str, str]
    emotion_blendshapes: dict[str, dict[str, float]]
    tts_voice: str | None = None
    tts_style: str | None = None
```

GET `/api/character/{id}` のレスポンスにも新フィールドを含める。

## 3. 管理画面UI の拡張

### 変更ファイル: `static/index.html`, `static/js/admin/character.js`

キャラクター編集画面に言語タブを追加:

```
[日本語] [English] [バイリンガル]
```

各タブに:
- システムプロンプト（textarea）
- ルール（動的リスト）
- TTSスタイル（textarea）

**実装**:
- 3つのタブ切替ボタン
- タブ切替時に対応するフィールドを表示/非表示
- `saveCharacter()` で全言語の値を送信
- `loadCharacterById()` で全言語の値をセット

## 4. セリフ生成プロンプトの完全刷新

### 変更ファイル: `src/prompt_builder.py`

新関数 `build_lesson_dialogue_prompt()` を追加:

```python
def build_lesson_dialogue_prompt(
    char: dict,
    role: str,
    self_note: str = None,
    persona: str = None,
) -> str:
    """授業セリフ生成用のシステムプロンプトを構築する

    言語モードに応じて全セクション（性格・ルール・self_note・persona・
    言語ルール・感情・出力形式）を適切な言語で生成。
    """
```

含めるセクション:
1. **キャラ紹介** — "You are {name}..." / "あなたは「{name}」です..."
2. **キャラ system_prompt** — `get_localized_field(char, "system_prompt")` で言語版を選択
3. **ルール** — `get_localized_field(char, "rules")` で言語版を選択
4. **自分の記憶メモ** — self_note
5. **ペルソナ** — persona
6. **言語ルール** — 言語モード別の発話言語指示（英語のみ/バイリンガル混ぜレベル）
7. **感情ガイド** — emotion の使い分け
8. **出力形式** — JSON `{content, tts_text, emotion}` + tts_text タグルール

各セクションは `en = (primary != "ja")` で分岐:
- **en=True**: 全セクションが英語テンプレート
- **en=False**: 全セクションが日本語テンプレート（バイリンガル時は言語ルールのみ追加）

### 変更ファイル: `src/lesson_generator.py`

#### `get_lesson_characters()` 改修 — self_note, persona も取得

```python
def get_lesson_characters() -> dict:
    for role in ("teacher", "student"):
        row = db.get_character_by_role(channel_id, role)
        if row:
            config = json.loads(row["config"])
            config["name"] = row["name"]
            memory = db.get_character_memory(row["id"])
            config["self_note"] = memory.get("self_note", "")
            config["persona"] = memory.get("persona", "")
            result[role] = config
    return result
```

#### `_generate_single_dialogue()` — プロンプト差し替え

現在の手動プロンプト構築（line 1508-1541）を `build_lesson_dialogue_prompt()` 呼び出しに差し替え:

```python
from src.prompt_builder import build_lesson_dialogue_prompt

system_prompt = build_lesson_dialogue_prompt(
    char=character_config,
    role=role,
    self_note=character_config.get("self_note"),
    persona=character_config.get("persona"),
)
```

## 5. TTS スタイルの言語対応

### 変更ファイル: `src/tts.py`

`get_tts_config()` 関数で、キャラ config から言語モードに応じた `tts_style` を選択:

```python
from src.prompt_builder import get_localized_field
style = get_localized_field(config, "tts_style")
```

## 6. ドキュメント更新

### 変更ファイル: `docs/speech-generation-flow.md`

- Phase B-2 のシステムプロンプト説明を更新
- 「self_note/persona は未使用」→「self_note/persona も含む」に修正
- 言語モード別のプロンプト構築・キャラ3パターンについて記載

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/ai_responder.py` | DEFAULT_CHARACTER / DEFAULT_STUDENT_CHARACTER に英語/バイリンガル版追加 |
| `src/prompt_builder.py` | `get_localized_field()`, `build_lesson_dialogue_prompt()` 追加 |
| `src/lesson_generator.py` | `get_lesson_characters()` 改修、`_generate_single_dialogue()` プロンプト差し替え |
| `src/tts.py` | `get_tts_config()` 言語対応 |
| `scripts/routes/character.py` | `CharacterUpdate` スキーマ拡張 |
| `static/index.html` | 言語タブUI追加 |
| `static/js/admin/character.js` | 言語タブ切替 + 保存/読込対応 |
| `docs/speech-generation-flow.md` | Phase B-2 説明更新 |
| `tests/test_prompt_builder.py` | 新関数テスト |
| `tests/test_lesson_generator.py` | キャラデータ拡充テスト |

## リスク

1. **キャラ個性の言語間一貫性**: 英語版system_promptの翻訳品質が低いとキャラがブレる → 管理画面で確認・調整可能
2. **既存キャラの初期値**: 既存のDBキャラには英語/バイリンガル版がない → フォールバックで日本語版を使用（即座に壊れない）
3. **日本語モードのリグレッション**: 日本語版フィールドは既存のまま → 影響なし

## 検証

```bash
python3 -m pytest tests/ -q
```

手動検証:
1. 管理画面 → キャラクター → 3言語タブで設定確認・編集
2. 英語モード → 授業生成 → セリフ英語 + generation メタデータで英語プロンプト確認
3. バイリンガルモード → セリフに日英混在
4. 日本語モード → セリフ日本語（リグレッションなし）
