"""TTS（音声合成）モジュール - Gemini 2.5 Flash TTS"""

import io
import os
import wave

from google import genai
from google.genai import types


# Gemini TTS で利用可能な音声
# Aoede, Charon, Fenrir, Kore, Puck, Leda, Orus, Zephyr
DEFAULT_VOICE = "Kore"

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY が設定されていません")
        _client = genai.Client(api_key=api_key)
    return _client


def synthesize(text, output_path, voice=None):
    """テキストから音声ファイルを生成する

    Args:
        text: 読み上げるテキスト
        output_path: 出力ファイルパス (.wav)
        voice: 音声名 (デフォルト: Kore)
    """
    client = _get_client()
    voice = voice or os.environ.get("TTS_VOICE", DEFAULT_VOICE)

    response = client.models.generate_content(
        model=os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts"),
        contents=f"次のテキストをそのまま読み上げてください: {text}",
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
    data = response.candidates[0].content.parts[0].inline_data.data
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16bit
        wf.setframerate(24000)
        wf.writeframes(data)

    return output_path
