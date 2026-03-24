# 06: 英語授業の発音改善

ステータス: 未着手

## 背景・問題

英語の授業なのに英語の発音が悪すぎる。現状の問題:

### 1. スクリプト生成プロンプトに `[lang:en]` タグの説明がない
- `generate_lesson_script` / `generate_lesson_script_from_plan` の両方で、`tts_text` の説明が「TTS用テキスト（発音指示・言語タグ付き）」のみ
- LLMが `[lang:en]...[/lang]` タグの形式を知らないため、適切なタグが付かない
- `tts.py` の `_convert_lang_tags()` がタグなしテキストを処理すると、正規表現フォールバックで英語部分を検出するが精度が低い（短い単語は漏れる、日本語ローマ字と混同する可能性）

### 2. TTSスタイルが授業内容に適応しない
- `build_tts_style()` は配信言語設定（primary/sub）に基づくが、授業の内容（英語授業かどうか）は考慮しない
- 英語授業でも日本語配信ならTTSスタイルは日本語寄りになる
- 英語の例文を読み上げる際に、ネイティブ発音を強調する指示がない

### 3. コメント応答用の `[lang:en]` 説明はあるが授業スクリプトにはない
- `prompt_builder.py` の `build_system_prompt()` には tts_text の `[lang:xx]` タグの詳細説明がある（L247-253）
- 授業スクリプト生成プロンプトにはこの説明が一切ない

## 方針

**プロンプト改善だけで解決する**（コードの構造変更は最小限）

## 実装ステップ

### Step 1: 授業スクリプト生成プロンプトに `[lang:en]` タグ説明を追加

対象: `src/lesson_generator.py`

- `generate_lesson_script()` のシステムプロンプト（L362-400）に以下を追加:
  - `tts_text` の `[lang:xx]...[/lang]` タグ形式の説明
  - 具体的な例（英語フレーズ・単語の場合）
  - 「日本語のみの場合はタグ不要」のルール

- `generate_lesson_script_from_plan()` のシステムプロンプト（L510-540）にも同様に追加

`build_system_prompt()` の該当部分（L246-253）と同じ形式:
```
## tts_textの書き方（重要・厳守）
- tts_text: TTS音声合成に送信するテキスト。contentと同じ内容だが、日本語以外の言語部分に [lang:xx]...[/lang] タグを付ける
  - xx = en, es, ko 等の言語コード
  - 例: content="Helloは挨拶だよ" → tts_text="[lang:en]Hello[/lang]は挨拶だよ"
  - 例: content="How are you?って聞かれたら..." → tts_text="[lang:en]How are you?[/lang]って聞かれたら..."
  - 日本語のみの場合はタグ不要（contentと同じ内容にする）
  - 英語の単語1つでもタグを付ける（例: [lang:en]apple[/lang]）
```

### Step 2: 英語授業向けのTTSスタイル強化

対象: `src/lesson_generator.py` のスクリプト生成プロンプト

英語を教える授業であることをプロンプトで明示し、`tts_text` での発音指示を強化:

```
## 英語発音のルール（英語を含む授業の場合）
- 英語の単語・フレーズは必ずネイティブ英語の発音で読み上げさせること
- tts_textでは英語部分を必ず [lang:en]...[/lang] で囲む
- 例文を読み上げる際は、英語部分をゆっくり・はっきり発音するような指示をcontentに含める
  - NG: "apple, appleだよ"
  - OK: "apple、えーぴーぴーえるいー、apple！"（...は不要、tts_textで制御）
```

ただしこれは汎用的なルールとして追加する（「バイリンガルで教える」の部分を拡充）。英語授業かどうかの判定はLLMに任せる（教材テキストから自動判断）。

### Step 3: TTSスタイルを授業コンテキストに適応させる

対象: `src/tts.py` または `src/lesson_runner.py`

授業セクション再生時のTTSスタイルに「英語はネイティブ発音で」を追加する選択肢:

**案A: lesson_runner側でtts_textに発音ヒントをプレフィックス**
- `_play_section()` でTTS呼び出し前に、tts_textの先頭に発音指示を付加
- 例: `"英語部分はネイティブ英語の発音で、はっきりと: " + tts_text`
- メリット: tts.pyを変更せず、授業時のみ影響
- デメリット: 毎回余計な指示テキストがTTSに送られる

**案B: synthesize()にstyle_override引数を追加**
- `tts.py` の `synthesize()` に `style` 引数を追加し、授業時は専用スタイルを渡す
- メリット: 柔軟、他の機能にも応用可能
- デメリット: tts.pyのインターフェース変更

**→ 案Bを採用**。`synthesize()` に `style` オプション引数を追加し、授業時は英語発音を強調したスタイルを渡す。

実装:
1. `tts.py` の `synthesize(text, output_path, voice=None)` → `synthesize(text, output_path, voice=None, style=None)`
   - `style` 指定時はそれを使い、なければ従来通り `_get_tts_style()` を使用
2. `speech_pipeline.py` の `generate_tts()` と `_speak_impl()` に `style` を伝搬
3. `lesson_runner.py` の `_play_section()` でTTS呼び出し時に授業用スタイルを指定

授業用TTSスタイル（lesson_runner.py に定義）:
```python
LESSON_TTS_STYLE = (
    "Read in a cheerful, warm, always-smiling tone. "
    "CRITICAL: When you encounter English words or phrases enclosed in [English]...[Japanese] markers, "
    "pronounce them with clear, native English pronunciation. "
    "Do NOT read English words with Japanese accent. "
    "Switch cleanly between Japanese and English pronunciation."
)
```

## リスク・注意点

- **TTSモデル依存**: Gemini 2.5 Flash TTS の言語切り替え能力に依存。`[English]...[Japanese]` マーカーがどこまで効くかはモデル次第
- **プロンプト肥大化**: スクリプト生成プロンプトが長くなるが、品質向上のためのトレードオフ
- **既存キャッシュ**: 既に生成済みのTTSキャッシュには影響しない。再生成が必要

## テスト

- 既存テスト全通過を確認（プロンプト変更のみなのでロジック変更なし、Step 3のみインターフェース変更あり）
- Step 3: `synthesize()` のインターフェース変更 → 既存呼び出し元に影響ないことを確認（style=None がデフォルト）
