"""lipsync.analyze_amplitude のテスト"""

import array
import math
import tempfile
import wave
from pathlib import Path

from src.lipsync import analyze_amplitude


def _make_wav(samples, framerate=24000):
    """テスト用WAVファイルを作成する"""
    path = Path(tempfile.mkdtemp()) / "test.wav"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(array.array("h", samples).tobytes())
    return path


class TestAnalyzeAmplitude:
    def test_silent_audio(self):
        """無音WAVは全フレーム0.0"""
        samples = [0] * 24000  # 1秒
        path = _make_wav(samples)
        result = analyze_amplitude(path)
        assert all(v == 0.0 for v in result)

    def test_constant_amplitude(self):
        """一定振幅は全フレーム1.0"""
        samples = [10000] * 24000
        path = _make_wav(samples)
        result = analyze_amplitude(path)
        assert all(v == 1.0 for v in result)

    def test_frame_count(self):
        """フレーム数 = サンプル数 / (framerate / fps)"""
        samples = [100] * 24000  # 1秒 @ 24kHz
        path = _make_wav(samples)
        result = analyze_amplitude(path, fps=30)
        assert len(result) == 30

    def test_values_normalized_0_to_1(self):
        """全値が0.0〜1.0の範囲"""
        # 振幅が変化するデータ
        samples = []
        for i in range(24000):
            samples.append(int(math.sin(i * 0.1) * 20000))
        path = _make_wav(samples)
        result = analyze_amplitude(path)
        assert all(0.0 <= v <= 1.0 for v in result)
        assert max(result) == 1.0  # 最大値は1.0に正規化

    def test_varying_amplitude(self):
        """前半無音・後半有音で差が出る"""
        silent = [0] * 12000
        loud = [20000] * 12000
        path = _make_wav(silent + loud)
        result = analyze_amplitude(path, fps=30)
        first_half = result[:15]
        second_half = result[15:]
        assert max(first_half) < 0.01  # 前半はほぼ無音
        assert max(second_half) == 1.0  # 後半は最大
