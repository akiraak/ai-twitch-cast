"""初期SE（効果音）ファイルを生成するスクリプト

WAV 16-bit mono 24kHz で resources/audio/se/ に出力する。
"""

import math
import struct
import wave
from pathlib import Path

SE_DIR = Path(__file__).resolve().parent.parent / "resources" / "audio" / "se"
SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit


def _write_wav(filename: str, samples: list[float], duration_hint: float = 0):
    """正規化されたfloatサンプル列をWAVファイルに書き出す"""
    path = SE_DIR / filename
    # クリッピング防止: ピーク正規化
    peak = max(abs(s) for s in samples) if samples else 1.0
    if peak > 0:
        samples = [s / peak * 0.8 for s in samples]

    with wave.open(str(path), "w") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        data = b"".join(
            struct.pack("<h", int(max(-32767, min(32767, s * 32767))))
            for s in samples
        )
        wf.writeframes(data)
    print(f"  {filename}: {len(samples)} samples ({len(samples)/SAMPLE_RATE:.2f}s)")


def _envelope(t: float, attack: float, decay: float, duration: float) -> float:
    """ADSR風エンベロープ（sustain=0）"""
    if t < attack:
        return t / attack
    elif t < attack + decay:
        return 1.0 - (t - attack) / decay
    return 0.0


def _sine(freq: float, t: float) -> float:
    return math.sin(2 * math.pi * freq * t)


def generate_greeting():
    """明るいチャイム — 2音の上昇和音"""
    duration = 0.6
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # C5 → E5 の2音
        env1 = _envelope(t, 0.01, 0.4, duration)
        env2 = _envelope(max(0, t - 0.15), 0.01, 0.35, duration)
        s = _sine(523.25, t) * env1 * 0.5 + _sine(659.25, t) * env2 * 0.5
        samples.append(s)
    _write_wav("greeting.wav", samples)


def generate_surprise():
    """上昇スウィープ音"""
    duration = 0.5
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # 周波数が300Hz → 1200Hzに上昇
        freq = 300 + 900 * (t / duration) ** 0.5
        env = _envelope(t, 0.01, 0.4, duration)
        s = _sine(freq, t) * env
        samples.append(s)
    _write_wav("surprise.wav", samples)


def generate_success():
    """達成音 — 3音の上昇アルペジオ"""
    duration = 0.8
    n = int(SAMPLE_RATE * duration)
    samples = []
    notes = [(0.0, 523.25), (0.2, 659.25), (0.4, 783.99)]  # C5, E5, G5
    for i in range(n):
        t = i / SAMPLE_RATE
        s = 0.0
        for onset, freq in notes:
            dt = t - onset
            if dt >= 0:
                env = _envelope(dt, 0.01, 0.35, duration)
                s += _sine(freq, t) * env * 0.4
        samples.append(s)
    _write_wav("success.wav", samples)


def generate_thinking():
    """柔らかいベル — 低めの単音"""
    duration = 0.7
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _envelope(t, 0.02, 0.6, duration)
        # 基音 + 倍音で柔らかいベル
        s = (_sine(440, t) * 0.6 + _sine(880, t) * 0.2 + _sine(1320, t) * 0.1) * env
        samples.append(s)
    _write_wav("thinking.wav", samples)


def generate_sad():
    """下降音 — ゆっくり周波数が下がる"""
    duration = 0.7
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = 600 - 250 * (t / duration)
        env = _envelope(t, 0.02, 0.6, duration)
        s = _sine(freq, t) * env
        samples.append(s)
    _write_wav("sad.wav", samples)


def generate_excited():
    """ファンファーレ風 — 短い3連音"""
    duration = 0.7
    n = int(SAMPLE_RATE * duration)
    samples = []
    notes = [(0.0, 523.25), (0.12, 659.25), (0.24, 783.99)]  # C5, E5, G5
    for i in range(n):
        t = i / SAMPLE_RATE
        s = 0.0
        for onset, freq in notes:
            dt = t - onset
            if dt >= 0:
                env = _envelope(dt, 0.005, 0.25, duration)
                # 矩形波風（倍音追加）でブラス感
                s += (_sine(freq, t) * 0.5 + _sine(freq * 2, t) * 0.15 + _sine(freq * 3, t) * 0.05) * env * 0.5
        samples.append(s)
    _write_wav("excited.wav", samples)


def main():
    SE_DIR.mkdir(parents=True, exist_ok=True)
    print("SE音源ファイル生成中...")
    generate_greeting()
    generate_surprise()
    generate_success()
    generate_thinking()
    generate_sad()
    generate_excited()
    print(f"完了: {SE_DIR}")


if __name__ == "__main__":
    main()
