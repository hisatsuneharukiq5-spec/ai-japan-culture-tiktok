"""AI analysis and evolution engine for Facts & Wonders."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any
from xml.etree import ElementTree as ET

import requests
from dotenv import load_dotenv

import config_facts

# Optional imports — fail gracefully so brain still runs without them
try:
    from pytrends.request import TrendReq as _TrendReq
    _PYTRENDS_AVAILABLE = True
except ImportError:
    _PYTRENDS_AVAILABLE = False

load_dotenv()

ROOT = Path(__file__).resolve().parent
OUTPUT_ANALYTICS_DIR = ROOT / "output" / "analytics"
ANALYSIS_DIR = ROOT / "analysis"
REPORT_PATH = OUTPUT_ANALYTICS_DIR / "facts_report_latest.json"
BRAIN_LOG_PATH = ANALYSIS_DIR / "facts_brain_log.json"
REGISTRY_PATH = OUTPUT_ANALYTICS_DIR / "facts_upload_registry.jsonl"
AB_TEST_PATH = OUTPUT_ANALYTICS_DIR / "facts_ab_tests.json"

LOG_PATH = ROOT / "logs" / "facts_brain.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    filename=str(LOG_PATH),
    filemode="a",
    format="%(asctime)s [facts_brain] %(levelname)s: %(message)s",
)
logger = logging.getLogger("facts_brain")


@dataclass
class AnalysisResult:
    summary: dict[str, Any]
    config_changes: dict[str, Any]
    reason: str


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load JSON %s: %s", path, exc)
        return default


def _append_json_list(path: Path, item: dict[str, Any]) -> None:
    items = _load_json(path, default=[])
    if not isinstance(items, list):
        items = []
    items.append(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_registry() -> list[dict[str, Any]]:
    if not REGISTRY_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _extract_topic(title: str) -> str:
    cleaned = re.sub(r"#\w+", "", title).strip()
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", cleaned)
    if not tokens:
        return "general"
    return " ".join(tokens[:3]).lower()


def _title_pattern(title: str) -> str:
    if title.lower().startswith("did you know"):
        return "did-you-know"
    if any(ch.isdigit() for ch in title):
        return "numeric"
    return "statement"


def _mine_internal_patterns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "top5_patterns": [],
            "bottom5_issues": ["Not enough data"],
            "retention_script_pattern": "Short punchy sentences with numbers",
        }

    sorted_rows = sorted(rows, key=lambda r: r.get("view_count", 0), reverse=True)
    top5 = sorted_rows[:5]
    bottom5 = sorted_rows[-5:]

    top_title_lengths = [len(r.get("title", "")) for r in top5 if r.get("title")]
    top_patterns = Counter(_title_pattern(r.get("title", "")) for r in top5)
    top_topics = Counter(_extract_topic(r.get("title", "")) for r in top5)
    top_hours = Counter(r.get("scheduled_time", "00:00")[:2] for r in top5)

    bottom_notes: list[str] = []
    for row in bottom5:
        t = row.get("title", "")
        if len(t) < 20:
            bottom_notes.append("Titles are too short")
        if not any(ch.isdigit() for ch in t):
            bottom_notes.append("Titles miss concrete numbers")

    retention_pattern = "Hook with 'Did you know that', 3-5 short numbered facts, CTA at the end"

    return {
        "top5_patterns": [
            {
                "avg_title_length": round(mean(top_title_lengths), 1) if top_title_lengths else 0,
                "title_pattern_counts": dict(top_patterns),
                "topic_counts": dict(top_topics),
                "post_hour_counts": dict(top_hours),
            }
        ],
        "bottom5_issues": sorted(set(bottom_notes)) or ["Collect more data to identify weak patterns"],
        "retention_script_pattern": retention_pattern,
    }


def _fetch_real_video_stats(video_ids: list[str]) -> dict[str, dict[str, int]]:
    """Fetch real views/likes/comments from YouTube Data API v3 using OAuth token.

    Returns {video_id: {"views": N, "likes": N, "comments": N}}.
    Falls back to empty dict on any auth/network error.
    """
    if not video_ids:
        return {}
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_file = ROOT / "config" / "youtube_token_facts.json"
        if not token_file.exists():
            return {}
        token_data = json.loads(token_file.read_text(encoding="utf-8"))
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes", []),
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        svc = build("youtube", "v3", credentials=creds)
        result: dict[str, dict[str, int]] = {}
        # Process in batches of 50 (API limit)
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            resp = svc.videos().list(
                part="statistics", id=",".join(batch)
            ).execute()
            for item in resp.get("items", []):
                stats = item.get("statistics", {})
                result[item["id"]] = {
                    "views": int(stats.get("viewCount", 0) or 0),
                    "likes": int(stats.get("likeCount", 0) or 0),
                    "comments": int(stats.get("commentCount", 0) or 0),
                }
        return result
    except Exception as exc:
        logger.warning("Could not fetch real video stats: %s", exc)
        return {}


def _enrich_registry_with_real_stats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pull live stats from YouTube API, merge into registry rows, and persist.

    Updates both the in-memory rows and rewrites the JSONL registry file so
    post-hour optimization and A/B comparisons use real view data.
    """
    ids = [r["video_id"] for r in rows if r.get("video_id")]
    if not ids:
        return rows
    stats = _fetch_real_video_stats(ids)
    if not stats:
        return rows
    updated = False
    for row in rows:
        vid = row.get("video_id")
        if vid and vid in stats:
            row["view_count"] = stats[vid]["views"]
            row["like_count"] = stats[vid]["likes"]
            row["comment_count"] = stats[vid]["comments"]
            updated = True
    if updated:
        try:
            REGISTRY_PATH.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                encoding="utf-8",
            )
            logger.info("Registry enriched with live stats for %d videos", len(stats))
        except Exception as exc:
            logger.warning("Could not persist enriched stats to registry: %s", exc)
    return rows


