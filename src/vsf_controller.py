"""VSeeFace VMC Protocol (OSC) 制御モジュール"""

import math
import os

from pythonosc import udp_client

from src.wsl_path import resolve_host


class VSFController:
    """VSeeFace を VMC Protocol (OSC) で制御するクラス"""

    def __init__(self, host=None, port=None):
        self.host = resolve_host(host or os.environ.get("VSF_OSC_HOST", "127.0.0.1"))
        self.port = int(port or os.environ.get("VSF_OSC_PORT", "39539"))
        self._client = None

    def connect(self):
        """OSCクライアントを作成する"""
        self._client = udp_client.SimpleUDPClient(self.host, self.port)
        print(f"VSeeFaceに接続しました ({self.host}:{self.port})")

    def disconnect(self):
        """OSCクライアントを破棄する"""
        self._client = None
        print("VSeeFaceから切断しました")

    def set_blendshape(self, name, value):
        """BlendShapeの値を設定して適用する

        Args:
            name: BlendShape名 (例: "Joy", "A", "Blink")
            value: 0.0〜1.0
        """
        self._client.send_message("/VMC/Ext/Blend/Val", [name, float(value)])
        self._client.send_message("/VMC/Ext/Blend/Apply", [])

    def set_blendshapes(self, shapes):
        """複数のBlendShapeを一括設定して適用する

        Args:
            shapes: {名前: 値} の辞書 (例: {"A": 0.8, "Joy": 1.0})
        """
        for name, value in shapes.items():
            self._client.send_message("/VMC/Ext/Blend/Val", [name, float(value)])
        self._client.send_message("/VMC/Ext/Blend/Apply", [])

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
