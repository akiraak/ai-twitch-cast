"""VSFController のクォータニオン演算テスト"""

import math

from src.vsf_controller import VSFController


class TestQuat:
    def test_zero_rotation(self):
        """0度回転は単位クォータニオン"""
        qx, qy, qz, qw = VSFController._quat(1, 0, 0, 0)
        assert qx == 0.0
        assert qy == 0.0
        assert qz == 0.0
        assert qw == 1.0

    def test_90_degree_x_axis(self):
        """X軸90度回転"""
        qx, qy, qz, qw = VSFController._quat(1, 0, 0, 90)
        assert abs(qx - math.sin(math.radians(45))) < 1e-10
        assert qy == 0.0
        assert qz == 0.0
        assert abs(qw - math.cos(math.radians(45))) < 1e-10

    def test_180_degree(self):
        """180度回転"""
        qx, qy, qz, qw = VSFController._quat(0, 0, 1, 180)
        assert abs(qx) < 1e-10
        assert abs(qy) < 1e-10
        assert abs(qz - 1.0) < 1e-10
        assert abs(qw) < 1e-10

    def test_negative_angle(self):
        """負の角度は逆回転"""
        q_pos = VSFController._quat(1, 0, 0, 30)
        q_neg = VSFController._quat(1, 0, 0, -30)
        assert abs(q_pos[0] + q_neg[0]) < 1e-10  # qxが符号反転
        assert abs(q_pos[3] - q_neg[3]) < 1e-10  # qwは同じ


class TestQuatMultiply:
    def test_identity_multiply(self):
        """単位クォータニオンとの積は元のまま"""
        identity = (0.0, 0.0, 0.0, 1.0)
        q = VSFController._quat(1, 0, 0, 45)
        result = VSFController._quat_multiply(q, identity)
        for a, b in zip(result, q):
            assert abs(a - b) < 1e-10

    def test_inverse_multiply(self):
        """逆回転との積は単位クォータニオン"""
        q = VSFController._quat(0, 1, 0, 60)
        q_inv = (-q[0], -q[1], -q[2], q[3])
        result = VSFController._quat_multiply(q, q_inv)
        assert abs(result[0]) < 1e-10
        assert abs(result[1]) < 1e-10
        assert abs(result[2]) < 1e-10
        assert abs(result[3] - 1.0) < 1e-10

    def test_unit_quaternion_preserved(self):
        """2つの単位クォータニオンの積も単位クォータニオン"""
        q1 = VSFController._quat(1, 0, 0, 30)
        q2 = VSFController._quat(0, 1, 0, 45)
        result = VSFController._quat_multiply(q1, q2)
        norm = math.sqrt(sum(c * c for c in result))
        assert abs(norm - 1.0) < 1e-10
