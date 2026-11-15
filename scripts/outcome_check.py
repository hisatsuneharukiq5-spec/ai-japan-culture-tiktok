"""Outcome watchdog: is each channel actually PUBLISHING, not just "running"?

For every channel in config/watchdog.yaml it reads (read-only) the newest
PUBLIC video's publish time via the YouTube Data API and flags the channel as
ABNORMAL when that is older than the threshold (default 36h).

It also surfaces expiry problems early: if the OAuth token can no longer be
refreshed, the channel is reported as ABNORMAL with category "auth".

Read-only guarantees:
- API calls: channels.list, playlistItems.list, videos.list (≈3 quota units/channel).
- The token file is NEVER written; a refreshed access token lives in memory only.
- No uploads, edits, comments. Secrets and channel IDs are never printed.

Usage:
  python scripts/outcome_check.py                # threshold from config
  python scripts/outcome_check.py --max-hours 48 # override
  WATCHDOG_MAX_HOURS=48 python scripts/outcome_check.py
Exit code: 0 = all OK, 1 = at least one ABNORMAL, 2 = config/runtime error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "config" / "watchdog.yaml"


def _load_config() -> dict[str, Any]:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("outcome_check", {})


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _build_client(token_file: Path):
    """Load existing OAuth token read-only; refresh in memory if needed."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not token_file.exists():
        raise PermissionError(f"token file missing: {token_file.relative_to(ROOT)}")
    creds = Credentials.from_authorized_user_file(str(token_file))
    if not creds.valid:
        if not creds.refresh_token:
            raise PermissionError("token has no refresh_token (re-auth required)")
        try:
            creds.refresh(Request())  # in memory only — file is not rewritten
        except RefreshError as exc:
            # str(exc) contains only the OAuth error code (e.g. invalid_grant), no secrets.
            raise PermissionError(f"token refresh failed: {str(exc)[:120]}") from exc
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def check_channel(ch: dict[str, Any], max_hours: float, scan: int, now: datetime) -> dict[str, Any]:
    result: dict[str, Any] = {
        "key": ch["key"],
        "label": ch.get("label", ch["key"]),
        "max_hours": max_hours,
        "status": "ABNORMAL",
        "category": None,
        "reason": "",
        "channel_name": None,
        "channel_id_matches_env": None,
        "latest_public_title": None,
        "latest_public_at": None,
        "hours_since_latest_public": None,
        "scheduled_not_yet_public": 0,
        "recent_uploads_scanned": 0,
    }
    try:
        yt = _build_client(ROOT / ch["token_file"])
    except PermissionError as exc:
        result.update(category="auth", reason=str(exc))
        return result

    try:
        chan = yt.channels().list(part="snippet,contentDetails", mine=True, maxResults=1).execute()
        items = chan.get("items") or []
        if not items:
            result.update(category="auth", reason="authenticated account has no channel")
            return result
        item = items[0]
        name = item["snippet"]["title"]
        result["channel_name"] = name
        expected = (ch.get("expected_name_contains") or "").lower()
        if expected and expected not in name.lower():
            result.update(category="wrong_channel", reason=f"token belongs to '{name}', expected '*{ch['expected_name_contains']}*'")
            return result
        env_name = ch.get("expected_channel_id_env")
        env_id = (os.getenv(env_name, "") if env_name else "").strip()
        if env_id:
            result["channel_id_matches_env"] = item["id"] == env_id
            if not result["channel_id_matches_env"]:
                result.update(category="wrong_channel", reason=f"channel id differs from {env_name}")
                return result

        uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]
        pl = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=min(50, scan)).execute()
        ids = [p["contentDetails"]["videoId"] for p in pl.get("items", [])]
        result["recent_uploads_scanned"] = len(ids)
        if not ids:
            result.update(category="no_output", reason="channel has no uploads")
            return result

        vids = yt.videos().list(part="snippet,status", id=",".join(ids), maxResults=50).execute().get("items", [])
        public = [v for v in vids if v["status"].get("privacyStatus") == "public"]
        result["scheduled_not_yet_public"] = sum(1 for v in vids if v["status"].get("publishAt") and v["status"].get("privacyStatus") != "public")
        if not public:
            result.update(category="no_output", reason=f"none of the last {len(ids)} uploads is public")
            return result

        latest = max(public, key=lambda v: _parse_ts(v["snippet"]["publishedAt"]))
        latest_at = _parse_ts(latest["snippet"]["publishedAt"])
        hours = (now - latest_at).total_seconds() / 3600
        result.update(
            latest_public_title=latest["snippet"]["title"],
            latest_public_at=latest_at.isoformat().replace("+00:00", "Z"),
            hours_since_latest_public=round(hours, 1),
        )
        if hours > max_hours:
            result.update(category="no_output", reason=f"last public video {hours:.1f}h ago (> {max_hours:g}h)")
        else:
            result.update(status="OK", category=None, reason=f"last public video {hours:.1f}h ago")
        return result
    except Exception as exc:  # API / network errors
        msg = _describe_error(exc)
        if "quotaExceeded" in msg or "dailyLimitExceeded" in msg:
            cat = "quota"
        elif any(s in msg for s in ("invalid_grant", "unauthorized", "401", "insufficientPermissions", "forbidden")):
            cat = "auth"
        else:
            cat = "api_error"
        result.update(category=cat, reason=msg[:300])
        return result


