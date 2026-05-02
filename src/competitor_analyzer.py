"""Competitor YouTube channel analyzer for Facts & Wonders.

Searches for top-performing Shorts in the science/facts niche,
extracts title patterns, hook phrases, hashtags, and topics,
then returns structured insights for facts_brain to auto-apply.

Works with or without YOUTUBE_API_KEY_FACTS:
- With key:    live data from YouTube Data API v3 (550 quota units/run)
- Without key: pytrends + curated baseline patterns
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
INSIGHTS_PATH = ROOT / "output" / "analytics" / "competitor_insights.json"
logger = logging.getLogger("competitor_analyzer")

# Search queries targeting top-viewed facts Shorts
SEARCH_QUERIES = [
    "did you know facts #shorts",
    "amazing science facts shorts",
    "mind blowing facts you didn't know",
    "did you know that #shorts",
    "shocking science discovery shorts",
    "incredible nature facts shorts",
]

# Stop words excluded from topic keyword extraction
_STOP_WORDS = {
    "did", "you", "know", "that", "the", "a", "an", "in", "of", "for",
    "are", "is", "was", "were", "fact", "facts", "shorts", "short",
    "this", "its", "and", "but", "not", "with", "all", "more", "your",
    "will", "from", "new", "one", "can", "has", "get", "just", "even",
    "about", "these", "their", "they", "been", "than", "when", "what",
    "how", "why", "its", "had",
}

# Curated baseline patterns — used when API key unavailable.
# Derived from manual research on top Facts/Science Shorts channels.
BASELINE_PATTERNS = {
    "title_templates": [
        "Did you know that {fact}? #Shorts",
        "{number} {topic} facts that will blow your mind #Shorts",
        "Scientists just discovered {topic} and it changes everything #Shorts",
        "Why {topic} is more {adjective} than you think #Shorts",
        "Only {number}% of people know this about {topic} #Shorts",
        "The real reason {topic} does this will shock you #Shorts",
        "What happens to your body when {scenario}? #Shorts",
    ],
    "hook_phrases": [
        "Did you know that",
        "Scientists just discovered",
        "Here's why most people don't know",
        "The shocking truth about",
        "What if I told you that",
        "Most people don't realize",
        "This will change how you see",
        "You won't believe what",
    ],
    "power_words": [
        "shocking", "incredible", "amazing", "mind-blowing", "never",
        "secret", "discovered", "rare", "only", "deadliest", "fastest",
        "impossible", "strangest", "terrifying", "unbelievable", "extreme",
    ],
    "top_hashtags": [
        "#Facts", "#DidYouKnow", "#AmazingFacts", "#Science",
        "#Nature", "#Shorts", "#Space", "#Mind", "#Learn", "#WowFact",
    ],
    "top_topics": [
        "space", "human brain", "deep ocean", "ancient history",
        "extreme animals", "earth science", "body facts",
        "science discovery", "technology", "nature records",
    ],
    "pattern_counts": {
        "did-you-know": 42,
        "number-lead": 18,
        "wh-question": 16,
        "science-discovery": 14,
        "statistic": 6,
        "statement": 4,
    },
    "avg_duration_secs": 57,
}


# ── YouTube Data API helpers ──────────────────────────────────────────────────

def _parse_iso_duration(duration: str) -> int:
    """Parse ISO 8601 duration string to seconds. Returns 0 on failure."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def _search_top_shorts(api_key: str, query: str, max_results: int = 25) -> list[dict]:
    """Search YouTube for top-viewed Shorts matching *query*. Returns list of {video_id, title}."""
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "key": api_key,
                "q": query,
                "type": "video",
                "videoDuration": "short",
                "part": "snippet",
                "maxResults": max_results,
                "order": "viewCount",
                "relevanceLanguage": "en",
            },
            timeout=20,
        )
        resp.raise_for_status()
        return [
            {
                "video_id": item["id"]["videoId"],
                "channel_id": item["snippet"]["channelId"],
                "title": item["snippet"]["title"],
            }
            for item in resp.json().get("items", [])
            if item.get("id", {}).get("videoId")
        ]
    except Exception as exc:
        logger.warning("Shorts search failed for '%s': %s", query, exc)
        return []


