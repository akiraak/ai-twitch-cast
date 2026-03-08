"""TTS（音声合成）モジュール - Gemini 2.5 Flash TTS"""

import os
import wave

from google.genai import types

from src.gemini_client import get_client

# Gemini TTS で利用可能な音声
# Aoede, Charon, Fenrir, Kore, Puck, Leda, Orus, Zephyr
DEFAULT_VOICE = "Kore"


def synthesize(text, output_path, voice=None):
    """テキストから音声ファイルを生成する

    Args:
        text: 読み上げるテキスト
        output_path: 出力ファイルパス (.wav)
        voice: 音声名 (デフォルト: Kore)
    """
    client = get_client()
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
