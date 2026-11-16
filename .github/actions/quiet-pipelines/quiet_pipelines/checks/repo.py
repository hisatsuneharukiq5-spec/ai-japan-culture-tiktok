"""repo_file_freshness — when was a file in a GitHub repo last committed?

Good for pipelines that commit their output (a registry, a report, a dataset).

Params:
  path (required), repo (default: $GITHUB_REPOSITORY), branch (default: repo default),
  max_age_hours (default 36),
  ignore_authors (optional list) — skip commits by these logins/names, e.g. to ignore
  a bot that only touches timestamps.
Uses $GITHUB_TOKEN (or token_env) — contents:read is enough.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from .base import CONFIG, BaseCheck, CheckError, NO_OUTPUT, parse_iso


class RepoFileFreshness(BaseCheck):
    type_name = "repo_file_freshness"
    required = ("path",)

    def latest_output(self) -> tuple[datetime, dict[str, Any]]:
        repo = self.params.get("repo") or os.environ.get("GITHUB_REPOSITORY", "")
        if not repo or "/" not in repo:
            raise CheckError(CONFIG, "repo not set (owner/name) and GITHUB_REPOSITORY is empty")
        api = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
        token = os.environ.get(self.params.get("token_env") or "GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        params: dict[str, Any] = {"path": self.params["path"], "per_page": 30}
        if self.params.get("branch"):
            params["sha"] = self.params["branch"]

        commits = self.expect_ok(self.get(f"{api}/repos/{repo}/commits", headers=headers, params=params), "commits").json()
        ignore = {a.lower() for a in self.params.get("ignore_authors") or []}
        for c in commits or []:
            login = ((c.get("author") or {}).get("login") or "").lower()
            name = (((c.get("commit") or {}).get("author") or {}).get("name") or "").lower()
            if ignore and (login in ignore or name in ignore):
                continue
            date = ((c.get("commit") or {}).get("committer") or {}).get("date") or ((c.get("commit") or {}).get("author") or {}).get("date")
            if date:
                return parse_iso(date), {"sha": (c.get("sha") or "")[:7], "author": login or name}
        raise CheckError(NO_OUTPUT, f"no commits touching {self.params['path']}" + (" (after ignore_authors)" if ignore else ""))
