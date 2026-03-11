"""ストリームコントローラー - xvfb + Chromium + PulseAudio + FFmpeg によるOBS不要配信"""

import asyncio
import logging
import os
import signal
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent


class StreamController:
    """OBSを使わずにxvfb + Chromium + PulseAudio + FFmpegで配信する"""

    def __init__(self):
        self._xvfb_proc: subprocess.Popen | None = None
        self._browser_proc: subprocess.Popen | None = None
        self._ffmpeg_proc: subprocess.Popen | None = None
        self._pulse_module_id: int | None = None

        self._display = os.environ.get("BROADCAST_DISPLAY", ":99")
        self._resolution = os.environ.get("BROADCAST_RESOLUTION", "1920x1080")
        self._framerate = int(os.environ.get("BROADCAST_FRAMERATE", "30"))
        self._video_bitrate = os.environ.get("BROADCAST_VIDEO_BITRATE", "3500k")
        self._audio_bitrate = os.environ.get("BROADCAST_AUDIO_BITRATE", "128k")
        self._preset = os.environ.get("BROADCAST_PRESET", "veryfast")
        self._pulse_sink = "broadcast"
        # WSLg PulseAudioサーバー対応
        self._pulse_server = os.environ.get("PULSE_SERVER", "")
        if not self._pulse_server and Path("/mnt/wslg/PulseServer").exists():
            self._pulse_server = "/mnt/wslg/PulseServer"

        self._streaming = False
        self._stream_start_time: float | None = None
        self._setup_done = False

        # broadcast_to_broadcast関数（state.pyから注入）
        self._broadcast_fn = None

    @property
    def is_setup(self) -> bool:
        return self._setup_done

    @property
    def is_streaming(self) -> bool:
        return self._streaming and self._ffmpeg_proc is not None and self._ffmpeg_proc.poll() is None

    def set_broadcast_fn(self, fn):
        """WebSocketブロードキャスト関数を設定（state.pyから呼ぶ）"""
        self._broadcast_fn = fn

    async def setup(self):
        """xvfb + PulseAudio sink + Chromium を起動"""
        if self._setup_done:
            logger.info("既にセットアップ済み")
            return

        logger.info("ストリームセットアップ開始")

        # 1. xvfb起動
        await self._start_xvfb()

        # 2. PulseAudio仮想シンク作成
        await self._setup_pulse_sink()

        # 3. Chromium起動
        await self._start_browser()

        self._setup_done = True
        logger.info("ストリームセットアップ完了")

    async def teardown(self):
        """全プロセスを停止"""
        logger.info("ストリームティアダウン開始")

        if self._streaming:
            await self.stop_stream()

        self._stop_process("browser", self._browser_proc)
        self._browser_proc = None

        await self._cleanup_pulse_sink()

        self._stop_process("xvfb", self._xvfb_proc)
        self._xvfb_proc = None

        self._setup_done = False
        logger.info("ストリームティアダウン完了")

    async def start_stream(self):
        """FFmpegでRTMP配信を開始"""
        if not self._setup_done:
            raise RuntimeError("先にsetup()を呼んでください")
        if self._streaming:
            logger.warning("既に配信中")
            return

        stream_key = os.environ.get("TWITCH_STREAM_KEY", "")
        if not stream_key:
            raise ValueError("TWITCH_STREAM_KEY が .env に設定されていません。Twitchダッシュボードからストリームキーを取得して .env に追加してください")

        rtmp_url = f"rtmp://live-tyo.twitch.tv/app/{stream_key}"
        width, height = self._resolution.split("x")

        cmd = [
            "ffmpeg",
            "-f", "x11grab",
            "-video_size", self._resolution,
            "-framerate", str(self._framerate),
            "-draw_mouse", "0",
            "-i", self._display,
            "-f", "pulse",
            "-i", f"{self._pulse_sink}.monitor",
            "-c:v", "libx264",
            "-preset", self._preset,
            "-tune", "zerolatency",
            "-b:v", self._video_bitrate,
            "-maxrate", self._video_bitrate,
            "-bufsize", str(int(self._video_bitrate.replace("k", "")) * 2) + "k",
            "-pix_fmt", "yuv420p",
            "-g", str(self._framerate * 2),
            "-c:a", "aac",
            "-b:a", self._audio_bitrate,
            "-ar", "44100",
            "-f", "flv",
            rtmp_url,
        ]

        env = os.environ.copy()
        env["DISPLAY"] = self._display
        if self._pulse_server:
            env["PULSE_SERVER"] = self._pulse_server

        logger.info("FFmpeg RTMP配信開始")
        self._ffmpeg_proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._streaming = True
        self._stream_start_time = time.time()
        logger.info("RTMP配信開始 (PID: %d)", self._ffmpeg_proc.pid)

    async def stop_stream(self):
        """FFmpegを停止して配信を終了"""
        if not self._streaming:
            return

        self._stop_process("ffmpeg", self._ffmpeg_proc)
        self._ffmpeg_proc = None
        self._streaming = False
        self._stream_start_time = None
        logger.info("RTMP配信停止")

    async def set_scene(self, name: str):
        """broadcast.htmlにシーン切替コマンドを送信"""
        if self._broadcast_fn:
            await self._broadcast_fn({"type": "scene", "name": name})
        logger.info("シーン切替: %s", name)

    async def set_volume(self, source: str, volume: float):
        """broadcast.htmlに音量変更コマンドを送信"""
        if self._broadcast_fn:
            await self._broadcast_fn({"type": "volume", "source": source, "volume": volume})
        logger.info("音量変更: %s = %.2f", source, volume)

    def get_stream_status(self) -> dict:
        """配信状態を返す"""
        status = {
            "setup": self._setup_done,
            "streaming": self.is_streaming,
            "xvfb_running": self._xvfb_proc is not None and self._xvfb_proc.poll() is None,
            "browser_running": self._browser_proc is not None and self._browser_proc.poll() is None,
            "ffmpeg_running": self._ffmpeg_proc is not None and self._ffmpeg_proc.poll() is None,
            "display": self._display,
            "resolution": self._resolution,
            "framerate": self._framerate,
        }
        if self._stream_start_time:
            status["uptime_seconds"] = int(time.time() - self._stream_start_time)
        return status

    # === 内部メソッド ===

    def _cleanup_stale_xvfb(self):
        """前回のサーバー再起動で残ったXvfbプロセスとロックファイルを掃除"""
        import glob
        display_num = self._display.lstrip(":")
        lock_file = f"/tmp/.X{display_num}-lock"
        socket_file = f"/tmp/.X11-unix/X{display_num}"

        # 古いXvfbプロセスをkill
        try:
            result = subprocess.run(
                ["pkill", "-f", f"Xvfb {self._display}"],
                capture_output=True, timeout=3,
            )
        except Exception:
            pass

        # ロックファイル削除
        for f in [lock_file, socket_file]:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.warning("ロックファイル削除失敗 %s: %s", f, e)

    async def _start_xvfb(self):
        """Xvfb仮想ディスプレイを起動"""
        # 既存プロセスがあれば停止
        self._stop_process("xvfb", self._xvfb_proc)
        self._cleanup_stale_xvfb()

        cmd = [
            "Xvfb", self._display,
            "-screen", "0", f"{self._resolution}x24",
            "-nolisten", "tcp",
            "-ac",
        ]
        logger.info("Xvfb起動: %s", " ".join(cmd))
        self._xvfb_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        # 起動待ち
        await asyncio.sleep(0.5)
        if self._xvfb_proc.poll() is not None:
            stderr = self._xvfb_proc.stderr.read().decode() if self._xvfb_proc.stderr else ""
            raise RuntimeError(f"Xvfb起動失敗: {stderr}")
        logger.info("Xvfb起動完了 (PID: %d, DISPLAY: %s)", self._xvfb_proc.pid, self._display)

    def _pactl_env(self) -> dict:
        """pactl用の環境変数を返す"""
        env = os.environ.copy()
        if self._pulse_server:
            env["PULSE_SERVER"] = self._pulse_server
        return env

    async def _setup_pulse_sink(self):
        """PulseAudio仮想シンクを作成"""
        # 既存シンクがあれば削除
        await self._cleanup_pulse_sink()

        try:
            result = subprocess.run(
                ["pactl", "load-module", "module-null-sink",
                 f"sink_name={self._pulse_sink}",
                 f"sink_properties=device.description=BroadcastSink"],
                capture_output=True, text=True, timeout=5,
                env=self._pactl_env(),
            )
            if result.returncode == 0:
                self._pulse_module_id = int(result.stdout.strip())
                logger.info("PulseAudioシンク作成: %s (module: %d)", self._pulse_sink, self._pulse_module_id)
            else:
                logger.warning("PulseAudioシンク作成失敗: %s", result.stderr)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("PulseAudio操作失敗: %s", e)

    async def _cleanup_pulse_sink(self):
        """PulseAudioシンクを削除"""
        if self._pulse_module_id is not None:
            try:
                subprocess.run(
                    ["pactl", "unload-module", str(self._pulse_module_id)],
                    capture_output=True, timeout=5,
                    env=self._pactl_env(),
                )
                logger.info("PulseAudioシンク削除: module %d", self._pulse_module_id)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            self._pulse_module_id = None

    async def _start_browser(self):
        """ヘッドレスChromiumを起動してbroadcast.htmlを表示"""
        self._stop_process("browser", self._browser_proc)
        # 前回の残存Chromiumプロセスをkill
        try:
            subprocess.run(["pkill", "-f", "chromium.*broadcast"], capture_output=True, timeout=3)
        except Exception:
            pass

        web_port = os.environ.get("WEB_PORT", "8080")
        broadcast_url = f"http://localhost:{web_port}/broadcast"
        width, height = self._resolution.split("x")

        cmd = [
            "chromium-browser",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-software-rasterizer",
            f"--window-size={width},{height}",
            "--start-fullscreen",
            "--kiosk",
            "--autoplay-policy=no-user-gesture-required",
            "--disable-features=AudioServiceOutOfProcess",
            "--no-first-run",
            "--disable-translate",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            broadcast_url,
        ]

        env = os.environ.copy()
        env["DISPLAY"] = self._display
        # PulseAudioのデフォルト出力先をbroadcastシンクに設定
        env["PULSE_SINK"] = self._pulse_sink
        if self._pulse_server:
            env["PULSE_SERVER"] = self._pulse_server

        logger.info("Chromium起動: %s", broadcast_url)
        self._browser_proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        # 起動待ち
        await asyncio.sleep(2)
        if self._browser_proc.poll() is not None:
            stderr = self._browser_proc.stderr.read().decode() if self._browser_proc.stderr else ""
            raise RuntimeError(f"Chromium起動失敗: {stderr}")
        logger.info("Chromium起動完了 (PID: %d)", self._browser_proc.pid)

    def _stop_process(self, name: str, proc: subprocess.Popen | None):
        """プロセスを安全に停止"""
        if proc is None or proc.poll() is not None:
            return
        logger.info("%s停止中 (PID: %d)", name, proc.pid)
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("%s SIGTERM応答なし、SIGKILL送信", name)
                proc.kill()
                proc.wait(timeout=3)
        except Exception as e:
            logger.error("%s停止エラー: %s", name, e)
