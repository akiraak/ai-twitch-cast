"""src/audio_utils.py のテスト"""

import array
import math
import wave

import pytest

from src.audio_utils import (
    trim_leading_silence_pcm,
    trim_trailing_silence_pcm,
    trim_wav_file,
)


SR = 24000


def _sine_pcm(duration_sec: float, freq: float = 440.0, amp: float = 0.3) -> bytes:
    """正弦波の16bit signed PCMを生成"""
    n = int(SR * duration_sec)
    samples = array.array("h")
    for i in range(n):
        v = int(amp * 32767 * math.sin(2 * math.pi * freq * i / SR))
        samples.append(v)
    return samples.tobytes()


def _silence_pcm(duration_sec: float) -> bytes:
    n = int(SR * duration_sec)
    samples = array.array("h", [0] * n)
    return samples.tobytes()


def _pcm_duration_ms(pcm: bytes, sample_width: int = 2, sr: int = SR) -> float:
    return len(pcm) / sample_width / sr * 1000


class TestTrimPcm:
    def test_trims_trailing_silence(self):
        voiced = _sine_pcm(1.0)
        trailing = _silence_pcm(0.5)
        pcm = voiced + trailing
        before_ms = _pcm_duration_ms(pcm)
        after = trim_trailing_silence_pcm(pcm, sample_rate=SR, keep_ms=80)
        after_ms = _pcm_duration_ms(after)
        # 元 1500ms → voiced 1000ms + keep 80ms 程度（許容±30ms）
        assert before_ms == pytest.approx(1500, abs=1)
        assert after_ms == pytest.approx(1080, abs=30)

    def test_keeps_short_silence(self):
        voiced = _sine_pcm(1.0)
        trailing = _silence_pcm(0.05)  # 50ms < keep_ms (80ms)
        pcm = voiced + trailing
        before_ms = _pcm_duration_ms(pcm)
        after = trim_trailing_silence_pcm(pcm, sample_rate=SR, keep_ms=80)
        # 余裕に収まる無音はトリミングされない
        assert len(after) == len(pcm)
        assert _pcm_duration_ms(after) == pytest.approx(before_ms, abs=1)

    def test_all_silence_returns_unchanged(self):
        pcm = _silence_pcm(1.0)
        after = trim_trailing_silence_pcm(pcm, sample_rate=SR)
        # 全部無音だと何もしない（トリミング対象なしのフォールバック）
        assert len(after) == len(pcm)

    def test_empty_input(self):
        assert trim_trailing_silence_pcm(b"", sample_rate=SR) == b""

    def test_unsupported_sample_width_passthrough(self):
        pcm = b"\x00\x00\x00\x00" * 100
        # sample_width=4 は非対応 → そのまま返す
        assert trim_trailing_silence_pcm(pcm, sample_rate=SR, sample_width=4) == pcm

    def test_no_trailing_silence(self):
        pcm = _sine_pcm(0.5)
        after = trim_trailing_silence_pcm(pcm, sample_rate=SR, keep_ms=80)
        # 末尾に無音がほぼない場合は変化しない
        assert len(after) == len(pcm)

    def test_keep_ms_zero(self):
        voiced = _sine_pcm(1.0)
        trailing = _silence_pcm(0.5)
        pcm = voiced + trailing
        after = trim_trailing_silence_pcm(pcm, sample_rate=SR, keep_ms=0)
        # keep_ms=0 だと voiced 終わりピッタリで切れる
        assert _pcm_duration_ms(after) == pytest.approx(1000, abs=10)


