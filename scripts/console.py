"""アバター対話式コンソール"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from src.vts_controller import VTSController

HELP_TEXT = """
コマンド一覧:
  vts connect          VTube Studioに接続
  vts disconnect       VTube Studioから切断
  vts status           VTS接続状態・モデル情報を表示
  vts model            現在のモデル情報を表示
  vts params           パラメータ一覧を表示
  vts param <名前> <値> パラメータの値を設定
  vts hotkeys          ホットキー一覧を表示
  vts hotkey <ID>      ホットキーを実行
  vts demo             デモ動作（口パク・まばたき・体の動き）

  help                 このヘルプを表示
  quit / exit          終了
""".strip()


class Console:
    def __init__(self):
        self.vts = VTSController()
        self._vts_connected = False

    # --- VTSコマンド ---

    async def cmd_vts_connect(self):
        await self.vts.connect()
        self._vts_connected = True

    async def cmd_vts_disconnect(self):
        await self.vts.disconnect()
        self._vts_connected = False

    async def cmd_vts_status(self):
        if not self._vts_connected:
            print("VTube Studio: 未接続")
            return
        print("VTube Studio: 接続中")
        model = await self.vts.get_model_info()
        print(f"  モデル: {model['model_name']}")
        print(f"  ロード済み: {model['model_loaded']}")

    async def cmd_vts_model(self):
        await self._require_vts()
        model = await self.vts.get_model_info()
        print(f"モデル名: {model['model_name']}")
        print(f"モデルID: {model['model_id']}")
        print(f"ロード済み: {model['model_loaded']}")

    async def cmd_vts_params(self):
        await self._require_vts()
        params = await self.vts.get_parameters()
        print(f"パラメータ ({len(params)}件):")
        for p in params:
            print(f"  {p['name']}: {p['value']} ({p['min']}〜{p['max']})")

    async def cmd_vts_param(self, name, value):
        await self._require_vts()
        await self.vts.set_parameter(name, float(value))
        print(f"{name} = {value}")

    async def cmd_vts_hotkeys(self):
        await self._require_vts()
        hotkeys = await self.vts.get_hotkeys()
        print(f"ホットキー ({len(hotkeys)}件):")
        for hk in hotkeys:
            print(f"  {hk['name']} (ID: {hk['id']}, Type: {hk['type']})")

    async def cmd_vts_hotkey(self, hotkey_id):
        await self._require_vts()
        await self.vts.trigger_hotkey(hotkey_id)
        print(f"ホットキーを実行しました: {hotkey_id}")

    async def cmd_vts_demo(self):
        await self._require_vts()
        print("デモ開始...")

        print("  口パク...")
        for _ in range(3):
            await self.vts.set_parameter("MouthOpen", 1.0)
            await asyncio.sleep(0.3)
            await self.vts.set_parameter("MouthOpen", 0.0)
            await asyncio.sleep(0.2)

        await asyncio.sleep(0.5)

        print("  まばたき...")
        await self.vts.set_parameter("EyeOpenLeft", 0.0)
        await self.vts.set_parameter("EyeOpenRight", 0.0)
        await asyncio.sleep(0.3)
        await self.vts.set_parameter("EyeOpenLeft", 1.0)
        await self.vts.set_parameter("EyeOpenRight", 1.0)

        await asyncio.sleep(0.5)

        print("  体の動き...")
        await self.vts.set_parameter("FaceAngleZ", 15.0)
        await asyncio.sleep(0.5)
        await self.vts.set_parameter("FaceAngleZ", -15.0)
        await asyncio.sleep(0.5)
        await self.vts.set_parameter("FaceAngleZ", 0.0)

        print("デモ完了")

    # --- ユーティリティ ---

    async def _require_vts(self):
        if not self._vts_connected:
            await self.cmd_vts_connect()

    async def dispatch(self, line):
        """コマンドをパースして実行する"""
        parts = line.strip().split()
        if not parts:
            return

        cmd = parts[0]
        args = parts[1:]

        try:
            if cmd == "help":
                print(HELP_TEXT)
            elif cmd == "vts" and args:
                await self._dispatch_vts(args)
            elif cmd in ("quit", "exit"):
                raise SystemExit
            else:
                print(f"不明なコマンド: {line.strip()}")
                print("'help' でコマンド一覧を表示")
        except RuntimeError as e:
            print(f"エラー: {e}")
        except Exception as e:
            print(f"エラー: {type(e).__name__}: {e}")

    async def _dispatch_vts(self, args):
        sub = args[0]
        if sub == "connect":
            await self.cmd_vts_connect()
        elif sub == "disconnect":
            await self.cmd_vts_disconnect()
        elif sub == "status":
            await self.cmd_vts_status()
        elif sub == "model":
            await self.cmd_vts_model()
        elif sub == "params":
            await self.cmd_vts_params()
        elif sub == "param":
            if len(args) >= 3:
                await self.cmd_vts_param(args[1], args[2])
            else:
                print("使い方: vts param <名前> <値>  (例: vts param MouthOpen 1.0)")
        elif sub == "hotkeys":
            await self.cmd_vts_hotkeys()
        elif sub == "hotkey":
            if len(args) >= 2:
                await self.cmd_vts_hotkey(args[1])
            else:
                print("使い方: vts hotkey <ID>")
        elif sub == "demo":
            await self.cmd_vts_demo()
        else:
            print(f"不明なVTSコマンド: {' '.join(args)}")

    async def cleanup(self):
        """終了時のクリーンアップ"""
        if self._vts_connected:
            await self.vts.disconnect()


async def main():
    console = Console()
    print("AI Twitch Cast コンソール (helpでコマンド一覧)\n")

    try:
        await console.cmd_vts_connect()
    except Exception as e:
        print(f"VTS: 接続失敗 ({e})")

    print()

    loop = asyncio.get_event_loop()
    try:
        while True:
            try:
                line = await loop.run_in_executor(None, input, "> ")
            except EOFError:
                break
            await console.dispatch(line)
    except (SystemExit, KeyboardInterrupt):
        pass
    finally:
        await console.cleanup()
        print("終了")


asyncio.run(main())
