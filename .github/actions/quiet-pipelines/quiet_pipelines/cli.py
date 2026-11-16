"""quiet-pipelines command line.

  quiet-pipelines run      [--config F] [--dry-run] [--no-issues] [--no-diagnose] [--output report.json] [--fail-on-abnormal]
  quiet-pipelines check    [--config F]            # outcome checks only, print results
  quiet-pipelines ledger   [--config F]            # expiry ledger only
  quiet-pipelines scan     [--config F]            # warnings: failures hidden inside successful runs
  quiet-pipelines validate [--config F]            # parse config, list checks

Exit codes: 0 ok · 1 abnormal (only with --fail-on-abnormal for `run`; always for check/ledger) · 2 config error.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .checks import build
from .config import ConfigError, load
from .ledger import evaluate

DEFAULT_CONFIG = "quiet-pipelines.yml"


def run_checks(cfg) -> list[dict[str, Any]]:
    return [build(spec).run().to_dict() for spec in cfg.checks]


def print_checks(results: list[dict[str, Any]]) -> None:
    for r in results:
        mark = "OK " if r["status"] == "ok" else "NG "
        cat = f" [{r['category']}]" if r.get("category") else ""
        print(f"  [{mark}] {r['name']} ({r['type']}){cat}: {r['message']}")


def print_ledger(rep) -> None:
    print(f"  expired/broken: {len(rep.expired_or_broken)} | expiring <={rep.warn_within_days}d: {len(rep.expiring_soon)}"
          f" | unknown expiry: {len(rep.unknown)} | stale: {len(rep.stale)} | unused: {len(rep.unused)} | invalid: {len(rep.invalid)}")
    for r in rep.expired_or_broken:
        print(f"    ! {r['id']} [{r['kind']}/{r['status']}] {r['name']}")
    for r in rep.expiring_soon:
        print(f"    ~ {r['id']} {r['expires']} ({r['days_left']}d) {r['name']}")
    for r in rep.invalid:
        print(f"    x {r['id']}: {r['problem']}")


def cmd_run(args, cfg) -> int:
    now = datetime.now(timezone.utc)
    print(f"[quiet-pipelines {__version__}] {len(cfg.checks)} check(s), {len(cfg.ledger_items)} ledger item(s)")
    results = run_checks(cfg)
    print_checks(results)
    rep = evaluate(cfg.ledger_items, date.today(), cfg.warn_within_days, cfg.stale_after_days) if cfg.ledger_items else None
    if rep:
        print("  ledger:")
        print_ledger(rep)

    actions: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] | None = None
    need_gh = (cfg.issues.enabled and not args.no_issues) or cfg.log_scan.enabled
    gh = None
    if need_gh:
        from .github import GitHub, GitHubError
        try:
            gh = GitHub(dry_run=args.dry_run)
        except GitHubError as exc:
            print(f"  github: skipped ({exc})")
    if gh is not None and cfg.log_scan.enabled:
        from .scan import scan_successful_runs
        try:
            warnings = [w.to_dict() for w in scan_successful_runs(gh, cfg.log_scan, cfg.check_workflows())]
            print_warnings(warnings)
        except Exception as exc:  # scanning is best effort
            print(f"  log scan: failed ({type(exc).__name__}: {str(exc)[:120]})")
    if cfg.issues.enabled and not args.no_issues:
        from .github import GitHubError
        from .issues import sync_all
        if gh is not None:
            diagnose_for = None
            if cfg.diagnose.enabled and not args.no_diagnose and not args.dry_run:
                from .diagnose import diagnose

                def diagnose_for(result: dict[str, Any]):
                    spec = next((c for c in cfg.checks if c["name"] == result["name"]), {})
                    return diagnose(result, cfg.diagnose, gh=gh, workflows=spec.get("workflows"))
            try:
                actions = sync_all(gh, results, rep, cfg, now=now, diagnose_for=diagnose_for, warnings=warnings)
            except GitHubError as exc:
                print(f"  issues: failed ({exc})")
            for a in actions:
                if a["action"] != "none":
                    print(f"  issue {a['key']}: {a['action']}{' #' + str(a['number']) if a.get('number') else ''}"
                          f"{' (dry-run)' if args.dry_run else ''}")

    abnormal = any(r["status"] != "ok" for r in results) or bool(rep and rep.needs_attention)
    report = {"checked_at": now.isoformat(timespec="seconds"), "abnormal": abnormal, "checks": results,
              "ledger": rep.to_dict() if rep else None, "warnings": warnings or [], "issue_actions": actions}
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"  report: {args.output}")
    print(f"  overall: {'ABNORMAL' if abnormal else 'OK'}" + (f" ({len(warnings)} warning(s))" if warnings else ""))
    return 1 if (abnormal and args.fail_on_abnormal) else 0


def print_warnings(warnings: list[dict[str, Any]]) -> None:
    print(f"  hidden failures in successful runs: {len(warnings)}")
    for w in warnings[:20]:
        print(f"    ? {w['run_name']} {w.get('created_at') or ''} | {w['job']} / {w['step']}: {w['line'][:140]}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # never crash on a console that can't show a character (e.g. cp932)
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="quiet-pipelines", description="Catch pipelines that run but stop producing.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "check", "ledger", "scan", "validate"):
        p = sub.add_parser(name)
        p.add_argument("--config", default=DEFAULT_CONFIG)
        if name == "run":
            p.add_argument("--dry-run", action="store_true", help="no GitHub writes, no Claude calls")
            p.add_argument("--no-issues", action="store_true")
            p.add_argument("--no-diagnose", action="store_true")
            p.add_argument("--fail-on-abnormal", action="store_true")
            p.add_argument("--output", default=None)
    args = ap.parse_args(argv)

    try:
        cfg = load(args.config)
    except (ConfigError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "validate":
        print(f"OK: {len(cfg.checks)} check(s): " + ", ".join(f"{c['name']}({c['type']})" for c in cfg.checks))
        rep = evaluate(cfg.ledger_items, date.today(), cfg.warn_within_days, cfg.stale_after_days)
        if rep.invalid:
            print_ledger(rep)
            return 2
        print(f"OK: {len(cfg.ledger_items)} ledger item(s)")
        return 0
    if args.cmd == "check":
        results = run_checks(cfg)
        print_checks(results)
        return 1 if any(r["status"] != "ok" for r in results) else 0
    if args.cmd == "scan":
        from .github import GitHub, GitHubError
        from .scan import scan_successful_runs
        try:
            gh = GitHub(dry_run=True)
        except GitHubError as exc:
            print(f"scan needs GitHub access: {exc}", file=sys.stderr)
            return 2
        warnings = [w.to_dict() for w in scan_successful_runs(gh, cfg.log_scan, cfg.check_workflows())]
        print_warnings(warnings)
        return 1 if warnings else 0
    if args.cmd == "ledger":
        rep = evaluate(cfg.ledger_items, date.today(), cfg.warn_within_days, cfg.stale_after_days)
        print_ledger(rep)
        return 2 if rep.invalid else (1 if rep.needs_attention else 0)
    return cmd_run(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
