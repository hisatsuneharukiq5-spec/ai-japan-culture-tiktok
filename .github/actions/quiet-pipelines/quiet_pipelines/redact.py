"""Mask secrets in text before it leaves the machine (e.g. CI logs sent to an LLM).

Two layers:
1. Exact values: every environment variable whose NAME looks secret
   (KEY / TOKEN / SECRET / PASSWORD / PAT / CREDENTIAL / COOKIE / SESSION) and
   whose value is >= 8 chars is replaced verbatim. This catches secrets with no
   recognizable shape. JSON-valued secrets (OAuth token files) are also split
   into their string fields.
2. Patterns: well-known token formats, credentials in URLs, Authorization
   headers, key=value assignments, private key blocks, JWTs, and long mixed-case
   alphanumeric blobs. Pure lowercase hex (git SHAs) is left alone on purpose.

Redaction is best-effort defence in depth. Do not rely on it as the only control.
"""
from __future__ import annotations

import json
import os
import re
from typing import Iterable, Mapping

MASK = "[REDACTED]"

# Matched against the "_"/"-" separated words of an env var NAME (so PATH != PAT,
# GIT_AUTHOR_NAME != AUTH). APIKEY / ACCESSTOKEN style compounds are matched by suffix.
_SECRET_WORDS = {"KEY", "KEYS", "TOKEN", "TOKENS", "SECRET", "SECRETS", "PASSWORD", "PASSWD", "PWD",
                 "PAT", "CREDENTIAL", "CREDENTIALS", "COOKIE", "SESSION", "AUTH", "SID", "DSN"}
_SECRET_SUFFIXES = ("APIKEY", "TOKEN", "SECRET", "PASSWORD")


def _is_secret_name(name: str) -> bool:
    if name.upper() in {"PWD", "OLDPWD"}:  # shell working-directory vars, not passwords
        return False
    words = [w for w in re.split(r"[_\-]", name.upper()) if w]
    return any(w in _SECRET_WORDS or w.endswith(_SECRET_SUFFIXES) for w in words)

# (label, pattern). Order matters: specific formats before generic ones.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S)),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("google_oauth_access", re.compile(r"\bya29\.[0-9A-Za-z_\-\.]{20,}")),
    ("google_oauth_refresh", re.compile(r"\b1//0[0-9A-Za-z_\-]{20,}")),
    ("google_client_secret", re.compile(r"\bGOCSPX-[0-9A-Za-z_\-]{10,}")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[0-9A-Za-z\-]{10,}")),
    ("huggingface_token", re.compile(r"\bhf_[A-Za-z0-9]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    # https://user:pass@host  or  https://token@host
    ("url_credentials", re.compile(r"(?P<scheme>[a-z][a-z0-9+.\-]*://)(?P<cred>[^/\s:@]+(?::[^/\s@]*)?)@", re.I)),
    # Authorization: Bearer xxx / token xxx / Basic xxx
    ("auth_header", re.compile(r"(?P<prefix>\b(?:authorization|x-api-key|api-key|x-goog-api-key)\s*[:=]\s*(?:bearer\s+|token\s+|basic\s+)?)(?P<val>[^\s'\",;]{6,})", re.I)),
    ("bearer", re.compile(r"(?P<prefix>\bbearer\s+)(?P<val>[A-Za-z0-9_\-\.=~+/]{12,})", re.I)),
    # key=value / "key": "value" for secret-looking names
    ("assignment", re.compile(
        r"(?P<prefix>(?:[\"']?)(?:[A-Za-z0-9_\-]*?(?:api[_\-]?key|secret|token|password|passwd|refresh_token|access_token|client_secret|cookie|session[_\-]?id|sid))(?:[\"']?)\s*[:=]\s*[\"']?)(?P<val>(?=[^\s'\",&;]*[A-Za-z])[^\s'\",&;]{6,})",
        re.I)),
    # Long mixed-case alphanumeric blobs (must contain upper, lower AND digit; >= 32 chars).
    ("high_entropy", re.compile(r"(?<![A-Za-z0-9_\-])(?=[A-Za-z0-9_\-]*[A-Z])(?=[A-Za-z0-9_\-]*[a-z])(?=[A-Za-z0-9_\-]*[0-9])[A-Za-z0-9_\-]{32,}(?![A-Za-z0-9_\-])")),
]


def secret_values_from_env(env: Mapping[str, str] | None = None, min_len: int = 8) -> list[str]:
    """Values of env vars with secret-looking names (plus string fields of JSON values)."""
    env = os.environ if env is None else env
    values: set[str] = set()
    for name, value in env.items():
        if not value or not _is_secret_name(name):
            continue
        value = value.strip()
        if len(value) >= min_len:
            values.add(value)
        if value.startswith("{"):
            try:
                obj = json.loads(value)
            except ValueError:
                continue
            stack = [obj]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    stack.extend(cur.values())
                elif isinstance(cur, list):
                    stack.extend(cur)
                elif isinstance(cur, str) and len(cur) >= min_len and not cur.startswith("http"):
                    values.add(cur)
    # Longest first so a value containing another is replaced whole.
    return sorted(values, key=len, reverse=True)


def redact(text: str, extra_values: Iterable[str] = (), env: Mapping[str, str] | None = None) -> tuple[str, dict[str, int]]:
    """Return (redacted_text, counts_by_rule). Never returns the secrets themselves."""
    counts: dict[str, int] = {}
    if not text:
        return text, counts

    for value in [*sorted({v for v in extra_values if v and len(v) >= 8}, key=len, reverse=True), *secret_values_from_env(env)]:
        if value in text:
            counts["known_value"] = counts.get("known_value", 0) + text.count(value)
            text = text.replace(value, MASK)

    for label, pattern in _PATTERNS:
        def _sub(m: re.Match[str], _label: str = label) -> str:
            counts[_label] = counts.get(_label, 0) + 1
            groups = m.groupdict()
            if "scheme" in groups and groups.get("scheme"):
                return f"{groups['scheme']}{MASK}@"
            if "prefix" in groups and groups.get("prefix") is not None:
                return f"{groups['prefix']}{MASK}"
            return MASK

        text = pattern.sub(_sub, text)
    return text, counts
