# 英語のみモード対応プラン

ステータス: 未着手

## コンテキスト

現在の言語システムは `set_stream_language(primary, sub, mix)` で `primary="en", sub="none"` を設定可能だが、コードの多くの箇所が日本語をベース言語としてハードコードしている。英語のみモードに切り替えると、TTS発音が壊れたり、AIへの指示が矛盾したり、授業スクリプトが日本語ベースのまま生成される。

**ゴール**: `primary="en"` のとき、LLMへのプロンプトも生成される出力物（プラン・スクリプト・チャット応答・TTS）もすべて英語になること。

## 方針

- **`get_stream_language()["primary"]` を判定基準に使用**
- **既存動作を壊さない**: 日本語モード（デフォルト）の動作は変更しない
- 内部プロンプト（メモ生成・ペルソナ等）は日本語のままでOK（Geminiは日本語指示を理解して英語で出力できる）
- `primary != "ja"` のときに英語系のプロンプト・処理に切り替える

## 修正対象

### 1. `src/prompt_builder.py` — チャット応答プロンプトの言語対応（4箇所）

**1a. `build_language_rules()`** (L52-69)
- 問題: `f"{p_name}で返答する。"` → `"Englishで返答する。"` になる（動くが不自然）
- 修正: primary=en のとき英語でルール生成
  ```python
  # primary=en, sub=none の場合:
  "Respond in English."
  "- If a comment is in another language → respond in that language, mixing in English naturally"
  "- Put Japanese translation in the translation field"
  ```

**1b. `build_system_prompt()`** (L151)
- 問題: `"日本語で{max_chars}文字以内を目指す"` がハードコード
- 修正: primary=en のとき `"Aim for about {word_count} words"` （max_chars÷5≒語数目安）

**1c. `build_tts_style()`** (L110)
- 問題: `"にこにこ"` は日本語ネイティブ用の表現
- 修正: primary=en のとき `"Read in a cheerful, warm, always-smiling tone."` （にこにこ除去）

**1d. `build_system_prompt()`** (L247-253)
- 問題: tts_text説明が「日本語以外の言語部分に [lang:xx]...」と日本語ベース前提
- 修正: primary=en のとき「英語以外の言語部分に [lang:xx]...[/lang] タグを付ける。英語のみの場合はタグ不要」

### 2. `src/tts.py` — `_convert_lang_tags()` のベース言語を動的化

**問題**: `[Japanese]` がハードコード（L53, L61）。英語テキストが全て `[English]...[Japanese]` でラップされてTTSが日本語発音に切り替わる

**修正**:
- `get_stream_language()` からベース言語名を取得
- `[lang:xx]` タグ処理: `[Japanese]` → `[{base_lang_name}]` に置換
- フォールバック正規表現: primary=en の場合、英語テキストのラップをスキップし、代わりにCJK文字を検出して `[Japanese]` タグ付け

```python
def _convert_lang_tags(text):
    from src.prompt_builder import get_stream_language, SUPPORTED_LANGUAGES
    lang = get_stream_language()
    base_lang = SUPPORTED_LANGUAGES.get(lang["primary"], "Japanese")
    # ... [lang:xx] タグ → [{lang_name}]content[{base_lang}] に変換
    # フォールバック: primary=en なら CJK検出、primary=ja なら英語検出
```

### 3. `src/ai_responder.py` — `generate_event_response()` の言語対応

**問題**: プロンプト内のルール説明・見出し・tts_text説明が日本語固定（L477-506）

**修正**: primary=en のとき英語でプロンプトを構築
- `"## ルール"` → `"## Rules"`
- `"1文で簡潔に。40文字以内"` → `"Keep it to 1 sentence, about 10 words"`
- `"## 直前のイベント応答"` → `"## Recent event responses (avoid repeating)"`
- tts_text説明を英語ベースに

### 4. `src/lesson_generator.py` — プラン・スクリプト生成の全面英語対応

**問題**: 全プロンプトが日本語固定。`get_stream_language()` を参照していない。英語モードでも日本語ベースのバイリンガル授業が生成される。

**修正方針**: 各関数の先頭で `get_stream_language()["primary"]` を取得し、en のとき英語プロンプトに切り替える。

**4a. `generate_lesson_plan()`** — 3つのLLM呼び出しプロンプト
- 知識先生プロンプト → "Knowledge Expert" プロンプト（英語）
- エンタメ先生プロンプト → "Entertainment Expert" プロンプト（英語）
- 監督プロンプト → "Director" プロンプト（英語）
- title指示: `"10文字以内"` → `"max 5 words"`
- progress メッセージも英語に

**4b. `generate_lesson_script()`** — スクリプト生成プロンプト
- `"バイリンガル（日本語と英語を自然に混ぜる）で教える"` → `"Teach entirely in English"`
- content/tts_text の違い説明を英語ベースに: `"英語以外の部分に [lang:xx] タグ"` → `"For non-English parts, add [lang:xx] tags"`
- tts_text の例を英語ベースに更新
- `"視聴者は教材テキストを持っていない"` → `"Viewers do NOT have the source material"`

**4c. `generate_lesson_script_from_plan()`** — プランベーススクリプト生成
- 4b と同様の変更

**実装パターン**: プロンプト文字列を直接 if/else で分岐する（ヘルパー関数は不要。各関数内で完結）

### 5. テスト追加

- `tests/test_tts.py`: 英語モードでのlangタグ変換テスト（CJK検出）
- `tests/test_prompt_builder.py`: 英語モードでのルール・プロンプト生成テスト
- `tests/test_lesson_generator.py`（既存テストがあれば追加、なければ省略）: プロンプト内容の確認は困難なため、テストは prompt_builder/tts 側で担保

## 対象外（意図的にスキップ）

| 項目 | 理由 |
|------|------|
| `generate_user_notes()` 等の内部プロンプト | Geminiは日本語指示で英語出力可能 |
| `DEFAULT_CHARACTER` の日本語システムプロンプト | 言語ルールが出力言語をオーバーライド |
| UI日本語ラベル | 管理UIは開発者用 |
| 音声選択（DEFAULT_VOICE） | ユーザー設定で変更可能 |

## 実装順序

1. `src/prompt_builder.py` — 基盤（言語ルール・プロンプト構築）
2. `src/tts.py` — TTS言語タグ処理
3. `src/ai_responder.py` — イベント応答
4. `src/lesson_generator.py` — プラン・スクリプト生成
5. `tests/test_prompt_builder.py` — テスト
6. `tests/test_tts.py` — テスト

## 検証方法

1. `python3 -m pytest tests/ -q` — 全テスト通過
2. APIで言語切替: `POST /api/language {"primary":"en","sub":"none"}`
3. TTS: 英語テキスト読み上げで日本語発音が混ざらないこと
4. チャット応答: 英語で返答、translationに日本語
5. 授業プラン生成: 英語でプラン・スクリプトが生成されること
6. 授業スクリプト: content/tts_text/display_text がすべて英語
7. 日本語モード復帰: 既存動作が壊れていないこと
