"""Find failures that a "green" run swallowed (`|| true`, `continue-on-error`, try/except-and-log).

Scans the job logs of SUCCESSFUL runs for configurable regex patterns and returns
warnings. Matched lines are redacted before they are returned.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .redact import redact

DEFAULT_PATTERNS = [
    r"\b40[13]\b",
    r"\bdenied\b",
    r"\binvalid_grant\b",
    r"\bquotaExceeded\b",
    r"\brateLimitExceeded\b",
    r"Resource not accessible",
    r"failed to push|\[rejected\]",
    r"Traceback \(most recent call last\)",
]
_STAMP = re.compile(r"^\ufeff?\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z\s?")
_GROUP = re.compile(r"^##\[group\](?:Run\s+)?(.*)")


@dataclass
class ScanConfig:
    enabled: bool = True
    workflows: list[str] = field(default_factory=list)   # empty = the checks' workflows (or all if none)
    lookback_hours: int = 24
    max_runs: int = 10
    patterns: list[str] = field(default_factory=lambda: list(DEFAULT_PATTERNS))
    extra_patterns: list[str] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)       # regexes; matching lines are skipped
    max_matches_per_run: int = 5


@dataclass
class Warning_:
    run_id: int
    run_name: str
    html_url: str | None
    created_at: str | None
    job: str
    step: str
    pattern: str
    line: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compile_patterns(cfg: ScanConfig) -> tuple[list[re.Pattern[str]], list[re.Pattern[str]]]:
    try:
        pats = [re.compile(p, re.I) for p in [*cfg.patterns, *cfg.extra_patterns]]
        ign = [re.compile(p, re.I) for p in cfg.ignore]
    except re.error as exc:
        raise ValueError(f"log_scan: invalid regex: {exc}") from exc
    return pats, ign


def scan_log(text: str, pats: list[re.Pattern[str]], ign: list[re.Pattern[str]], limit: int) -> list[tuple[str, str, str]]:
    """Return [(step, pattern, redacted_line)] for matching lines, at most `limit`."""
    out: list[tuple[str, str, str]] = []
    step = "?"
    for raw in text.splitlines():
        line = _STAMP.sub("", raw)
        g = _GROUP.match(line)
        if g:
            step = g.group(1).strip()[:80] or step
            continue
        if line.startswith("##[endgroup]") or not line.strip():
            continue
        if any(i.search(line) for i in ign):
            continue
        for p in pats:
            if p.search(line):
                out.append((step, p.pattern, redact(line.strip()[:240])[0]))
                break
        if len(out) >= limit:
            break
    return out


def scan_successful_runs(gh, cfg: ScanConfig, workflows: list[str] | None = None) -> list[Warning_]:
    import os

    pats, ign = compile_patterns(cfg)
    me = os.environ.get("GITHUB_WORKFLOW", "")  # never scan the watchdog's own runs (it prints the patterns)
    runs = [r for r in gh.runs(cfg.workflows or workflows, cfg.lookback_hours, status="success")
            if not (me and r.get("name") == me)][: cfg.max_runs]
    warnings: list[Warning_] = []
    for run in runs:
        for job in gh.jobs(run["id"]):
            if job.get("conclusion") != "success":
                continue
            try:
                text = gh.job_log(job["id"])
            except Exception:
                continue  # logs expire / skipped jobs have none
            for step, pat, line in scan_log(text, pats, ign, cfg.max_matches_per_run):
                warnings.append(Warning_(run_id=run["id"], run_name=run.get("name", ""), html_url=run.get("html_url"),
                                         created_at=run.get("created_at"), job=job.get("name", ""), step=step,
                                         pattern=pat, line=line))
    return warnings