def _analyze_competitors() -> dict[str, Any]:
    """Run full competitor analysis via competitor_analyzer module.

    Returns a unified dict with popular_topics, hashtags, hook_phrases,
    title_templates, and power_words extracted from top-performing Shorts.
    """
    try:
        from src.competitor_analyzer import analyze as _ca_analyze
        insights = _ca_analyze()
    except Exception as exc:
        logger.warning("competitor_analyzer failed: %s — using baseline", exc)
        from src.competitor_analyzer import BASELINE_PATTERNS
        insights = dict(BASELINE_PATTERNS)
        insights["source"] = "baseline_error"

    return {
        "status": insights.get("source", "unknown"),
        "videos_analyzed": insights.get("videos_analyzed", 0),
        "popular_topics": insights.get("top_topics", ["space", "human body", "animals"])[:8],
        "hashtags": insights.get("top_hashtags", ["#Facts", "#DidYouKnow", "#Shorts"]),
        "hook_phrases": insights.get("hook_phrases", insights.get("top_hooks", [])),
        "title_templates": insights.get("title_templates", []),
        "power_words": insights.get("power_words", []),
        "pattern_counts": insights.get("pattern_counts", {}),
        "optimal_length_seconds": [55, 59],
    }


def _seasonal_topics() -> list[str]:
    month = datetime.now().month
    if month in (12,):
        return ["winter space phenomena", "holiday science myths"]
    if month in (6, 7, 8):
        return ["ocean facts", "sun and heat facts"]
    return ["space exploration", "human body mysteries", "extreme nature facts"]


def _analyze_trends_pytrends() -> list[str]:
    """Return trending science/facts keywords via pytrends. Empty list on failure."""
    if not _PYTRENDS_AVAILABLE:
        return []
    try:
        pt = _TrendReq(hl="en-US", tz=0, timeout=(10, 25), retries=2, backoff_factor=0.5)
        # Science/facts adjacent queries
        kw_groups = [
            ["science facts", "did you know", "amazing facts"],
            ["space facts", "nature facts", "human body facts"],
        ]
        trending: list[str] = []
        for kws in kw_groups:
            pt.build_payload(kws, timeframe="now 7-d", geo="US")
            related = pt.related_queries()
            for kw in kws:
                data = related.get(kw, {})
                rising = data.get("rising")
                if rising is not None and not rising.empty:
                    for q in rising["query"].head(3).tolist():
                        topic = re.sub(r"\bfacts?\b|\bscience\b|\bamazing\b", "", q, flags=re.I).strip()
                        if topic and len(topic) > 3:
                            trending.append(topic)
        # Also pull real-time trending searches
        try:
            rt = pt.realtime_trending_searches(pn="US")
            if rt is not None and not rt.empty and "title" in rt.columns:
                for t in rt["title"].head(5).tolist():
                    t = str(t).strip()
                    if t:
                        trending.append(t)
        except Exception:
            pass
        return list(dict.fromkeys(trending))[:10]  # dedupe, cap at 10
    except Exception as exc:
        logger.warning("pytrends failed: %s", exc)
        return []


