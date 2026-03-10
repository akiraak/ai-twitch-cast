"""リップシンク用WAV振幅解析"""

import array
import math
import wave


def analyze_amplitude(wav_path, fps=30):
    """WAVファイルの振幅エンベロープを解析する（フレーム単位）

    Args:
        wav_path: WAVファイルパス
        fps: 解析フレームレート（idle loopに合わせる）

    Returns:
        list[float]: 各フレームの口の開き具合 (0.0〜1.0)
    """
    with wave.open(str(wav_path), "rb") as wf:
        n_frames = wf.getnframes()
        framerate = wf.getframerate()
        raw = wf.readframes(n_frames)

    samples = array.array("h", raw)  # 16-bit signed
    samples_per_frame = framerate // fps

    amplitudes = []
    for i in range(0, len(samples), samples_per_frame):
        chunk = samples[i:i + samples_per_frame]
        if not chunk:
            break
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
        amplitudes.append(rms)

    max_amp = max(amplitudes) if amplitudes else 1.0
    if max_amp > 0:
        amplitudes = [min(a / max_amp, 1.0) for a in amplitudes]

    return amplitudes
