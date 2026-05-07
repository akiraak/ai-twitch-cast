"""音声ユーティリティ - 末尾無音トリミング等"""

import array
import logging
import wave

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD_RATIO = 0.01
DEFAULT_KEEP_MS = 80
DEFAULT_LEADING_KEEP_MS = 120  # 先頭は突然始まると違和感が出やすいので末尾より長めに残す


def trim_trailing_silence_pcm(
    pcm_bytes,
    sample_rate=24000,
    sample_width=2,
    threshold_ratio=DEFAULT_THRESHOLD_RATIO,
    keep_ms=DEFAULT_KEEP_MS,
):
    """16bit signed PCM（モノラル）の末尾無音をトリミングする

    Args:
        pcm_bytes: 16bit signed little-endian PCMバイト列
        sample_rate: サンプリング周波数 (Hz)
        sample_width: サンプル幅（バイト）。16bit (=2) のみ対応
        threshold_ratio: 無音判定のフルスケール比。0.01 ≒ -40 dBFS
        keep_ms: 末尾に残す余裕（ms）。突然切ってプチノイズ感が出るのを防ぐ

    Returns:
        トリミング後のPCMバイト列。サンプル幅が想定外、全部無音、トリミング不要の場合は元のまま返す
    """
    if sample_width != 2:
        return pcm_bytes
    samples = array.array("h")
    try:
        samples.frombytes(pcm_bytes)
    except ValueError:
        return pcm_bytes
    n = len(samples)
    if n == 0:
        return pcm_bytes

    threshold = int(32767 * threshold_ratio)
    last_voiced = -1
    for i in range(n - 1, -1, -1):
        s = samples[i]
        if s > threshold or s < -threshold:
            last_voiced = i
            break
    if last_voiced < 0:
        return pcm_bytes

    keep_samples = int(sample_rate * keep_ms / 1000)
    cut_idx = min(n, last_voiced + 1 + keep_samples)
    if cut_idx >= n:
        return pcm_bytes
    return samples[:cut_idx].tobytes()


def trim_leading_silence_pcm(
    pcm_bytes,
    sample_rate=24000,
    sample_width=2,
    threshold_ratio=DEFAULT_THRESHOLD_RATIO,
    keep_ms=DEFAULT_LEADING_KEEP_MS,
):
    """16bit signed PCM（モノラル）の先頭無音をトリミングする

    Args:
        pcm_bytes: 16bit signed little-endian PCMバイト列
        sample_rate: サンプリング周波数 (Hz)
        sample_width: サンプル幅（バイト）。16bit (=2) のみ対応
        threshold_ratio: 無音判定のフルスケール比。0.01 ≒ -40 dBFS
        keep_ms: 先頭に残す余裕（ms）。突然始まる違和感を避けるため

    Returns:
        トリミング後のPCMバイト列。サンプル幅が想定外、全部無音、トリミング不要の場合は元のまま返す
    """
    if sample_width != 2:
        return pcm_bytes
    samples = array.array("h")
    try:
        samples.frombytes(pcm_bytes)
    except ValueError:
        return pcm_bytes
    n = len(samples)
    if n == 0:
        return pcm_bytes

    threshold = int(32767 * threshold_ratio)
    first_voiced = -1
    for i in range(n):
        s = samples[i]
        if s > threshold or s < -threshold:
            first_voiced = i
            break
    if first_voiced < 0:
        return pcm_bytes

    keep_samples = int(sample_rate * keep_ms / 1000)
    cut_idx = max(0, first_voiced - keep_samples)
    if cut_idx <= 0:
        return pcm_bytes
    return samples[cut_idx:].tobytes()


def trim_wav_file(
    path,
    threshold_ratio=DEFAULT_THRESHOLD_RATIO,
    keep_ms=DEFAULT_KEEP_MS,
    leading_keep_ms=DEFAULT_LEADING_KEEP_MS,
    trim_leading=True,
):
    """既存のwavファイルの先頭・末尾の無音をトリミングして上書き保存する

    Args:
        path: wavファイルパス
        threshold_ratio: 無音判定のフルスケール比
        keep_ms: 末尾に残す余裕 (ms)
        leading_keep_ms: 先頭に残す余裕 (ms)
        trim_leading: True なら先頭トリミングも行う

    Returns:
        (trimmed_ms, original_ms) のタプル。先頭・末尾の合計削減量。トリミングしなかった場合は (0, original_ms)
    """
    path = str(path)
    with wave.open(path, "rb") as wf:
        n_ch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        nframes = wf.getnframes()
        data = wf.readframes(nframes)

    if n_ch != 1 or sw != 2:
        logger.debug("[audio] skip trim (unsupported format): %s ch=%d sw=%d", path, n_ch, sw)
        return 0, int(nframes / sr * 1000) if sr else 0

    new_data = data
    if trim_leading:
        new_data = trim_leading_silence_pcm(
            new_data, sample_rate=sr, sample_width=sw,
            threshold_ratio=threshold_ratio, keep_ms=leading_keep_ms,
        )
    new_data = trim_trailing_silence_pcm(
        new_data, sample_rate=sr, sample_width=sw,
        threshold_ratio=threshold_ratio, keep_ms=keep_ms,
    )

    original_ms = int(nframes / sr * 1000)
    if len(new_data) == len(data):
        return 0, original_ms

    new_nframes = len(new_data) // sw
    with wave.open(path, "wb") as wf:
        wf.setnchannels(n_ch)
        wf.setsampwidth(sw)
        wf.setframerate(sr)
        wf.writeframes(new_data)
    trimmed_ms = int((nframes - new_nframes) / sr * 1000)
    return trimmed_ms, original_ms
