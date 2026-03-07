"""OBS・VTube Studio対話式コンソール"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.obs_controller import OBSController
from src.scene_config import SCENES
from src.vsf_controller import VSFController
from src.vts_controller import VTSController

HELP_TEXT = """
コマンド一覧:
  obs connect          OBSに接続
  obs disconnect       OBSから切断
  obs status           OBS接続状態・配信状態を表示
  obs scenes           シーン一覧を表示
  obs scene <名前>     シーンを切り替え
  obs sources          現在のシーンのソース一覧を表示
  obs setup            シーン・ソースを一括作成
  obs teardown         シーン・ソースを一括削除
  obs add scene <名前>           シーンを追加
  obs add image <名前> <パス>     画像ソースを追加
  obs add text <名前> <テキスト>  テキストソースを追加
  obs add capture <名前>         ゲームキャプチャを追加
  obs remove <名前>              ソースを削除

  vts connect          VTube Studioに接続
  vts disconnect       VTube Studioから切断
  vts status           VTS接続状態・モデル情報を表示
  vts model            現在のモデル情報を表示
  vts params           パラメータ一覧を表示
  vts param <名前> <値> パラメータの値を設定
  vts hotkeys          ホットキー一覧を表示
  vts hotkey <ID>      ホットキーを実行
  vts demo             デモ動作（口パク・まばたき・体の動き）

  vsf connect          VSeeFace (VMC Protocol) に接続
  vsf disconnect       VSeeFaceから切断
  vsf status           VSF接続状態を表示
  vsf pose             デフォルトポーズを適用（腕を下ろす）
  vsf blend <名前> <値> BlendShapeを設定（例: vsf blend Joy 1.0）
  vsf bone <名前> <qx> <qy> <qz> <qw>  ボーン回転を設定
  vsf demo             デモ動作（リップシンク・表情・体の動き）

  stream start         配信を開始
  stream stop          配信を停止
  stream status        配信状態を表示

  init                 初期化（OBS・VTS接続 → シーン構築）

  help                 このヘルプを表示
  quit / exit          終了
