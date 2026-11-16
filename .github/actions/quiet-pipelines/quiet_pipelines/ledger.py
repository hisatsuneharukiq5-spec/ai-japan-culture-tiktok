"""Expiry ledger: the external things a pipeline silently depends on.

Each item (names and locations only — never values):
  id (required), kind (required), name (required), status (default active)
  expires: YYYY-MM-DD | null      last_verified: YYYY-MM-DD | null
  used_by: [...], workflows: [...], check: "how to verify / find the expiry", note
status: active | expired | broken | unused
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

REQUIRED = ("id", "kind", "name")
STATUSES = {"active", "expired", "broken", "unused"}


@dataclass
class LedgerReport:
    checked_on: str
    warn_within_days: int
    expired_or_broken: list[dict] = field(default_factory=list)
    expiring_soon: list[dict] = field(default_factory=list)
    unknown: list[dict] = field(default_factory=list)
    stale: list[dict] = field(default_factory=list)
    unused: list[dict] = field(default_factory=list)
    invalid: list[dict] = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        return bool(self.expired_or_broken or self.expiring_soon)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def as_date(value: Any) -> date | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def evaluate(items: list[dict], today: date, warn_within_days: int = 30, stale_after_days: int | None = 30) -> LedgerReport:
    rep = LedgerReport(checked_on=today.isoformat(), warn_within_days=warn_within_days)
    seen: set[str] = set()
    for it in items or []:
        missing = [k for k in REQUIRED if not it.get(k)]
        status = it.get("status", "active")
        problem = None
        if missing:
            problem = f"missing {', '.join(missing)}"
        elif it["id"] in seen:
            problem = "duplicate id"
        elif status not in STATUSES:
            problem = f"unknown status {status!r}"
        try:
            exp, verified = as_date(it.get("expires")), as_date(it.get("last_verified"))
        except ValueError:
            problem = problem or "bad date (use YYYY-MM-DD)"
            exp = verified = None
        if problem:
            rep.invalid.append({"id": it.get("id"), "problem": problem})
            continue
        seen.add(it["id"])

        row = {
            "id": it["id"], "kind": it["kind"], "name": it["name"], "status": status,
            "expires": exp.isoformat() if exp else None,
            "days_left": (exp - today).days if exp else None,
            "last_verified": verified.isoformat() if verified else None,
            "check": " ".join(str(it.get("check", "")).split()),
            "workflows": list(it.get("workflows") or []),
        }
        if status == "unused":
            rep.unused.append(row)
            continue
        if status in ("expired", "broken") or (exp and exp < today):
            rep.expired_or_broken.append(row)
        elif exp and (exp - today).days <= warn_within_days:
            rep.expiring_soon.append(row)
        elif exp is None:
            rep.unknown.append(row)
        if stale_after_days is not None and (verified is None or (today - verified).days > stale_after_days):
            rep.stale.append(row)
    rep.expiring_soon.sort(key=lambda r: r["days_left"])
    return rep