def _get_video_details(api_key: str, video_ids: list[str]) -> list[dict]:
    """Fetch snippet + statistics + duration for up to 50 video IDs."""
    if not video_ids:
        return []
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "key": api_key,
                "id": ",".join(video_ids[:50]),
                "part": "snippet,statistics,contentDetails",
            },
            timeout=20,
        )
        resp.raise_for_status()
        results = []
        for item in resp.json().get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            duration_secs = _parse_iso_duration(
                item.get("contentDetails", {}).get("duration", "")
            )
            results.append({
                "video_id": item["id"],
                "channel_id": snippet.get("channelId", ""),
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "tags": snippet.get("tags", []),
                "views": int(stats.get("viewCount", 0) or 0),
                "likes": int(stats.get("likeCount", 0) or 0),
                "duration_secs": duration_secs,
            })
        return sorted(results, key=lambda x: x["views"], reverse=True)
    except Exception as exc:
        logger.warning("Video details fetch failed: %s", exc)
        return []


# ── Pattern extraction ────────────────────────────────────────────────────────

def _classify_title(title: str) -> str:
    t = title.lower().strip()
    if t.startswith("did you know"):
        return "did-you-know"
    if re.match(r"^\d+\s", t):
        return "number-lead"
    if t.startswith(("why ", "how ", "what ", "when ", "where ")):
        return "wh-question"
    if any(w in t for w in ("scientists", "researchers", "study", "discovered")):
        return "science-discovery"
    if "%" in t or " in " in t:
        return "statistic"
    return "statement"


def _generate_title_templates(titles: list[str]) -> list[str]:
    """Convert real titles into reusable parametric templates."""
    templates: set[str] = set(BASELINE_PATTERNS["title_templates"])
    for title in titles:
        # Skip non-ASCII (Hindi, Japanese, emoji-heavy) titles
        if not title.isascii():
            continue
        t = re.sub(r"\b\d+\b", "{number}", title)
        t = re.sub(r"\s*#\w+", "", t).strip()
        # Generalise proper nouns/topic words (max 2 replacements)
        t = re.sub(r"\b([A-Z][a-z]{3,})\b", "{topic}", t, count=2)
        word_count = len(t.split())
        # Only add if: has a placeholder, 4-12 words, no duplicate placeholders
        if (
            "{" in t
            and 4 <= word_count <= 12
            and t.count("{topic}") <= 1  # avoid "How {topic} Do {topic} Have..."
            and t.isascii()
        ):
            templates.add(t.rstrip(" .!?,") + " #Shorts")
    return sorted(templates)[:10]


