#!/usr/bin/env python3
"""Upload generated Pexels thumbnails to YouTube with delays."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.youtube_uploader import YouTubeUploader
from src.utils import setup_logger

logger = setup_logger("upload_pexels_thumbnails")

# Videos with their IDs and new thumbnail files
VIDEOS = [
    {
        "id": "B8mewBpmCc4",
        "title": "Hanami — Why Japan Goes Crazy for Cherry Blossoms 🌸",
        "filename": "hanami_pexels.jpg"
    },
    {
        "id": "SzztC4iR7mI",
        "title": "Japan Etiquette Guide — 5 Rules Tourists Must Know",
        "filename": "etiquette_pexels.jpg"
    },
    {
        "id": "TTZON3PzeyU",
        "title": "How to Make Friends in Japan as a Foreigner",
        "filename": "friends_pexels.jpg"
    },
    {
        "id": "OF3wwKby0Xk",
        "title": "Why Tipping is RUDE in Japan (Service Culture Explained)",
        "filename": "tipping_pexels.jpg"
    },
    {
        "id": "lED2InG7_Xo",
        "title": "How Japan Keeps Its Streets So Incredibly Clean",
        "filename": "clean_streets_pexels.jpg"
    },
    {
        "id": "b0Tz9PiLRL8",
        "title": "Why Japanese Convenience Stores Are World — Class",
        "filename": "convenience_pexels.jpg"
    },
]


def upload_thumbnail(uploader: YouTubeUploader, video_id: str, thumbnail_path: Path) -> bool:
    """Upload thumbnail to YouTube."""
    try:
        logger.info(f"📤 Uploading thumbnail (Video ID: {video_id})...")
        
        uploader.youtube.thumbnails().set(
            videoId=video_id,
            media_body=str(thumbnail_path)
        ).execute()
        
        logger.info(f"✅ Successfully uploaded!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to upload: {e}")
        return False


def main():
    """Upload all Pexels thumbnails with delays."""
    logger.info("=" * 80)
    logger.info("UPLOAD PEXELS THUMBNAILS TO YOUTUBE")
    logger.info("=" * 80)
    logger.info(f"Target videos: {len(VIDEOS)}")
    logger.info(f"Delay between uploads: 60 seconds")
    logger.info("=" * 80)
    
    output_dir = Path("output/thumbnails")
    uploader = YouTubeUploader()
    
    success_count = 0
    fail_count = 0
    
    for i, video in enumerate(VIDEOS, 1):
        logger.info("")
        logger.info(f"[{i}/{len(VIDEOS)}] {video['title']}")
        logger.info("-" * 80)
        
        thumbnail_path = output_dir / video['filename']
        
        if not thumbnail_path.exists():
            logger.error(f"❌ Thumbnail file not found: {thumbnail_path}")
            fail_count += 1
            continue
        
        try:
            upload_success = upload_thumbnail(uploader, video['id'], thumbnail_path)
            
            if upload_success:
                success_count += 1
                logger.info(f"✅ [{i}/{len(VIDEOS)}] COMPLETED")
            else:
                fail_count += 1
                logger.error(f"❌ [{i}/{len(VIDEOS)}] FAILED")
            
            # Wait before next upload (except for last video)
            if i < len(VIDEOS):
                logger.info(f"⏳ Waiting 60 seconds before next upload...")
                time.sleep(60)
                
        except KeyboardInterrupt:
            logger.warning("⚠️  Process interrupted by user")
            break
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            fail_count += 1
            if i < len(VIDEOS):
                time.sleep(60)
    
    # Final summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("UPLOAD COMPLETE")
    logger.info("=" * 80)
    logger.info(f"✅ Successful: {success_count}/{len(VIDEOS)}")
    logger.info(f"❌ Failed: {fail_count}/{len(VIDEOS)}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
