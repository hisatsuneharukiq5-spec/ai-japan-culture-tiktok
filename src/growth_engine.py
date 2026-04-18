"""Growth automation for Facts & Wonders YouTube channel.

Post-upload actions (run from facts_scheduler after every video):
  1. Add video to a topic-based playlist (creates playlist if missing)
  2. Update video description with trending pytrends keywords

Delayed engagement (run from facts_growth.yml ~35 min after upload):
  1. Post engagement comment on videos that have gone public
  2. Cap at MAX_COMMENTS_PER_DAY to avoid spam signals

Daily actions (run from facts_brain via facts_analyze.yml):
  1. Update channel description with current trending science keywords
  2. Retroactive playlist sync (weekly)
  3. Description refresh on recent videos
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("growth_engine")

ROOT = Path(__file__).resolve().parent.parent
PLAYLIST_CACHE_PATH = ROOT / "output" / "analytics" / "facts_playlists.json"
REGISTRY_PATH = ROOT / "output" / "analytics" / "facts_upload_registry.jsonl"
COMMENT_LOG_PATH = ROOT / "output" / "analytics" / "facts_comment_log.json"

# Max comments per day — staying well below spam thresholds
MAX_COMMENTS_PER_DAY = 3

# Varied CTAs — rotated randomly to avoid fingerprinting
_COMMENT_CTAS = [
    "Which fact surprised you most? Drop it below! 🔔 Subscribe for daily science facts.",
    "Did you know any of these already? 👇 Follow for a new mind-blowing fact every day!",
    "Comment your favorite fact! Science is wild 🌍 Subscribe to never miss one.",
    "What topic should we cover next? Subscribe for daily facts 🚀",
    "Fact-check us! Reply if something surprised you. Subscribe for more 🔬",
    "Which one was most shocking? New facts drop every single day ⚡",
    "Tag someone who needs to know this 👇 Subscribe for your daily science fix 🧪",
    "Save this for later 📌 and subscribe — new fact every day!",
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

_BASELINE_TRENDING = [
    "science facts", "amazing facts", "did you know", "mind blowing facts",
    "fun facts", "daily facts", "cool science", "nature facts", "space facts",
]


# ── Comment log helpers ───────────────────────────────────────────────────────

def _load_comment_log() -> dict:
    if not COMMENT_LOG_PATH.exists():
        return {}
    try:
        return json.loads(COMMENT_LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_comment_log(data: dict) -> None:
    COMMENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMMENT_LOG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _comments_posted_today() -> int:
    log = _load_comment_log()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return int(log.get("date_counts", {}).get(today, 0))


def _record_comment(video_id: str) -> None:
    log = _load_comment_log()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.setdefault("date_counts", {})[today] = _comments_posted_today() + 1
    log.setdefault("posted_ids", []).append(video_id)
    _save_comment_log(log)


def already_commented(video_id: str) -> bool:
    log = _load_comment_log()
    return video_id in log.get("posted_ids", [])


# ── Playlist helpers ──────────────────────────────────────────────────────────

def _load_playlist_cache() -> dict[str, str]:
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
    from src.quota_guard import can_afford, charge

    if playlist_name in cache:
        return cache[playlist_name]

    if not can_afford("playlists.list"):
        return None
    try:
        charge("playlists.list")
        resp = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
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

    if not can_afford("playlists.insert"):
        return None
    try:
        charge("playlists.insert")
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
    from src.quota_guard import can_afford, charge
    if not can_afford("playlistItems.insert"):
        return False
    try:
        charge("playlistItems.insert")
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
    from src.quota_guard import can_afford, charge

    if already_commented(video_id):
        logger.info("Comment already posted on %s — skip", video_id)
        return False
    if _comments_posted_today() >= MAX_COMMENTS_PER_DAY:
        logger.info("Daily comment limit reached (%d) — skip", MAX_COMMENTS_PER_DAY)
        return False
    if not can_afford("commentThreads.insert"):
        return False

    comment_text = random.choice(_COMMENT_CTAS)
    try:
        charge("commentThreads.insert")
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": comment_text}},
                }
            },
        ).execute()
        _record_comment(video_id)
        logger.info("Posted engagement comment on %s", video_id)
        return True
    except Exception as exc:
        logger.warning("Comment post failed for %s: %s", video_id, exc)
        return False


def _fetch_trending_keywords() -> list[str]:
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
        logger.debug("pytrends unavailable (%s), using baseline", exc)
        return _BASELINE_TRENDING


def _update_video_description(youtube: Any, video_id: str, base_description: str, trending_keywords: list[str]) -> bool:
    from src.quota_guard import can_afford, charge
    if not can_afford("videos.list") or not can_afford("videos.update"):
        return False
    try:
        charge("videos.list")
        resp = youtube.videos().list(part="snippet", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return False
        snippet = items[0]["snippet"]
        kw_line = " | ".join(k.title() for k in trending_keywords[:6])
        updated_desc = (base_description.rstrip() + f"\n\n🔍 Trending: {kw_line}")[:5000]
        snippet["description"] = updated_desc
        charge("videos.update")
        youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
        logger.info("Updated description with trending keywords for %s", video_id)
        return True
    except Exception as exc:
        logger.warning("Description update failed for %s: %s", video_id, exc)
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def post_upload_actions(
    youtube: Any,
    video_id: str,
    title: str,
    topic: str,
    base_description: str = "",
) -> dict[str, Any]:
    """Playlist add + description update immediately after upload.
    Comment is intentionally skipped here — posted later by facts_growth.yml
    with a human-like 35-minute delay.
    """
    results: dict[str, Any] = {
        "video_id": video_id,
        "comment_posted": False,
        "playlist_added": False,
        "playlist_name": None,
        "description_updated": False,
    }

    # Playlist management
    time.sleep(random.uniform(5, 15))
    playlist_name = _topic_to_playlist_name(topic or title)
    results["playlist_name"] = playlist_name
    cache = _load_playlist_cache()
    playlist_id = _get_or_create_playlist(youtube, playlist_name, cache)
    if playlist_id:
        results["playlist_added"] = _add_to_playlist(youtube, playlist_id, video_id)

    # Description with trending keywords
    time.sleep(random.uniform(10, 25))
    if base_description:
        trending = _fetch_trending_keywords()
        results["description_updated"] = _update_video_description(youtube, video_id, base_description, trending)

    logger.info("Post-upload actions for %s: playlist=%s desc=%s", video_id, results["playlist_added"], results["description_updated"])
    return results


def post_delayed_comments(youtube: Any, lookback_minutes: int = 60) -> dict[str, Any]:
    """Post engagement comments on recently uploaded public videos.
    Called by facts_growth.yml ~35 min after each post slot.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    results: dict[str, Any] = {"checked": 0, "commented": 0, "skipped": 0}

    if not REGISTRY_PATH.exists():
        return results

    for line in reversed(REGISTRY_PATH.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        created_str = entry.get("created_at", "")
        try:
            created_dt = datetime.fromisoformat(created_str).replace(tzinfo=timezone.utc)
        except Exception:
            continue

        if created_dt < cutoff:
            break  # registry is chronological; stop once past the window

        video_id = entry.get("video_id", "")
        if not video_id:
            continue

        results["checked"] += 1
        time.sleep(random.uniform(15, 45))  # human-like pause between comments
        if _post_engagement_comment(youtube, video_id):
            results["commented"] += 1
        else:
            results["skipped"] += 1

    logger.info("Delayed comment sweep: %s", results)
    return results


def update_channel_description(youtube: Any) -> bool:
    from src.quota_guard import can_afford, charge
    if not can_afford("channels.list") or not can_afford("channels.update"):
        return False
    try:
        charge("channels.list")
        resp = youtube.channels().list(part="snippet", mine=True).execute()
        items = resp.get("items", [])
        if not items:
            return False
        channel_id = items[0]["id"]
        snippet = items[0]["snippet"]
        trending = _fetch_trending_keywords()
        kw_section = " • ".join(k.title() for k in trending[:8])
        snippet["description"] = (
            "Daily 60-second science facts that will blow your mind! 🧬🚀🌍\n\n"
            "New video every day — Subscribe and hit the bell 🔔\n\n"
            f"Trending topics: {kw_section}\n\n"
            "#Facts #Science #DidYouKnow #Shorts #AmazingFacts #Nature #Space"
        )[:1000]
        charge("channels.update")
        youtube.channels().update(part="snippet", body={"id": channel_id, "snippet": snippet}).execute()
        logger.info("Channel description updated")
        return True
    except Exception as exc:
        logger.warning("Channel description update failed: %s", exc)
        return False


def sync_all_playlists(youtube: Any, registry_path: Path) -> dict[str, int]:
    """Retrospectively add all registry videos to their topic playlists. Weekly."""
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
        if not video_id:
            continue
        playlist_name = _topic_to_playlist_name(entry.get("topic", "") or entry.get("title", ""))
        playlist_id = _get_or_create_playlist(youtube, playlist_name, cache)
        if playlist_id and _add_to_playlist(youtube, playlist_id, video_id):
            counts[playlist_name] = counts.get(playlist_name, 0) + 1
        time.sleep(random.uniform(0.5, 1.5))  # avoid quota burst
    logger.info("Playlist sync: %s", counts)
    return counts
