#!/usr/bin/env python3
"""
TikTok Reels uploader with caption and hashtag automation.
"""

import os
import requests
from pathlib import Path
from typing import Optional
import json
import logging

from src.utils import setup_logger, PROJECT_ROOT

logger = setup_logger("tiktok_reels_uploader")


class TikTokReelsUploader:
    """Upload short videos to TikTok."""
    
    # Hashtags to use for all TikTok content
    DEFAULT_HASHTAGS = [
        "#Japan", "#JapaneseCulture", "#LearnJapanese", "#JapanFacts",
        "#AIJapan", "#JapanTok", "#FYP", "#ForYouPage"
    ]
    
    def __init__(self):
        self.access_token = os.getenv("TIKTOK_ACCESS_TOKEN")
        self.client_key = os.getenv("TIKTOK_CLIENT_KEY")
        self.client_secret = os.getenv("TIKTOK_CLIENT_SECRET")
        
        if not self.access_token:
            raise ValueError("TIKTOK_ACCESS_TOKEN not set in .env")
        
        self.api_base = "https://open.tiktok.com/v1"
    
    def upload_video(
        self,
        video_path: str | Path,
        title: str,
        description: Optional[str] = None,
        add_hashtags: bool = True
    ) -> Optional[str]:
        """Upload video to TikTok.
        
        Args:
            video_path: Path to MP4 video file
            title: Video title (used as description)
            description: Optional additional description
            add_hashtags: Whether to append default hashtags
            
        Returns:
            TikTok video ID if successful, None otherwise
        """
        try:
            video_path = Path(video_path)
            if not video_path.exists():
                logger.error(f"Video not found: {video_path}")
                return None
            
            # Step 1: Request upload URL from TikTok API
            logger.info(f"📤 Requesting upload URL for: {video_path.name}")
            
            # Build caption with hashtags
            caption = title
            if description:
                caption = f"{title}\n\n{description}"
            if add_hashtags:
                caption = f"{caption}\n\n{' '.join(self.DEFAULT_HASHTAGS)}"
            
            # Trim caption to TikTok limits (2200 chars)
            if len(caption) > 2200:
                caption = caption[:2197] + "..."
            
            # Request signed upload URL
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            upload_request = {
                "source": "FILE_UPLOAD",
                "video_size": video_path.stat().st_size
            }
            
            resp = requests.post(
                f"{self.api_base}/post/publish/video/init/",
                json=upload_request,
                headers=headers,
                timeout=30
            )
            
            if resp.status_code != 200:
                logger.error(f"Upload URL request failed: {resp.status_code} {resp.text}")
                return None
            
            data = resp.json()
            if data.get("error", {}).get("code") != "ok":
                logger.error(f"Upload init error: {data}")
                return None
            
            upload_url = data.get("data", {}).get("upload_url")
            upload_token = data.get("data", {}).get("upload_token")
            
            if not upload_url:
                logger.error("No upload URL returned")
                return None
            
            # Step 2: Upload video file
            logger.info("📤 Uploading video to TikTok...")
            with open(video_path, "rb") as f:
                video_data = f.read()
            
            upload_headers = {
                "Content-Type": "video/mp4",
            }
            
            resp = requests.put(
                upload_url,
                data=video_data,
                headers=upload_headers,
                timeout=600
            )
            
            if resp.status_code not in [200, 201]:
                logger.error(f"Upload failed: {resp.status_code} {resp.text}")
                return None
            
            logger.info("✓ Video uploaded")
            
            # Step 3: Publish video with caption
            logger.info("📝 Publishing with caption and hashtags...")
            
            publish_request = {
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_path.stat().st_size
                },
                "post_info": {
                    "title": caption,
                    "disable_comment": False,
                    "disable_duet": False,
                    "disable_stitch": False,
                },
                "upload_token": upload_token
            }
            
            resp = requests.post(
                f"{self.api_base}/post/publish/action/publish/",
                json=publish_request,
                headers=headers,
                timeout=30
            )
            
            if resp.status_code != 200:
                logger.error(f"Publish failed: {resp.status_code} {resp.text}")
                return None
            
            data = resp.json()
            if data.get("error", {}).get("code") != "ok":
                logger.error(f"Publish error: {data}")
                return None
            
            video_id = data.get("data", {}).get("video_id")
            if video_id:
                logger.info(f"✅ TikTok video published!")
                logger.info(f"   Video ID: {video_id}")
                logger.info(f"   URL: https://www.tiktok.com/video/{video_id}")
                return video_id
            else:
                logger.warning("Video published but no ID returned")
                return True
            
        except Exception as e:
            logger.error(f"TikTok upload failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def build_caption(self, title: str, include_hashtags: bool = True) -> str:
        """Build optimized caption with hashtags.
        
        Args:
            title: Main title/description
            include_hashtags: Whether to add default hashtags
            
        Returns:
            Formatted caption string
        """
        caption = title
        if include_hashtags:
            caption = f"{caption}\n\n{' '.join(self.DEFAULT_HASHTAGS)}"
        
        # Trim to TikTok limit
        if len(caption) > 2200:
            caption = caption[:2197] + "..."
        
        return caption


class TikTokAuthHelper:
    """Helper to manage TikTok OAuth flow."""
    
    def __init__(self, client_key: str, client_secret: str, redirect_uri: str = "http://localhost:8000/callback"):
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_base = "https://open.tiktok.com/platform/oauth/connect"
        self.token_url = "https://open.tiktok.com/oauth/access_token"
    
    def build_auth_url(self) -> str:
        """Build authorization URL for user to visit."""
        from urllib.parse import urlencode
        params = {
            "client_key": self.client_key,
            "response_type": "code",
            "scope": "video.upload,user.info.basic",
            "redirect_uri": self.redirect_uri,
            "state": "random_state_123"
        }
        return f"{self.auth_base}?{urlencode(params)}"
    
    def exchange_code_for_token(self, code: str) -> Optional[dict]:
        """Exchange authorization code for access token.
        
        Args:
            code: Authorization code from OAuth callback
            
        Returns:
            Token response dict or None if failed
        """
        data = {
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri
        }
        
        try:
            resp = requests.post(self.token_url, data=data, timeout=30)
            resp.raise_for_status()
            response = resp.json()
            
            if response.get("error"):
                logger.error(f"Token exchange failed: {response['error']}")
                return None
            
            # Save token to .env or config
            token = response.get("data", {}).get("access_token")
            expires_in = response.get("data", {}).get("expires_in")
            
            if token:
                logger.info(f"✓ Access token obtained (expires in {expires_in}s)")
                return {
                    "access_token": token,
                    "expires_in": expires_in,
                    "refresh_token": response.get("data", {}).get("refresh_token")
                }
            
        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return None


if __name__ == "__main__":
    # Example usage
    uploader = TikTokReelsUploader()
    print(f"Caption example:\n{uploader.build_caption('This is a Japan fact', include_hashtags=True)}")
