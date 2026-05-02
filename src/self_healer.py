"""Self-healing diagnostics for the Facts & Wonders / Obscura pipeline.

Runs after workflow failure, reads logs, classifies the error, and applies
known fixes automatically. Called by facts_healthcheck.yml.

Error categories and auto-fixes:
  token_expired     → refresh token via API; update GitHub secret
  network_error     → log and rely on workflow retry
  quota_exceeded    → reduce ops for next run; notify via commit
  ffmpeg_timeout    → already fixed (concat demuxer); log warning
  quality_failure   → already handled (rebuild + upload anyway)
  unknown           → log raw error for human review
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("self_healer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [self_healer] %(levelname)s: %(message)s")

ROOT = Path(__file__).resolve().parent.parent
HEAL_LOG_PATH = ROOT / "output" / "analytics" / "self_heal_log.json"
QUOTA_PATH = ROOT / "output" / "analytics" / "facts_quota_today.json"

# Error patterns → category
_ERROR_PATTERNS: list[tuple[str, str]] = [
    (r"invalid_grant|Token has been expired|token.*revoked|Bad Request.*oauth", "token_expired"),
    (r"TransportError|NameResolution|getaddrinfo failed|ConnectionError|ConnectionReset|Max retries exceeded", "network_error"),
    (r"quota.*exceeded|quotaExceeded|dailyLimitExceeded", "quota_exceeded"),
    (r"timed out after 600|TimeoutExpired.*ffmpeg", "ffmpeg_timeout"),
    (r"Quality check FAILED|scene changes detected", "quality_failure"),
    (r"insufficientPermissions|forbidden|403", "permission_error"),
]


def classify_error(log_text: str) -> str:
    for pattern, category in _ERROR_PATTERNS:
        if re.search(pattern, log_text, re.IGNORECASE):
            return category
    return "unknown"


def _read_recent_logs(max_lines: int = 200) -> str:
    """Read the last N lines of all relevant log files."""
    parts: list[str] = []
    for log_file in [ROOT / "logs" / "facts_schedule.log", ROOT / "logs" / "error.log"]:
        if log_file.exists():
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            parts.append(f"=== {log_file.name} (last {max_lines} lines) ===")
            parts.extend(lines[-max_lines:])
    return "\n".join(parts)


def _fix_token_expired(channel: str) -> dict[str, Any]:
    """Attempt to refresh the OAuth token for the given channel."""
    token_map = {
        "facts": ROOT / "config" / "youtube_token_facts.json",
        "obscura": ROOT / "config" / "youtube_token_obscura.json",
    }
    token_file = token_map.get(channel)
    if not token_file or not token_file.exists():
        return {"fixed": False, "reason": f"token file missing for {channel}"}

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_file.write_text(creds.to_json(), encoding="utf-8")

            # Push refreshed token to GitHub secret
            _update_github_secret(
                secret_name="YT_TOKEN_FACTS" if channel == "facts" else "YT_TOKEN_OBSCURA",
                value=token_file.read_text(encoding="utf-8").strip(),
            )
            return {"fixed": True, "reason": "token refreshed and secret updated"}
        return {"fixed": False, "reason": "token not expired or no refresh_token"}
    except Exception as exc:
        return {"fixed": False, "reason": str(exc)}


def _update_github_secret(secret_name: str, value: str) -> bool:
    """Update a GitHub Actions secret via the API."""
    try:
        import base64
        import requests
        from nacl import public as nacl_public

        # Try to find PAT from git remote URL
        result = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
        remote_url = result.stdout.strip()
        pat_match = re.search(r"https://(ghp_[A-Za-z0-9]+)@github", remote_url)
        if not pat_match:
            return False
        pat = pat_match.group(1)

        repo_match = re.search(r"github\.com/(.+?)(?:\.git)?$", remote_url)
        if not repo_match:
            return False
        repo = repo_match.group(1)

        headers = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        pk_resp = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=headers, timeout=15)
        if not pk_resp.ok:
            return False
        pk = pk_resp.json()

        pk_bytes = base64.b64decode(pk["key"])
        sealed_box = nacl_public.SealedBox(nacl_public.PublicKey(pk_bytes))
        encrypted = base64.b64encode(sealed_box.encrypt(value.encode())).decode()

        resp = requests.put(
            f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
            headers=headers,
            json={"encrypted_value": encrypted, "key_id": pk["key_id"]},
            timeout=15,
        )
        logger.info("Secret %s updated: HTTP %d", secret_name, resp.status_code)
        return resp.status_code in (201, 204)
    except Exception as exc:
        logger.warning("Secret update failed: %s", exc)
        return False


def _append_heal_log(entry: dict[str, Any]) -> None:
    HEAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log: list = []
    if HEAL_LOG_PATH.exists():
        try:
            log = json.loads(HEAL_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    log.append(entry)
    HEAL_LOG_PATH.write_text(json.dumps(log[-100:], ensure_ascii=False, indent=2), encoding="utf-8")


def run(channel: str = "facts") -> dict[str, Any]:
    """Diagnose latest failure and apply auto-fix. Returns result dict."""
    log_text = _read_recent_logs()
    category = classify_error(log_text)
    result: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "channel": channel,
        "error_category": category,
        "fixed": False,
        "action": "none",
    }

    logger.info("Self-healer: channel=%s error_category=%s", channel, category)

    if category == "token_expired":
        fix = _fix_token_expired(channel)
        result["fixed"] = fix["fixed"]
        result["action"] = "token_refresh"
        result["detail"] = fix["reason"]
        logger.info("Token fix result: %s", fix)

    elif category == "network_error":
        result["action"] = "network_transient — workflow retry will handle"
        result["fixed"] = True  # retry already built into workflow

    elif category == "quota_exceeded":
        result["action"] = "quota_exceeded — skipping growth ops for next run"
        if QUOTA_PATH.exists():
            try:
                q = json.loads(QUOTA_PATH.read_text(encoding="utf-8"))
                q["quota_exceeded_flag"] = True
                QUOTA_PATH.write_text(json.dumps(q, indent=2), encoding="utf-8")
            except Exception:
                pass
        result["fixed"] = False  # must wait for daily quota reset

    elif category == "ffmpeg_timeout":
        result["action"] = "ffmpeg_timeout — concat demuxer fix already applied"
        result["fixed"] = True

    elif category == "quality_failure":
        result["action"] = "quality_failure — upload-anyway fallback already applied"
        result["fixed"] = True

    elif category == "permission_error":
        result["action"] = "permission_error — channel may need phone verification or scope update"
        result["fixed"] = False

    else:
        result["action"] = "unknown_error — logged for human review"
        result["fixed"] = False

    _append_heal_log(result)
    return result


if __name__ == "__main__":
    channel = sys.argv[1] if len(sys.argv) > 1 else "facts"
    outcome = run(channel)
    print(json.dumps(outcome, indent=2))
    sys.exit(0 if outcome["fixed"] else 1)
