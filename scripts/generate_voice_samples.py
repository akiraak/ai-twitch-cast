"""全女性ボイスのサンプル音声を生成するスクリプト

各ボイスについてノーマル・高め・低めの3パターンを生成する。
ピッチ変更はnumpyでリサンプリングして実現。
"""

import os
import sys
import wave
import struct
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# .envを読み込む
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from src.tts import synthesize

# 女性ボイス一覧
FEMALE_VOICES = ["Aoede", "Kore", "Leda", "Puck"]

# サンプルテキスト
SAMPLE_TEXT = "こんにちは！あかりです。今日も楽しく配信していきましょう！よろしくお願いします。"

# ピッチ設定（倍率: >1で高く、<1で低く）
PITCH_VARIANTS = [
    ("normal", 1.0),
    ("high", 1.15),
    ("low", 0.85),
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "assets", "voice-samples")


def change_pitch(input_path, output_path, pitch_factor):
    """WAVファイルのピッチを変更する（リサンプリング方式）"""
    with wave.open(input_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)

    # PCM 16bitデータをnumpy配列に変換
    samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float64)

    # リサンプリングでピッチ変更
    # pitch_factor > 1 → 高い声（サンプル数を減らす）
    original_length = len(samples)
    new_length = int(original_length / pitch_factor)
    indices = np.linspace(0, original_length - 1, new_length)
    resampled = np.interp(indices, np.arange(original_length), samples)

    # クリッピング防止
    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)  # フレームレートは同じに保つ
        wf.writeframes(resampled.tobytes())


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total = len(FEMALE_VOICES) * len(PITCH_VARIANTS)
    count = 0

    for voice in FEMALE_VOICES:
        print(f"\n=== {voice} ===")

        # まずノーマル音声を生成
        normal_path = os.path.join(OUTPUT_DIR, f"{voice.lower()}_normal.wav")
        print(f"  生成中: {voice} (normal)...")
        synthesize(SAMPLE_TEXT, normal_path, voice=voice)
        count += 1
        print(f"  [{count}/{total}] {normal_path}")

        # ピッチ変更バリエーション
        for variant_name, pitch_factor in PITCH_VARIANTS:
            if variant_name == "normal":
                continue
            output_path = os.path.join(OUTPUT_DIR, f"{voice.lower()}_{variant_name}.wav")
            print(f"  ピッチ変更: {voice} ({variant_name}, x{pitch_factor})...")
            change_pitch(normal_path, output_path, pitch_factor)
            count += 1
            print(f"  [{count}/{total}] {output_path}")

    print(f"\n完了！ {count}ファイルを生成しました: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
