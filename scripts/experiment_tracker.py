#!/usr/bin/env python
"""Simple experiment tracker: compute deltas between latest and previous
analytics snapshots and flag significant changes.

Writes `output/experiment_alerts.json` and `output/experiment_report.md`.
"""
import json
from pathlib import Path
from datetime import datetime
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils import PROJECT_ROOT, setup_logger

logger = setup_logger("experiment_tracker")


def load_timeseries(ts_file: Path):
    if not ts_file.exists():
        return {}
    data = {}
    with open(ts_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            vid = rec.get("video_id")
            data.setdefault(vid, []).append(rec)
    # sort each list by snapshot_at
    for vid, arr in data.items():
        arr.sort(key=lambda r: r.get("snapshot_at"))
    return data


def safe_int(x):
    try:
        return int(x)
    except Exception:
        return None


def analyze(data):
    alerts = []
    report_lines = []
    now = datetime.utcnow().isoformat() + "Z"
    for vid, arr in data.items():
        if len(arr) < 2:
            report_lines.append(f"- {vid}: only {len(arr)} snapshot(s); skipping delta.")
            continue
        prev = arr[-2]
        latest = arr[-1]
        prev_views = safe_int(prev.get("analytics", {}).get("views")) or 0
        latest_views = safe_int(latest.get("analytics", {}).get("views")) or 0
        delta = None
        pct = None
        if prev_views == 0 and latest_views > 0:
            pct = None
            delta = latest_views - prev_views
            note = "Increase from zero views"
        elif prev_views == 0 and latest_views == 0:
            pct = 0
            delta = 0
            note = "No change"
        else:
            delta = latest_views - prev_views
            try:
                pct = (delta / prev_views) * 100
            except Exception:
                pct = None
            note = ""

        significant = False
        if pct is not None and abs(pct) >= 30:
            significant = True
        if prev_views == 0 and latest_views >= 10:
            significant = True

        report_lines.append(f"- {vid}: prev={prev_views} latest={latest_views} delta={delta} pct={pct}")
        if significant:
            alerts.append({
                "video_id": vid,
                "prev_views": prev_views,
                "latest_views": latest_views,
                "delta": delta,
                "pct": pct,
                "detected_at": now,
            })

    return alerts, report_lines


def main():
    ts_file = PROJECT_ROOT / "output" / "analytics_timeseries.jsonl"
    data = load_timeseries(ts_file)
    alerts, report_lines = analyze(data)

    out_alerts = PROJECT_ROOT / "output" / "experiment_alerts.json"
    with open(out_alerts, "w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)

    report_md = PROJECT_ROOT / "output" / "experiment_report.md"
    with open(report_md, "w", encoding="utf-8") as f:
        f.write(f"# Experiment Tracker Report ({datetime.utcnow().isoformat()}Z)\n\n")
        if not report_lines:
            f.write("No data available.\n")
        else:
            f.write("\n".join(report_lines))
            f.write("\n\n---\n\n")
            f.write("## Alerts\n\n")
            if not alerts:
                f.write("No significant changes detected.\n")
            else:
                for a in alerts:
                    f.write(f"- {a['video_id']}: {a['prev_views']} -> {a['latest_views']} (delta={a['delta']}, pct={a['pct']}) detected_at={a['detected_at']}\n")

    logger.info(f"Wrote alerts: {out_alerts} and report: {report_md}")
    print(out_alerts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
