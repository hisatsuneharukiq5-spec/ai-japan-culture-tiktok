#!/usr/bin/env python
"""Simple upload scheduler:

Place pending uploads in `output/upload_queue.json` as a list of objects:
  { "video_path": "output/videos/xxx.mp4", "metadata": "output/scripts/meta_x.json", "scheduled_at": "2026-03-03T18:00:00Z" }

Run with `--dry-run` to list due uploads without performing them.
Run with `--run-due` to perform uploads.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import sys
import subprocess

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.youtube_uploader import YouTubeUploader
from src.utils import PROJECT_ROOT, setup_logger

logger = setup_logger("schedule_uploads")


def load_queue(qpath: Path):
    if not qpath.exists():
        return []
    with open(qpath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(qpath: Path, items):
    with open(qpath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="List due uploads")
    parser.add_argument("--run-due", action="store_true", help="Upload due items")
    args = parser.parse_args()

    qpath = PROJECT_ROOT / "output" / "upload_queue.json"
    queue = load_queue(qpath)
    now = datetime.now(timezone.utc)
    due = []
    for item in queue:
        sa = item.get("scheduled_at")
        try:
            sat = datetime.fromisoformat(sa.replace("Z", "+00:00")) if sa else None
        except Exception:
            sat = None
        if not sat or sat <= now:
            due.append(item)

    if not due:
        print("No uploads due.")
        return 0

    print(f"{len(due)} uploads due:")
    for d in due:
        print("-", d.get("video_path"), "scheduled_at", d.get("scheduled_at"))

    if args.dry_run:
        return 0

    if args.run_due:
        uploader = YouTubeUploader()
        remaining = [i for i in queue if i not in due]
        for d in due:
            vp = PROJECT_ROOT / d.get("video_path")
            meta_path = PROJECT_ROOT / d.get("metadata") if d.get("metadata") else None
            meta = {}
            if meta_path and meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            if not vp.exists():
                logger.warning(f"Video missing: {vp}")
                continue
            # Optionally, generate and upload a Short first
            if d.get("create_short"):
                short_start = d.get("short_start", "00:00:30")
                short_duration = d.get("short_duration", "00:00:30")
                short_out = PROJECT_ROOT / "output" / "shorts" / (vp.stem + "_short.mp4")
                # call the short generator
                try:
                    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_shorts.py"), "--in", str(vp), "--out", str(short_out), "--start", short_start, "--duration", short_duration], check=True)
                    logger.info(f"Generated short: {short_out}")
                    # upload short via upload_short
                    try:
                        short_vid = uploader.upload_short(short_out, meta)
                        logger.info(f"Uploaded Short {short_out} -> {short_vid}")
                    except Exception as e:
                        logger.warning(f"Short upload failed: {e}")
                except Exception as e:
                    logger.warning(f"Short generation failed: {e}")

            vid = uploader.upload(vp, meta)
            logger.info(f"Uploaded scheduled video {vp} -> {vid}")
        # save remaining queue
        save_queue(qpath, remaining)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
