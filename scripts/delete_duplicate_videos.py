#!/usr/bin/env python3
"""
Delete duplicate Japanese Culture Radio videos from YouTube.
Keeps only the most recent one (zu5kg-HETRg).
"""

from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.utils import setup_logger
from src.youtube_uploader import YouTubeUploader

logger = setup_logger("delete_duplicate_videos")

# Duplicate video IDs to delete (keep only the first/newest one)
VIDEOS_TO_DELETE = [
    ("pzoUI7msd4k", "Japanese Culture Radio - Vol.1 (2026-03-04 09:44:58)"),
    ("fZvcnntUwfw", "Japanese Culture Radio - Vol.1 (2026-03-04 09:38:18)"),
    ("HaniST0Vg00", "Japanese Culture Radio - Vol.1 (2026-03-04 09:35:14)"),
    ("YKMiUb0XBtY", "Japanese Culture Radio 🎌 - Vol.1 (old emoji version, 2026-03-04 09:33:22)"),
]

def delete_videos():
    """Delete duplicate videos from YouTube."""
    try:
        uploader = YouTubeUploader()
        youtube = uploader.youtube
        
        deleted = 0
        failed = 0
        
        for video_id, description in VIDEOS_TO_DELETE:
            try:
                logger.info(f"Deleting: {description}")
                youtube.videos().delete(id=video_id).execute()
                logger.info(f"✓ Deleted: {video_id}\n")
                deleted += 1
            except Exception as e:
                logger.error(f"✗ Failed to delete {video_id}: {e}\n")
                failed += 1
        
        # Summary
        print("\n" + "="*80)
        print("DELETE SUMMARY")
        print("="*80)
        print(f"Successfully deleted: {deleted}")
        print(f"Failed: {failed}")
        print(f"\nKept (most recent): zu5kg-HETRg - Japanese Culture Radio - Learn About Japan While You Work/Study | Vol.1")
        print("="*80 + "\n")
        
        return failed == 0
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    success = delete_videos()
    sys.exit(0 if success else 1)
