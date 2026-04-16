#!/usr/bin/env python3
"""
Instagram Reels uploader with caption and hashtag automation.
Uses Meta Graph API for programmatic Reels publishing.
"""

import os
import requests
from pathlib import Path
from typing import Optional
import logging
import time

from src.utils import setup_logger, PROJECT_ROOT

logger = setup_logger("instagram_reels_uploader")


class InstagramReelsUploader:
    """Upload short videos as Instagram Reels."""
    
    # Hashtags to use for all Instagram content
    DEFAULT_HASHTAGS = [
        "#japan", "#japaneseculture", "#learnjapanese", "#japanfacts",
        "#aijapan", "#japantok", "#explore", "#reels", "#viral"
    ]
    
    def __init__(self):
        self.ig_business_id = os.getenv("INSTAGRAM_BUSINESS_ID")
        self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
        
        if not self.ig_business_id:
            raise ValueError("INSTAGRAM_BUSINESS_ID not set in .env")
        if not self.access_token:
            raise ValueError("INSTAGRAM_ACCESS_TOKEN not set in .env")
        
        self.api_base = "https://graph.instagram.com"
        self.api_version = "v18.0"
    
    def _url(self, path: str) -> str:
        """Build full API URL."""
        return f"{self.api_base}/{self.api_version}/{path}"
    
    def upload_reel(
        self,
        video_path: str | Path,
        title: str,
        description: Optional[str] = None,
        add_hashtags: bool = True,
        thumb_url: Optional[str] = None,
        wait_for_completion: bool = True,
        timeout: int = 300
    ) -> Optional[str]:
        """Upload video as Instagram Reel.
        
        Args:
            video_path: Path to MP4 video file
            title: Reel title (used in caption)
            description: Optional additional description
            add_hashtags: Whether to append default hashtags
            thumb_url: Optional thumbnail URL
            wait_for_completion: Wait for upload to complete
            timeout: Timeout in seconds
            
        Returns:
            Instagram Reels post ID if successful, None otherwise
        """
        try:
            video_path = Path(video_path)
            if not video_path.exists():
                logger.error(f"Video not found: {video_path}")
                return None
            
            file_size = video_path.stat().st_size
            logger.info(f"📤 Instagram Reel upload: {video_path.name} ({file_size / 1_048_576:.1f} MB)")
            
            # Build caption with hashtags
            caption = title
            if description:
                caption = f"{title}\n\n{description}"
            if add_hashtags:
                caption = f"{caption}\n{' '.join(self.DEFAULT_HASHTAGS)}"
            
            # Trim caption to Instagram limits (2200 chars)
            if len(caption) > 2200:
                caption = caption[:2197] + "..."
            
            # Step 1: Upload video file (if using local file)
            # Instagram Graph API requires either:
            # - Public video URL (uploaded via HTTP)
            # - Or upload via media container with signed upload
            
            # For simplicity, we'll use the direct media creation approach
            logger.info("📝 Creating media container...")
            
            params = {
                "access_token": self.access_token,
            }
            
            files = {
                "video": open(video_path, "rb"),
            }
            
            data = {
                "caption": caption,
            }
            
            if thumb_url:
                data["thumb_url"] = thumb_url
            
            resp = requests.post(
                self._url(f"{self.ig_business_id}/media"),
                data=data,
                files=files,
                params=params,
                timeout=60
            )
            
            files["video"].close()
            
            if resp.status_code not in [200, 201]:
                logger.error(f"Media creation failed: {resp.status_code}")
                logger.error(f"Response: {resp.text}")
                return None
            
            response_data = resp.json()
            
            if response_data.get("error"):
                logger.error(f"API error: {response_data['error']}")
                return None
            
            creation_id = response_data.get("id")
            if not creation_id:
                logger.error("No media ID returned")
                return None
            
            logger.info(f"✓ Media container created: {creation_id}")
            
            # Step 2: Publish the media
            logger.info("📤 Publishing Reel...")
            
            publish_params = {
                "creation_id": creation_id,
                "access_token": self.access_token,
            }
            
            publish_resp = requests.post(
                self._url(f"{self.ig_business_id}/media_publish"),
                data=publish_params,
                timeout=30
            )
            
            if publish_resp.status_code not in [200, 201]:
                logger.error(f"Publish failed: {publish_resp.status_code}")
                logger.error(f"Response: {publish_resp.text}")
                return None
            
            publish_data = publish_resp.json()
            if publish_data.get("error"):
                logger.error(f"Publish error: {publish_data['error']}")
                return None
            
            post_id = publish_data.get("id")
            
            # Step 3: Wait for completion if requested
            if wait_for_completion:
                logger.info("⏳ Waiting for publish completion...")
                post_id = self._wait_for_completion(creation_id, timeout)
            
            if post_id:
                logger.info(f"✅ Instagram Reel published!")
                logger.info(f"   Post ID: {post_id}")
                logger.info(f"   URL: https://instagram.com/reel/{post_id}/")
                return post_id
            else:
                logger.warning("Reel published but no post ID returned")
                return creation_id
            
        except Exception as e:
            logger.error(f"Instagram upload failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _wait_for_completion(self, media_id: str, timeout: int = 300) -> Optional[str]:
        """Poll for media publish completion.
        
        Args:
            media_id: Media creation ID
            timeout: Timeout in seconds
            
        Returns:
            Published post ID or None
        """
        start_time = time.time()
        poll_interval = 5  # Start with 5 second intervals
        
        while time.time() - start_time < timeout:
            try:
                resp = requests.get(
                    self._url(f"{media_id}"),
                    params={"access_token": self.access_token, "fields": "status,id"},
                    timeout=30
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status")
                    
                    if status == "FINISHED":
                        return data.get("id")
                    elif status == "ERROR":
                        logger.error("Media publishing failed")
                        return None
                
                time.sleep(poll_interval)
                
            except Exception as e:
                logger.debug(f"Poll error (retrying): {e}")
                time.sleep(poll_interval)
        
        logger.warning(f"Publish poll timed out after {timeout}s")
        return None
    
    def build_caption(
        self,
        title: str,
        topic: Optional[str] = None,
        include_hashtags: bool = True
    ) -> str:
        """Build optimized Instagram caption.
        
        Args:
            title: Main title/description
            topic: Optional topic for engagement
            include_hashtags: Whether to add default hashtags
            
        Returns:
            Formatted caption string
        """
        caption = title
        
        if topic:
            caption = f"{caption}\n\nTopic: {topic}"
        
        if include_hashtags:
            caption = f"{caption}\n\n{' '.join(self.DEFAULT_HASHTAGS)}"
        
        # Trim to Instagram limit
        if len(caption) > 2200:
            caption = caption[:2197] + "..."
        
        return caption
    
    def verify_token(self) -> bool:
        """Verify access token is valid.
        
        Returns:
            True if token is valid
        """
        try:
            resp = requests.get(
                self._url("me"),
                params={"access_token": self.access_token},
                timeout=10
            )
            
            if resp.status_code == 200:
                data = resp.json()
                username = data.get("username")
                ig_id = data.get("id")
                logger.info(f"✓ Token valid: {username} ({ig_id})")
                return True
            else:
                logger.error(f"Token invalid: {resp.status_code} {resp.text}")
                return False
                
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return False


class InstagramTokenManager:
    """Manage Instagram access token lifecycle."""
    
    def __init__(self):
        self.api_base = "https://graph.instagram.com"
        self.api_version = "v18.0"
        self.ig_business_id = os.getenv("INSTAGRAM_BUSINESS_ID")
        self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    
    def refresh_long_lived_token(self) -> Optional[str]:
        """Refresh access token to extend expiry (60 days).
        
        Returns:
            New long-lived token or None if failed
        """
        try:
            if not self.access_token:
                logger.error("No access token available")
                return None
            
            logger.info("🔄 Refreshing Instagram access token...")
            
            # This endpoint requires app access token and long-lived token trading
            # Requires additional setup with app token exchange
            logger.warning("Token refresh requires app credentials. Manual refresh recommended.")
            logger.info("Visit: https://developers.facebook.com/tools/explorer")
            logger.info("Generate new Long-Lived Token there")
            
            return None
            
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return None


if __name__ == "__main__":
    # Example usage
    uploader = InstagramReelsUploader()
    
    # Test token
    uploader.verify_token()
    
    # Example caption
    caption = uploader.build_caption(
        "This is a Japan fact",
        topic="Japanese culture",
        include_hashtags=True
    )
    print(f"Caption example:\n{caption}")
