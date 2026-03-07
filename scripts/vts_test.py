"""VTube Studio接続テスト: モデル情報・パラメータ・ホットキーを表示する"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.vts_controller import VTSController

load_dotenv()


async def main():
    async with VTSController() as vts:
        # モデル情報
        model = await vts.get_model_info()
        print(f"\nモデル: {model['model_name']}")
        print(f"モデルID: {model['model_id']}")
        print(f"ロード済み: {model['model_loaded']}")

        # パラメータ一覧
        params = await vts.get_parameters()
        print(f"\nパラメータ ({len(params)}件):")
        for p in params:
            print(f"  {p['name']}: {p['value']} ({p['min']}〜{p['max']})")

        # ホットキー一覧
        hotkeys = await vts.get_hotkeys()
        print(f"\nホットキー ({len(hotkeys)}件):")
        for hk in hotkeys:
            print(f"  {hk['name']} (ID: {hk['id']}, Type: {hk['type']})")


asyncio.run(main())
