"""VSeeFace VMC Protocol (OSC) 制御モジュール"""

import logging
import math
import os
import random
import threading
import time

from pythonosc import udp_client

from src.wsl_path import resolve_host

logger = logging.getLogger(__name__)


class VSFController:
    """VSeeFace を VMC Protocol (OSC) で制御するクラス"""

    def __init__(self, host=None, port=None):
        self.host = resolve_host(host or os.environ.get("VSF_OSC_HOST", "127.0.0.1"))
        self.port = int(port or os.environ.get("VSF_OSC_PORT", "39539"))
        self._client = None
        self._idle_thread = None
        self._idle_stop = threading.Event()
        # リップシンク状態
        self._lipsync_frames = None
        self._lipsync_start = 0.0
        self._lipsync_lock = threading.Lock()

    def connect(self):
        """OSCクライアントを作成する"""
        self._client = udp_client.SimpleUDPClient(self.host, self.port)
        logger.info("VSeeFaceに接続しました (%s:%s)", self.host, self.port)

    def disconnect(self):
        """OSCクライアントを破棄する"""
        self._client = None
        logger.info("VSeeFaceから切断しました")

    def _send_blend_apply(self, shapes):
        """BlendShapeのVal/Applyペアを1回送信する"""
        for name, value in shapes.items():
            self._client.send_message("/VMC/Ext/Blend/Val", [name, float(value)])
        self._client.send_message("/VMC/Ext/Blend/Apply", [])

    def set_blendshape(self, name, value):
        """BlendShapeの値を設定して適用する

        Args:
            name: BlendShape名 (例: "Joy", "A", "Blink")
            value: 0.0〜1.0
        """
        self.set_blendshapes({name: value})

    def set_blendshapes(self, shapes):
        """複数のBlendShapeを一括設定して適用する

        VSeeFaceがUDP受信を確実に反映するよう複数フレーム送信する。

        Args:
            shapes: {名前: 値} の辞書 (例: {"A": 0.8, "Joy": 1.0})
        """
        for _ in range(3):
            self._send_blend_apply(shapes)

    def set_bone(self, bone, px=0.0, py=0.0, pz=0.0, qx=0.0, qy=0.0, qz=0.0, qw=1.0):
        """ボーンの位置・回転を設定する

        Args:
            bone: ボーン名 (例: "Head", "Neck", "Spine")
            px, py, pz: 位置
            qx, qy, qz, qw: 回転（クォータニオン）
        """
        self._client.send_message("/VMC/Ext/Bone/Pos", [
            bone,
            float(px), float(py), float(pz),
            float(qx), float(qy), float(qz), float(qw),
        ])

    def set_root(self, px=0.0, py=0.0, pz=0.0, qx=0.0, qy=0.0, qz=0.0, qw=1.0):
        """ルートの位置・回転を設定する"""
        self._client.send_message("/VMC/Ext/Root/Pos", [
            "root",
            float(px), float(py), float(pz),
            float(qx), float(qy), float(qz), float(qw),
        ])

    @staticmethod
    def _quat(ax, ay, az, angle_deg):
        """軸と角度（度）からクォータニオンを生成する"""
        rad = math.radians(angle_deg) / 2
        s = math.sin(rad)
        return (ax * s, ay * s, az * s, math.cos(rad))

    def apply_default_pose(self):
        """自然な立ちポーズを適用する（T-poseから腕を下ろす）

        VRMのT-poseでは全ボーンの回転がゼロ。
        腕を下ろすにはローカル座標のZ軸（前方軸）で回転させる。
        右腕は正方向、左腕は負方向。
        """
        # 上腕を下ろす（前方Z軸回転で約70度）
        qx, qy, qz, qw = self._quat(0, 0, 1, -70)
        self.set_bone("RightUpperArm", qx=qx, qy=qy, qz=qz, qw=qw)
        qx, qy, qz, qw = self._quat(0, 0, 1, 70)
        self.set_bone("LeftUpperArm", qx=qx, qy=qy, qz=qz, qw=qw)

        # 前腕を少し曲げる
        qx, qy, qz, qw = self._quat(0, 1, 0, 20)
        self.set_bone("RightLowerArm", qx=qx, qy=qy, qz=qz, qw=qw)
        qx, qy, qz, qw = self._quat(0, 1, 0, -20)
        self.set_bone("LeftLowerArm", qx=qx, qy=qy, qz=qz, qw=qw)

    @staticmethod
    def _quat_multiply(a, b):
        """2つのクォータニオン (qx,qy,qz,qw) を合成する"""
        ax, ay, az, aw = a
        bx, by, bz, bw = b
        return (
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        )

    def start_lipsync(self, frames):
        """リップシンクを開始する（振幅フレームデータを設定）"""
        with self._lipsync_lock:
            self._lipsync_frames = frames
            self._lipsync_start = time.time()

    def stop_lipsync(self):
        """リップシンクを停止する"""
        with self._lipsync_lock:
            self._lipsync_frames = None
        self._send_blend_apply({"A": 0.0})

    def _idle_loop(self, scale):
        """待機モーションのメインループ（専用スレッドで実行）

        asyncioイベントループとは独立したスレッドで動作するため、
        サーバーの負荷やイベントループのブロッキングに影響されない。

        Args:
            scale: 動きの大きさの倍率 (1.0が標準)
        """
        s = scale
        t0 = time.time()
        next_blink = t0 + random.uniform(2.0, 5.0)
        blink_end = 0.0
        next_ear_twitch = t0 + random.uniform(3.0, 8.0)
        ear_twitch_end = 0.0
        ear_twitch_start = 0.0
        ear_twitch_duration = 0.2

        frame_interval = 1.0 / 30
        next_frame = time.time()

        while not self._idle_stop.is_set():
            try:
                now = time.time()
                # フレームタイミング調整（一定間隔を維持）
                sleep_time = next_frame - now
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    now = time.time()
                next_frame = now + frame_interval

                t = now - t0

                # --- 呼吸: 胸が前後にゆっくり動く (約4秒周期) ---
                breath = math.sin(t * 1.6) * 0.8 * s
                qx, qy, qz, qw = self._quat(1, 0, 0, breath)
                self.set_bone("Chest", qx=qx, qy=qy, qz=qz, qw=qw)

                # --- 体の揺れ: 背骨が左右にゆったり (約7秒周期) ---
                sway = (math.sin(t * 0.9) * 1.0 + math.sin(t * 0.37) * 0.4) * s
                qx, qy, qz, qw = self._quat(0, 0, 1, sway)
                self.set_bone("Spine", qx=qx, qy=qy, qz=qz, qw=qw)

                # --- 頭の動き: 複数の波を重ねて自然に ---
                head_x = (math.sin(t * 0.7) * 1.2 + math.sin(t * 1.3) * 0.6) * s
                head_z = (math.sin(t * 0.5) * 1.6 + math.sin(t * 1.1) * 0.6) * s
                head_y = math.sin(t * 0.4) * 1.2 * s
                q = self._quat(1, 0, 0, head_x)
                q = self._quat_multiply(q, self._quat(0, 1, 0, head_y))
                q = self._quat_multiply(q, self._quat(0, 0, 1, head_z))
                self.set_bone("Head", qx=q[0], qy=q[1], qz=q[2], qw=q[3])

                # --- 腕の揺れ: デフォルトポーズ(-70/70度)に揺れを加算 ---
                r_arm_sway = math.sin(t * 0.6 + 1.0) * 0.8 * s
                l_arm_sway = math.sin(t * 0.6 + 2.5) * 0.8 * s
                q_r = self._quat(0, 0, 1, -70 + r_arm_sway)
                q_l = self._quat(0, 0, 1, 70 + l_arm_sway)
                self.set_bone("RightUpperArm", qx=q_r[0], qy=q_r[1], qz=q_r[2], qw=q_r[3])
                self.set_bone("LeftUpperArm", qx=q_l[0], qy=q_l[1], qz=q_l[2], qw=q_l[3])

                # --- 前腕の揺れ ---
                r_fore = 20 + math.sin(t * 0.8 + 0.5) * 0.6 * s
                l_fore = -20 + math.sin(t * 0.8 + 2.0) * 0.6 * s
                q_rf = self._quat(0, 1, 0, r_fore)
                q_lf = self._quat(0, 1, 0, l_fore)
                self.set_bone("RightLowerArm", qx=q_rf[0], qy=q_rf[1], qz=q_rf[2], qw=q_rf[3])
                self.set_bone("LeftLowerArm", qx=q_lf[0], qy=q_lf[1], qz=q_lf[2], qw=q_lf[3])

                # --- BlendShapeをフレームごとにまとめて送信 ---
                frame_shapes = {}

                # まばたき: フレームベース（ブロッキングsleep廃止）
                if now >= next_blink and blink_end == 0.0:
                    blink_end = now + 0.08
                if blink_end > 0:
                    if now < blink_end:
                        frame_shapes["Blink"] = 1.0
                    else:
                        frame_shapes["Blink"] = 0.0
                        blink_end = 0.0
                        next_blink = now + random.uniform(2.0, 6.0)

                # 耳ぴくぴく: ランダム間隔で耳を動かす
                if now >= next_ear_twitch and now >= ear_twitch_end:
                    ear_twitch_duration = random.uniform(0.15, 0.3)
                    ear_twitch_end = now + ear_twitch_duration
                    ear_twitch_start = now
                    next_ear_twitch = now + random.uniform(3.0, 10.0)

                if now < ear_twitch_end:
                    progress = (now - ear_twitch_start) / ear_twitch_duration
                    frame_shapes["ear_stand"] = math.sin(progress * math.pi)
                else:
                    frame_shapes["ear_stand"] = 0.0

                # リップシンク: 音声振幅に合わせて口を動かす
                with self._lipsync_lock:
                    ls_frames = self._lipsync_frames
                    ls_start = self._lipsync_start
                if ls_frames is not None:
                    frame_idx = int((now - ls_start) * 30)
                    if 0 <= frame_idx < len(ls_frames):
                        frame_shapes["A"] = ls_frames[frame_idx]
                    else:
                        with self._lipsync_lock:
                            self._lipsync_frames = None
                        frame_shapes["A"] = 0.0

                self._send_blend_apply(frame_shapes)

            except Exception as e:
                logger.warning("idle loop エラー (継続): %s", e)
                time.sleep(0.1)

    def start_idle(self, scale=1.0):
        """待機モーションを開始する

        Args:
            scale: 動きの大きさの倍率 (1.0が標準、2.0で2倍、0.5で半分)
        """
        self.stop_idle()
        self._idle_stop.clear()
        self._idle_thread = threading.Thread(
            target=self._idle_loop, args=(scale,), daemon=True, name="vsf-idle"
        )
        self._idle_thread.start()

    def stop_idle(self):
        """待機モーションを停止する"""
        if self._idle_thread and self._idle_thread.is_alive():
            self._idle_stop.set()
            self._idle_thread.join(timeout=2.0)
            self._idle_thread = None

    @property
    def is_idle_running(self):
        return self._idle_thread is not None and self._idle_thread.is_alive()
