# TTS 日英混在テキストの英語発音改善プラン

## 背景

日本語モードでTTS音声を生成する際、テキスト中の英語（例: "YouTube", "Claude Code"）がカタカナ風の日本語発音になることがある。Gemini 2.5 Flash TTSの仕様上、日本語コンテキストでは英語部分もカタカナ読みされやすい。スタイルプロンプトに英語発音指示を入れても一貫性は約70%程度。

## ステータス: 調査完了・未実装

## 現状の実装

- `src/tts.py`: `synthesize()` が `f"{style}: {text}"` でGemini TTSに送信
- `src/ai_responder.py` L43: 日本語モードの `tts_style` にスタイル指示
- 現在のスタイル: `"終始にこにこしているような、柔らかく楽しげなトーンで読み上げてください。Use natural English pronunciation for any English words or phrases"`

## Gemini TTS の制約

- **SSMLは公式未サポート**: `<lang xml:lang="en-US">`や`<phoneme>`は動く場合もあるがバージョン依存で不安定
- **`language_code`パラメータ**: `SpeechConfig`に設定可能だが、リクエスト全体に適用。単語単位の言語切替は不可
  ```python
  speech_config=types.SpeechConfig(
      language_code="ja-JP",  # リクエスト全体の言語
      voice_config=...
  )
  ```
- **スタイルプロンプト**: 唯一の公式な制御手段。英語で書いた方が英語発音指示を守りやすい
- **ブラケットタグ**: `[slow]`, `[whispering]`, `[uhm]` 等は動作実績あり（非公式）
- 一貫性は最善でも約70%程度（Zenn記事での検証結果）

## 対策手法一覧（信頼度順）

### 1. テキスト前処理で発音ヒント挿入（信頼度: 高）

TTS送信前に英語部分を検出してマークアップする。

```python
# 例: 正規表現で英語単語を検出してヒントを付与
import re

def add_pronunciation_hints(text):
    # 連続する英語単語をまとめて検出
    def replace_english(match):
        word = match.group(0)
        return f'[pronounce in English: {word}]'
    return re.sub(r'[A-Za-z][A-Za-z0-9\s\.\-\']*[A-Za-z0-9]', replace_english, text)

# "今日はYouTubeの動画を見ました"
# → "今日は[pronounce in English: YouTube]の動画を見ました"
```

**メリット**: 特定の英語単語に対して確実に効く
**デメリット**: 正規表現の精度、ブラケット記法が非公式

### 2. スタイルプロンプトを英語ベースに変更（信頼度: 中〜高）

日本語のトーン指示も含めて全てを英語で記述する。

```python
# Before
"終始にこにこしているような、柔らかく楽しげなトーンで読み上げてください。Use natural English pronunciation for any English words or phrases"

# After
"Read in a cheerful, warm, always-smiling tone. IMPORTANT: When you encounter English words or phrases, pronounce them with native English pronunciation, NOT katakana Japanese pronunciation. Switch naturally between Japanese and English pronunciation as needed."
```

**メリット**: コード変更が1行で済む、英語プロンプトの方がTTSが英語発音指示を守りやすい
**デメリット**: 日本語のニュアンス指示が伝わりにくくなる可能性

### 3. SSML `<lang>` タグ（信頼度: 中）

英語部分をSSML言語タグで囲む。

```python
def wrap_english_with_lang_tags(text):
    import re
    def replace_english(match):
        word = match.group(0)
        return f'<lang xml:lang="en-US">{word}</lang>'
    return re.sub(r'[A-Za-z][A-Za-z0-9\s\.\-\']*[A-Za-z0-9]', replace_english, text)

# "今日はYouTubeの動画を見ました"
# → "今日は<lang xml:lang=\"en-US\">YouTube</lang>の動画を見ました"
```

**メリット**: 標準的なSSML記法
**デメリット**: Gemini TTSでは公式未サポート、バージョンアップで壊れる可能性

### 4. ブラケットタグで言語切替（信頼度: 中）

`[slow]`等と同様のブラケット記法で言語を切り替える。

```python
# テキスト前処理
"今日は[English]YouTube[Japanese]の動画を見ました"
```

**メリット**: シンプル
**デメリット**: `[English]`/`[Japanese]` タグの動作は非公式・未検証

### 5. IPA発音記号埋め込み（信頼度: 低〜中）

特定の頻出単語にIPA発音記号を埋め込む。

```python
PRONUNCIATIONS = {
    "YouTube": "juːtjuːb",
    "GitHub": "ɡɪthʌb",
}
# テキスト内の単語を置換: YouTube → YouTube(juːtjuːb)
```

**メリット**: 特定単語の発音を精密に制御可能
**デメリット**: 辞書管理が面倒、スケールしない

### 6. 二段階アプローチ（信頼度: 高、実装コスト: 高）

1. AIテキスト生成時に英語部分に発音マーカーを付けさせる
2. TTS送信時にマーカーを適切な形式に変換

```python
# AI生成プロンプトに追加:
# "英語の単語やフレーズには <<EN>>word<</EN>> マーカーを付けてください"

# TTS前処理でマーカーを変換:
# <<EN>>YouTube<</EN>> → [pronounce in English: YouTube]
```

**メリット**: AIが文脈を理解して正確に英語部分を特定
**デメリット**: テキスト生成プロンプトの変更が必要、マーカーが字幕に表示される問題

## 推奨アプローチ

**手法2（スタイルプロンプト英語化）+ 手法1（テキスト前処理）の組み合わせ**

1. まずスタイルプロンプトを英語ベースに変更（低コスト）
2. それでも不安定なら、テキスト前処理で英語部分に発音ヒントを追加
3. `src/tts.py` の `synthesize()` 内に前処理関数を追加

## 参考情報

- [Gemini API TTS Documentation](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Google Cloud Gemini-TTS Documentation](https://docs.cloud.google.com/text-to-speech/docs/gemini-tts)
- [Google Cloud SSML Documentation (lang/phoneme tags)](https://docs.cloud.google.com/text-to-speech/docs/ssml)
- [Deep Dive: Gemini 2.5 Pro TTS with Emotion & SSML Tags (DEV.to)](https://dev.to/abdalrohman/deep-dive-i-tested-googles-new-gemini-25-pro-tts-with-emotion-ssml-tags-5d3i)
- [Gemini 2.5 Flash Preview TTS Verification (Zenn/dsflon)](https://zenn.dev/dsflon/articles/b48b3f28f747e7)
- [Gemini 2.5 Pro TTS Japanese Quality (Zenn/acntechjp)](https://zenn.dev/acntechjp/articles/150c9bb24c09ad)
- [Gemini 2.5 Flash TTS Japanese Narration (Qiita)](https://qiita.com/akira_papa_AI/items/1b398b9901134a8ce865)
- [Gemini TTS Language Codes Forum](https://discuss.ai.google.dev/t/gemini-2-5-pro-tts-language-codes/108683)
- [Gemini TTS Pronunciation Workaround Forum](https://discuss.ai.google.dev/t/how-can-i-force-gemini-to-correct-its-mispronunciation-of-obscure-words-such-as-requiter/101725)