class TestTrimLeadingPcm:
    def test_trims_leading_silence(self):
        leading = _silence_pcm(0.5)
        voiced = _sine_pcm(1.0)
        pcm = leading + voiced
        before_ms = _pcm_duration_ms(pcm)
        after = trim_leading_silence_pcm(pcm, sample_rate=SR, keep_ms=120)
        after_ms = _pcm_duration_ms(after)
        # 元 1500ms → 1000ms voiced + keep 120ms 程度（許容±30ms）
        assert before_ms == pytest.approx(1500, abs=1)
        assert after_ms == pytest.approx(1120, abs=30)

    def test_keeps_short_leading(self):
        leading = _silence_pcm(0.05)  # 50ms < keep_ms (120ms)
        voiced = _sine_pcm(1.0)
        pcm = leading + voiced
        after = trim_leading_silence_pcm(pcm, sample_rate=SR, keep_ms=120)
        # 余裕に収まる無音はトリミングされない
        assert len(after) == len(pcm)

    def test_all_silence_returns_unchanged(self):
        pcm = _silence_pcm(1.0)
        after = trim_leading_silence_pcm(pcm, sample_rate=SR)
        assert len(after) == len(pcm)

    def test_empty_input(self):
        assert trim_leading_silence_pcm(b"", sample_rate=SR) == b""

    def test_unsupported_sample_width_passthrough(self):
        pcm = b"\x00\x00\x00\x00" * 100
        assert trim_leading_silence_pcm(pcm, sample_rate=SR, sample_width=4) == pcm

    def test_no_leading_silence(self):
        pcm = _sine_pcm(0.5)
        after = trim_leading_silence_pcm(pcm, sample_rate=SR, keep_ms=120)
        assert len(after) == len(pcm)

    def test_leading_keep_ms_zero(self):
        leading = _silence_pcm(0.5)
        voiced = _sine_pcm(1.0)
        pcm = leading + voiced
        after = trim_leading_silence_pcm(pcm, sample_rate=SR, keep_ms=0)
        # keep_ms=0 だと voiced 開始ピッタリで切れる
        assert _pcm_duration_ms(after) == pytest.approx(1000, abs=10)


class TestTrimWavFile:
    def _write_wav(self, path, pcm: bytes, sr: int = SR, n_ch: int = 1, sw: int = 2):
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(n_ch)
            wf.setsampwidth(sw)
            wf.setframerate(sr)
            wf.writeframes(pcm)

    def test_trims_existing_wav_trailing_only(self, tmp_path):
        path = tmp_path / "in.wav"
        pcm = _sine_pcm(1.0) + _silence_pcm(0.5)
        self._write_wav(path, pcm)

        trimmed_ms, original_ms = trim_wav_file(path, keep_ms=80, trim_leading=False)
        assert original_ms == pytest.approx(1500, abs=2)
        # 約 0.5s 弱削減（keep_ms=80 だけ残るので ~420ms 削減）
        assert 350 < trimmed_ms < 480

        with wave.open(str(path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == SR
            new_ms = wf.getnframes() / wf.getframerate() * 1000
        assert new_ms == pytest.approx(original_ms - trimmed_ms, abs=2)

    def test_trims_existing_wav_both_ends(self, tmp_path):
        path = tmp_path / "in.wav"
        # 先頭500ms無音 + 1000ms voiced + 末尾500ms無音 = 2000ms
        pcm = _silence_pcm(0.5) + _sine_pcm(1.0) + _silence_pcm(0.5)
        self._write_wav(path, pcm)

        trimmed_ms, original_ms = trim_wav_file(
            path, keep_ms=80, leading_keep_ms=120, trim_leading=True,
        )
        assert original_ms == pytest.approx(2000, abs=2)
        # 先頭: 500-120=380ms / 末尾: 500-80=420ms 削減 → 計 ~800ms
        assert 720 < trimmed_ms < 850

        with wave.open(str(path), "rb") as wf:
            new_ms = wf.getnframes() / wf.getframerate() * 1000
        # 残るのは voiced(1000ms) + leading_keep(120ms) + trailing_keep(80ms) ≒ 1200ms
        assert new_ms == pytest.approx(1200, abs=30)

    def test_skips_unsupported_format(self, tmp_path):
        path = tmp_path / "stereo.wav"
        pcm = b"\x00\x00\x00\x00" * 24000  # ステレオ16bitの無音1秒相当
        self._write_wav(path, pcm, n_ch=2, sw=2)
        before_size = path.stat().st_size

        trimmed_ms, original_ms = trim_wav_file(path)
        # 非対応フォーマットは触らない
        assert trimmed_ms == 0
        assert path.stat().st_size == before_size

    def test_no_change_when_no_trailing(self, tmp_path):
        path = tmp_path / "in.wav"
        pcm = _sine_pcm(1.0)
        self._write_wav(path, pcm)
        before_size = path.stat().st_size

        trimmed_ms, _ = trim_wav_file(path, keep_ms=80)
        assert trimmed_ms == 0
        assert path.stat().st_size == before_size