""".strip()


class Console:
    def __init__(self):
        self.obs = OBSController()
        self.vts = VTSController()
        self.vsf = VSFController()
        self._obs_connected = False
        self._vts_connected = False
        self._vsf_connected = False

    # --- OBSコマンド ---

    def cmd_obs_connect(self):
        self.obs.connect()
        self._obs_connected = True

    def cmd_obs_disconnect(self):
        self.obs.disconnect()
        self._obs_connected = False

    def cmd_obs_status(self):
        if not self._obs_connected:
            print("OBS: 未接続")
            return
        print("OBS: 接続中")
        status = self.obs.get_stream_status()
        state = "配信中" if status["active"] else "停止中"
        print(f"  配信: {state}")
        if status["active"]:
            print(f"  経過時間: {status['timecode']}")

    def cmd_obs_scenes(self):
        self._require_obs()
        scenes = self.obs._client.get_scene_list()
        current = scenes.current_program_scene_name
        print("シーン一覧:")
        for s in scenes.scenes:
            marker = " *" if s["sceneName"] == current else ""
            print(f"  {s['sceneName']}{marker}")

    def cmd_obs_scene(self, name):
        self._require_obs()
        self.obs._client.set_current_program_scene(name)
        print(f"シーンを切り替えました: {name}")

    def cmd_obs_sources(self):
        self._require_obs()
        scenes = self.obs._client.get_scene_list()
        current = scenes.current_program_scene_name
        items = self.obs._client.get_scene_item_list(current)
        print(f"ソース一覧 ({current}):")
        for item in items.scene_items:
            enabled = "ON" if item["sceneItemEnabled"] else "OFF"
            print(f"  [{enabled}] {item['sourceName']} ({item['inputKind'] or 'group'})")

    def cmd_obs_setup(self):
        self._require_obs()
        self.obs.setup_scenes(SCENES)

    def cmd_obs_teardown(self):
        self._require_obs()
        self.obs.teardown_scenes(SCENES)

    def cmd_obs_add_scene(self, name):
        self._require_obs()
        self.obs.create_scene(name)

    def cmd_obs_add_image(self, name, path):
        self._require_obs()
        scenes = self.obs._client.get_scene_list()
        current = scenes.current_program_scene_name
        self.obs.add_image_source(current, name, path)

    def cmd_obs_add_text(self, name, text):
        self._require_obs()
        scenes = self.obs._client.get_scene_list()
        current = scenes.current_program_scene_name
        self.obs.add_text_source(current, name, text)

    def cmd_obs_add_capture(self, name):
        self._require_obs()
        scenes = self.obs._client.get_scene_list()
        current = scenes.current_program_scene_name
        self.obs.add_game_capture(current, name)

    def cmd_obs_remove(self, name):
        self._require_obs()
        self.obs.remove_input(name)

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

    # --- VSFコマンド ---

    def cmd_vsf_connect(self):
        self.vsf.connect()
        self._vsf_connected = True
        self.vsf.apply_default_pose()

    def cmd_vsf_disconnect(self):
        self.vsf.disconnect()
        self._vsf_connected = False

    def cmd_vsf_status(self):
        if not self._vsf_connected:
            print("VSeeFace: 未接続")
        else:
            print(f"VSeeFace: 接続中 ({self.vsf.host}:{self.vsf.port})")

    def cmd_vsf_pose(self):
        self._require_vsf()
        self.vsf.apply_default_pose()
        print("デフォルトポーズを適用しました")

    def cmd_vsf_blend(self, name, value):
        self._require_vsf()
        self.vsf.set_blendshape(name, float(value))
        print(f"BlendShape {name} = {value}")

    def cmd_vsf_bone(self, bone, qx, qy, qz, qw):
        self._require_vsf()
        self.vsf.set_bone(bone, qx=float(qx), qy=float(qy), qz=float(qz), qw=float(qw))
        print(f"Bone {bone} = ({qx}, {qy}, {qz}, {qw})")

    async def cmd_vsf_demo(self):
        self._require_vsf()
        import math

        def quat_from_axis_angle(ax, ay, az, angle_deg):
            """軸と角度（度）からクォータニオンを生成"""
            rad = math.radians(angle_deg) / 2
            s = math.sin(rad)
            c = math.cos(rad)
            return (ax * s, ay * s, az * s, c)

        print("デモ開始...")

        print("  リップシンク...")
        for vowel in ["A", "I", "U", "E", "O"]:
            self.vsf.set_blendshape(vowel, 0.8)
            await asyncio.sleep(0.3)
            self.vsf.set_blendshape(vowel, 0.0)
            await asyncio.sleep(0.1)

        await asyncio.sleep(0.3)

        print("  表情（Joy）...")
        self.vsf.set_blendshape("Joy", 1.0)
        await asyncio.sleep(1.0)
        self.vsf.set_blendshape("Joy", 0.0)

        await asyncio.sleep(0.3)

        print("  まばたき...")
        self.vsf.set_blendshape("Blink", 1.0)
        await asyncio.sleep(0.2)
        self.vsf.set_blendshape("Blink", 0.0)

        await asyncio.sleep(0.3)

        print("  頷き...")
        for i in range(20):
            angle = math.sin(i * 0.6) * 15  # 上下15度
            qx, qy, qz, qw = quat_from_axis_angle(1, 0, 0, angle)
            self.vsf.set_bone("Head", qx=qx, qy=qy, qz=qz, qw=qw)
            await asyncio.sleep(0.05)
        self.vsf.set_bone("Head")

        await asyncio.sleep(0.3)

        print("  首かしげ...")
        for i in range(20):
            angle = math.sin(i * 0.5) * 20  # 左右20度
            qx, qy, qz, qw = quat_from_axis_angle(0, 0, 1, angle)
            self.vsf.set_bone("Head", qx=qx, qy=qy, qz=qz, qw=qw)
            await asyncio.sleep(0.05)
        self.vsf.set_bone("Head")

        await asyncio.sleep(0.3)

        print("  体の揺れ...")
        for i in range(30):
            angle = math.sin(i * 0.4) * 10  # 左右10度
            qx, qy, qz, qw = quat_from_axis_angle(0, 0, 1, angle)
            self.vsf.set_bone("Spine", qx=qx, qy=qy, qz=qz, qw=qw)
            await asyncio.sleep(0.05)
        self.vsf.set_bone("Spine")

        await asyncio.sleep(0.3)

        print("  手を振る...")
        for i in range(20):
            angle = -30 + math.sin(i * 1.0) * 30  # -60〜0度
            qx, qy, qz, qw = quat_from_axis_angle(0, 0, 1, angle)
            self.vsf.set_bone("RightUpperArm", qx=qx, qy=qy, qz=qz, qw=qw)
            await asyncio.sleep(0.05)
        self.vsf.set_bone("RightUpperArm")

        print("デモ完了")

    # --- 配信コマンド ---

    def cmd_stream_start(self):
        self._require_obs()
        self.obs.start_stream()

    def cmd_stream_stop(self):
        self._require_obs()
        self.obs.stop_stream()

    def cmd_stream_status(self):
        self._require_obs()
        status = self.obs.get_stream_status()
        state = "配信中" if status["active"] else "停止中"
        print(f"配信: {state}")
        if status["active"]:
            print(f"経過時間: {status['timecode']}")
            print(f"送信バイト数: {status['bytes']}")

    # --- 初期化 ---

    async def cmd_init(self):
        """OBS・アバターアプリ接続 → シーン構築を一括実行"""
        from src.scene_config import AVATAR_APP
        print("初期化開始...")
        self.cmd_obs_connect()
        if AVATAR_APP == "vsf":
            self.cmd_vsf_connect()
        else:
            await self.cmd_vts_connect()
        self.cmd_obs_setup()
        self.obs.set_scene(SCENES[0]["name"])
        print("\n初期化完了")

    # --- ユーティリティ ---

    def _require_obs(self):
        if not self._obs_connected:
            self.cmd_obs_connect()

    async def _require_vts(self):
        if not self._vts_connected:
            await self.cmd_vts_connect()

    def _require_vsf(self):
        if not self._vsf_connected:
            self.cmd_vsf_connect()

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
            elif cmd == "obs" and args:
                await self._dispatch_obs(args)
            elif cmd == "vts" and args:
                await self._dispatch_vts(args)
            elif cmd == "vsf" and args:
                await self._dispatch_vsf(args)
            elif cmd == "stream" and args:
                self._dispatch_stream(args)
            elif cmd == "init":
                await self.cmd_init()
            elif cmd in ("quit", "exit"):
                raise SystemExit
            else:
                print(f"不明なコマンド: {line.strip()}")
                print("'help' でコマンド一覧を表示")
        except RuntimeError as e:
            print(f"エラー: {e}")
        except Exception as e:
            print(f"エラー: {type(e).__name__}: {e}")

    async def _dispatch_obs(self, args):
        sub = args[0]
        if sub == "connect":
            self.cmd_obs_connect()
        elif sub == "disconnect":
            self.cmd_obs_disconnect()
        elif sub == "status":
            self.cmd_obs_status()
        elif sub == "scenes":
            self.cmd_obs_scenes()
        elif sub == "scene":
            if len(args) >= 2:
                self.cmd_obs_scene(" ".join(args[1:]))
            else:
                print("使い方: obs scene <名前>")
        elif sub == "sources":
            self.cmd_obs_sources()
        elif sub == "setup":
            self.cmd_obs_setup()
        elif sub == "teardown":
            self.cmd_obs_teardown()
        elif sub == "add":
            if len(args) >= 2:
                self._dispatch_obs_add(args[1:])
            else:
                print("使い方: obs add scene|image|text|capture <名前> [引数...]")
        elif sub == "remove":
            if len(args) >= 2:
                self.cmd_obs_remove(" ".join(args[1:]))
            else:
                print("使い方: obs remove <名前>")
        else:
            print(f"不明なOBSコマンド: {' '.join(args)}")

    def _dispatch_obs_add(self, args):
        kind = args[0]
        if kind == "scene":
            if len(args) >= 2:
                self.cmd_obs_add_scene(" ".join(args[1:]))
            else:
                print("使い方: obs add scene <名前>")
        elif kind == "image":
            if len(args) >= 3:
                self.cmd_obs_add_image(args[1], args[2])
            else:
                print("使い方: obs add image <名前> <パス>")
        elif kind == "text":
            if len(args) >= 3:
                self.cmd_obs_add_text(args[1], " ".join(args[2:]))
            else:
                print("使い方: obs add text <名前> <テキスト>")
        elif kind == "capture":
            if len(args) >= 2:
                self.cmd_obs_add_capture(" ".join(args[1:]))
            else:
                print("使い方: obs add capture <名前>")
        else:
            print(f"不明なaddコマンド: {' '.join(args)}")

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

    async def _dispatch_vsf(self, args):
        sub = args[0]
        if sub == "connect":
            self.cmd_vsf_connect()
        elif sub == "disconnect":
            self.cmd_vsf_disconnect()
        elif sub == "status":
            self.cmd_vsf_status()
        elif sub == "pose":
            self.cmd_vsf_pose()
        elif sub == "blend":
            if len(args) >= 3:
                self.cmd_vsf_blend(args[1], args[2])
            else:
                print("使い方: vsf blend <名前> <値>  (例: vsf blend Joy 1.0)")
        elif sub == "bone":
            if len(args) >= 6:
                self.cmd_vsf_bone(args[1], args[2], args[3], args[4], args[5])
            else:
                print("使い方: vsf bone <名前> <qx> <qy> <qz> <qw>  (例: vsf bone Head 0.1 0 0 1)")
        elif sub == "demo":
            await self.cmd_vsf_demo()
        else:
            print(f"不明なVSFコマンド: {' '.join(args)}")

    def _dispatch_stream(self, args):
        sub = args[0]
        if sub == "start":
            self.cmd_stream_start()
        elif sub == "stop":
            self.cmd_stream_stop()
        elif sub == "status":
            self.cmd_stream_status()
        else:
            print(f"不明な配信コマンド: {' '.join(args)}")

    async def cleanup(self):
        """終了時のクリーンアップ"""
        if self._vsf_connected:
            self.vsf.disconnect()
        if self._vts_connected:
            await self.vts.disconnect()
        if self._obs_connected:
            self.obs.disconnect()


async def main():
    console = Console()
    print("AI Twitch Cast コンソール (helpでコマンド一覧)\n")

    # 起動時に自動接続を試行
    from src.scene_config import AVATAR_APP

    try:
        console.cmd_obs_connect()
    except Exception as e:
        print(f"OBS: 接続失敗 ({e})")

    if AVATAR_APP == "vsf":
        try:
            console.cmd_vsf_connect()
        except Exception as e:
            print(f"VSF: 接続失敗 ({e})")
    else:
        try:
            await console.cmd_vts_connect()
        except Exception as e:
            print(f"VTS: 接続失敗 ({e})")

    print()

    try:
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            await console.dispatch(line)
    except (SystemExit, KeyboardInterrupt):
        pass
    finally:
        await console.cleanup()
        print("終了")


asyncio.run(main())
