"""TTS（音声合成）モジュール - Gemini 2.5 Flash TTS"""

import logging
import os
import re
import time
import wave

from google.genai import types

from src.gemini_client import get_client

logger = logging.getLogger(__name__)

# Gemini TTS で利用可能な音声（全30種）
# Zephyr, Puck, Charon, Kore, Fenrir, Leda, Orus, Aoede, Callirrhoe, Autonoe,
# Enceladus, Iapetus, Umbriel, Algieba, Despina, Erinome, Algenib, Rasalgethi,
# Laomedeia, Achernar, Alnilam, Schedar, Gacrux, Pulcherrima, Achird,
# Zubenelgenubi, Vindemiatrix, Sadachbia, Sadaltager, Sulafat
DEFAULT_VOICE = "Despina"
DEFAULT_STYLE = "終始にこにこしているような、柔らかく楽しげなトーンで読み上げてください"


def _get_tts_style():
    """現在の配信言語設定に応じたTTSスタイルを返す"""
    try:
        from src.prompt_builder import build_tts_style
        return build_tts_style()
    except Exception:
        return DEFAULT_STYLE


def _get_base_lang_name():
    """現在の配信言語設定からベース言語名を返す"""
    try:
        from src.prompt_builder import get_stream_language, SUPPORTED_LANGUAGES
        lang = get_stream_language()
        primary = lang["primary"]
        # SUPPORTED_LANGUAGES の値は日本語名なので TTS 用に英語名を使う
        _TTS_LANG_NAMES = {
            "ja": "Japanese", "en": "English", "ko": "Korean",
            "es": "Spanish", "zh": "Chinese", "fr": "French",
            "pt": "Portuguese", "de": "German",
        }
        return primary, _TTS_LANG_NAMES.get(primary, "Japanese")
    except Exception:
        return "ja", "Japanese"


def _convert_lang_tags(text):
    """[lang:xx]...[/lang] タグを TTS用の発音ヒントに変換する

    AIが生成した言語タグを、TTSが理解しやすい形式に変換。
    タグがない場合は正規表現で非ベース言語部分を検出してフォールバック。

    例 (ja): "今日は[lang:en]YouTube[/lang]の動画" → "今日は[English]YouTube[Japanese]の動画"
    例 (en): "Let's learn [lang:ja]こんにちは[/lang] today" → "Let's learn [Japanese]こんにちは[English] today"
    """
    base_code, base_lang_name = _get_base_lang_name()

    # [lang:xx]...[/lang] タグがある場合はそれを変換
    LANG_NAMES = {
        "en": "English", "es": "Spanish", "ko": "Korean",
        "fr": "French", "zh": "Chinese", "de": "German",
        "pt": "Portuguese", "ru": "Russian", "it": "Italian",
        "ar": "Arabic", "th": "Thai", "vi": "Vietnamese",
        "ja": "Japanese",
    }
    if "[lang:" in text:
        def replace_tag(m):
            code = m.group(1)
            content = m.group(2)
            lang_name = LANG_NAMES.get(code, code.upper())
            return f"[{lang_name}]{content}[{base_lang_name}]"
        return re.sub(r'\[lang:(\w+)\](.*?)\[/lang\]', replace_tag, text)

    # フォールバック: ベース言語以外の部分を自動検出
    if base_code == "ja":
        # 日本語ベース: 英語部分を検出
        def replace_match(m):
            word = m.group(0).strip()
            if len(word) < 2:
                return m.group(0)
            return f'[English]{word}[Japanese]'
        return re.sub(r'[A-Za-z][A-Za-z0-9](?:[A-Za-z0-9\s\.\-\']*[A-Za-z0-9])?', replace_match, text)
    else:
        # 英語等ベース: CJK文字を検出して [Japanese] タグ付け
        def replace_cjk(m):
            content = m.group(0)
            return f'[Japanese]{content}[{base_lang_name}]'
        return re.sub(r'[\u3000-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]+', replace_cjk, text)


def synthesize(text, output_path, voice=None, style=None):
    """テキストから音声ファイルを生成する

    Args:
        text: 読み上げるテキスト
        output_path: 出力ファイルパス (.wav)
        voice: 音声名 (デフォルト: Despina)
        style: TTSスタイル指示（デフォルト: 環境変数 or 言語設定から自動生成）
    """
    if style is None:
        style = os.environ.get("TTS_STYLE") or _get_tts_style()
    processed_text = _convert_lang_tags(text)
    prompt = f"{style}: {processed_text}"
    logger.info("[tts] prompt: %s", prompt)
    return synthesize_with_prompt(prompt, output_path, voice=voice)


def synthesize_with_prompt(prompt, output_path, voice=None):
    """プロンプトでスタイルを指定して音声を生成する

    Args:
        prompt: スタイル指示を含むプロンプト
        output_path: 出力ファイルパス (.wav)
        voice: 音声名 (デフォルト: Leda)
    """
    client = get_client()
    voice = voice or os.environ.get("TTS_VOICE", DEFAULT_VOICE)
    max_retries = 3

    for attempt in range(max_retries):
        response = client.models.generate_content(
            model=os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts"),
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice,
                        )
                    )
                ),
            ),
        )

        # レスポンスからPCMデータを取得してWAVに書き出す
        try:
            data = response.candidates[0].content.parts[0].inline_data.data
        except (AttributeError, IndexError, TypeError):
            if attempt < max_retries - 1:
                logger.warning("[tts] 音声データ取得失敗、リトライ %d/%d", attempt + 1, max_retries)
                time.sleep(1)
                continue
            raise RuntimeError("TTS音声データの取得に3回失敗しました")

        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16bit
            wf.setframerate(24000)
            wf.writeframes(data)

        return output_path
