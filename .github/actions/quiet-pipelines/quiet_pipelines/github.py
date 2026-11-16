"""Minimal GitHub REST client: failed runs + job logs (read), issues (write).

Designed for the built-in Actions GITHUB_TOKEN with:
  permissions: { contents: read, actions: read, issues: write }
so the watchdog never depends on a personal access token it might be watching.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


class GitHubError(RuntimeError):
    pass


class GitHub:
    def __init__(self, repo: str | None = None, token: str | None = None, api: str | None = None,
                 session: requests.Session | None = None, dry_run: bool = False, timeout: float = 30.0):
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self.api = (api or os.environ.get("GITHUB_API_URL") or "https://api.github.com").rstrip("/")
        self.session = session or requests.Session()
        self.dry_run = dry_run
        self.timeout = timeout
        self.writes: list[dict[str, Any]] = []  # what was (or would be) written — for reports/tests
        if not self.repo or "/" not in self.repo:
            raise GitHubError("GITHUB_REPOSITORY (owner/name) is not set")

    # -- plumbing ---------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _req(self, method: str, path: str, **kw: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{self.api}/repos/{self.repo}{path}"
        resp = self.session.request(method, url, headers=self._headers(), timeout=self.timeout, **kw)
        if resp.status_code >= 400:
            raise GitHubError(f"{method} {path}: HTTP {resp.status_code}")
        return resp

    def _write(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.writes.append({"method": method, "path": path, "payload": payload})
        if self.dry_run:
            return {"dry_run": True, "number": None, "html_url": None}
        return self._req(method, path, json=payload).json()

    # -- runs / logs (read) -------------------------------------------------
    def runs(self, workflows: list[str] | None = None, lookback_hours: int = 48, now: datetime | None = None,
             status: str | None = None, per_page: int = 30) -> list[dict[str, Any]]:
        """Runs created in the lookback window (newest first). `status` e.g. "failure", "success", "completed"."""
        now = now or datetime.now(timezone.utc)
        since = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params: dict[str, Any] = {"per_page": per_page, "created": f">={since}"}
        if status:
            params["status"] = status
        out: list[dict[str, Any]] = []
        for wf in workflows or [None]:
            path = f"/actions/workflows/{wf}/runs" if wf else "/actions/runs"
            out.extend(self._req("GET", path, params=params).json().get("workflow_runs", []))
        out.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return out

    def failed_runs(self, workflows: list[str] | None = None, lookback_hours: int = 48,
                    now: datetime | None = None) -> list[dict[str, Any]]:
        """Runs whose LATEST attempt failed (newest first)."""
        return self.runs(workflows, lookback_hours, now, status="failure", per_page=20)

    def failed_attempts(self, workflows: list[str] | None = None, lookback_hours: int = 48,
                        now: datetime | None = None) -> list[dict[str, Any]]:
        """Earlier attempts that failed in runs that were re-run (e.g. failed, then re-run green).

        The runs list only shows the latest attempt, so a failure fixed by "Re-run" is
        invisible without this. Each item is the attempt object plus `run_attempt`.
        """
        found: list[dict[str, Any]] = []
        for run in self.runs(workflows, lookback_hours, now, status="completed"):
            latest = int(run.get("run_attempt") or 1)
            for n in range(1, latest):
                att = self._req("GET", f"/actions/runs/{run['id']}/attempts/{n}").json()
                if att.get("conclusion") == "failure":
                    att.setdefault("run_attempt", n)
                    att["html_url"] = f"{run.get('html_url', '')}/attempts/{n}"
                    att["created_at"] = att.get("run_started_at") or att.get("created_at") or run.get("created_at")
                    found.append(att)
        found.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return found

    def jobs(self, run_id: int, attempt: int | None = None) -> list[dict[str, Any]]:
        path = f"/actions/runs/{run_id}" + (f"/attempts/{attempt}" if attempt else "") + "/jobs"
        return self._req("GET", path, params={"per_page": 50}).json().get("jobs", [])

    def failed_jobs(self, run_id: int, attempt: int | None = None) -> list[dict[str, Any]]:
        return [j for j in self.jobs(run_id, attempt) if j.get("conclusion") == "failure"]

    def job_log(self, job_id: int) -> str:
        # 302 to a signed blob URL; requests drops Authorization on cross-host redirects.
        return self._req("GET", f"/actions/jobs/{job_id}/logs", allow_redirects=True).text

    # -- issues ---------------------------------------------------------------
    def open_issues(self, label: str) -> list[dict[str, Any]]:
        items = self._req("GET", "/issues", params={"state": "open", "labels": label, "per_page": 100}).json()
        return [i for i in items if "pull_request" not in i]

    def comments(self, number: int) -> list[dict[str, Any]]:
        """Up to the last 100 comments, oldest first."""
        return self._req("GET", f"/issues/{number}/comments", params={"per_page": 100}).json()

    def create_issue(self, title: str, body: str, labels: list[str], assignees: list[str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": title, "body": body, "labels": labels}
        if assignees:
            payload["assignees"] = assignees
        return self._write("POST", "/issues", payload)

    def comment(self, number: int, body: str) -> dict[str, Any]:
        return self._write("POST", f"/issues/{number}/comments", {"body": body})

    def close(self, number: int) -> dict[str, Any]:
        return self._write("PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "completed"})
