#!/usr/bin/env python3
"""録画 MP4 の AV PTS を計測する。

二つの計測モードを持つ:

1. **音声/映像 PTS アラインメント**（常時実行）
   - `ffprobe -show_packets` で映像/音声の PTS を取り出し、
     ストリーム長・先頭/末尾オフセット・時系列バケットでの差分を出す。
   - 音声ギャップ（>50ms 既定）も検出する。
   - `recording-av-sync-fix.md`（α 検証）と `recording-screen-capture-alternative.md`
     （A0 loopback 検証）の両方で共有する基本計測。

2. **赤フラッシュ ↔ PTS ドリフト**（`av_sync_test.html` 録画専用）
   - 1 秒ごとの赤フラッシュを検出し、各フラッシュの実 PTS と期待時刻のズレを出す。
   - `--no-flash` で無効化できる（一般録画での全フレーム RGB 走査をスキップ）。

使い方:
    python3 scripts/verify_av_sync.py videos/broadcast_YYYYMMDD_HHmmss.mp4
    python3 scripts/verify_av_sync.py debug-ss/poc_loopback_xxx.mp4 --no-flash
    python3 scripts/verify_av_sync.py xxx.mp4 --bucket-sec 1 --gap-ms 30
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


def get_audio_packet_pts(ffprobe: str, mp4: Path) -> list[float]:
    """音声パケットの pts_time(秒) を取得する。

    `frame=pts_time` だと AAC の decoder delay 分が引かれた値が出るので、
    container の packet PTS を見る（generator 出力 / loopback パイプ入力時刻に近い）。
    音声ストリームが無い MP4 では空リストを返す。
    """
    out = subprocess.check_output([
        ffprobe, "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "packet=pts_time",
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
    times.sort()
    return times


def report_av_alignment(
    video_pts: list[float],
    audio_pts: list[float],
    bucket_sec: float,
    gap_ms: float,
) -> None:
    """映像/音声 PTS のアラインメントとギャップを出力する。"""
    print("[av-align]")
    if not video_pts:
        print("  no video frames")
        return
    if not audio_pts:
        print("  no audio packets (映像のみ MP4 か、音声ストリーム未収録)")
        v_start, v_end = video_pts[0], video_pts[-1]
        print(f"  video stream : {v_start:.3f} → {v_end:.3f} "
              f"(duration {v_end - v_start:.3f}s, {len(video_pts)} frames)")
        print()
        return

    v_start, v_end = video_pts[0], video_pts[-1]
    a_start, a_end = audio_pts[0], audio_pts[-1]
    v_dur = v_end - v_start
    a_dur = a_end - a_start

    print(f"  video stream : {v_start:>7.3f}s → {v_end:>7.3f}s "
          f"(duration {v_dur:7.3f}s, {len(video_pts):>5d} frames, "
          f"{len(video_pts) / v_dur if v_dur > 0 else 0:.1f} fps avg)")
    print(f"  audio stream : {a_start:>7.3f}s → {a_end:>7.3f}s "
          f"(duration {a_dur:7.3f}s, {len(audio_pts):>5d} packets, "
          f"{len(audio_pts) / a_dur if a_dur > 0 else 0:.1f} pps avg)")
    print(f"  start offset (audio - video) : {(a_start - v_start) * 1000:+8.1f} ms")
    print(f"  end   offset (audio - video) : {(a_end   - v_end  ) * 1000:+8.1f} ms")
    print(f"  duration drift (audio - video): {(a_dur - v_dur) * 1000:+8.1f} ms"
          "  ← OS wallclock 同期なら ±10ms 程度に収まるべき")
    print()

    # 時系列バケット: bucket_sec ごとに「その時刻までに到達した PTS の最後の値」を出す
    # 共通時間軸 (両ストリーム共に MP4 先頭=0 基準) で比較する
    base = min(v_start, a_start)
    end_t = max(v_end, a_end)
    n_buckets = int((end_t - base) / bucket_sec) + 1
    if n_buckets > 1:
        print(f"  per-{bucket_sec:g}s bucket (last PTS reached at wallclock t):")
        print(f"    {'t(s)':>7}  {'video_pts':>10}  {'audio_pts':>10}  {'diff(ms)':>10}")
        v_idx = 0
        a_idx = 0
        for i in range(1, n_buckets + 1):
            t = base + i * bucket_sec
            while v_idx < len(video_pts) and video_pts[v_idx] <= t:
                v_idx += 1
            while a_idx < len(audio_pts) and audio_pts[a_idx] <= t:
                a_idx += 1
            v_ok = v_idx > 0
            a_ok = a_idx > 0
            last_v = video_pts[v_idx - 1] if v_ok else 0.0
            last_a = audio_pts[a_idx - 1] if a_ok else 0.0
            v_str = f"{last_v:>10.3f}" if v_ok else f"{'-':>10}"
            a_str = f"{last_a:>10.3f}" if a_ok else f"{'-':>10}"
            diff_str = f"{(last_a - last_v) * 1000.0:>+10.1f}" if v_ok and a_ok else f"{'-':>10}"
            print(f"    {t:>7.1f}  {v_str}  {a_str}  {diff_str}")
        print()

    # 音声ギャップ検出: 連続パケット間隔が gap_ms を超える箇所を列挙
    gaps = []
    for i in range(1, len(audio_pts)):
        delta_ms = (audio_pts[i] - audio_pts[i - 1]) * 1000.0
        if delta_ms > gap_ms:
            gaps.append((i, audio_pts[i - 1], audio_pts[i], delta_ms))
    if gaps:
        print(f"  audio gaps (>{gap_ms:g}ms): {len(gaps)} 箇所")
        # 多すぎたら頭 10 件だけ
        for idx, prev_t, cur_t, delta_ms in gaps[:10]:
            print(f"    pkt#{idx:>5}  {prev_t:>7.3f}s → {cur_t:>7.3f}s  gap {delta_ms:>7.1f} ms")
        if len(gaps) > 10:
            print(f"    ... +{len(gaps) - 10} more")
    else:
        print(f"  audio gaps (>{gap_ms:g}ms): なし")
    print()


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
    ap.add_argument("--no-flash", action="store_true",
                    help="赤フラッシュ検出をスキップ（av_sync_test.html 以外の一般録画用・全フレーム RGB 走査を省ける）")
    ap.add_argument("--bucket-sec", type=float, default=5.0,
                    help="AV アラインメント時系列バケットの粒度（秒）。既定 5s")
    ap.add_argument("--gap-ms", type=float, default=50.0,
                    help="音声ギャップ閾値(ms)。連続パケット間隔がこれを超えたら gap として列挙する。既定 50ms")
    args = ap.parse_args()

    if not args.mp4.exists():
        print(f"Error: {args.mp4} not found", file=sys.stderr)
        return 1

    ffprobe = require("ffprobe")

    print(f"[verify] Reading frame PTS from {args.mp4}")
    pts = get_frame_pts(ffprobe, args.mp4)
    print(f"[verify]   → {len(pts)} video frames")
    if not pts:
        print("Error: no video frames in input", file=sys.stderr)
        return 1

    print(f"[verify] Reading audio packet PTS from {args.mp4}")
    apts = get_audio_packet_pts(ffprobe, args.mp4)
    print(f"[verify]   → {len(apts)} audio packets\n")

    report_av_alignment(pts, apts, bucket_sec=args.bucket_sec, gap_ms=args.gap_ms)

    if args.no_flash:
        return 0

    ffmpeg = require("ffmpeg")
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
        print("Note: no flashes detected — was this MP4 recorded from av_sync_test.html?",
              file=sys.stderr)
        print("      （`--no-flash` を付けるとフラッシュ検出をスキップして AV アラインメントだけ出します）",
              file=sys.stderr)
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
