"""OBS WebSocket制御モジュール"""

import logging
import os
from pathlib import Path

import obsws_python as obs

# obsws-pythonのlogger.exception()によるトレースバック出力を抑制
logging.getLogger("obsws_python").setLevel(logging.CRITICAL)

from src.wsl_path import resolve_host, to_windows_path


class OBSController:
    """OBS WebSocketを通じてOBSを制御するクラス"""

    def __init__(self, host=None, port=None, password=None):
        self.host = resolve_host(host or os.environ.get("OBS_WS_HOST", "localhost"))
        self.port = int(port or os.environ.get("OBS_WS_PORT", "4455"))
        self.password = password or os.environ.get("OBS_WS_PASSWORD", "")
        self._client = None

    def connect(self):
        """OBS WebSocketに接続する"""
        try:
            self._client = obs.ReqClient(
                host=self.host, port=self.port, password=self.password, timeout=5
            )
        except ConnectionRefusedError:
            raise ConnectionError(
                f"OBSに接続できません ({self.host}:{self.port})。"
                " OBSが起動しているか、WebSocketサーバーが有効か確認してください。"
                " WSL2から接続する場合はOBS_WS_HOSTにWindowsのIPアドレスを設定してください。"
            )
        version = self._client.get_version()
        print(f"OBSに接続しました (OBS {version.obs_version}, WebSocket {version.obs_web_socket_version})")

    def disconnect(self):
        """OBS WebSocketから切断する"""
        if self._client:
            self._client.base_client.ws.close()
            self._client = None
            print("OBSから切断しました")

    def get_stream_status(self):
        """配信状態を取得する"""
        status = self._client.get_stream_status()
        return {
            "active": status.output_active,
            "reconnecting": status.output_reconnecting,
            "timecode": status.output_timecode,
            "bytes": status.output_bytes,
        }

    def start_stream(self):
        """配信を開始する"""
        status = self.get_stream_status()
        if status["active"]:
            print("既に配信中です")
            return
        self._client.start_stream()
        print("配信を開始しました")

    def stop_stream(self):
        """配信を停止する"""
        status = self.get_stream_status()
        if not status["active"]:
            print("配信していません")
            return
        self._client.stop_stream()
        print("配信を停止しました")

    def get_scenes(self):
        """シーン一覧を取得する"""
        result = self._client.get_scene_list()
        return {
            "current": result.current_program_scene_name,
            "scenes": [s["sceneName"] for s in result.scenes],
        }

    def create_scene(self, name):
        """シーンを作成する"""
        self._client.create_scene(name)
        print(f"シーンを作成しました: {name}")

    def set_scene(self, name):
        """シーンを切り替える"""
        self._client.set_current_program_scene(name)
        print(f"シーンを切り替えました: {name}")

    def add_image_source(self, scene_name, source_name, wsl_path):
        """WSLパスの画像をソースとして追加する"""
        win_path = to_windows_path(str(wsl_path))
        self._client.create_input(
            sceneName=scene_name,
            inputName=source_name,
            inputKind="image_source",
            inputSettings={"file": win_path},
            sceneItemEnabled=True,
        )
        print(f"画像ソースを追加しました: {source_name}")

    def add_game_capture(self, scene_name, source_name, window="", allow_transparency=False):
        """ゲームキャプチャソースを追加する"""
        settings = {
            "capture_mode": "window" if window else "any_fullscreen",
            "allow_transparency": allow_transparency,
        }
        if window:
            settings["window"] = window
        self._client.create_input(
            sceneName=scene_name,
            inputName=source_name,
            inputKind="game_capture",
            inputSettings=settings,
            sceneItemEnabled=True,
        )
        print(f"ゲームキャプチャを追加しました: {source_name}")

    def add_text_source(self, scene_name, source_name, text, font_size=48):
        """テキストソースを追加する"""
        self._client.create_input(
            sceneName=scene_name,
            inputName=source_name,
            inputKind="text_gdiplus_v3",
            inputSettings={
                "text": text,
                "font": {"face": "Yu Gothic UI", "size": font_size},
                "color": 0xFFFFFFFF,
                "align": "center",
                "valign": "center",
            },
            sceneItemEnabled=True,
        )
        print(f"テキストソースを追加しました: {source_name}")

    def set_source_transform(self, scene_name, source_name, transform):
        """ソースの位置・サイズを設定する"""
        item_id = self._client.get_scene_item_id(scene_name, source_name).scene_item_id
        self._client.set_scene_item_transform(scene_name, item_id, transform)

    def remove_scene(self, name):
        """シーンを削除する"""
        self._client.remove_scene(name)
        print(f"シーンを削除しました: {name}")

    def remove_input(self, input_name):
        """入力ソースを削除する"""
        self._client.remove_input(input_name)
        print(f"ソースを削除しました: {input_name}")

    def setup_scenes(self, scenes_config):
        """シーン構成を一括作成する"""
        for scene in scenes_config:
            scene_name = scene["name"]
            try:
                self.create_scene(scene_name)
            except Exception:
                print(f"シーン '{scene_name}' は既に存在します")

            for source in scene["sources"]:
                try:
                    self._add_source(scene_name, source)
                    if "transform" in source:
                        self.set_source_transform(scene_name, source["name"], source["transform"])
                except Exception as e:
                    print(f"  ソース '{source['name']}' の追加に失敗: {e}")

        print(f"\nセットアップ完了 ({len(scenes_config)}シーン)")

    def teardown_scenes(self, scenes_config):
        """シーン構成を一括削除する"""
        # ソースを先に削除（他シーンとの共有を考慮）
        removed_inputs = set()
        for scene in scenes_config:
            for source in scene["sources"]:
                if source["name"] not in removed_inputs:
                    try:
                        self.remove_input(source["name"])
                        removed_inputs.add(source["name"])
                    except Exception:
                        pass

        # シーンを削除
        for scene in scenes_config:
            try:
                self.remove_scene(scene["name"])
            except Exception:
                pass

        print(f"\nティアダウン完了")

    def _add_source(self, scene_name, source):
        """ソース定義に基づいてソースを追加する"""
        kind = source["kind"]
        name = source["name"]

        if kind == "image":
            self.add_image_source(scene_name, name, source["path"])
        elif kind == "text":
            self.add_text_source(
                scene_name, name,
                source["text"],
                source.get("font_size", 48),
            )
        elif kind == "game_capture":
            self.add_game_capture(
                scene_name, name,
                window=source.get("window", ""),
                allow_transparency=source.get("allow_transparency", False),
            )
        else:
            print(f"  不明なソース種類: {kind}")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
