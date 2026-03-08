"""VTube Studio API制御モジュール"""

import json
import logging
import os
from pathlib import Path

import pyvts
import websockets

from src.wsl_path import resolve_host

logger = logging.getLogger(__name__)


class VTSController:
    """VTube Studio APIを通じてアバターを制御するクラス"""

    def __init__(self, host=None, port=None):
        self.host = resolve_host(host or os.environ.get("VTS_HOST", "localhost"))
        self.port = int(port or os.environ.get("VTS_PORT", "8001"))
        self._vts = None

    async def _establish_websocket(self):
        """WebSocket接続を確立する"""
        self._vts.websocket = await websockets.connect(
            f"ws://{self.host}:{self.port}",
            ping_interval=30,
            ping_timeout=10,
        )

    async def connect(self):
        """VTube Studioに接続・認証する"""
        token_path = str(Path(__file__).resolve().parent.parent / ".vts_token")
        self._vts = pyvts.vts(
            plugin_info={
                "plugin_name": "AI Twitch Cast",
                "developer": "ai-twitch-cast",
                "authentication_token_path": token_path,
            },
            vts_api_info={
                "host": self.host,
                "port": self.port,
                "name": "VTubeStudioPublicAPI",
                "version": "1.0",
            },
        )
        try:
            await self._establish_websocket()
        except Exception:
            raise ConnectionError(
                f"VTube Studioに接続できません ({self.host}:{self.port})。"
                " VTube StudioでAPIが有効になっているか確認してください。"
                " WSL2から接続する場合はVTS_HOSTにWindowsのIPアドレスを設定してください。"
            )
        await self._vts.request_authenticate_token()
        await self._vts.request_authenticate()
        logger.info("VTube Studioに接続しました")

    async def reconnect(self):
        """WebSocket接続を再確立する"""
        await self._establish_websocket()
        await self._vts.request_authenticate()
        logger.info("VTube Studioに再接続しました")

    async def _request(self, request_msg):
        """リクエストを送信する。接続が切れていたら自動再接続する"""
        try:
            await self._vts.websocket.send(json.dumps(request_msg))
            response = await self._vts.websocket.recv()
            return json.loads(response)
        except websockets.exceptions.ConnectionClosed:
            await self.reconnect()
            await self._vts.websocket.send(json.dumps(request_msg))
            response = await self._vts.websocket.recv()
            return json.loads(response)

    async def disconnect(self):
        """VTube Studioから切断する"""
        if self._vts:
            await self._vts.close()
            self._vts = None
            logger.info("VTube Studioから切断しました")

    async def get_model_info(self):
        """現在のモデル情報を取得する"""
        response = await self._request(
            self._vts.vts_request.BaseRequest(
                "CurrentModelRequest",
            )
        )
        data = response["data"]
        return {
            "model_name": data.get("modelName", ""),
            "model_id": data.get("modelID", ""),
            "model_loaded": data.get("modelLoaded", False),
        }

    async def set_parameter(self, parameter, value, weight=1.0):
        """パラメータの値を設定する（リップシンク・表情等）"""
        request = self._vts.vts_request.requestSetParameterValue(
            parameter=parameter,
            value=value,
            weight=weight,
        )
        await self._request(request)

    async def trigger_hotkey(self, hotkey_id):
        """ホットキーを実行する（表情切替・モーション再生等）"""
        request = self._vts.vts_request.requestTriggerHotKey(
            hotkeyID=hotkey_id,
        )
        await self._request(request)

    async def get_hotkeys(self):
        """利用可能なホットキー一覧を取得する"""
        response = await self._request(
            self._vts.vts_request.requestHotKeyList()
        )
        hotkeys = response["data"].get("availableHotkeys", [])
        return [
            {
                "name": hk.get("name", ""),
                "id": hk.get("hotkeyID", ""),
                "type": hk.get("type", ""),
            }
            for hk in hotkeys
        ]

    async def get_parameters(self):
        """現在のモデルのパラメータ一覧を取得する"""
        response = await self._request(
            self._vts.vts_request.BaseRequest(
                "InputParameterListRequest",
            )
        )
        params = response["data"].get("defaultParameters", []) + response["data"].get("customParameters", [])
        return [
            {
                "name": p.get("name", ""),
                "value": p.get("value", 0),
                "min": p.get("min", 0),
                "max": p.get("max", 0),
            }
            for p in params
        ]

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
        return False
