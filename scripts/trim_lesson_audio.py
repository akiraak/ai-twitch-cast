"""既存のlesson wav音声の末尾無音を一括トリミングするスクリプト

使い方:
    python3 scripts/trim_lesson_audio.py            # resources/audio/lessons 配下を処理
    python3 scripts/trim_lesson_audio.py --dry-run  # 削減量の見積もりのみ
    python3 scripts/trim_lesson_audio.py path/to/dir [path/...]  # 任意ディレクトリ
"""

import argparse
import logging
import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.audio_utils import (  # noqa: E402
    DEFAULT_KEEP_MS,
    DEFAULT_LEADING_KEEP_MS,
    DEFAULT_THRESHOLD_RATIO,
    trim_leading_silence_pcm,
    trim_trailing_silence_pcm,
    trim_wav_file,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("trim_lesson_audio")


def _estimate_trim_ms(
    path: Path, threshold_ratio: float, keep_ms: int, leading_keep_ms: int, trim_leading: bool,
) -> tuple[int, int]:
    """ファイルを書き換えずに削減見積もりだけ返す"""
    import wave
    with wave.open(str(path), "rb") as wf:
        n_ch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        nframes = wf.getnframes()
        data = wf.readframes(nframes)
    original_ms = int(nframes / sr * 1000) if sr else 0
    if n_ch != 1 or sw != 2:
        return 0, original_ms
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
    if len(new_data) == len(data):
        return 0, original_ms
    new_nframes = len(new_data) // sw
    return int((nframes - new_nframes) / sr * 1000), original_ms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths", nargs="*", type=Path,
        help="対象ディレクトリ（指定なしで resources/audio/lessons）",
    )
    parser.add_argument("--dry-run", action="store_true", help="書き換えずに削減量だけ表示")
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD_RATIO,
        help=f"無音判定閾値（フルスケール比、既定 {DEFAULT_THRESHOLD_RATIO}）",
    )
    parser.add_argument(
        "--keep-ms", type=int, default=DEFAULT_KEEP_MS,
        help=f"末尾に残す余裕ms（既定 {DEFAULT_KEEP_MS}）",
    )
    parser.add_argument(
        "--leading-keep-ms", type=int, default=DEFAULT_LEADING_KEEP_MS,
        help=f"先頭に残す余裕ms（既定 {DEFAULT_LEADING_KEEP_MS}）",
    )
    parser.add_argument(
        "--no-leading", action="store_true",
        help="先頭トリミングを行わない（末尾のみ）",
    )
    args = parser.parse_args()
    trim_leading = not args.no_leading

    targets = args.paths or [ROOT / "resources" / "audio" / "lessons"]
    files: list[Path] = []
    for t in targets:
        if not t.exists():
            logger.warning("not found: %s", t)
            continue
        if t.is_file():
            if t.suffix.lower() == ".wav":
                files.append(t)
        else:
            files.extend(sorted(t.rglob("*.wav")))

    if not files:
        logger.info("対象ファイルが見つかりません")
        return

    logger.info("対象 %d ファイル", len(files))
    logger.info(
        "dry-run=%s threshold=%.3f keep_ms=%d leading_keep_ms=%d trim_leading=%s",
        args.dry_run, args.threshold, args.keep_ms, args.leading_keep_ms, trim_leading,
    )

    total_trimmed = 0
    total_original = 0
    changed = 0
    for f in files:
        try:
            if args.dry_run:
                trimmed_ms, original_ms = _estimate_trim_ms(
                    f, args.threshold, args.keep_ms, args.leading_keep_ms, trim_leading,
                )
            else:
                trimmed_ms, original_ms = trim_wav_file(
                    f, threshold_ratio=args.threshold, keep_ms=args.keep_ms,
                    leading_keep_ms=args.leading_keep_ms, trim_leading=trim_leading,
                )
        except Exception as e:
            logger.error("FAILED %s: %s", f, e)
            continue
        total_original += original_ms
        if trimmed_ms > 0:
            changed += 1
            total_trimmed += trimmed_ms
            rel = f.relative_to(ROOT) if f.is_relative_to(ROOT) else f
            logger.info("  -%4d ms  %s (was %d ms)", trimmed_ms, rel, original_ms)

    logger.info("")
    logger.info("==== サマリ ====")
    logger.info("変更ファイル数 : %d / %d", changed, len(files))
    logger.info("合計削減       : %.2f sec", total_trimmed / 1000)
    logger.info("合計再生時間   : %.2f sec", total_original / 1000)
    if total_original > 0:
        logger.info("削減率         : %.2f %%", total_trimmed / total_original * 100)


if __name__ == "__main__":
    main()
