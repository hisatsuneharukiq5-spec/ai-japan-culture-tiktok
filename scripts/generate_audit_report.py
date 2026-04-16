#!/usr/bin/env python
"""Generate actionable channel recommendations from `output/channel_audit.json`.

Creates `output/channel_actionable_report.json` and `output/channel_actionable_report.md`.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils import PROJECT_ROOT, setup_logger

logger = setup_logger("generate_audit_report")


def score_keywords(tags):
    # simple heuristic: prioritize short, high-level tags
    kws = [t.lower() for t in tags]
    return kws


def best_local_thumbnail_match(title, local_thumbs):
    title_tokens = set(re.findall(r"[A-Za-z0-9]{3,}", title.lower()))
    best = None
    best_score = 0
    for t in local_thumbs:
        name = t.lower()
        tokens = set(re.findall(r"[A-Za-z0-9]{3,}", name))
        score = len(title_tokens & tokens)
        if score > best_score:
            best_score = score
            best = t
    return best


def analyze(audit):
    local = audit.get("local", {})
    remote = audit.get("remote", [])
    local_thumbs = local.get("local_thumbnails", [])

    recs = []
    for v in remote:
        rid = v.get("id")
        title = v.get("title", "")
        desc = v.get("description", "") or ""
        tags = v.get("tags", [])
        published = v.get("publishedAt")
        views = int(v.get("viewCount") or 0)
        like = int(v.get("likeCount") or 0)
        thumb_url = v.get("thumbnail", "")

        rec = {"id": rid, "current_title": title, "issues": [], "recommendations": {}}

        # Title length
        if len(title) > 60:
            rec["issues"].append("title_too_long")
            rec["recommendations"]["title"] = title[:57].rstrip() + "..."

        # Description length (words)
        desc_words = len(re.findall(r"\w+", desc))
        if desc_words < 80:
            rec["issues"].append("description_short")
            rec["recommendations"]["description"] = (
                "Expand description to 150-250 words, include Substack CTA and 3-5 hashtags."
            )

        # Tags
        if not tags or len(tags) < 6:
            rec["issues"].append("few_tags")
            rec["recommendations"]["tags"] = (tags[:10] if tags else [])

        # Thumbnail check: YouTube default thumbnail URL contains '/default.jpg'
        if thumb_url and thumb_url.endswith("/default.jpg"):
            rec["issues"].append("no_custom_thumbnail")
            match = best_local_thumbnail_match(title, local_thumbs)
            rec["recommendations"]["thumbnail_suggestion"] = match

        # Low views early: recommend A/B thumbnail + redistribute
        if views < 50 and published:
            rec["issues"].append("low_views")
            rec["recommendations"]["experiment"] = (
                "Run thumbnail A/B test and try 2 title variants; repost as Short clip."
            )

        # Privacy check
        if v.get("privacyStatus") != "public":
            rec["issues"].append("not_public")
            rec["recommendations"]["privacy"] = "Set to public if ready, or schedule publish."

        recs.append(rec)

    return recs


def write_reports(recs):
    out_json = PROJECT_ROOT / "output" / "channel_actionable_report.json"
    out_md = PROJECT_ROOT / "output" / "channel_actionable_report.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# Channel Actionable Report\n"]
    for r in recs:
        lines.append(f"## Video {r['id']} - {r['current_title']}\n")
        if r["issues"]:
            lines.append("- Issues: " + ", ".join(r["issues"]))
        else:
            lines.append("- Issues: none")
        lines.append("- Recommendations:\n")
        for k, v in r["recommendations"].items():
            lines.append(f"  - {k}: {v}\n")
        lines.append("\n")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    return out_json, out_md


def main():
    path = PROJECT_ROOT / "output" / "channel_audit.json"
    if not path.exists():
        logger.error(f"Audit file not found: {path}")
        return 1
    audit = json.loads(path.read_text(encoding="utf-8"))
    recs = analyze(audit)
    j, m = write_reports(recs)
    print(f"Actionable report written: {j} and {m}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