def _describe_error(exc: Exception) -> str:
    """Human-readable error WITHOUT the request URL (it embeds playlist/channel IDs)."""
    try:
        from googleapiclient.errors import HttpError
    except Exception:  # pragma: no cover
        HttpError = ()  # type: ignore[assignment]
    if isinstance(exc, HttpError):
        status = getattr(exc, "status_code", None) or getattr(exc.resp, "status", "?")
        details = getattr(exc, "error_details", None) or []
        codes = ",".join(sorted({d.get("reason", "") for d in details if isinstance(d, dict) and d.get("reason")}))
        import re
        text = re.sub(r"<[^>]+>", "", str(exc._get_reason()))
        return f"HTTP {status} {codes} — {text}".strip()
    return f"{type(exc).__name__}: {exc}"


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")  # only to read optional *_CHANNEL_ID names; values never printed
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-hours", type=float, default=None, help="override threshold for all channels")
    ap.add_argument("--output", default=None, help="override JSON output path")
    args = ap.parse_args(argv)

    try:
        cfg = _load_config()
        channels = cfg["channels"]
    except Exception as exc:
        print(f"[watchdog] config error: {exc}", file=sys.stderr)
        return 2

    override = args.max_hours if args.max_hours is not None else (float(os.environ["WATCHDOG_MAX_HOURS"]) if os.getenv("WATCHDOG_MAX_HOURS") else None)
    default_hours = float(cfg.get("default_max_hours", 36))
    scan = int(cfg.get("scan_recent_uploads", 25))
    now = datetime.now(timezone.utc)

    results = []
    for ch in channels:
        max_hours = override if override is not None else float(ch.get("max_hours", default_hours))
        results.append(check_channel(ch, max_hours, scan, now))

    overall = "OK" if all(r["status"] == "OK" for r in results) else "ABNORMAL"
    report = {"checked_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"), "overall": overall, "channels": results}

    out = ROOT / (args.output or cfg.get("output_file", "output/analytics/outcome_check.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[watchdog] outcome check at {report['checked_at']} — overall: {overall}")
    for r in results:
        mark = "OK " if r["status"] == "OK" else "NG "
        cat = f" [{r['category']}]" if r["category"] else ""
        print(f"  [{mark}] {r['label']}{cat}: {r['reason']}")
        if r["latest_public_title"]:
            print(f"        latest public: {r['latest_public_at']}  \"{r['latest_public_title'][:70]}\"")
        if r["scheduled_not_yet_public"]:
            print(f"        scheduled (not yet public): {r['scheduled_not_yet_public']}")
    print(f"  report: {out.relative_to(ROOT)}")
    return 0 if overall == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