def _analyze_trends() -> dict[str, Any]:
    google_topics: list[str] = []

    # Try pytrends first (richer data), fall back to RSS
    pytrends_topics = _analyze_trends_pytrends()

    try:
        rss_url = "https://trends.google.com/trending/rss?geo=US"
        resp = requests.get(rss_url, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        for item in root.findall("./channel/item/title")[:10]:
            title = (item.text or "").strip()
            if title:
                google_topics.append(title)
    except Exception as exc:
        logger.warning("Google Trends RSS fetch failed: %s", exc)

    yt_trending: list[str] = []
    try:
        api_key = config_facts.YOUTUBE_API_KEY or ""
        if api_key:
            from src.competitor_analyzer import _search_top_shorts
            hits = _search_top_shorts(api_key, "facts shorts", max_results=15)
            yt_trending = [h.get("title", "") for h in hits if h.get("title")]
    except Exception as exc:
        logger.warning("YouTube trend fetch failed: %s", exc)

    return {
        "google_trends": {
            "status": "ok" if google_topics else "fallback",
            "topics": google_topics or _seasonal_topics(),
        },
        "youtube_trending": {
            "status": "ok" if yt_trending else "heuristic",
            "topics": yt_trending or ["did you know", "science shorts", "nature shorts"],
        },
        "pytrends": {
            "status": "ok" if pytrends_topics else "unavailable",
            "topics": pytrends_topics,
        },
        "seasonal": _seasonal_topics(),
    }


def _compute_top_post_hours(rows: list[dict[str, Any]]) -> list[int]:
    """Return up to 5 best-performing post hours based on real view data.

    Falls back to config default if not enough data.
    """
    default = getattr(config_facts, "PREFERRED_POST_HOURS", [3, 7, 11, 15, 19])
    hour_views: dict[int, list[int]] = {}
    for row in rows:
        t = row.get("scheduled_time", "")
        views = int(row.get("view_count", 0) or 0)
        if t and ":" in t:
            try:
                h = int(t.split(":")[0])
                hour_views.setdefault(h, []).append(views)
            except ValueError:
                pass
    if not hour_views:
        return default
    avg_by_hour = {h: mean(vs) for h, vs in hour_views.items() if vs}
    top = sorted(avg_by_hour, key=lambda h: avg_by_hour[h], reverse=True)[:5]
    return sorted(top) if len(top) >= 3 else default


_COMPLAINT_KEYWORDS = [
    "loop", "loops", "looping", "repeat", "repeating", "repeated",
    "stuck", "freeze", "frozen", "glitch", "broken", "same clip",
    "same video", "same footage", "over and over", "keeps repeating",
    "keeps looping", "subtitle", "subtitles", "caption", "text",
    "can't read", "cannot read", "unreadable", "gibberish", "weird text",
]


def _check_youtube_comments_for_issues(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Fetch recent video comments and detect quality complaint patterns.

    Uses OAuth token (no separate API key needed) so it works without
    YOUTUBE_API_KEY_FACTS being configured.
    """
    recent_ids = [r["video_id"] for r in rows[-15:] if r.get("video_id")]
    if not recent_ids:
        return {"status": "no_videos", "complaints": []}

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_file = ROOT / "config" / "youtube_token_facts.json"
        if not token_file.exists():
            return {"status": "no_token", "complaints": []}
        token_data = json.loads(token_file.read_text(encoding="utf-8"))
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes", []),
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        svc = build("youtube", "v3", credentials=creds)
    except Exception as exc:
        logger.warning("Comment monitor: auth failed: %s", exc)
        return {"status": "auth_error", "complaints": []}

    complaints: list[dict[str, Any]] = []
    for vid_id in recent_ids[-8:]:  # Check last 8 videos
        try:
            resp = svc.commentThreads().list(
                part="snippet",
                videoId=vid_id,
                maxResults=30,
                order="relevance",
                textFormat="plainText",
            ).execute()
            for item in resp.get("items", []):
                text = (
                    item.get("snippet", {})
                    .get("topLevelComment", {})
                    .get("snippet", {})
                    .get("textDisplay", "")
                    .lower()
                )
                matched = [kw for kw in _COMPLAINT_KEYWORDS if kw in text]
                if matched:
                    complaints.append({
                        "video_id": vid_id,
                        "keywords": matched,
                        "comment": text[:300],
                    })
        except Exception as exc:
            logger.warning("Comment fetch failed for %s: %s", vid_id, exc)

    quality_alert = len(complaints) >= 2
    if quality_alert:
        logger.warning(
            "Quality complaints detected in %d comments across recent videos: %s",
            len(complaints),
            [c["keywords"] for c in complaints],
        )

    return {
        "status": "ok",
        "videos_checked": min(8, len(recent_ids)),
        "complaints_found": len(complaints),
        "quality_alert": quality_alert,
        "complaints": complaints,
    }


def _analyze_video_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Examine clip-quality metrics from recent registry entries.

    Returns a summary and, when quality is poor, suggestions for the next run.
    """
    recent = rows[-30:] if len(rows) > 30 else rows
    if not recent:
        return {"status": "no_data", "suggestions": []}

    real_clips_counts: list[int] = []
    lavfi_counts: list[int] = []
    static_skipped_counts: list[int] = []

    for row in recent:
        cq = row.get("clip_quality")
        if not isinstance(cq, dict):
            continue
        real_clips_counts.append(int(cq.get("real_clips", 0)))
        lavfi_counts.append(int(cq.get("lavfi_clips", 0)))
        static_skipped_counts.append(int(cq.get("static_skipped", 0)))

    if not real_clips_counts:
        return {"status": "legacy_entries_only", "suggestions": []}

    avg_real = mean(real_clips_counts) if real_clips_counts else 0
    avg_lavfi = mean(lavfi_counts) if lavfi_counts else 0
    avg_static_skip = mean(static_skipped_counts) if static_skipped_counts else 0
    lavfi_rate = avg_lavfi / max(1, avg_real + avg_lavfi)

    suggestions: list[str] = []
    if lavfi_rate > 0.3:
        suggestions.append(
            "High lavfi-fallback rate (%.0f%%) — expand search keywords or add "
            "more varied topics to improve real footage coverage." % (lavfi_rate * 100)
        )
    if avg_static_skip > 2:
        suggestions.append(
            "Avg %.1f static clips skipped per video — consider lowering "
            "MIN_SOURCE_HEIGHT or broadening keywords." % avg_static_skip
        )
    if avg_real < 10:
        suggestions.append(
            "Avg real clip count is low (%.1f) — consider adding PIXABAY_API_KEY "
            "or increasing MAX_SEARCH_URLS." % avg_real
        )

    return {
        "status": "ok",
        "avg_real_clips": round(avg_real, 1),
        "avg_lavfi_clips": round(avg_lavfi, 1),
        "avg_static_skipped": round(avg_static_skip, 1),
        "lavfi_rate_pct": round(lavfi_rate * 100, 1),
        "suggestions": suggestions,
    }


def _compose_changes(summary: dict[str, Any]) -> dict[str, Any]:
    competitor = summary.get("competitor", {})
    trends = summary.get("trends", {})
    internal = summary.get("internal", {})

    popular = competitor.get("popular_topics", [])
    seasonal = trends.get("seasonal", [])
    pytrends_topics = trends.get("pytrends", {}).get("topics", [])

    # Topics: pytrends (real-time) > competitor > seasonal
    all_topics = list(dict.fromkeys([*pytrends_topics, *popular, *seasonal]))
    merged_topics = ", ".join(all_topics[:8]) or config_facts.TOPIC_STYLE

    # Title templates: use competitor-learned templates, validated, fall back to defaults.
    # Must have a placeholder, be English, reasonable length, no duplicate {topic}.
    _GOOD_TEMPLATES = [
        "Did you know that {fact}? #Shorts",
        "{number} {topic} facts that will blow your mind #Shorts",
        "Scientists just discovered {topic} and it changes everything #Shorts",
        "Why {topic} is more {adjective} than you think #Shorts",
        "Only {number}% of people know this about {topic} #Shorts",
        "The real reason {topic} does this will shock you #Shorts",
        "What happens to your body when {scenario}? #Shorts",
        "{number} facts in {seconds} seconds #Shorts",
    ]
    raw_templates = competitor.get("title_templates", [])
    validated_templates = [
        t for t in raw_templates
        if t and t.isascii()
        and "{" in t
        and t.count("{topic}") <= 1
        and 4 <= len(t.split()) <= 14
    ]
    title_templates = validated_templates if len(validated_templates) >= 3 else _GOOD_TEMPLATES
    if internal.get("top5_patterns"):
        title_templates = list(dict.fromkeys(
            title_templates + ["{number} facts in {seconds} seconds #Shorts"]
        ))

    # Hook phrases: competitor-learned, validated, fall back to hardcoded.
    # Must be short (≤ 6 words), English-only, no hashtags, not a complete sentence.
    _GOOD_HOOKS = [
        "Did you know that",
        "Scientists just discovered",
        "Here's why most people don't know",
        "The shocking truth about",
        "What if I told you that",
        "Most people don't realize",
        "This will change how you see",
        "You won't believe what",
    ]
    raw_hooks = competitor.get("hook_phrases", [])
    validated_hooks = [
        h for h in raw_hooks
        if h and h.isascii()
        and 2 <= len(h.split()) <= 6
        and "#" not in h
        and not h[0].isdigit()
    ]
    hook_phrases = validated_hooks if len(validated_hooks) >= 3 else _GOOD_HOOKS

    rows = summary.get("_rows", [])
    best_hours = _compute_top_post_hours(rows)

    return {
        "LEARNED_TOPIC_STYLE": merged_topics,
        "LEARNED_TITLE_TEMPLATES": title_templates[:8],
        "LEARNED_HOOK_PHRASES": hook_phrases[:8],
        "LEARNED_HASHTAGS": competitor.get("hashtags", config_facts.SHORTS_HASHTAGS),
        "PREFERRED_POST_HOURS": best_hours,
    }


def _replace_managed_block(content: str, updates: dict[str, Any]) -> str:
    lines = [
        "# FACTS_BRAIN_MANAGED_START",
        f"LEARNED_TOPIC_STYLE = {json.dumps(updates['LEARNED_TOPIC_STYLE'])}",
        f"LEARNED_TITLE_TEMPLATES = {json.dumps(updates['LEARNED_TITLE_TEMPLATES'], ensure_ascii=False, indent=2)}",
        f"LEARNED_HOOK_PHRASES = {json.dumps(updates['LEARNED_HOOK_PHRASES'], ensure_ascii=False, indent=2)}",
        f"LEARNED_HASHTAGS = {json.dumps(updates['LEARNED_HASHTAGS'], ensure_ascii=False, indent=2)}",
        f"PREFERRED_POST_HOURS = {json.dumps(updates['PREFERRED_POST_HOURS'])}",
        "# FACTS_BRAIN_MANAGED_END",
    ]
    new_block = "\n".join(lines)
    pattern = r"# FACTS_BRAIN_MANAGED_START[\s\S]*?# FACTS_BRAIN_MANAGED_END"
    if re.search(pattern, content):
        return re.sub(pattern, new_block, content)
    return content + "\n\n" + new_block + "\n"


def _update_config_file(updates: dict[str, Any]) -> None:
    config_path = ROOT / "config_facts.py"
    content = config_path.read_text(encoding="utf-8")
    updated = _replace_managed_block(content, updates)
    config_path.write_text(updated, encoding="utf-8")


def _pick_ab_pair_from_registry() -> tuple[str, str] | None:
    """Pick two recently uploaded videos with different title patterns for A/B test.

    Prefers pairs where one uses "Did you know" and the other uses a different
    template, so the test is meaningful. Falls back to the two most recent videos.
    """
    rows = _load_registry()
    if len(rows) < 2:
        return None
    recent = rows[-40:]  # look back at last 40 uploads
    did_you_know = [r for r in recent if r.get("title", "").lower().startswith("did you know")]
    other = [r for r in recent if not r.get("title", "").lower().startswith("did you know")]
    # Prefer one "did you know" vs one "other" pair for a meaningful comparison
    if did_you_know and other:
        import random as _rnd
        return _rnd.choice(did_you_know)["title"], _rnd.choice(other)["title"]
    # Fallback: two most recent with different templates
    last = rows[-2:]
    if last[0].get("title") and last[1].get("title"):
        return last[0]["title"], last[1]["title"]
    return None


def _update_ab_tests() -> dict[str, Any]:
    now = _now_iso()
    tests = _load_json(AB_TEST_PATH, default=[])
    if not isinstance(tests, list):
        tests = []

    pair = _pick_ab_pair_from_registry()
    if pair:
        title_a, title_b = pair
    else:
        title_a = "Did you know that your brain uses 20% of your oxygen?"
        title_b = "Only 20% oxygen: the brain fact that surprises everyone"

    new_test = {
        "created_at": now,
        "title_a": title_a,
        "title_b": title_b,
        "compare_after_hours": 48,
        "status": "pending",
    }
    tests.append(new_test)

    rows = _load_registry()

    def _title_views(needle: str) -> int:
        needle_l = needle.lower()
        total = 0
        for row in rows:
            title = str(row.get("title", "")).lower()
            if needle_l[:18] in title:
                total += int(row.get("view_count", 0) or 0)
        return total

    for test in tests:
        if test.get("status") != "pending":
            continue
        created_at = test.get("created_at")
        try:
            created_dt = datetime.fromisoformat(created_at)
        except Exception:
            created_dt = datetime.now() - timedelta(hours=49)

        if datetime.now() - created_dt < timedelta(hours=48):
            continue

        views_a = _title_views(test.get("title_a", ""))
        views_b = _title_views(test.get("title_b", ""))
        winner = "title_a" if views_a >= views_b else "title_b"
        loser = "title_b" if winner == "title_a" else "title_a"

        test["status"] = "learned"
        test["winner"] = winner
        test["loser"] = loser
        test["views_a"] = views_a
        test["views_b"] = views_b
        test["reason"] = "Compared 48h view counts from facts upload registry"

    AB_TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    AB_TEST_PATH.write_text(json.dumps(tests, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "total_tests": len(tests),
        "latest_status": tests[-1].get("status") if tests else "none",
    }


def run_daily_analysis() -> AnalysisResult:
    logger.info("Starting facts brain analysis")

    rows = _load_registry()
    # Enrich registry rows with live YouTube stats (views/likes)
    rows = _enrich_registry_with_real_stats(rows)
    internal = _mine_internal_patterns(rows)
    competitor = _analyze_competitors()
    trends = _analyze_trends()

    summary = {
        "timestamp": _now_iso(),
        "internal": internal,
        "competitor": competitor,
        "trends": trends,
        "_rows": rows,  # passed to _compose_changes for hour optimization; stripped before saving
    }

    video_quality = _analyze_video_quality(rows)
    comment_monitor = _check_youtube_comments_for_issues(rows)
    changes = _compose_changes(summary)
    summary.pop("_rows", None)  # don't persist raw rows in report
    summary["video_quality"] = video_quality
    summary["comment_monitor"] = comment_monitor
    _update_config_file(changes)
    ab_result = _update_ab_tests()
    summary["ab_test"] = ab_result

    # Proactive daily growth sweep — runs autonomously every cycle
    try:
        from facts_scheduler import _authenticate_youtube
        from src.growth_engine import (
            update_channel_description,
            sync_all_playlists,
            _fetch_trending_keywords,
            _update_video_description,
        )
        _yt = _authenticate_youtube()

        # 1. Update channel description with today's trending keywords
        summary["channel_desc_updated"] = update_channel_description(_yt)

        # 2. Retroactive playlist sync — add any registry videos not yet in a playlist
        #    Runs weekly (checks last-sync date to avoid daily quota burn)
        last_sync_path = OUTPUT_ANALYTICS_DIR / "facts_playlist_sync_date.txt"
        today_str = datetime.now().strftime("%Y-%m-%d")
        last_sync = last_sync_path.read_text().strip() if last_sync_path.exists() else ""
        days_since = 999
        if last_sync:
            try:
                days_since = (datetime.now() - datetime.strptime(last_sync, "%Y-%m-%d")).days
            except Exception:
                pass
        if days_since >= 7:
            counts = sync_all_playlists(_yt, REGISTRY_PATH)
            summary["playlist_sync"] = counts
            last_sync_path.write_text(today_str)
            logger.info("Weekly playlist sync: %s", counts)

        # 3. Retroactive description refresh for the 3 most recent videos
        #    Injects fresh trending keywords so older videos stay discoverable
        trending = _fetch_trending_keywords()
        refreshed = 0
        for row in rows[-3:]:
            vid = row.get("video_id", "")
            if not vid:
                continue
            base_desc = row.get("description", "Amazing facts you can learn in under 60 seconds. Subscribe for daily science, space, and nature surprises.")
            if _update_video_description(_yt, vid, base_desc, trending):
                refreshed += 1
        summary["description_refreshed"] = refreshed
        logger.info("Proactive description refresh: %d videos updated", refreshed)

    except Exception as _growth_exc:
        logger.warning("Proactive growth sweep skipped: %s", _growth_exc)
        summary["channel_desc_updated"] = False

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "analysis_summary": {
            "internal": {
                "top5_patterns": internal.get("top5_patterns", []),
                "bottom5_issues": internal.get("bottom5_issues", []),
            },
            "competitor_topics": competitor.get("popular_topics", []),
            "trends": trends.get("seasonal", []),
        },
        "changed_settings": changes,
        "change_reason": "Adopt top performing topics, hashtags, and posting windows from latest analysis",
        "post_change_performance": {
            "status": "pending",
            "note": "Will be updated after next publish cycle",
        },
    }
    _append_json_list(BRAIN_LOG_PATH, entry)

    logger.info("Facts brain analysis completed")
    return AnalysisResult(summary=summary, config_changes=changes, reason=entry["change_reason"])


def run_daily_analysis_safe() -> dict[str, Any]:
    try:
        result = run_daily_analysis()
        return {
            "ok": True,
            "summary": result.summary,
            "config_changes": result.config_changes,
            "reason": result.reason,
        }
    except Exception as exc:
        logger.exception("facts brain analysis failed")
        return {"ok": False, "error": str(exc)}


def latest_report() -> dict[str, Any]:
    return _load_json(REPORT_PATH, default={})


def brain_log() -> list[dict[str, Any]]:
    log = _load_json(BRAIN_LOG_PATH, default=[])
    return log if isinstance(log, list) else []


def format_latest_report() -> str:
    report = latest_report()
    if not report:
        return "No facts analysis report found. Run: py main.py facts-analyze"

    internal = report.get("internal", {})
    competitor = report.get("competitor", {})
    trends = report.get("trends", {})

    lines = [
        f"Report timestamp: {report.get('timestamp', 'unknown')}",
        "",
        "Internal performance:",
        f"- Top patterns: {json.dumps(internal.get('top5_patterns', []), ensure_ascii=False)}",
        f"- Bottom issues: {', '.join(internal.get('bottom5_issues', []))}",
        "",
        "Competitor market:",
        f"- Popular topics: {', '.join(competitor.get('popular_topics', []))}",
        f"- Hashtags: {' '.join(competitor.get('hashtags', []))}",
        "",
        "Trend insights:",
        f"- Seasonal topics: {', '.join(trends.get('seasonal', []))}",
    ]
    return "\n".join(lines)


def format_brain_log() -> str:
    entries = brain_log()
    if not entries:
        return "No brain log found yet."

    latest = entries[-10:]
    lines = ["Facts brain evolution log (latest 10):"]
    for item in latest:
        lines.append(f"- {item.get('date')}: {item.get('change_reason', '')}")
    return "\n".join(lines)
