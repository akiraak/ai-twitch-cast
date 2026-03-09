"""全ボイスのサンプル音声を生成するスクリプト

全30ボイス × 4スタイルのサンプルを生成する。
スタイルはTTSのプロンプトで指定する（ピッチ変更ではない）。
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from src.tts import synthesize_with_prompt

# 全30ボイス
ALL_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir",
    "Leda", "Orus", "Aoede", "Callirrhoe", "Autonoe",
    "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina",
    "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird",
    "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]

# ベースのセリフ
BASE_TEXT_JA = "こんにちは！あかりです。今日も楽しく配信していきましょう！よろしくお願いします。"
BASE_TEXT_EN = "Hi everyone! I'm Akari! Let's have a fun stream today! Thanks for joining!"

# スタイル設定（名前, プロンプト）
STYLES = [
    ("normal", f"次のテキストを自然に読み上げてください: {BASE_TEXT_JA}"),
    ("energetic", f"テンション高めで元気いっぱいに読み上げてください: {BASE_TEXT_JA}"),
    ("calm", f"落ち着いた穏やかなトーンで、ニュースキャスターのように読み上げてください: {BASE_TEXT_JA}"),
    ("laughing", f"元気で楽しそうに、途中で笑いを交えながら読み上げてください: {BASE_TEXT_JA}"),
    ("laughing_en", f"Read the following text in a cheerful, energetic way, laughing and giggling throughout: {BASE_TEXT_EN}"),
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "assets", "voice-samples")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total = len(ALL_VOICES) * len(STYLES)
    count = 0
    errors = []

    for voice in ALL_VOICES:
        print(f"\n=== {voice} ===")

        for style_name, prompt in STYLES:
            output_path = os.path.join(OUTPUT_DIR, f"{voice.lower()}_{style_name}.wav")
            count += 1
            if os.path.exists(output_path):
                print(f"  [{count}/{total}] {voice} ({style_name})... SKIP (exists)")
                continue
            print(f"  [{count}/{total}] {voice} ({style_name})...", end=" ", flush=True)
            try:
                synthesize_with_prompt(prompt, output_path, voice=voice)
                print("OK")
            except Exception as e:
                print(f"ERROR: {e}")
                errors.append(f"{voice}_{style_name}: {e}")
            # レート制限対策
            time.sleep(0.5)

    print(f"\n完了！ {count - len(errors)}/{total} ファイルを生成しました: {OUTPUT_DIR}")
    if errors:
        print(f"\nエラー ({len(errors)}件):")
        for err in errors:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
