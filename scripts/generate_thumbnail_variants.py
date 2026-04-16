#!/usr/bin/env python
"""Generate 3 thumbnail variants per video based on the actionable report.

Saves variants to `output/thumbnails/variants/{video_id}/`.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils import PROJECT_ROOT, setup_logger
from src.thumbnail_generator import create_thumbnail

logger = setup_logger("generate_thumbnail_variants")


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def main():
    report_file = PROJECT_ROOT / "output" / "channel_actionable_report.json"
    if not report_file.exists():
        logger.error(f"Report not found: {report_file}")
        return 1

    report = json.loads(report_file.read_text(encoding="utf-8"))
    variants_root = PROJECT_ROOT / "output" / "thumbnails" / "variants"
    ensure_dir(variants_root)

    created = []
    for item in report:
        vid = item.get("id")
        title = item.get("current_title") or "AI Japan"
        suggested = item.get("recommendations", {}).get("thumbnail_suggestion")
        # if suggestion is None, fall back to latest_thumbnail
        topic = ""
        dest_dir = variants_root / vid
        ensure_dir(dest_dir)

        # create 3 variants by tweaking the title to influence template selection
        variants = [title, "RULES: " + title, "SHOCK: " + title]
        for i, vt in enumerate(variants, start=1):
            fname = dest_dir / f"{vid}_variant{i}.jpg"
            try:
                # create_thumbnail will try AI background then fallback templates
                create_thumbnail(title=vt, topic=topic, output_filename=str(fname.name))
                # create_thumbnail writes into output/thumbnails/<name>
                # move it into our variants folder
                src_path = PROJECT_ROOT / "output" / "thumbnails" / fname.name
                if src_path.exists():
                    src_path.replace(fname)
                    created.append(str(fname))
            except Exception as e:
                logger.warning(f"Failed to create variant for {vid}: {e}")

    print(f"Created {len(created)} variant thumbnails. Examples:\n{created[:10]}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
