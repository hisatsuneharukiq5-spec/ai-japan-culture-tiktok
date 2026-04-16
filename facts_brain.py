"""AI analysis and evolution engine for Facts & Wonders."""

from __future__ import annotations

import json
import logging
import os
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
    """Pull live stats from YouTube API and merge into registry rows in-place."""
    ids = [r["video_id"] for r in rows if r.get("video_id")]
    if not ids:
        return rows
    stats = _fetch_real_video_stats(ids)
    if not stats:
        return rows
    for row in rows:
        vid = row.get("video_id")
        if vid and vid in stats:
            row["view_count"] = stats[vid]["views"]
            row["like_count"] = stats[vid]["likes"]
            row["comment_count"] = stats[vid]["comments"]
    return rows


def _youtube_search(api_key: str, query: str, max_results: int = 10) -> list[dict[str, Any]]:
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "order": "viewCount",
        "key": api_key,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return [
        {
            "title": item.get("snippet", {}).get("title", ""),
            "channel": item.get("snippet", {}).get("channelTitle", ""),
            "publishedAt": item.get("snippet", {}).get("publishedAt", ""),
        }
        for item in items
    ]


def _analyze_competitors() -> dict[str, Any]:
    api_key = config_facts.YOUTUBE_API_KEY or ""
    queries = [
        "amazing facts shorts",
        "did you know facts",
        "science facts shorts",
        "nature facts shorts",
    ]

    if not api_key:
        return {
            "status": "skipped",
            "reason": "YOUTUBE_API_KEY_FACTS is not set",
            "title_patterns": ["Did you know", "Number-led headline"],
            "popular_topics": ["space", "human body", "animals"],
            "hashtags": ["#Facts", "#DidYouKnow", "#Shorts"],
            "optimal_length_seconds": [55, 59],
            "thumbnail_style": "Bold center text with bright contrast",
        }

    all_titles: list[str] = []
    raw: dict[str, Any] = {}
    for q in queries:
        try:
            items = _youtube_search(api_key, q)
            raw[q] = items
            all_titles.extend(i["title"] for i in items)
        except Exception as exc:
            logger.warning("Competitor query failed for %s: %s", q, exc)
            raw[q] = []

    title_patterns = Counter(_title_pattern(t) for t in all_titles)
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", " ".join(all_titles).lower())
    topic_counts = Counter(w for w in words if w in {"space", "science", "animal", "nature", "human", "brain", "earth"})

    return {
        "status": "ok",
        "raw": raw,
        "title_patterns": dict(title_patterns),
        "popular_topics": [k for k, _ in topic_counts.most_common(5)] or ["science", "space"],
        "hashtags": ["#Facts", "#DidYouKnow", "#AmazingFacts", "#Science", "#Nature", "#Shorts"],
        "optimal_length_seconds": [55, 59],
        "thumbnail_style": "Bright colorful b-roll with large center captions",
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
            yt_items = _youtube_search(api_key, "facts shorts", max_results=15)
            yt_trending = [i.get("title", "") for i in yt_items if i.get("title")]
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


def _compose_changes(summary: dict[str, Any]) -> dict[str, Any]:
    competitor = summary.get("competitor", {})
    trends = summary.get("trends", {})
    internal = summary.get("internal", {})

    popular = competitor.get("popular_topics", [])
    seasonal = trends.get("seasonal", [])
    pytrends_topics = trends.get("pytrends", {}).get("topics", [])

    # Merge topic sources: pytrends (real-time) > internal top performers > competitor > seasonal
    all_topics = list(dict.fromkeys([*pytrends_topics, *popular, *seasonal]))
    merged_topics = ", ".join(all_topics[:8]) or config_facts.TOPIC_STYLE

    title_patterns = [
        "Did you know that {fact}?",
        "Only {number}% of people know this",
    ]
    if internal.get("top5_patterns"):
        title_patterns.append("{number} facts in {seconds} seconds")

    rows = summary.get("_rows", [])
    best_hours = _compute_top_post_hours(rows)

    return {
        "LEARNED_TOPIC_STYLE": merged_topics,
        "LEARNED_TITLE_PATTERNS": title_patterns,
        "LEARNED_HASHTAGS": competitor.get("hashtags", config_facts.SHORTS_HASHTAGS),
        "PREFERRED_POST_HOURS": best_hours,
    }


def _replace_managed_block(content: str, updates: dict[str, Any]) -> str:
    lines = [
        "# FACTS_BRAIN_MANAGED_START",
        f"LEARNED_TOPIC_STYLE = {json.dumps(updates['LEARNED_TOPIC_STYLE'])}",
        f"LEARNED_TITLE_PATTERNS = {json.dumps(updates['LEARNED_TITLE_PATTERNS'], ensure_ascii=False, indent=2)}",
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


def _update_ab_tests(summary: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    tests = _load_json(AB_TEST_PATH, default=[])
    if not isinstance(tests, list):
        tests = []

    new_test = {
        "created_at": now,
        "title_a": "Did you know that your brain uses 20% of your oxygen?",
        "title_b": "Only 20% oxygen: the brain fact that surprises everyone",
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

    changes = _compose_changes(summary)
    summary.pop("_rows", None)  # don't persist raw rows in report
    _update_config_file(changes)
    ab_result = _update_ab_tests(summary)
    summary["ab_test"] = ab_result

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
