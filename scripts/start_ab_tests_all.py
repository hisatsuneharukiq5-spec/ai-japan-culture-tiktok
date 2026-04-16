#!/usr/bin/env python
"""Start A/B thumbnail tests for all videos listed in actionable report.

Sets variant1 as the current thumbnail now and records swap time (default 48h).
Writes manifest to `output/ab_tests/manifest.json` which `ab_test_runner.py` can process.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils import PROJECT_ROOT, setup_logger
from src.youtube_uploader import YouTubeUploader

logger = setup_logger("start_ab_tests_all")


def main(hours_until_swap: int = 48):
    report_file = PROJECT_ROOT / "output" / "channel_actionable_report.json"
    if not report_file.exists():
        logger.error("Actionable report not found; run generate_audit_report.py first.")
        return 1

    report = json.loads(report_file.read_text(encoding="utf-8"))
    manifest = []
    uploader = YouTubeUploader()

    for item in report:
        vid = item.get("id")
        if not vid:
            continue
        variants_dir = PROJECT_ROOT / "output" / "thumbnails" / "variants" / vid
        v1 = variants_dir / f"{vid}_variant1.jpg"
        v2 = variants_dir / f"{vid}_variant2.jpg"

        entry = {
            "video_id": vid,
            "variant1": str(v1) if v1.exists() else None,
            "variant2": str(v2) if v2.exists() else None,
            "started_at": datetime.utcnow().isoformat() + "Z",
            "swap_at": (datetime.utcnow() + timedelta(hours=hours_until_swap)).isoformat() + "Z",
            "status": "started",
            "swapped_at": None,
        }

        # Attempt to set variant1 as thumbnail now
        if v1.exists():
            try:
                uploader.youtube.thumbnails().set(videoId=vid, media_body=str(v1)).execute()
                logger.info(f"Set variant1 thumbnail for {vid}")
            except Exception as e:
                logger.warning(f"Failed to set variant1 for {vid}: {e}")
                entry["status"] = "failed_initial_set"
        else:
            logger.warning(f"Variant1 not found for {vid}; skipping initial set")
            entry["status"] = "no_variant1"

        manifest.append(entry)

    out_dir = PROJECT_ROOT / "output" / "ab_tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = out_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"A/B tests started for {len(manifest)} videos. Manifest: {manifest_file}")
    return 0


if __name__ == '__main__':
    # allow optional hours argument
    hours = 48
    if len(sys.argv) > 1:
        try:
            hours = int(sys.argv[1])
        except Exception:
            pass
    raise SystemExit(main(hours_until_swap=hours))
