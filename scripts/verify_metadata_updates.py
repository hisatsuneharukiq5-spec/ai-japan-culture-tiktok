#!/usr/bin/env python
"""Verify that metadata updates were applied: fetch current snippet and statistics
for videos listed in `output/metadata_optimizer_report.json` and write a verification report.
"""
import json
from pathlib import Path
import sys

# Ensure repo root on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.youtube_uploader import YouTubeUploader
from src.utils import PROJECT_ROOT, setup_logger

logger = setup_logger("verify_metadata_updates")


def main():
    in_file = PROJECT_ROOT / "output" / "metadata_optimizer_report.json"
    if not in_file.exists():
        logger.error(f"Input report not found: {in_file}")
        return 1

    with open(in_file, "r", encoding="utf-8") as f:
        items = json.load(f)

    uploader = YouTubeUploader()
    out = []
    for it in items:
        vid = it.get("video_id")
        if not vid:
            continue
        resp = uploader.youtube.videos().list(part="snippet,statistics", id=vid).execute()
        arr = resp.get("items") or []
        if not arr:
            logger.warning(f"No data for video: {vid}")
            continue
        current = arr[0]
        snippet = current.get("snippet", {})
        stats = current.get("statistics", {})

        out.append({
            "video_id": vid,
            "title": snippet.get("title"),
            "description_excerpt": (snippet.get("description") or "")[:300],
            "tags": snippet.get("tags", []),
            "statistics": {
                "viewCount": stats.get("viewCount"),
                "likeCount": stats.get("likeCount"),
                "commentCount": stats.get("commentCount"),
            },
            "fetched_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        })

    out_file = PROJECT_ROOT / "output" / "metadata_verification.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    logger.info(f"Wrote verification report: {out_file}")
    print(out_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
