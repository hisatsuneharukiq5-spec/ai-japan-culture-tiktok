#!/usr/bin/env python
"""Channel audit: examine local assets and list current YouTube uploads.

Saves report to `output/channel_audit.json` and prints a short summary.
"""
import json
import sys
from pathlib import Path

# ensure repo root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils import PROJECT_ROOT, setup_logger
from src.youtube_uploader import YouTubeUploader

logger = setup_logger("channel_audit")


def scan_local():
    project = PROJECT_ROOT
    videos = list((project / "output" / "videos").glob("*.mp4"))
    thumbs = list((project / "output" / "thumbnails").glob("*.jpg"))
    scripts = list((project / "output" / "scripts").glob("*.txt"))
    meta_file = project / "output" / "scripts" / "latest_metadata.json"
    latest_meta = None
    if meta_file.exists():
        try:
            latest_meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            latest_meta = None

    return {
        "local_videos": [str(p.name) for p in videos],
        "local_thumbnails": [str(p.name) for p in thumbs],
        "local_scripts": [str(p.name) for p in scripts],
        "latest_metadata": latest_meta,
    }


def fetch_channel_uploads(uploader: YouTubeUploader):
    # get uploads playlist
    ch = uploader.youtube.channels().list(part="contentDetails", mine=True).execute()
    items = []
    if ch.get("items"):
        uploads_pid = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        # list up to 50 recent uploads
        pl = uploader.youtube.playlistItems().list(part="contentDetails,snippet", playlistId=uploads_pid, maxResults=50).execute()
        for it in pl.get("items", []):
            vid = it["contentDetails"]["videoId"]
            vs = uploader.youtube.videos().list(part="snippet,statistics,status", id=vid).execute()
            if not vs.get("items"):
                continue
            v = vs["items"][0]
            items.append({
                "id": vid,
                "title": v["snippet"].get("title"),
                "description": v["snippet"].get("description"),
                "tags": v["snippet"].get("tags", []),
                "publishedAt": v["snippet"].get("publishedAt"),
                "viewCount": v.get("statistics", {}).get("viewCount"),
                "likeCount": v.get("statistics", {}).get("likeCount"),
                "privacyStatus": v.get("status", {}).get("privacyStatus"),
                "thumbnail": v["snippet"].get("thumbnails", {}).get("default", {}).get("url"),
            })
    return items


def main():
    logger.info("Starting channel audit")
    report = {"local": scan_local(), "remote": []}

    try:
        uploader = YouTubeUploader()
        report["remote"] = fetch_channel_uploads(uploader)
    except Exception as e:
        logger.warning(f"YouTube API unavailable or not authorized: {e}")

    out = PROJECT_ROOT / "output" / "channel_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Audit saved: {out}")
    # print concise summary
    print(f"Local videos: {len(report['local']['local_videos'])}")
    print(f"Local thumbnails: {len(report['local']['local_thumbnails'])}")
    print(f"Remote uploads (fetched): {len(report.get('remote', []))}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
