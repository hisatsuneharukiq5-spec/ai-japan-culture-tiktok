"""Helper for TikTok Content API (OAuth + upload helpers).

This module provides utilities to build an authorization URL,
exchange an authorization code for an access token, and upload a
video using a signed upload URL returned by the provider.

Notes:
- TikTok's API endpoints and exact parameters change; the class
  uses configurable endpoint URLs so you can adapt them to the
  current Developer documentation.
- The upload flow here assumes you receive a signed `upload_url`
  from TikTok's API and can PUT the file to that URL.
"""
from __future__ import annotations

import os
import typing
from urllib.parse import urlencode

import requests


class TikTokUploader:
    def __init__(self, client_key: str, client_secret: str, redirect_uri: str,
                 auth_base: str = "https://open.tiktok.com/platform/oauth/connect",
                 token_url: str = "https://open.tiktok.com/oauth/access_token",
                 api_base: str = "https://open.tiktok.com"):
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_base = auth_base
        self.token_url = token_url
        self.api_base = api_base

    def build_authorize_url(self, scope: str = "user.info.basic,video.upload", state: typing.Optional[str] = None, response_type: str = "code") -> str:
        """Return an OAuth2 authorization URL to visit in the browser.

        You should open the returned URL and complete the OAuth flow
        to get an authorization `code` which can be exchanged.
        """
        params = {
            "client_key": self.client_key,
            "response_type": response_type,
            "scope": scope,
            "redirect_uri": self.redirect_uri,
        }
        if state:
            params["state"] = state
        return f"{self.auth_base}?{urlencode(params)}"

    def exchange_code_for_access_token(self, code: str) -> dict:
        """Exchange an authorization `code` for an access token.

        Returns the JSON response from the token endpoint. Caller
        should persist tokens securely.
        """
        data = {
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }
        resp = requests.post(self.token_url, data=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def upload_via_signed_url(self, upload_url: str, file_path: str, chunk_size: int = 4 * 1024 * 1024) -> requests.Response:
        """Upload a file to a signed `upload_url` (PUT or POST depending on provider).

        This performs a streaming upload; many providers expect a PUT to
        a pre-signed URL. If TikTok's response requires multipart/form-data
        adjustment, adapt the caller to use `requests.post(..., files=...)`.
        """
        # Use PUT by default; the upload_url returned by TikTok commonly
        # is a pre-signed URL accepting PUT. If your provider requires POST
        # include form fields and use multipart upload instead.
        headers = {"User-Agent": "ai-japan-youtube-uploader/1.0"}
        with open(file_path, "rb") as fh:
            resp = requests.put(upload_url, data=fh, headers=headers, timeout=600)
        resp.raise_for_status()
        return resp

    def api_post(self, path: str, access_token: str, json: typing.Optional[dict] = None) -> dict:
        """Generic POST helper to call TikTok API paths under `api_base`.

        `path` may begin with a slash or not. Access token is sent as
        a Bearer token in Authorization header if provided.
        """
        url = f"{self.api_base.rstrip('/')}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
        resp = requests.post(url, json=json or {}, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    print("TikTokUploader: helpers for OAuth and signed-url uploads.")
