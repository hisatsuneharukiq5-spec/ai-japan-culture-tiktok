"""rss_freshness and http_freshness — "did this URL change recently?"

rss_freshness
  url, max_age_hours. Reads RSS 2.0 (<item><pubDate>) and Atom
  (<entry><updated>/<published>); uses the newest date found.
  Optional headers_env: name of an env var holding a JSON object of headers.

http_freshness
  url, max_age_hours, source:
    last_modified (default) — the Last-Modified response header
    json_field              — `field` is a dotted path into a JSON body
                              (e.g. "data.updated_at"; list index allowed: "items.0.ts").
                              Value may be ISO-8601 or a UNIX epoch (s or ms).
    regex                   — `pattern` with one group capturing an ISO-8601 timestamp
  Optional headers_env (JSON object of headers, e.g. auth), method: GET|HEAD.
"""
from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from .base import API_ERROR, CONFIG, BaseCheck, CheckError, NO_OUTPUT, parse_iso


def _headers_from_env(name: str | None) -> dict[str, str]:
    if not name:
        return {}
    raw = os.environ.get(name, "")
    if not raw:
        raise CheckError(CONFIG, f"headers_env {name} is empty or not set")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise CheckError(CONFIG, f"headers_env {name} is not a JSON object") from exc
    if not isinstance(data, dict):
        raise CheckError(CONFIG, f"headers_env {name} is not a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def parse_any_date(value: Any) -> datetime:
    """ISO-8601, RFC-822 (RSS) or UNIX epoch seconds/milliseconds -> aware UTC datetime."""
    if isinstance(value, (int, float)) or (isinstance(value, str) and re.fullmatch(r"\d{9,13}(\.\d+)?", value.strip())):
        num = float(value)
        if num > 1e11:  # milliseconds
            num /= 1000
        return datetime.fromtimestamp(num, tz=timezone.utc)
    text = str(value).strip()
    try:
        return parse_iso(text)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError) as exc:
        raise CheckError(API_ERROR, f"unparseable date: {text[:40]!r}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


class RssFreshness(BaseCheck):
    type_name = "rss_freshness"
    required = ("url",)

    def latest_output(self) -> tuple[datetime, dict[str, Any]]:
        resp = self.expect_ok(self.get(self.params["url"], headers=_headers_from_env(self.params.get("headers_env"))), "feed")
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            raise CheckError(API_ERROR, f"feed is not valid XML: {exc}") from exc

        dates: list[datetime] = []
        titles: dict[datetime, str] = {}
        for node in root.iter():
            if _local(node.tag) not in ("item", "entry"):
                continue
            stamp, title = None, ""
            for child in node:
                tag = _local(child.tag)
                if tag in ("pubdate", "updated", "published", "date") and (child.text or "").strip():
                    try:
                        cand = parse_any_date(child.text)
                    except CheckError:
                        continue
                    stamp = cand if stamp is None or cand > stamp else stamp
                elif tag == "title":
                    title = (child.text or "").strip()
            if stamp:
                dates.append(stamp)
                titles[stamp] = title
        if not dates:
            raise CheckError(NO_OUTPUT, "feed has no dated items")
        newest = max(dates)
        return newest, {"items": len(dates), "latest_title": titles.get(newest, "")[:120]}


def _dig(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if isinstance(cur, list) and part.lstrip("-").isdigit():
            idx = int(part)
            if not -len(cur) <= idx < len(cur):
                raise CheckError(API_ERROR, f"field '{path}': index {idx} out of range")
            cur = cur[idx]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise CheckError(API_ERROR, f"field '{path}' not found in JSON")
    return cur


class HttpFreshness(BaseCheck):
    type_name = "http_freshness"
    required = ("url",)

    def latest_output(self) -> tuple[datetime, dict[str, Any]]:
        source = self.params.get("source", "last_modified")
        headers = _headers_from_env(self.params.get("headers_env"))
        method = str(self.params.get("method", "GET")).upper()
        if method == "HEAD":
            try:
                resp = self.session.head(self.params["url"], headers=headers, timeout=self.timeout, allow_redirects=True)
            except Exception as exc:
                raise CheckError("unreachable", f"request failed: {type(exc).__name__}") from exc
        else:
            resp = self.get(self.params["url"], headers=headers)
        self.expect_ok(resp, "http")

        if source == "last_modified":
            value = resp.headers.get("Last-Modified")
            if not value:
                raise CheckError(API_ERROR, "response has no Last-Modified header")
            return parse_any_date(value), {"source": "Last-Modified"}
        if source == "json_field":
            field = self.params.get("field")
            if not field:
                raise CheckError(CONFIG, "source=json_field needs `field`")
            try:
                body = resp.json()
            except ValueError as exc:
                raise CheckError(API_ERROR, "response is not JSON") from exc
            return parse_any_date(_dig(body, field)), {"source": f"json:{field}"}
        if source == "regex":
            pattern = self.params.get("pattern")
            if not pattern:
                raise CheckError(CONFIG, "source=regex needs `pattern`")
            found = [parse_any_date(m) for m in re.findall(pattern, resp.text or "")]
            if not found:
                raise CheckError(NO_OUTPUT, "pattern matched nothing")
            return max(found), {"source": "regex", "matches": len(found)}
        raise CheckError(CONFIG, f"unknown source: {source}")
