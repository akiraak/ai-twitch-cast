"""TTS（音声合成）モジュール - Gemini 2.5 Flash TTS"""

import logging
import os
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
    """現在の言語モードに応じたTTSスタイルを返す"""
    try:
        from src.ai_responder import get_language_mode, LANGUAGE_MODES
        mode = get_language_mode()
        lang = LANGUAGE_MODES.get(mode, {})
        return lang.get("tts_style", DEFAULT_STYLE)
    except Exception:
        return DEFAULT_STYLE


def synthesize(text, output_path, voice=None):
    """テキストから音声ファイルを生成する

    Args:
        text: 読み上げるテキスト
        output_path: 出力ファイルパス (.wav)
        voice: 音声名 (デフォルト: Despina)
    """
    style = os.environ.get("TTS_STYLE") or _get_tts_style()
    prompt = f"{style}: {text}"
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
