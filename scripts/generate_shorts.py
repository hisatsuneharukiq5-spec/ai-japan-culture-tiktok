#!/usr/bin/env python
"""Generate a vertical Short clip from a source video using ffmpeg.

Usage:
  py -u scripts/generate_shorts.py --in <input_video> --out <output_short> [--start 00:00:30] [--duration 00:00:30]

Requires `ffmpeg` available on PATH.
"""
import argparse
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils import setup_logger
logger = setup_logger("generate_shorts")


def run_ffmpeg(in_path: Path, out_path: Path, start: str, duration: str):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Resize to 720x1280 vertical, copy audio, re-encode video for compatibility
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", start,
        "-i", str(in_path),
        "-t", duration,
        "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:a", "aac",
        "-b:a", "128k",
        "-c:v", "libx264",
        "-preset", "fast",
        "-profile:v", "main",
        "-crf", "23",
        "-movflags", "+faststart",
        str(out_path)
    ]
    logger.info("Running ffmpeg: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("ffmpeg failed: %s", e)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="infile", required=True)
    parser.add_argument("--out", dest="outfile", required=True)
    parser.add_argument("--start", default="00:00:30")
    parser.add_argument("--duration", default="00:00:30")
    args = parser.parse_args()

    inp = Path(args.infile)
    out = Path(args.outfile)
    if not inp.exists():
        logger.error("Input video not found: %s", inp)
        return 2

    run_ffmpeg(inp, out, args.start, args.duration)
    print(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
