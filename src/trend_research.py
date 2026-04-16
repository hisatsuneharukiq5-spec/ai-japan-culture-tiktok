"""Lightweight trend research for autonomous mode.

Free-first approach: uses local topics list and recent analytics to propose candidate topics.
"""
from src.utils import get_all_topics, setup_logger, PROJECT_ROOT
from pathlib import Path
import json
import re

logger = setup_logger("trend_research")


def _load_recent_titles(limit=50):
    # Read analytics_timeseries to find recent video titles from metadata_verification
    ver = PROJECT_ROOT / "output" / "metadata_verification.json"
    if not ver.exists():
        return []
    try:
        with open(ver, "r", encoding="utf-8") as f:
            arr = json.load(f)
        titles = [a.get("title", "") for a in arr][:limit]
        return [t for t in titles if t]
    except Exception as e:
        logger.warning(f"Could not load recent titles: {e}")
        return []


def _tokenize_title(t: str):
    words = re.findall(r"[A-Za-z0-9%\u3000-\u30FF\u4E00-\u9FFF]{3,}", t)
    return [w.lower() for w in words]


def get_candidate_topics(limit: int = 10) -> list[dict]:
    """Return list of candidate topics with simple scores and reasons.

    Each item: {"topic": str, "score": float, "reason": str}
    """
    base_topics = get_all_topics()
    recent = _load_recent_titles()

    # Score base topics by appearance in recent titles
    scores = {}
    for t in base_topics:
        scores[t] = 0.1  # baseline

    for title in recent:
        toks = _tokenize_title(title)
        for t in base_topics:
            if any(tok in t.lower() or t.lower() in " ".join(toks) for tok in toks):
                scores[t] = scores.get(t, 0.1) + 1.0

    # Also include recent title n-grams as possible candidates
    extra = []
    for title in recent:
        if len(extra) >= limit:
            break
        extra.append({"topic": title, "score": 0.5, "reason": "recent top title"})

    ranked = sorted([{"topic": t, "score": s, "reason": "matches recent titles"} for t, s in scores.items()], key=lambda x: -x["score"])[:limit]
    # Merge unique extras
    out = []
    seen = set()
    for r in ranked:
        out.append(r)
        seen.add(r["topic"])
    for e in extra:
        if e["topic"] not in seen and len(out) < limit:
            out.append(e)
            seen.add(e["topic"])

    logger.info(f"Generated {len(out)} candidate topics")
    return out
