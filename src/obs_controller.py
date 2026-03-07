"""OBS WebSocket制御モジュール"""

import os

import obsws_python as obs


class OBSController:
    """OBS WebSocketを通じてOBSを制御するクラス"""

    def __init__(self, host=None, port=None, password=None):
        self.host = host or os.environ.get("OBS_WS_HOST", "localhost")
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

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
