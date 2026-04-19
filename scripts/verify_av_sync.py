#!/usr/bin/env python3
"""録画 MP4 の映像 PTS ドリフトを計測する。

av_sync_test.html で録画された MP4 を入力に取り、
1秒ごとの赤フラッシュを検出して、各フラッシュの PTS と期待時刻のズレを出す。

使い方:
    python3 scripts/verify_av_sync.py videos/broadcast_YYYYMMDD_HHmmss.mp4

出力:
    各フラッシュの期待時刻 / 実PTS / ズレ(ms) を表形式で表示し、
    先頭・末尾・最大・平均のサマリを出す。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np


SCALE_W = 320
SCALE_H = 180
FRAME_BYTES = SCALE_W * SCALE_H * 3  # rgb24
FLASH_MIN_RATIO = 0.30  # フレーム内の「赤」ピクセル比がこの閾値超でフラッシュ判定


def require(cmd: str) -> str:
    path = shutil.which(cmd)
    if not path:
        print(f"Error: {cmd} not found in PATH", file=sys.stderr)
        sys.exit(1)
    return path


def get_frame_pts(ffprobe: str, mp4: Path) -> list[float]:
    """全映像フレームの pts_time(秒) を取得する。"""
    out = subprocess.check_output([
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "frame=pts_time",
        "-of", "csv=p=0",
        str(mp4),
    ], text=True)
    times: list[float] = []
    for line in out.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            times.append(float(s))
        except ValueError:
            pass
    return times


def iter_frames(ffmpeg: str, mp4: Path):
    """映像フレームを SCALE_W×SCALE_H の RGB24 配列としてストリーミングで返す。

    `-fps_mode passthrough` で VFR 入力でも源フレームだけを出す（CFR 化による
    重複フレーム埋めを避ける）。これで ffprobe が返す PTS 配列と 1:1 対応する。
    """
    proc = subprocess.Popen([
        ffmpeg, "-v", "error",
        "-i", str(mp4),
        "-vf", f"scale={SCALE_W}:{SCALE_H}",
        "-fps_mode", "passthrough",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-",
    ], stdout=subprocess.PIPE)
    assert proc.stdout is not None
    try:
        while True:
            buf = proc.stdout.read(FRAME_BYTES)
            if len(buf) < FRAME_BYTES:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(SCALE_H, SCALE_W, 3)
            yield frame
    finally:
        proc.stdout.close()
        proc.wait()


def compute_red_ratio(frame: np.ndarray) -> float:
    """『赤』と見なせるピクセルの比率を返す (R>200 かつ G<100 かつ B<100)。"""
    r = frame[:, :, 0]
    g = frame[:, :, 1]
    b = frame[:, :, 2]
    red_mask = (r > 200) & (g < 100) & (b < 100)
    return float(red_mask.mean())


def detect_flash_events(pts: list[float], ratios: list[float]) -> list[tuple[int, float]]:
    """連続する "red" フレーム群を一つのイベントに集約し、中心フレームの PTS を返す。

    戻り値: [(frame_index, center_pts), ...]
    """
    events = []
    in_flash = False
    start_i = 0
    for i, ratio in enumerate(ratios):
        is_flash = ratio >= FLASH_MIN_RATIO
        if is_flash and not in_flash:
            start_i = i
            in_flash = True
        elif not is_flash and in_flash:
            end_i = i - 1
            center_i = (start_i + end_i) // 2
            events.append((center_i, pts[center_i]))
            in_flash = False
    if in_flash:
        end_i = len(ratios) - 1
        center_i = (start_i + end_i) // 2
        events.append((center_i, pts[center_i]))
    return events


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mp4", type=Path, help="録画 MP4 ファイル")
    ap.add_argument("--duration", type=int, default=60, help="テスト合計秒（= 期待フラッシュ数）")
    args = ap.parse_args()

    if not args.mp4.exists():
        print(f"Error: {args.mp4} not found", file=sys.stderr)
        return 1

    ffprobe = require("ffprobe")
    ffmpeg = require("ffmpeg")

    print(f"[verify] Reading frame PTS from {args.mp4}")
    pts = get_frame_pts(ffprobe, args.mp4)
    print(f"[verify]   → {len(pts)} video frames")
    if not pts:
        print("Error: no video frames in input", file=sys.stderr)
        return 1

    print(f"[verify] Scanning frames for red flash (scale={SCALE_W}x{SCALE_H})...")
    ratios: list[float] = []
    for frame in iter_frames(ffmpeg, args.mp4):
        ratios.append(compute_red_ratio(frame))
    print(f"[verify]   → {len(ratios)} frames scanned")

    n = min(len(pts), len(ratios))
    pts = pts[:n]
    ratios = ratios[:n]

    events = detect_flash_events(pts, ratios)
    print(f"[verify] Detected {len(events)} flash events (期待 {args.duration})\n")

    if not events:
        print("Error: no flashes detected", file=sys.stderr)
        return 2

    # 先頭フラッシュを t=0 とし、以降は 1 秒おきに整数秒を割り当てる
    base_pts = events[0][1]
    print(f"{'idx':>4}  {'frame':>6}  {'expected(s)':>12}  {'pts(s)':>10}  {'delta(ms)':>10}")
    deltas_ms: list[float] = []
    for i, (frame_idx, event_pts) in enumerate(events):
        expected = i * 1.0  # 先頭フラッシュ基準
        actual_rel = event_pts - base_pts
        delta_ms = (actual_rel - expected) * 1000.0
        deltas_ms.append(delta_ms)
        print(f"{i:>4}  {frame_idx:>6}  {expected:>12.3f}  {actual_rel:>10.3f}  {delta_ms:>10.1f}")

    print()
    arr = np.array(deltas_ms)
    print("[summary]")
    print(f"  flash count       : {len(events)}")
    print(f"  first drift (ms)  : {arr[0]:+.1f}")
    print(f"  last  drift (ms)  : {arr[-1]:+.1f}")
    print(f"  max |drift| (ms)  : {np.abs(arr).max():.1f}")
    print(f"  mean |drift| (ms) : {np.abs(arr).mean():.1f}")
    print(f"  stdev drift (ms)  : {arr.std():.1f}")
    print(f"  last - first (ms) : {arr[-1] - arr[0]:+.1f}  (累積ドリフト)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