def _extract_patterns(videos: list[dict]) -> dict[str, Any]:
    """Extract actionable patterns from a list of top-performing video dicts."""
    titles = [v["title"] for v in videos if v.get("title")]
    descriptions = [v["description"] for v in videos if v.get("description")]

    # Title classification
    pattern_counter: Counter = Counter(_classify_title(t) for t in titles)

    # Hook phrases: only extract first words when the title starts with a
    # known hook-style opener (e.g. "Did you know", "Scientists just").
    # Avoids polluting the config with raw video titles like "Squid Ink Science".
    _HOOK_OPENERS = {
        "did", "scientists", "here's", "what", "most", "this", "you",
        "only", "why", "how", "imagine", "the", "never", "meet", "warning",
    }
    hook_counter: Counter = Counter()
    for title in titles:
        # Skip non-English titles
        if not title.isascii():
            continue
        words = title.split()
        if not words:
            continue
        first = words[0].lower().rstrip(".,!?")
        if first not in _HOOK_OPENERS:
            continue
        # Take up to 5 words, strip trailing punctuation and hashtags
        phrase = " ".join(w for w in words[:5] if not w.startswith("#")).rstrip(".,!?")
        # Must be 2–6 words and no hashtags/emojis
        word_count = len(phrase.split())
        if 2 <= word_count <= 6 and phrase.isascii():
            hook_counter[phrase] += 1
    top_hooks = [h for h, _ in hook_counter.most_common(10)]
    # Always fall back to curated hooks if extraction yields too few
    if len(top_hooks) < 4:
        top_hooks = list(BASELINE_PATTERNS["hook_phrases"])

    # Emotional / power words
    all_text = " ".join(titles).lower()
    emotion_counter: Counter = Counter()
    for word in BASELINE_PATTERNS["power_words"]:
        cnt = all_text.count(word)
        if cnt:
            emotion_counter[word] = cnt
    # Also look for new power words (≥ 4 chars, appear ≥ 3 times, title-adjacent adjectives)
    for word in re.findall(r"\b[a-z]{5,}\b", all_text):
        if word not in _STOP_WORDS and emotion_counter.get(word, 0) == 0:
            if all_text.count(word) >= 3:
                emotion_counter[word] = all_text.count(word)

    # Hashtags from descriptions + tags
    hashtag_counter: Counter = Counter()
    for desc in descriptions:
        for tag in re.findall(r"#\w+", desc):
            hashtag_counter[tag.lower()] += 1
    for v in videos:
        for tag in v.get("tags", []):
            hashtag_counter[f"#{tag.lower()}"] += 1
    top_hashtags = [t for t, _ in hashtag_counter.most_common(15)]
    # Always include the essentials even if not seen
    for must in ("#facts", "#shorts", "#didyouknow"):
        if must not in top_hashtags:
            top_hashtags.append(must)

    # Topic keywords
    topic_counter: Counter = Counter()
    for title in titles:
        for word in re.findall(r"[a-z]{4,}", title.lower()):
            if word not in _STOP_WORDS:
                topic_counter[word] += 1
    top_topics = [w for w, _ in topic_counter.most_common(20)]

    # Title templates
    title_templates = _generate_title_templates(titles[:30])

    # Duration stats
    durations = [v["duration_secs"] for v in videos if 0 < v["duration_secs"] <= 60]
    avg_duration = sum(durations) / len(durations) if durations else 57.0

    return {
        "pattern_counts": dict(pattern_counter),
        "top_hooks": top_hooks,
        "power_words": [w for w, _ in emotion_counter.most_common(15)],
        "top_hashtags": top_hashtags,
        "top_topics": top_topics,
        "title_templates": title_templates,
        "avg_duration_secs": round(avg_duration, 1),
        "hook_phrases": top_hooks[:8],
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def analyze(max_videos: int = 100) -> dict[str, Any]:
    """Run full competitor analysis. Saves results to disk and returns insights dict.

    Falls back to BASELINE_PATTERNS if YOUTUBE_API_KEY_FACTS is not configured.
    Quota cost: ~550 units (5 searches × 100 + 50 video lookups × 1).
    """
    api_key = os.getenv("YOUTUBE_API_KEY_FACTS", "").strip()

    if not api_key:
        logger.info("YOUTUBE_API_KEY_FACTS not set — using curated baseline patterns")
        result: dict[str, Any] = {"source": "baseline", "videos_analyzed": 0}
        result.update(BASELINE_PATTERNS)
        result["timestamp"] = datetime.now().isoformat(timespec="seconds")
        _save(result)
        return result

    # Collect video IDs from multiple search queries
    seen_ids: set[str] = set()
    search_hits: list[dict] = []
    for query in SEARCH_QUERIES:
        for hit in _search_top_shorts(api_key, query, max_results=25):
            if hit["video_id"] not in seen_ids:
                seen_ids.add(hit["video_id"])
                search_hits.append(hit)
        if len(search_hits) >= max_videos:
            break

    video_ids = [h["video_id"] for h in search_hits[:50]]  # 50 = single API call
    videos = _get_video_details(api_key, video_ids)

    # Keep only true Shorts (≤ 60 s)
    shorts = [v for v in videos if 0 < v["duration_secs"] <= 60]
    logger.info("Competitor fetch: %d candidates → %d Shorts ≤60s", len(videos), len(shorts))

    if len(shorts) < 5:
        logger.warning("Too few Shorts found (%d); falling back to baseline", len(shorts))
        result = {"source": "baseline_fallback", "videos_analyzed": len(shorts)}
        result.update(BASELINE_PATTERNS)
    else:
        patterns = _extract_patterns(shorts)
        result = {"source": "youtube_api", "videos_analyzed": len(shorts), **patterns}

    result["timestamp"] = datetime.now().isoformat(timespec="seconds")
    _save(result)
    logger.info(
        "Competitor analysis done: %d videos, %d topics, %d hooks",
        result.get("videos_analyzed", 0),
        len(result.get("top_topics", [])),
        len(result.get("hook_phrases", [])),
    )
    return result


def load_latest() -> dict[str, Any]:
    """Load the most recent saved insights (or baseline if file missing)."""
    if not INSIGHTS_PATH.exists():
        return dict(BASELINE_PATTERNS)
    try:
        return json.loads(INSIGHTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(BASELINE_PATTERNS)


def _save(data: dict[str, Any]) -> None:
    INSIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    INSIGHTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
