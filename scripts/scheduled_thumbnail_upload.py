#!/usr/bin/env python3
"""
Upload thumbnails to YouTube videos with rate limiting.
Starts 24 hours from now, uploads one thumbnail per hour.
Excludes Radio videos.
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.youtube_uploader import YouTubeUploader
from src.utils import setup_logger

logger = setup_logger("scheduled_thumbnail_upload")

# Keyword → thumbnail file mapping
THUMBNAIL_MAPPING = {
    "convenience": "Why Japanese Convenience Store_thumbnail.jpg",
    "temple": "5 Temple Rules Every Visitor t_thumbnail.jpg",
    "train": "invideo-ai-1080-japanese-train-rules-2026-03-02_thumbnail.jpg",
    "tea": "Japanese tea ceremony_thumbnail.jpg",
    "tipping": "Untitled_Project_thumbnail.jpg",
    "clean": "Untitled_Project (1)_thumbnail.jpg",
    "osaka": "Untitled_Project (2)_thumbnail.jpg",
    "etiquette": "japan_etiquette_guide_thumbnail.jpg",
    "friends": "make_friends_japan_thumbnail.jpg",
    "hanami": "hanami_cherry_blossoms_thumbnail.jpg",
    "cherry": "hanami_cherry_blossoms_thumbnail.jpg",
}

# Exclude Radio from scheduled uploads
EXCLUDE_KEYWORDS = ["radio", "culture radio"]

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
    """Find thumbnail file matching video title (excluding Radio videos)."""
    thumb_dir = Path("output/thumbnails")
    title_lower = video_title.lower()
    
    # Exclude Radio videos
    for exclude_keyword in EXCLUDE_KEYWORDS:
        if exclude_keyword.lower() in title_lower:
            return None
    
    # Find matching thumbnail
    for keyword, thumb_filename in THUMBNAIL_MAPPING.items():
        if keyword.lower() in title_lower:
            thumb_path = thumb_dir / thumb_filename
            if thumb_path.exists():
                return thumb_path
    
    return None

def upload_thumbnails_scheduled(delay_hours=24, interval_hours=1):
    """
    Upload thumbnails with scheduling.
    
    Args:
        delay_hours: Hours to wait before starting (default: 24)
        interval_hours: Hours between each upload (default: 1)
    """
    try:
        uploader = YouTubeUploader()
        
        logger.info("Fetching YouTube videos...")
        videos = get_channel_videos()
        logger.info(f"Found {len(videos)} videos on channel")
        
        # Filter videos that have matching thumbnails (excluding Radio)
        videos_to_update = []
        for video in videos:
            thumb_path = find_thumbnail_for_video(video["title"])
            if thumb_path:
                videos_to_update.append({
                    "id": video["id"],
                    "title": video["title"],
                    "thumbnail": thumb_path
                })
        
        logger.info(f"Found {len(videos_to_update)} videos with matching thumbnails (excluding Radio)")
        
        if not videos_to_update:
            logger.info("No videos to update. Exiting.")
            return True
        
        # Calculate start time
        start_time = datetime.now() + timedelta(hours=delay_hours)
        logger.info(f"\n{'='*80}")
        logger.info(f"SCHEDULED THUMBNAIL UPLOAD PLAN")
        logger.info(f"{'='*80}")
        logger.info(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Videos to update: {len(videos_to_update)}")
        logger.info(f"Interval: {interval_hours} hour(s) between uploads")
        logger.info(f"Estimated completion: {(start_time + timedelta(hours=interval_hours * (len(videos_to_update) - 1))).strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*80}\n")
        
        # Display schedule
        logger.info("Upload Schedule:")
        for i, video in enumerate(videos_to_update):
            upload_time = start_time + timedelta(hours=interval_hours * i)
            logger.info(f"  {i+1}. {upload_time.strftime('%Y-%m-%d %H:%M')} - {video['title'][:60]}")
        logger.info(f"\n{'='*80}\n")
        
        # Wait until start time
        wait_seconds = (start_time - datetime.now()).total_seconds()
        if wait_seconds > 0:
            logger.info(f"Waiting {wait_seconds/3600:.1f} hours until start time...")
            logger.info(f"Press Ctrl+C to cancel\n")
            time.sleep(wait_seconds)
        
        # Upload thumbnails one by one
        uploaded = 0
        failed = 0
        
        for i, video_data in enumerate(videos_to_update):
            try:
                logger.info(f"\n[{i+1}/{len(videos_to_update)}] Uploading thumbnail for: {video_data['title']}")
                logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"Thumbnail: {video_data['thumbnail'].name}")
                
                uploader.youtube.thumbnails().set(
                    videoId=video_data['id'],
                    media_body=str(video_data['thumbnail']),
                ).execute()
                
                logger.info(f"✓ Success!")
                uploaded += 1
                
                # Wait before next upload (except for the last one)
                if i < len(videos_to_update) - 1:
                    next_upload = datetime.now() + timedelta(hours=interval_hours)
                    logger.info(f"Next upload at: {next_upload.strftime('%Y-%m-%d %H:%M:%S')}")
                    logger.info(f"Waiting {interval_hours} hour(s)...\n")
                    time.sleep(interval_hours * 3600)
                
            except KeyboardInterrupt:
                logger.info("\n\nUpload cancelled by user")
                break
            except Exception as e:
                logger.error(f"✗ Failed: {e}")
                failed += 1
                # Continue with next video even if one fails
                if i < len(videos_to_update) - 1:
                    next_upload = datetime.now() + timedelta(hours=interval_hours)
                    logger.info(f"Next upload at: {next_upload.strftime('%Y-%m-%d %H:%M:%S')}")
                    time.sleep(interval_hours * 3600)
        
        # Summary
        logger.info(f"\n{'='*80}")
        logger.info("UPLOAD SUMMARY")
        logger.info(f"{'='*80}")
        logger.info(f"Successfully uploaded: {uploaded}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Total: {len(videos_to_update)}")
        logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*80}\n")
        
        return failed == 0
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Upload thumbnails with rate limiting")
    parser.add_argument("--delay", type=int, default=24, 
                       help="Hours to wait before starting (default: 24)")
    parser.add_argument("--interval", type=int, default=1,
                       help="Hours between each upload (default: 1)")
    parser.add_argument("--now", action="store_true",
                       help="Start immediately instead of waiting")
    
    args = parser.parse_args()
    
    delay = 0 if args.now else args.delay
    
    success = upload_thumbnails_scheduled(delay_hours=delay, interval_hours=args.interval)
    sys.exit(0 if success else 1)
