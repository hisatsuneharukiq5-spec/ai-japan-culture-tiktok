#!/usr/bin/env python
"""Update the most-recently uploaded video's title/description/tags and thumbnail

Reads `output/scripts/latest_metadata.json` and `output/thumbnails/latest_thumbnail.jpg`.
Finds the channel's uploads playlist and picks the newest item, then updates its
snippet and uploads the provided thumbnail.
"""
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `src` is importable when running from /scripts
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.youtube_uploader import YouTubeUploader
from src.utils import PROJECT_ROOT, setup_logger

logger = setup_logger("update_latest_video_metadata")


def main():
    project = PROJECT_ROOT
    meta_file = project / "output" / "scripts" / "latest_metadata.json"
    thumb_file = project / "output" / "thumbnails" / "latest_thumbnail.jpg"

    if not meta_file.exists():
        logger.error(f"Metadata file not found: {meta_file}")
        return 1
    if not thumb_file.exists():
        logger.warning(f"Thumbnail not found: {thumb_file} — continuing without thumbnail upload")

    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    uploader = YouTubeUploader()

    # Get channel uploads playlist
    ch = uploader.youtube.channels().list(part="contentDetails", mine=True).execute()
    if not ch.get("items"):
        logger.error("Could not fetch channel details — ensure OAuth scopes are correct.")
        return 1

    uploads_pid = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # Get the newest playlist item
    pl = uploader.youtube.playlistItems().list(
        part="contentDetails,snippet",
        playlistId=uploads_pid,
        maxResults=1,
        ).execute()

    if not pl.get("items"):
        logger.error("No uploads found in channel uploads playlist.")
        return 1

    item = pl["items"][0]
    video_id = item["contentDetails"]["videoId"]

    logger.info(f"Found latest video id: {video_id}")

    # Prepare snippet update
    snippet = {
        "title": meta.get("title", "AI Japan Video")[:100],
        "description": meta.get("description", "")[:5000],
        "categoryId": uploader.channel_config.get("default_category_id", "22"),
        "defaultLanguage": uploader.channel_config.get("language", "en"),
    }
    tags = meta.get("tags", [])
    if tags:
        snippet["tags"] = tags

    body = {
        "id": video_id,
        "snippet": snippet,
    }

    logger.info(f"Updating video metadata for {video_id}: {snippet}")
    resp = uploader.youtube.videos().update(part="snippet", body=body).execute()
    logger.info(f"Update response: {resp.get('id')}")

    # Upload thumbnail if present
    if thumb_file.exists():
        try:
            uploader.youtube.thumbnails().set(videoId=video_id, media_body=str(thumb_file)).execute()
            logger.info(f"Thumbnail uploaded to video: {video_id}")
        except Exception as e:
            logger.warning(f"Thumbnail upload failed: {e}")

    logger.info(f"Completed metadata update for video: {video_id}")
    print(video_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
