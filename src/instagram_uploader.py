"""Instagram uploader using the Instagram Graph API.

This module provides a small helper class to create and publish
video containers for an Instagram Business or Creator account via
the Facebook Graph API.

Notes:
- The Instagram Graph API requires a Facebook App, a connected
  Instagram Business/Creator account and a Page access token.
- For video publishing the API accepts a public `video_url`. If
  you only have local files you must first host them on a public
  URL (S3, signed URL, etc.) or implement resumable upload.
"""
from __future__ import annotations

import time
from typing import Optional

import requests


class InstagramUploader:
    def __init__(self, ig_user_id: str, access_token: str, api_version: str = "v17.0"):
        self.ig_user_id = ig_user_id
        self.access_token = access_token
        self.api_version = api_version
        self.base = "https://graph.facebook.com"

    def _url(self, path: str) -> str:
        return f"{self.base}/{self.api_version}/{path}"

    def create_video_container(self, video_url: str, caption: Optional[str] = None, thumb_url: Optional[str] = None) -> str:
        """Create a media container for a video.

        Returns the creation id to be used with `publish_media`.
        """
        url = self._url(f"{self.ig_user_id}/media")
        params = {
            "access_token": self.access_token,
            "video_url": video_url,
        }
        if caption:
            params["caption"] = caption
        if thumb_url:
            params["thumb_url"] = thumb_url

        resp = requests.post(url, data=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if "id" not in data:
            raise RuntimeError(f"Unexpected response creating container: {data}")
        return data["id"]

    def publish_media(self, creation_id: str) -> dict:
        """Publish a previously-created media container.

        Returns the Graph API response (usually contains the published post id).
        """
        url = self._url(f"{self.ig_user_id}/media_publish")
        params = {"creation_id": creation_id, "access_token": self.access_token}
        resp = requests.post(url, data=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def publish_video_from_url(self, video_url: str, caption: Optional[str] = None, wait: bool = True, poll_interval: int = 5, timeout: int = 300) -> dict:
        """Convenience method: create container, publish, and optionally poll.

        If `wait` is True this will poll for at most `timeout` seconds and
        return the final publish response or raise on timeout.
        """
        creation_id = self.create_video_container(video_url, caption=caption)
        publish_resp = self.publish_media(creation_id)

        if not wait:
            return publish_resp

        # Poll for published_id presence on publish response or timeout.
        start = time.time()
        while time.time() - start < timeout:
            # The publish call may return quickly; check for result keys.
            if publish_resp.get("id"):
                return publish_resp
            time.sleep(poll_interval)
        raise TimeoutError("Timed out waiting for Instagram publish to complete")


if __name__ == "__main__":
    print("This module provides `InstagramUploader` for programmatic uploads.")
