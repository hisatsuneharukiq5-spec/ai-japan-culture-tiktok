"""Growth automation for Facts & Wonders YouTube channel.

Post-upload actions (run after every video):
  1. Post an engagement comment to seed early interaction
  2. Add video to a topic-based playlist (creates playlist if missing)
  3. Update video description with trending pytrends keywords

Daily actions (run from facts_brain):
  1. Update channel description with current trending science keywords
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("growth_engine")

ROOT = Path(__file__).resolve().parent.parent
PLAYLIST_CACHE_PATH = ROOT / "output" / "analytics" / "facts_playlists.json"

# Varied CTAs for comment rotation — avoids spam fingerprint
_COMMENT_CTAS = [
    "Which fact surprised you most? Drop it in the comments! 🔔 Subscribe for daily science facts.",
    "Did you know any of these already? 👇 Follow for a new mind-blowing fact every day!",
    "Comment your favorite fact below! Science is wild 🌍 Subscribe to never miss one.",
    "What topic should we cover next? Subscribe for daily facts that will blow your mind 🚀",
    "Fact-check us! Drop a reply if something surprised you. Subscribe for more 🔬",
    "Which one was most shocking? Subscribe — new facts drop every single day! ⚡",
    "Tag someone who needs to know this 👇 Subscribe for your daily science fix 🧪",
]

# Topic → playlist name mapping
_TOPIC_PLAYLIST_MAP = [
    (["space", "planet", "star", "galaxy", "nasa", "orbit", "solar", "universe", "astronaut", "moon"], "Space Facts #Shorts"),
    (["brain", "body", "heart", "blood", "cell", "dna", "nerve", "muscle", "organ", "human"], "Human Body Facts #Shorts"),
    (["animal", "creature", "fish", "bird", "insect", "mammal", "reptile", "shark", "whale", "spider"], "Animal Facts #Shorts"),
    (["ocean", "deep", "sea", "marine", "coral", "tide", "wave", "underwater"], "Ocean Facts #Shorts"),
    (["earth", "volcano", "earthquake", "mountain", "weather", "climate", "atmosphere", "geology"], "Earth Science Facts #Shorts"),
    (["history", "ancient", "civilization", "empire", "war", "discovery", "explorer", "pyramid"], "History Facts #Shorts"),
]
_DEFAULT_PLAYLIST = "Amazing Facts #Shorts"

# Baseline trending keywords for description injection when pytrends unavailable
_BASELINE_TRENDING = [
    "science facts", "amazing facts", "did you know", "mind blowing facts",
    "fun facts", "daily facts", "cool science", "nature facts", "space facts",
]


def _load_playlist_cache() -> dict[str, str]:
    """Returns {playlist_name: playlist_id}."""
    if not PLAYLIST_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(PLAYLIST_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_playlist_cache(cache: dict[str, str]) -> None:
    PLAYLIST_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLAYLIST_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _topic_to_playlist_name(topic: str) -> str:
    topic_lower = (topic or "").lower()
    for keywords, playlist_name in _TOPIC_PLAYLIST_MAP:
        if any(kw in topic_lower for kw in keywords):
            return playlist_name
    return _DEFAULT_PLAYLIST


def _get_or_create_playlist(youtube: Any, playlist_name: str, cache: dict[str, str]) -> str | None:
    """Return playlist_id for playlist_name, creating it if needed."""
    if playlist_name in cache:
        return cache[playlist_name]

    # Search existing playlists (mine)
    try:
        resp = youtube.playlists().list(
            part="snippet",
            mine=True,
            maxResults=50,
        ).execute()
        for item in resp.get("items", []):
            title = item.get("snippet", {}).get("title", "")
            pid = item["id"]
            if title not in cache:
                cache[title] = pid
            if title == playlist_name:
                _save_playlist_cache(cache)
                return pid
    except Exception as exc:
        logger.warning("Playlist list failed: %s", exc)

    # Create the playlist
    try:
        result = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": playlist_name,
                    "description": f"Daily science Shorts — {playlist_name.replace(' #Shorts', '')}. Subscribe for a new fact every day!",
                    "defaultLanguage": "en",
                },
                "status": {"privacyStatus": "public"},
            },
        ).execute()
        pid = result["id"]
        cache[playlist_name] = pid
        _save_playlist_cache(cache)
        logger.info("Created playlist '%s' → %s", playlist_name, pid)
        return pid
    except Exception as exc:
        logger.warning("Playlist create failed for '%s': %s", playlist_name, exc)
        return None


def _add_to_playlist(youtube: Any, playlist_id: str, video_id: str) -> bool:
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        logger.info("Added %s to playlist %s", video_id, playlist_id)
        return True
    except Exception as exc:
        logger.warning("Playlist add failed: %s", exc)
        return False


def _post_engagement_comment(youtube: Any, video_id: str) -> bool:
    comment_text = random.choice(_COMMENT_CTAS)
    try:
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": comment_text}
                    },
                }
            },
        ).execute()
        logger.info("Posted engagement comment on %s", video_id)
        return True
    except Exception as exc:
        logger.warning("Comment post failed for %s: %s", video_id, exc)
        return False


def _fetch_trending_keywords() -> list[str]:
    """Fetch trending science/facts search terms via pytrends."""
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        keywords = ["amazing facts", "did you know", "science facts", "fun facts", "mind blowing"]
        pt.build_payload(keywords, timeframe="now 7-d", geo="")
        related = pt.related_queries()
        trending: list[str] = []
        for kw in keywords:
            rising = (related.get(kw) or {}).get("rising")
            if rising is not None and not rising.empty:
                trending.extend(rising["query"].head(3).tolist())
        return trending[:10] if trending else _BASELINE_TRENDING
    except Exception as exc:
        logger.debug("pytrends unavailable (%s), using baseline keywords", exc)
        return _BASELINE_TRENDING


def _update_video_description(youtube: Any, video_id: str, base_description: str, trending_keywords: list[str]) -> bool:
    """Append trending keyword tags to a video's description."""
    try:
        # Fetch current snippet first (need etag + all fields for update)
        resp = youtube.videos().list(part="snippet", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return False
        snippet = items[0]["snippet"]

        kw_line = " | ".join(k.title() for k in trending_keywords[:6])
        updated_desc = (base_description.rstrip() + f"\n\n🔍 Trending: {kw_line}")[:5000]

        snippet["description"] = updated_desc
        youtube.videos().update(
            part="snippet",
            body={"id": video_id, "snippet": snippet},
        ).execute()
        logger.info("Updated description with trending keywords for %s", video_id)
        return True
    except Exception as exc:
        logger.warning("Description update failed for %s: %s", video_id, exc)
        return False


def post_upload_actions(
    youtube: Any,
    video_id: str,
    title: str,
    topic: str,
    base_description: str = "",
) -> dict[str, Any]:
    """Run all post-upload growth actions. Safe — errors are logged but not raised."""
    results: dict[str, Any] = {
        "video_id": video_id,
        "comment_posted": False,
        "playlist_added": False,
        "playlist_name": None,
        "description_updated": False,
    }

    # 1. Engagement comment
    time.sleep(random.uniform(3, 8))  # brief delay feels more organic
    results["comment_posted"] = _post_engagement_comment(youtube, video_id)

    # 2. Playlist management
    playlist_name = _topic_to_playlist_name(topic or title)
    results["playlist_name"] = playlist_name
    cache = _load_playlist_cache()
    playlist_id = _get_or_create_playlist(youtube, playlist_name, cache)
    if playlist_id:
        results["playlist_added"] = _add_to_playlist(youtube, playlist_id, video_id)

    # 3. Update description with trending keywords
    if base_description:
        trending = _fetch_trending_keywords()
        results["description_updated"] = _update_video_description(
            youtube, video_id, base_description, trending
        )

    logger.info(
        "Post-upload growth actions for %s: comment=%s playlist=%s desc=%s",
        video_id,
        results["comment_posted"],
        results["playlist_added"],
        results["description_updated"],
    )
    return results


def update_channel_description(youtube: Any) -> bool:
    """Update the channel's description with current trending keywords. Run daily."""
    try:
        # Fetch channel info
        resp = youtube.channels().list(part="snippet", mine=True).execute()
        items = resp.get("items", [])
        if not items:
            logger.warning("No channel found for authenticated user")
            return False

        channel_id = items[0]["id"]
        snippet = items[0]["snippet"]
        trending = _fetch_trending_keywords()

        date_str = datetime.now().strftime("%B %Y")
        kw_section = " • ".join(k.title() for k in trending[:8])
        new_desc = (
            "Daily 60-second science facts that will blow your mind! 🧬🚀🌍\n\n"
            "New video every day — Subscribe and hit the bell 🔔\n\n"
            f"Trending topics: {kw_section}\n\n"
            "#Facts #Science #DidYouKnow #Shorts #AmazingFacts #Nature #Space"
        )

        snippet["description"] = new_desc[:1000]
        youtube.channels().update(
            part="snippet",
            body={"id": channel_id, "snippet": snippet},
        ).execute()
        logger.info("Channel description updated (%s)", date_str)
        return True
    except Exception as exc:
        logger.warning("Channel description update failed: %s", exc)
        return False


def sync_all_playlists(youtube: Any, registry_path: Path) -> dict[str, int]:
    """Retrospectively add all registry videos to their topic playlists. Run once or monthly."""
    if not registry_path.exists():
        return {}

    cache = _load_playlist_cache()
    counts: dict[str, int] = {}

    for line in registry_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        video_id = entry.get("video_id", "")
        topic = entry.get("topic", "")
        title = entry.get("title", "")
        if not video_id:
            continue

        playlist_name = _topic_to_playlist_name(topic or title)
        playlist_id = _get_or_create_playlist(youtube, playlist_name, cache)
        if playlist_id and _add_to_playlist(youtube, playlist_id, video_id):
            counts[playlist_name] = counts.get(playlist_name, 0) + 1
        time.sleep(0.3)  # avoid quota burst

    logger.info("Playlist sync complete: %s", counts)
    return counts
