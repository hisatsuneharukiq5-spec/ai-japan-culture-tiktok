#!/usr/bin/env python
"""Check and perform thumbnail swaps according to `output/ab_tests/manifest.json`.

Run periodically (cron / scheduler) to execute swaps when `swap_at` is reached.
"""
import json
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils import PROJECT_ROOT, setup_logger
from src.youtube_uploader import YouTubeUploader

logger = setup_logger("ab_test_runner")


def iso_to_dt(s: str):
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return None


def main():
    manifest_file = PROJECT_ROOT / "output" / "ab_tests" / "manifest.json"
    if not manifest_file.exists():
        logger.error("Manifest not found. Run start_ab_tests_all.py first.")
        return 1

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    uploader = YouTubeUploader()
    changed = False

    for entry in manifest:
        if entry.get("status") != "started":
            continue
        swap_at = iso_to_dt(entry.get("swap_at"))
        if not swap_at:
            continue
        if datetime.utcnow() >= swap_at:
            vid = entry["video_id"]
            v2 = entry.get("variant2")
            if not v2:
                logger.warning(f"No variant2 for {vid}; skipping swap")
                entry["status"] = "no_variant2"
                changed = True
                continue
            try:
                uploader.youtube.thumbnails().set(videoId=vid, media_body=str(v2)).execute()
                entry["status"] = "swapped"
                entry["swapped_at"] = datetime.utcnow().isoformat() + "Z"
                logger.info(f"Swapped thumbnail for {vid} to variant2")
                changed = True
            except Exception as e:
                logger.warning(f"Failed to swap for {vid}: {e}")

    if changed:
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Manifest updated")
    else:
        print("No swaps needed at this time.")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
