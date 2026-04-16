import os
import time
import hmac
import hashlib
import base64
import urllib.parse
import secrets

import requests

from src.utils import setup_logger

logger = setup_logger("x_poster")

X_API_BASE = "https://api.twitter.com/2"


class XPoster:
    """Post tweets to X (Twitter) using API v2 with OAuth 1.0a User Context."""

    def __init__(self):
        self.api_key = os.getenv("X_API_KEY")
        self.api_key_secret = os.getenv("X_API_KEY_SECRET")
        self.access_token = os.getenv("X_ACCESS_TOKEN")
        self.access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

        missing = [
            name for name, val in [
                ("X_API_KEY", self.api_key),
                ("X_API_KEY_SECRET", self.api_key_secret),
                ("X_ACCESS_TOKEN", self.access_token),
                ("X_ACCESS_TOKEN_SECRET", self.access_token_secret),
            ] if not val or val.startswith("your_")
        ]
        if missing:
            raise ValueError(
                f"Missing X API credentials in .env: {', '.join(missing)}\n"
                "X developer portal → Projects & Apps → Keys and Tokens:\n"
                "  X_API_KEY          = API Key (Consumer Key)\n"
                "  X_API_KEY_SECRET   = API Key Secret (Consumer Secret)\n"
                "  X_ACCESS_TOKEN     = Access Token\n"
                "  X_ACCESS_TOKEN_SECRET = Access Token Secret"
            )

    # ------------------------------------------------------------------
    # OAuth 1.0a signature (required for POST /2/tweets)
    # ------------------------------------------------------------------

    def _oauth_header(self, method: str, url: str, params: dict) -> str:
        oauth_params = {
            "oauth_consumer_key": self.api_key,
            "oauth_nonce": secrets.token_hex(16),
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self.access_token,
            "oauth_version": "1.0",
        }

        # Combine oauth + request params for signature base
        all_params = {**oauth_params, **params}
        sorted_params = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(all_params.items())
        )
        base_string = "&".join([
            method.upper(),
            urllib.parse.quote(url, safe=""),
            urllib.parse.quote(sorted_params, safe=""),
        ])

        signing_key = (
            urllib.parse.quote(self.api_key_secret, safe="")
            + "&"
            + urllib.parse.quote(self.access_token_secret, safe="")
        )
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
        ).decode()

        oauth_params["oauth_signature"] = signature
        header_parts = ", ".join(
            f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
        return f"OAuth {header_parts}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tweet(self, text: str) -> dict:
        """Post a tweet. Returns the API response dict (includes tweet id and text)."""
        url = f"{X_API_BASE}/tweets"
        body = {"text": text[:280]}

        auth_header = self._oauth_header("POST", url, {})
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
        }

        logger.info(f"Posting tweet ({len(text)} chars)")
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", resp.json())
        tweet_id = data.get("id")
        logger.info(f"Tweet posted: https://x.com/i/web/status/{tweet_id}")
        return data

    def tweet_video_published(self, title: str, video_url: str, substack_url: str = "") -> dict:
        """Compose and post a video-published announcement tweet."""
        substack_line = f"\n\n📰 Full article: {substack_url}" if substack_url else ""
        text = (
            f"🎌 New video just dropped!\n\n"
            f"{title}\n\n"
            f"▶️ Watch now: {video_url}"
            f"{substack_line}\n\n"
            "#Japan #JapanCulture #AI"
        )
        return self.tweet(text[:280])

    def tweet_article_published(self, title: str, article_url: str, video_url: str = "") -> dict:
        """Compose and post an article-published announcement tweet."""
        text = (
            f"{title}\n\n"
            f"{article_url}\n\n"
            "#Japan #AIJapan #JapanTravel"
        )
        return self.tweet(text[:280])
