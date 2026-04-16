#!/usr/bin/env python
"""Generate and optionally apply metadata (title/description/tags) improvements for videos.

Usage:
  py -u scripts/metadata_optimizer.py --dry-run
  py -u scripts/metadata_optimizer.py --apply --limit 5

This script lists recent uploads, generates improved title/description/tags using simple
heuristics, and either prints the proposed changes (dry-run) or applies them via
YouTube Data API (`videos().update`).
"""
import argparse
import json
import re
from pathlib import Path
import sys

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.youtube_uploader import YouTubeUploader
from src.utils import PROJECT_ROOT, setup_logger

logger = setup_logger("metadata_optimizer")


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def generate_title_candidate(orig_title: str) -> str:
    t = orig_title.strip()
    # Chop repeated punctuation and brackets
    t = re.sub(r"\s*[\|\-–:]+\s*", " — ", t)
    t = normalize_whitespace(t)
    # If too long, keep leading strong phrase (~70 chars)
    if len(t) > 85:
        t = t[:70].rstrip() + "..."
    # If very short, add clarifying suffix
    if len(t) < 40:
        if not re.search(r"explain|why|how|inside|why|secret|story", t, re.I):
            t = t + " — Explained"
    return t


def generate_description(title: str, orig_description: str, channel_tags: list) -> str:
    intro = f"{title}\n\nIn this video, we explain {title.split('—')[0].strip()}."
    blurb = (
        "\n\nFull notes, links and sources: (see Substack)\n" "\n"
    )
    hashtags = "\n\n" + " ".join([f"#{t.replace(' ', '')}" for t in channel_tags[:8]])
    desc = normalize_whitespace((intro + "\n\n" + orig_description.strip() + blurb + hashtags).strip())
    return desc[:5000]


def extract_tags(title: str, orig_tags: list, default_tags: list) -> list:
    # Heuristic: take words from title that look like keywords, plus existing tags and defaults
    words = re.findall(r"[A-Za-z0-9%]{3,}", title)
    candidates = [w for w in words if len(w) > 2]
    # lower-case, dedupe preserve order
    seen = set()
    tags = []
    for t in (candidates + orig_tags + default_tags):
        tag = t.lower().strip().lstrip('#')
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
        if len(tags) >= 30:
            break
    # Ensure json-serialized tags length under YouTube limit (~500 chars)
    import json as _json

    final = []
    for t in tags:
        candidate = final + [t]
        if len(_json.dumps(candidate)) > 500:
            break
        final = candidate
    return final


def list_recent_uploads(uploader: YouTubeUploader, limit: int = 10) -> list:
    ch = uploader.youtube.channels().list(part="contentDetails", mine=True).execute()
    uploads_pid = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    pl = uploader.youtube.playlistItems().list(
        part="contentDetails",
        playlistId=uploads_pid,
        maxResults=limit,
    ).execute()
    vids = [item["contentDetails"]["videoId"] for item in pl.get("items", [])]
    return vids


def fetch_video(uploader: YouTubeUploader, video_id: str) -> dict:
    resp = uploader.youtube.videos().list(part="snippet,statistics", id=video_id).execute()
    items = resp.get("items") or []
    if not items:
        return {}
    return items[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True, help="Print suggestions only")
    parser.add_argument("--apply", action="store_true", help="Apply suggested metadata changes")
    parser.add_argument("--limit", type=int, default=10, help="How many recent uploads to process")
    args = parser.parse_args()

    uploader = YouTubeUploader()
    vids = list_recent_uploads(uploader, limit=args.limit)
    if not vids:
        logger.info("No recent uploads found.")
        return 0

    results = []
    for vid in vids:
        item = fetch_video(uploader, vid)
        if not item:
            logger.warning(f"Could not fetch video: {vid}")
            continue
        snippet = item.get("snippet", {})
        orig_title = snippet.get("title", "")
        orig_desc = snippet.get("description", "")
        orig_tags = snippet.get("tags", []) or []

        candidate_title = generate_title_candidate(orig_title)
        candidate_tags = extract_tags(candidate_title, orig_tags, uploader.channel_config.get("default_tags", []))
        candidate_description = generate_description(candidate_title, orig_desc, uploader.channel_config.get("default_tags", []))

        results.append({
            "video_id": vid,
            "orig_title": orig_title,
            "candidate_title": candidate_title,
            "orig_tags": orig_tags,
            "candidate_tags": candidate_tags,
            "candidate_description": candidate_description[:300],
        })

        print("---")
        print(f"Video: https://www.youtube.com/watch?v={vid}")
        print(f"Original title: {orig_title}")
        print(f"Suggested title: {candidate_title}")
        print(f"Suggested tags: {candidate_tags}")
        print(f"Suggested description (preview):\n{candidate_description[:300]}\n")

        if args.apply:
            body = {
                "id": vid,
                "snippet": {
                    "title": candidate_title[:100],
                    "description": candidate_description,
                    "categoryId": uploader.channel_config.get("default_category_id", "22"),
                    "defaultLanguage": uploader.channel_config.get("language", "en"),
                },
            }
            if candidate_tags:
                body["snippet"]["tags"] = candidate_tags
            logger.info(f"Applying metadata update for {vid}")
            resp = uploader.youtube.videos().update(part="snippet", body=body).execute()
            logger.info(f"Update returned id: {resp.get('id')}")

    # Save a quick report
    out = PROJECT_ROOT / "output" / "metadata_optimizer_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Wrote metadata suggestions to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
