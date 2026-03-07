"""VSeeFace VMC Protocol (OSC) 制御モジュール"""

import asyncio
import math
import os
import random
import time

from pythonosc import udp_client

from src.wsl_path import resolve_host


class VSFController:
    """VSeeFace を VMC Protocol (OSC) で制御するクラス"""

    def __init__(self, host=None, port=None):
        self.host = resolve_host(host or os.environ.get("VSF_OSC_HOST", "127.0.0.1"))
        self.port = int(port or os.environ.get("VSF_OSC_PORT", "39539"))
        self._client = None
        self._idle_task = None

    def connect(self):
        """OSCクライアントを作成する"""
        self._client = udp_client.SimpleUDPClient(self.host, self.port)
        print(f"VSeeFaceに接続しました ({self.host}:{self.port})")

    def disconnect(self):
        """OSCクライアントを破棄する"""
        self._client = None
        print("VSeeFaceから切断しました")

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

    async def _idle_loop(self, scale):
        """待機モーションのメインループ

        Args:
            scale: 動きの大きさの倍率 (1.0が標準)
        """
        s = scale
        t0 = time.time()
        next_blink = t0 + random.uniform(2.0, 5.0)

        try:
            while True:
                t = time.time() - t0

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

                # --- まばたき: ランダム間隔 ---
                now = time.time()
                if now >= next_blink:
                    self.set_blendshape("Blink", 1.0)
                    await asyncio.sleep(0.08)
                    self.set_blendshape("Blink", 0.0)
                    next_blink = now + random.uniform(2.0, 6.0)

                await asyncio.sleep(1 / 30)  # 30fps
        except asyncio.CancelledError:
            pass

    def start_idle(self, scale=1.0):
        """待機モーションを開始する

        Args:
            scale: 動きの大きさの倍率 (1.0が標準、2.0で2倍、0.5で半分)
        """
        self.stop_idle()
        self._idle_task = asyncio.ensure_future(self._idle_loop(scale))

    def stop_idle(self):
        """待機モーションを停止する"""
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
            self._idle_task = None

    @property
    def is_idle_running(self):
        return self._idle_task is not None and not self._idle_task.done()
