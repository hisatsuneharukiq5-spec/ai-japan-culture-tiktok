"""Expiry watchdog: read config/expiry_ledger.yaml and list what needs attention.

Sections printed:
  1. EXPIRED / BROKEN   — status expired|broken, or `expires` already passed
  2. EXPIRING SOON      — `expires` within warn_within_days (config/watchdog.yaml, default 30)
  3. EXPIRY UNKNOWN     — `expires` is null (shows how to check)
  4. STALE              — last_verified older than --stale-days (default 30)
Items with status "unused" are listed separately and never cause a failure.

The ledger never contains secret values, and this script reads nothing else.

Usage:
  python scripts/expiry_check.py [--days 30] [--stale-days 30] [--json out.json]
Exit code: 0 = nothing expired/expiring, 1 = something expired/broken/expiring, 2 = ledger error.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_CONFIG = ROOT / "config" / "watchdog.yaml"
REQUIRED = ("id", "kind", "name", "status")


def _as_date(value: Any) -> date | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _load() -> tuple[list[dict[str, Any]], int, Path]:
    cfg = {}
    if WATCHDOG_CONFIG.exists():
        cfg = (yaml.safe_load(WATCHDOG_CONFIG.read_text(encoding="utf-8")) or {}).get("expiry_check", {})
    ledger_path = ROOT / cfg.get("ledger_file", "config/expiry_ledger.yaml")
    items = (yaml.safe_load(ledger_path.read_text(encoding="utf-8")) or {}).get("items", [])
    return items, int(cfg.get("warn_within_days", 30)), ledger_path


def classify(items: list[dict[str, Any]], today: date, warn_days: int, stale_days: int) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {"expired_or_broken": [], "expiring_soon": [], "unknown": [], "unused": [], "stale": [], "invalid": []}
    seen: set[str] = set()
    for it in items:
        missing = [k for k in REQUIRED if not it.get(k)]
        if missing or it.get("id") in seen:
            out["invalid"].append({"id": it.get("id"), "problem": f"missing {missing}" if missing else "duplicate id"})
            continue
        seen.add(it["id"])
        exp = _as_date(it.get("expires"))
        verified = _as_date(it.get("last_verified"))
        row = {
            "id": it["id"], "kind": it["kind"], "name": it["name"], "status": it["status"],
            "expires": exp.isoformat() if exp else None,
            "days_left": (exp - today).days if exp else None,
            "last_verified": verified.isoformat() if verified else None,
            "check": " ".join(str(it.get("check", "")).split()),
            "workflows": it.get("workflows") or [],
        }
        if it["status"] == "unused":
            out["unused"].append(row)
            continue
        if it["status"] in ("expired", "broken") or (exp and exp < today):
            out["expired_or_broken"].append(row)
        elif exp and (exp - today).days <= warn_days:
            out["expiring_soon"].append(row)
        elif exp is None:
            out["unknown"].append(row)
        if verified is None or (today - verified).days > stale_days:
            out["stale"].append(row)
    out["expiring_soon"].sort(key=lambda r: r["days_left"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=None, help="warn window in days (default from config, 30)")
    ap.add_argument("--stale-days", type=int, default=30, help="flag items not verified for this many days")
    ap.add_argument("--json", default=None, help="also write the result to this JSON file")
    args = ap.parse_args(argv)

    try:
        items, warn_days, ledger_path = _load()
    except Exception as exc:
        print(f"[expiry] ledger error: {exc}", file=sys.stderr)
        return 2
    if args.days is not None:
        warn_days = args.days

    today = date.today()
    res = classify(items, today, warn_days, args.stale_days)
    ci = lambda r: f" (CI: {', '.join(r['workflows'])})" if r["workflows"] else " (local only)"

    print(f"[expiry] {ledger_path.relative_to(ROOT)} — {len(items)} items, today {today}, window {warn_days}d")
    print(f"\n== EXPIRED / BROKEN ({len(res['expired_or_broken'])}) ==")
    for r in res["expired_or_broken"]:
        when = f" expired {r['expires']}" if r["expires"] else ""
        print(f"  ! {r['id']} [{r['kind']}/{r['status']}]{when}{ci(r)}\n      {r['name']}\n      fix/check: {r['check']}")
    print(f"\n== EXPIRING WITHIN {warn_days} DAYS ({len(res['expiring_soon'])}) ==")
    for r in res["expiring_soon"]:
        print(f"  ~ {r['id']} [{r['kind']}] {r['expires']} ({r['days_left']}d left){ci(r)}\n      {r['name']}")
    print(f"\n== EXPIRY UNKNOWN ({len(res['unknown'])}) — how to check ==")
    for r in res["unknown"]:
        print(f"  ? {r['id']} [{r['kind']}]{ci(r)}\n      {r['check'][:230]}")
    if res["stale"]:
        print(f"\n== NOT VERIFIED FOR >{args.stale_days} DAYS ({len(res['stale'])}) ==")
        for r in res["stale"]:
            print(f"  - {r['id']} (last_verified {r['last_verified']})")
    print(f"\n== UNUSED (info) ({len(res['unused'])}) == " + ", ".join(r["id"] for r in res["unused"]))
    if res["invalid"]:
        print(f"\n== INVALID LEDGER ENTRIES ({len(res['invalid'])}) ==")
        for r in res["invalid"]:
            print(f"  x {r['id']}: {r['problem']}")

    if args.json:
        p = ROOT / args.json
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"checked_on": today.isoformat(), "warn_within_days": warn_days, **res}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  report: {args.json}")

    if res["invalid"]:
        return 2
    return 1 if (res["expired_or_broken"] or res["expiring_soon"]) else 0


if __name__ == "__main__":
    sys.exit(main())
