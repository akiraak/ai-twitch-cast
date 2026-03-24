# Step 2: TTS style パラメータ

## ステータス: 未着手

## ゴール

**先生と生徒で異なる声・スタイルで喋らせる。** `synthesize()` に `style` パラメータを追加し、lesson_runner から話者ごとに voice + style を渡せるようにする。

ここまでで「2体のアバターが別々の声で喋る」が実現する。

## 変更対象

| ファイル | 変更内容 |
|---------|---------|
| `src/tts.py` | `synthesize()` に `style` 引数追加 |
| `src/speech_pipeline.py` | `generate_tts()` / `speak()` に `style` 伝搬 |

## 前提

- なし（他Stepと独立）

## 実装

### 3-1. tts.py

```python
def synthesize(text, output_path, voice=None, style=None):
    """テキストから音声ファイルを生成する

    Args:
        text: 読み上げるテキスト
        output_path: 出力ファイルパス (.wav)
        voice: 音声名 (デフォルト: Despina)
        style: TTSスタイル指示 (デフォルト: 環境変数 or 配信言語設定)
    """
    style = style or os.environ.get("TTS_STYLE") or _get_tts_style()
    processed_text = _convert_lang_tags(text)
    prompt = f"{style}: {processed_text}"
    logger.info("[tts] prompt: %s", prompt)
    return synthesize_with_prompt(prompt, output_path, voice=voice)
```

### 3-2. speech_pipeline.py

```python
async def generate_tts(self, text, voice=None, style=None, tts_text=None):
    wav_path = Path(tempfile.mkdtemp()) / "speech.wav"
    try:
        await asyncio.to_thread(synthesize, tts_text or text, str(wav_path),
                                voice=voice, style=style)
        return wav_path
    except Exception as e:
        # ...

async def speak(self, text, voice=None, style=None, subtitle=None,
                chat_result=None, tts_text=None, post_to_chat=None,
                se=None, wav_path=None, avatar_id=None):
    async with self._speak_lock:
        await self._speak_impl(text, voice=voice, style=style, ...)
```

### 3-3. 動作確認方法

Python REPLやテストスクリプトで:
```python
from src.tts import synthesize
synthesize("こんにちは！まなびだよ！", "/tmp/test_student.wav",
           voice="Kore", style="元気で明るい生徒のトーンで読み上げてください")
synthesize("はい、今日の授業を始めましょう", "/tmp/test_teacher.wav",
           voice="Despina")  # style=None → デフォルト
# 2つのWAVを聴き比べて声の差を確認
```

## 完了条件

- [ ] `synthesize(text, path, voice="Kore", style="元気で...")` が正常動作する
- [ ] `style=None` の場合は従来のデフォルトスタイルが使われる
- [ ] `generate_tts()` / `speak()` に `style` が伝搬される
- [ ] 既存の呼び出し元（comment_reader等）が影響を受けない
