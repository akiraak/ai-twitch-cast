"""Live2D + VTube Studio + OBS で配信するスクリプト

1. VTube Studioに接続してアバターの動作確認
2. OBSに接続して配信を開始
3. アバターの口パク・表情のデモ動作
4. 配信を停止
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.obs_controller import OBSController
from src.vts_controller import VTSController

load_dotenv()


async def demo_avatar(vts):
    """アバターのデモ動作（口パク・表情）"""
    print("\nアバターデモ開始...")

    # 口パクのデモ（3回）
    print("  口パクテスト...")
    for _ in range(3):
        await vts.set_parameter("MouthOpen", 1.0)
        await asyncio.sleep(0.3)
        await vts.set_parameter("MouthOpen", 0.0)
        await asyncio.sleep(0.2)

    await asyncio.sleep(0.5)

    # 目を閉じて開く
    print("  まばたきテスト...")
    await vts.set_parameter("EyeOpenLeft", 0.0)
    await vts.set_parameter("EyeOpenRight", 0.0)
    await asyncio.sleep(0.3)
    await vts.set_parameter("EyeOpenLeft", 1.0)
    await vts.set_parameter("EyeOpenRight", 1.0)

    await asyncio.sleep(0.5)

    # 体を左右に傾ける
    print("  体の動きテスト...")
    await vts.set_parameter("FaceAngleZ", 15.0)
    await asyncio.sleep(0.5)
    await vts.set_parameter("FaceAngleZ", -15.0)
    await asyncio.sleep(0.5)
    await vts.set_parameter("FaceAngleZ", 0.0)

    print("アバターデモ完了")


async def main():
    # VTube Studioに接続
    async with VTSController() as vts:
        model = await vts.get_model_info()
        print(f"モデル: {model['model_name']}")

        # OBSに接続して配信開始
        with OBSController() as obs:
            obs.start_stream()

            # 配信中にアバターをデモ動作
            await asyncio.sleep(2)  # 配信が安定するまで待機
            await demo_avatar(vts)

            # しばらく配信を続ける
            print("\n10秒間配信を続けます...")
            await asyncio.sleep(10)

            obs.stop_stream()

    print("\n完了")


asyncio.run(main())
