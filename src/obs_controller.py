"""OBS WebSocket制御モジュール"""

import os
from pathlib import Path

import obsws_python as obs

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
            scene_name=scene_name,
            input_name=source_name,
            input_kind="image_source",
            input_settings={"file": win_path},
            scene_item_enabled=True,
        )
        print(f"画像ソースを追加しました: {source_name}")

    def add_game_capture(self, scene_name, source_name, window_name=""):
        """ゲームキャプチャソースを追加する"""
        settings = {"capture_mode": "window"}
        if window_name:
            settings["window"] = window_name
        self._client.create_input(
            scene_name=scene_name,
            input_name=source_name,
            input_kind="game_capture",
            input_settings=settings,
            scene_item_enabled=True,
        )
        print(f"ゲームキャプチャを追加しました: {source_name}")

    def remove_input(self, input_name):
        """入力ソースを削除する"""
        self._client.remove_input(input_name)
        print(f"ソースを削除しました: {input_name}")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
