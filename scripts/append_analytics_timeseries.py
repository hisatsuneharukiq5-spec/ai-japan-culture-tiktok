#!/usr/bin/env python
"""Append analytics snapshot to a time-series JSONL file.

Reads `output/analytics_report.json` and appends each video's entry as a
separate JSON line in `output/analytics_timeseries.jsonl`. Also updates
`output/analytics_timeseries_latest.json` with the most recent snapshot.
"""
import json
from pathlib import Path
from datetime import datetime
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils import PROJECT_ROOT, setup_logger

logger = setup_logger("append_analytics_timeseries")


def main():
    in_file = PROJECT_ROOT / "output" / "analytics_report.json"
    if not in_file.exists():
        logger.error(f"Analytics report not found: {in_file}")
        return 1

    with open(in_file, "r", encoding="utf-8") as f:
        items = json.load(f)

    out_lines = []
    ts = datetime.utcnow().isoformat() + "Z"
    for it in items:
        rec = {
            "video_id": it.get("video_id"),
            "fetched_at": it.get("fetched_at", ts),
            "snapshot_at": ts,
            "start_date": it.get("start_date"),
            "end_date": it.get("end_date"),
            "analytics": it.get("analytics", {}),
        }
        out_lines.append(rec)

    ts_file = PROJECT_ROOT / "output" / "analytics_timeseries.jsonl"
    ts_file.parent.mkdir(parents=True, exist_ok=True)

    with open(ts_file, "a", encoding="utf-8") as f:
        for r in out_lines:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    latest_file = PROJECT_ROOT / "output" / "analytics_timeseries_latest.json"
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(out_lines, f, ensure_ascii=False, indent=2)

    logger.info(f"Appended {len(out_lines)} records to: {ts_file}")
    print(ts_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
