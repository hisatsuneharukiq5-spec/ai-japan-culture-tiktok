#!/usr/bin/env python3
"""Force upload thumbnails to all videos that have matching thumbnail files."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.youtube_uploader import YouTubeUploader
from src.utils import setup_logger

logger = setup_logger("force_upload_thumbnails")

# Keyword → thumbnail file mapping
THUMBNAIL_MAPPING = {
    "convenience": "Why Japanese Convenience Store_thumbnail.jpg",
    "clean": "Untitled_Project (1)_thumbnail.jpg",
    "tipping": "Untitled_Project_thumbnail.jpg",
    "etiquette": "japan_etiquette_guide_thumbnail.jpg",
    "friends": "make_friends_japan_thumbnail.jpg",
    "hanami": "hanami_cherry_blossoms_thumbnail.jpg",
    "cherry": "hanami_cherry_blossoms_thumbnail.jpg",
}

def get_channel_videos():
    """Fetch all videos from the channel."""
    uploader = YouTubeUploader()
    
    request = uploader.youtube.search().list(
        part="id,snippet",
        forMine=True,
        type="video",
        maxResults=50,
    )
    
    videos = []
    while request:
        response = request.execute()
        
        for item in response.get("items", []):
            video_id = item["id"]["videoId"]
            title = item["snippet"]["title"]
            videos.append({"id": video_id, "title": title})
        
        request = uploader.youtube.search().list_next(request, response)
    
    return videos

def find_thumbnail_for_video(video_title: str) -> Path | None:
    """Find thumbnail file matching video title (excluding Radio)."""
    thumb_dir = Path("output/thumbnails")
    title_lower = video_title.lower()
    
    # Exclude Radio videos
    if "radio" in title_lower:
        return None
    
    # Find matching thumbnail
    for keyword, thumb_filename in THUMBNAIL_MAPPING.items():
        if keyword.lower() in title_lower:
            thumb_path = thumb_dir / thumb_filename
            if thumb_path.exists():
                return thumb_path
    
    return None

def main():
    """Force upload all thumbnails."""
    try:
        uploader = YouTubeUploader()
        
        logger.info("Fetching YouTube videos...")
        videos = get_channel_videos()
        logger.info(f"Found {len(videos)} videos on channel\n")
        
        uploaded = 0
        failed = 0
        skipped = 0
        
        for video in videos:
            video_id = video["id"]
            video_title = video["title"]
            
            # Find matching thumbnail
            thumbnail_path = find_thumbnail_for_video(video_title)
            
            if not thumbnail_path:
                logger.info(f"⊘ No matching thumbnail: {video_title}")
                skipped += 1
                continue
            
            try:
                logger.info(f"\n⬆ Uploading: {video_title}")
                logger.info(f"  Video ID: {video_id}")
                logger.info(f"  Thumbnail: {thumbnail_path.name}")
                
                uploader.youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=str(thumbnail_path),
                ).execute()
                
                logger.info(f"✓ Success!")
                uploaded += 1
                
                # Wait 1 second between uploads to avoid rate limits
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"✗ Upload failed for {video_title}")
                logger.error(f"  Error: {e}")
                failed += 1
                
                # If rate limit, wait longer
                if "429" in str(e) or "uploadRateLimitExceeded" in str(e):
                    logger.warning("Rate limit hit. Waiting 60 seconds...")
                    time.sleep(60)
        
        # Summary
        print("\n" + "="*80)
        print("THUMBNAIL UPLOAD SUMMARY")
        print("="*80)
        print(f"✓ Successfully uploaded:  {uploaded}")
        print(f"✗ Failed:                 {failed}")
        print(f"⊘ Skipped (no match):     {skipped}")
        print("="*80 + "\n")
        
        return failed == 0
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
