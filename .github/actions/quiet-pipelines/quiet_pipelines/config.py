"""Load and validate quiet-pipelines.yml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .checks import REGISTRY
from .scan import ScanConfig, compile_patterns

DEFAULT_MODEL = "claude-sonnet-5-5"
META_KEYS = {"name", "type", "workflows", "enabled"}


class ConfigError(ValueError):
    pass


@dataclass
class DiagnoseConfig:
    enabled: bool = True
    model: str = DEFAULT_MODEL
    effort: str = "medium"
    language: str = "en"
    lookback_hours: int = 48
    max_log_chars: int = 60_000
    when: str = "new_or_changed"      # new_or_changed | every_run
    api_key_env: str = "ANTHROPIC_API_KEY"


@dataclass
class IssuesConfig:
    enabled: bool = True
    label: str = "quiet-pipelines"
    repeat_comment_hours: float = 24
    assignees: list[str] = field(default_factory=list)


@dataclass
class Config:
    checks: list[dict[str, Any]]
    ledger_items: list[dict[str, Any]]
    warn_within_days: int = 30
    stale_after_days: int | None = 30
    diagnose: DiagnoseConfig = field(default_factory=DiagnoseConfig)
    issues: IssuesConfig = field(default_factory=IssuesConfig)
    log_scan: ScanConfig = field(default_factory=ScanConfig)

    def check_workflows(self) -> list[str]:
        """Union of `workflows` declared on checks (order kept)."""
        seen: list[str] = []
        for c in self.checks:
            for wf in c.get("workflows") or []:
                if wf not in seen:
                    seen.append(wf)
        return seen


def _sub(cls, data: Any, where: str):
    if data is None:
        return cls()
    if not isinstance(data, dict):
        raise ConfigError(f"{where} must be a mapping")
    known = set(cls.__dataclass_fields__)
    unknown = set(data) - known
    if unknown:
        raise ConfigError(f"{where}: unknown key(s) {', '.join(sorted(unknown))}")
    return cls(**data)


def parse(data: dict[str, Any]) -> Config:
    if not isinstance(data, dict):
        raise ConfigError("top level must be a mapping")
    if data.get("version", 1) != 1:
        raise ConfigError(f"unsupported version {data.get('version')!r} (expected 1)")
    defaults = data.get("defaults") or {}

    checks: list[dict[str, Any]] = []
    names: set[str] = set()
    for i, raw in enumerate(data.get("checks") or []):
        if not isinstance(raw, dict):
            raise ConfigError(f"checks[{i}] must be a mapping")
        spec = {**defaults, **raw}
        if spec.get("enabled", True) is False:
            continue
        kind, name = spec.get("type"), spec.get("name")
        if kind not in REGISTRY:
            raise ConfigError(f"checks[{i}]: unknown type {kind!r}; known: {', '.join(sorted(REGISTRY))}")
        if not name:
            raise ConfigError(f"checks[{i}]: name is required")
        if name in names:
            raise ConfigError(f"checks[{i}]: duplicate name {name!r}")
        names.add(name)
        checks.append(spec)

    ledger = data.get("ledger") or {}
    if not isinstance(ledger, dict):
        raise ConfigError("ledger must be a mapping")
    scan = _sub(ScanConfig, data.get("log_scan"), "log_scan")
    try:
        compile_patterns(scan)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    return Config(
        checks=checks,
        ledger_items=list(ledger.get("items") or []),
        warn_within_days=int(ledger.get("warn_within_days", 30)),
        stale_after_days=ledger.get("stale_after_days", 30),
        diagnose=_sub(DiagnoseConfig, data.get("diagnose"), "diagnose"),
        issues=_sub(IssuesConfig, data.get("issues"), "issues"),
        log_scan=scan,
    )


def load(path: str | Path) -> Config:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config not found: {p}")
    return parse(yaml.safe_load(p.read_text(encoding="utf-8")) or {})


def check_params(spec: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in spec.items() if k not in META_KEYS}
