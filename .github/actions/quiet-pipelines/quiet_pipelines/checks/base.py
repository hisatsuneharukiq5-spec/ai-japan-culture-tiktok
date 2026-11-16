"""Common types for outcome checks.

A check answers one question: "when did this pipeline last PRODUCE something?"
It returns a CheckResult; it never raises for expected failures (network, auth,
quota) — those become a status with a category so they can be reported.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, ClassVar

import requests

# Status values
OK = "ok"
ABNORMAL = "abnormal"

# Categories (why a check is abnormal)
NO_OUTPUT = "no_output"        # works, but nothing new within the threshold
AUTH = "auth"                  # expired / revoked / wrong credentials
QUOTA = "quota"                # rate limit or daily quota exhausted
UNREACHABLE = "unreachable"    # DNS / timeout / 5xx
CONFIG = "config"              # bad settings in quiet-pipelines.yml / missing env
API_ERROR = "api_error"        # unexpected API response


@dataclass
class CheckResult:
    name: str
    type: str
    status: str
    category: str | None = None
    message: str = ""
    latest_at: str | None = None       # ISO-8601 UTC of the newest output found
    age_hours: float | None = None
    max_age_hours: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == OK

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CheckError(Exception):
    """Raised inside a check to end it with a given category."""

    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category
        self.message = message


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def require_env(name: str | None, what: str) -> str:
    if not name:
        raise CheckError(CONFIG, f"{what}: env var name not configured")
    value = os.environ.get(name, "").strip()
    if not value:
        raise CheckError(CONFIG, f"{what}: env var {name} is empty or not set")
    return value


def http_error_category(status: int, body: str = "") -> str:
    low = body.lower()
    if status == 429 or "quotaexceeded" in low or "ratelimitexceeded" in low or "dailylimitexceeded" in low:
        return QUOTA
    if status in (401,) or "invalid_grant" in low or "unauthorized" in low or "invalid_token" in low:
        return AUTH
    if status == 403:
        return AUTH  # forbidden without a quota reason = permission / revoked
    if status >= 500:
        return UNREACHABLE
    return API_ERROR


class BaseCheck:
    """Subclass, set `type_name`, implement `latest_output()`.

    `latest_output()` returns (datetime_of_newest_output, details) or raises CheckError.
    The base class turns that into an OK / ABNORMAL result against max_age_hours.
    """

    type_name: ClassVar[str] = ""
    required: ClassVar[tuple[str, ...]] = ()

    def __init__(self, name: str, params: dict[str, Any], session: requests.Session | None = None,
                 now: Callable[[], datetime] | None = None, timeout: float = 20.0):
        self.name = name
        self.params = params
        self.session = session or requests.Session()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.timeout = timeout

    # -- to implement -----------------------------------------------------
    def latest_output(self) -> tuple[datetime, dict[str, Any]]:  # pragma: no cover - abstract
        raise NotImplementedError

    # -- helpers ----------------------------------------------------------
    def get(self, url: str, **kw: Any) -> requests.Response:
        kw.setdefault("timeout", self.timeout)
        try:
            return self.session.get(url, **kw)
        except requests.RequestException as exc:
            raise CheckError(UNREACHABLE, f"request failed: {type(exc).__name__}") from exc

    def post(self, url: str, **kw: Any) -> requests.Response:
        kw.setdefault("timeout", self.timeout)
        try:
            return self.session.post(url, **kw)
        except requests.RequestException as exc:
            raise CheckError(UNREACHABLE, f"request failed: {type(exc).__name__}") from exc

    def expect_ok(self, resp: requests.Response, what: str) -> requests.Response:
        if resp.status_code >= 400:
            body = (resp.text or "")[:500]
            raise CheckError(http_error_category(resp.status_code, body), f"{what}: HTTP {resp.status_code} {_short_reason(body)}")
        return resp

    # -- runner -----------------------------------------------------------
    def run(self) -> CheckResult:
        max_age = float(self.params.get("max_age_hours", 36))
        result = CheckResult(name=self.name, type=self.type_name, status=ABNORMAL, max_age_hours=max_age)
        missing = [k for k in self.required if self.params.get(k) in (None, "")]
        if missing:
            result.category, result.message = CONFIG, f"missing parameter(s): {', '.join(missing)}"
            return result
        try:
            latest, details = self.latest_output()
        except CheckError as exc:
            result.category, result.message = exc.category, exc.message
            return result
        except Exception as exc:  # unexpected bug in a check: report, don't crash the run
            result.category, result.message = API_ERROR, f"{type(exc).__name__}: {str(exc)[:200]}"
            return result

        age = (self.now() - latest).total_seconds() / 3600
        result.latest_at, result.age_hours, result.details = iso(latest), round(age, 1), details
        if age > max_age:
            result.category = NO_OUTPUT
            result.message = f"newest output is {age:.1f}h old (threshold {max_age:g}h)"
        else:
            result.status, result.message = OK, f"newest output is {age:.1f}h old"
        return result


def _short_reason(body: str) -> str:
    """Pull a short machine reason out of a JSON error body without echoing the whole body."""
    import json
    try:
        data = json.loads(body)
    except ValueError:
        return ""
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        reasons = [e.get("reason") for e in err.get("errors", []) if isinstance(e, dict) and e.get("reason")]
        return ",".join(reasons) or str(err.get("status") or err.get("message", ""))[:80]
    if isinstance(err, str):
        return err[:80]
    if isinstance(data, dict) and data.get("message"):
        return str(data["message"])[:80]
    return ""
