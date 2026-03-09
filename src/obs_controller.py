"""OBS WebSocket制御モジュール"""

import logging
import os
from pathlib import Path

import obsws_python as obs

# obsws-pythonのlogger.exception()によるトレースバック出力を抑制
logging.getLogger("obsws_python").setLevel(logging.CRITICAL)

from src.wsl_path import resolve_host, to_windows_path

logger = logging.getLogger(__name__)


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
        logger.info("OBSに接続しました (OBS %s, WebSocket %s)", version.obs_version, version.obs_web_socket_version)

    def disconnect(self):
        """OBS WebSocketから切断する"""
        if self._client:
            self._client.base_client.ws.close()
            self._client = None
            logger.info("OBSから切断しました")

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
            logger.warning("既に配信中です")
            return
        self._client.start_stream()
        logger.info("配信を開始しました")

    def stop_stream(self):
        """配信を停止する"""
        status = self.get_stream_status()
        if not status["active"]:
            logger.warning("配信していません")
            return
        self._client.stop_stream()
        logger.info("配信を停止しました")

    def get_scenes(self):
        """シーン一覧を取得する"""
        result = self._client.get_scene_list()
        return {
            "current": result.current_program_scene_name,
            "scenes": [s["sceneName"] for s in result.scenes],
        }

    def get_scene_items(self, scene_name):
        """シーンのソース一覧を取得する"""
        result = self._client.get_scene_item_list(scene_name)
        return [
            {
                "name": item["sourceName"],
                "kind": item["inputKind"] or "group",
                "enabled": item["sceneItemEnabled"],
            }
            for item in result.scene_items
        ]

    def create_scene(self, name):
        """シーンを作成する"""
        self._client.create_scene(name)
        logger.info("シーンを作成しました: %s", name)

    def set_scene(self, name):
        """シーンを切り替える"""
        self._client.set_current_program_scene(name)
        logger.info("シーンを切り替えました: %s", name)

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
        logger.info("画像ソースを追加しました: %s", source_name)

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
        logger.info("ゲームキャプチャを追加しました: %s", source_name)

    def add_window_capture(self, scene_name, source_name, window="", cursor=True,
                           window_match=None):
        """ウィンドウキャプチャソースを追加する

        Args:
            window_match: ウィンドウタイトルに含まれるべきキーワードのリスト（すべて一致で選択）
        """
        settings = {"cursor": cursor}
        if window:
            settings["window"] = window
        self._client.create_input(
            sceneName=scene_name,
            inputName=source_name,
            inputKind="window_capture",
            inputSettings=settings,
            sceneItemEnabled=True,
        )
        # window_matchが指定されていてwindowが未指定の場合、利用可能なウィンドウから検索
        if window_match and not window:
            matched = self._find_matching_window(source_name, window_match)
            if matched:
                self._client.set_input_settings(source_name, {"window": matched}, overlay=True)
                logger.info("ウィンドウを自動選択しました: %s → %s", source_name, matched)
            else:
                logger.warning("一致するウィンドウが見つかりません: %s (キーワード: %s)",
                               source_name, window_match)
                return
        logger.info("ウィンドウキャプチャを追加しました: %s", source_name)

    def _find_matching_window(self, input_name, keywords):
        """入力ソースの利用可能なウィンドウ一覧からキーワードに一致するものを探す"""
        try:
            response = self._client.send("GetInputPropertiesListPropertyItems", {
                "inputName": input_name,
                "propertyName": "window",
            }, raw=True)
            items = response.get("propertyItems", [])
            for item in items:
                value = item.get("itemValue", "")
                title_lower = value.lower()
                if all(kw.lower() in title_lower for kw in keywords):
                    return value
        except Exception as e:
            logger.warning("ウィンドウ一覧の取得に失敗: %s", e)
        return None

    def add_browser_source(self, scene_name, source_name, url, width=1920, height=1080):
        """ブラウザソースを追加する"""
        import time
        sep = "&" if "?" in url else "?"
        cache_bust_url = f"{url}{sep}_v={int(time.time())}"
        self._client.create_input(
            sceneName=scene_name,
            inputName=source_name,
            inputKind="browser_source",
            inputSettings={
                "url": cache_bust_url,
                "width": width,
                "height": height,
                "reroute_audio": False,
            },
            sceneItemEnabled=True,
        )
        logger.info("ブラウザソースを追加しました: %s", source_name)

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
        logger.info("テキストソースを追加しました: %s", source_name)

    def get_source_transform(self, scene_name, source_name):
        """ソースの位置・サイズを取得する"""
        item_id = self._client.get_scene_item_id(scene_name, source_name).scene_item_id
        response = self._client.send("GetSceneItemTransform", {
            "sceneName": scene_name,
            "sceneItemId": item_id,
        }, raw=True)
        return response["sceneItemTransform"]

    def set_source_transform(self, scene_name, source_name, transform):
        """ソースの位置・サイズを設定する"""
        item_id = self._client.get_scene_item_id(scene_name, source_name).scene_item_id
        self._client.set_scene_item_transform(scene_name, item_id, transform)

    def remove_scene(self, name):
        """シーンを削除する"""
        self._client.remove_scene(name)
        logger.info("シーンを削除しました: %s", name)

    def remove_input(self, input_name):
        """入力ソースを削除する"""
        self._client.remove_input(input_name)
        logger.info("ソースを削除しました: %s", input_name)

    def _enable_input(self, input_name, enabled):
        """全シーンで指定入力の表示を切り替える"""
        scenes = self.get_scenes()["scenes"]
        for scene_name in scenes:
            try:
                item_id = self._client.get_scene_item_id(scene_name, input_name).scene_item_id
                self._client.set_scene_item_enabled(scene_name, item_id, enabled)
            except Exception:
                pass

    def mute_all_audio(self):
        """全音声入力をミュートする（デスクトップ音声・マイク等）"""
        try:
            response = self._client.get_input_list()
            for inp in response.inputs:
                kind = inp.get("inputKind", "")
                name = inp.get("inputName", "")
                if "audio" in kind or "monitor" in kind or "wasapi" in kind or "pulse" in kind:
                    try:
                        self._client.set_input_mute(name, True)
                        logger.info("音声をミュートしました: %s", name)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("音声ミュート処理に失敗: %s", e)

    def setup_scenes(self, scenes_config, main_scene=None):
        """シーン構成を一括作成する（既存のATC シーン・ソースは先に削除）"""
        self.teardown_scenes(scenes_config)
        for scene in scenes_config:
            scene_name = scene["name"]
            try:
                self.create_scene(scene_name)
            except Exception:
                logger.debug("シーン '%s' は既に存在します", scene_name)

            for source in scene["sources"]:
                try:
                    self._add_source(scene_name, source)
                    if "transform" in source:
                        self.set_source_transform(scene_name, source["name"], source["transform"])
                except Exception as e:
                    logger.warning("ソース '%s' の追加に失敗: %s", source['name'], e)

        # メインシーンにフォーカス
        if main_scene:
            self.set_scene(main_scene)
        elif scenes_config:
            self.set_scene(scenes_config[0]["name"])

        logger.info("セットアップ完了 (%dシーン)", len(scenes_config))

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

        logger.info("ティアダウン完了")

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
        elif kind == "window_capture":
            self.add_window_capture(
                scene_name, name,
                window=source.get("window", ""),
                cursor=source.get("cursor", True),
                window_match=source.get("window_match"),
            )
        elif kind == "browser":
            self.add_browser_source(
                scene_name, name,
                url=source.get("url", ""),
                width=source.get("width", 1920),
                height=source.get("height", 1080),
            )
        else:
            logger.warning("不明なソース種類: %s", kind)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
