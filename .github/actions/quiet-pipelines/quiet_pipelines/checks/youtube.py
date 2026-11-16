"""youtube_latest_upload — newest PUBLIC video on a YouTube channel.

Auth (pick one):
  auth: oauth   — token_json_env: name of an env var holding an authorized-user
                  token JSON (refresh_token, client_id, client_secret, token_uri),
                  e.g. the content of google-auth's `token.json`. Uses mine=true,
                  so it also sees scheduled/private uploads.
  auth: api_key — api_key_env + channel_id. Public data only.

Params:
  max_age_hours (default 36), scan_recent (default 25, max 50),
  expect_channel_name_contains (optional, oauth only — guards against a token
  for the wrong channel).

Read-only. Cost ≈ 3 quota units per run. The refreshed access token is kept in
memory only; nothing is written.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from .base import AUTH, CONFIG, BaseCheck, CheckError, NO_OUTPUT, parse_iso, require_env

API = "https://www.googleapis.com/youtube/v3"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


class YouTubeLatestUpload(BaseCheck):
    type_name = "youtube_latest_upload"

    def _auth(self) -> tuple[dict[str, str], dict[str, str]]:
        """Return (headers, extra_query_params)."""
        mode = self.params.get("auth", "oauth")
        if mode == "api_key":
            key = require_env(self.params.get("api_key_env"), "youtube api_key")
            if not self.params.get("channel_id"):
                raise CheckError(CONFIG, "auth=api_key needs channel_id")
            return {}, {"key": key}
        if mode != "oauth":
            raise CheckError(CONFIG, f"unknown auth mode: {mode}")

        raw = require_env(self.params.get("token_json_env"), "youtube oauth token")
        try:
            tok = json.loads(raw)
        except ValueError as exc:
            raise CheckError(CONFIG, f"{self.params.get('token_json_env')} is not valid JSON") from exc
        needed = [k for k in ("refresh_token", "client_id", "client_secret") if not tok.get(k)]
        if needed:
            raise CheckError(AUTH, f"token JSON lacks {', '.join(needed)} (re-authorize)")
        resp = self.post(tok.get("token_uri") or DEFAULT_TOKEN_URI, data={
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
            "client_id": tok["client_id"],
            "client_secret": tok["client_secret"],
        })
        if resp.status_code >= 400:
            try:
                code = resp.json().get("error", "")
            except ValueError:
                code = ""
            raise CheckError(AUTH, f"token refresh failed: HTTP {resp.status_code} {code}".strip())
        access = resp.json().get("access_token")
        if not access:
            raise CheckError(AUTH, "token refresh returned no access_token")
        return {"Authorization": f"Bearer {access}"}, {}

    def latest_output(self) -> tuple[datetime, dict[str, Any]]:
        headers, extra = self._auth()
        scan = max(1, min(50, int(self.params.get("scan_recent", 25))))

        q = {"part": "snippet,contentDetails", **extra}
        if self.params.get("auth", "oauth") == "oauth":
            q["mine"] = "true"
        else:
            q["id"] = self.params["channel_id"]
        chan = self.expect_ok(self.get(f"{API}/channels", params=q, headers=headers), "channels.list").json()
        items = chan.get("items") or []
        if not items:
            raise CheckError(AUTH if "mine" in q else CONFIG, "no channel found for these credentials / channel_id")
        channel = items[0]
        name = channel["snippet"]["title"]
        expect = (self.params.get("expect_channel_name_contains") or "").lower()
        if expect and expect not in name.lower():
            raise CheckError(AUTH, f"credentials belong to channel '{name}', expected '*{self.params['expect_channel_name_contains']}*'")

        uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]
        pl = self.expect_ok(self.get(f"{API}/playlistItems", headers=headers, params={
            "part": "contentDetails", "playlistId": uploads, "maxResults": scan, **extra}), "playlistItems.list").json()
        ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
        if not ids:
            raise CheckError(NO_OUTPUT, "channel has no uploads")

        vids = self.expect_ok(self.get(f"{API}/videos", headers=headers, params={
            "part": "snippet,status", "id": ",".join(ids), "maxResults": 50, **extra}), "videos.list").json().get("items", [])
        public = [v for v in vids if (v.get("status") or {}).get("privacyStatus") == "public"]
        scheduled = sum(1 for v in vids if (v.get("status") or {}).get("publishAt")
                        and (v.get("status") or {}).get("privacyStatus") != "public")
        if not public:
            raise CheckError(NO_OUTPUT, f"none of the last {len(ids)} uploads is public ({scheduled} scheduled)")
        newest = max(public, key=lambda v: parse_iso(v["snippet"]["publishedAt"]))
        return parse_iso(newest["snippet"]["publishedAt"]), {
            "channel_name": name,
            "latest_title": newest["snippet"].get("title", "")[:120],
            "scanned": len(ids),
            "scheduled_not_public": scheduled,
        }
