"""YouTube Data API v3 daily quota tracker.

Quota resets at midnight Pacific Time (≈ 09:00 JST).
Default daily budget: 10,000 units.

Costs (from YouTube API docs):
  videos.insert           = 1600
  search.list             = 100
  videos.list             = 1
  videos.update           = 50
  commentThreads.insert   = 50
  commentThreads.list     = 1
  playlists.insert        = 50
  playlists.list          = 1
  playlistItems.insert    = 50
  channels.list           = 1
  channels.update         = 50
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("quota_guard")

ROOT = Path(__file__).resolve().parent.parent
_QUOTA_FILE = ROOT / "output" / "analytics" / "facts_quota_today.json"

# Daily budget — leave 500 units as safety margin
DAILY_BUDGET = 9_500

COST = {
    "videos.insert": 1600,
    "search.list": 100,
    "videos.list": 1,
    "videos.update": 50,
    "commentThreads.insert": 50,
    "commentThreads.list": 1,
    "playlists.insert": 50,
    "playlists.list": 1,
    "playlistItems.insert": 50,
    "channels.list": 1,
    "channels.update": 50,
}


def _quota_reset_date() -> str:
    """Quota resets at 09:00 JST (00:00 Pacific). Returns the current quota-day as YYYY-MM-DD."""
    now_utc = datetime.now(timezone.utc)
    # Subtract 9 hours so the "day" rolls over at 09:00 JST
    from datetime import timedelta
    adjusted = now_utc - timedelta(hours=9)
    return adjusted.strftime("%Y-%m-%d")


def _load() -> dict:
    if not _QUOTA_FILE.exists():
        return {}
    try:
        return json.loads(_QUOTA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    _QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _QUOTA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def used_today() -> int:
    """Units consumed so far today."""
    data = _load()
    today = _quota_reset_date()
    if data.get("date") != today:
        return 0
    return int(data.get("used", 0))


def remaining() -> int:
    return max(0, DAILY_BUDGET - used_today())


def charge(operation: str, count: int = 1) -> int:
    """Record quota consumption. Returns units charged."""
    units = COST.get(operation, 50) * count
    data = _load()
    today = _quota_reset_date()
    if data.get("date") != today:
        data = {"date": today, "used": 0, "log": []}
    data["used"] = int(data.get("used", 0)) + units
    data.setdefault("log", []).append({"op": operation, "units": units, "ts": datetime.now().isoformat(timespec="seconds")})
    _save(data)
    logger.debug("Quota: charged %d for %s (total today: %d)", units, operation, data["used"])
    return units


def can_afford(operation: str, count: int = 1) -> bool:
    cost = COST.get(operation, 50) * count
    ok = remaining() >= cost
    if not ok:
        logger.warning("Quota low: skipping %s (need %d, have %d)", operation, cost, remaining())
    return ok


def status_line() -> str:
    u = used_today()
    return f"quota: {u}/{DAILY_BUDGET} used ({remaining()} remaining)"
