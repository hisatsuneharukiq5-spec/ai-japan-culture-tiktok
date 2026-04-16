#!/usr/bin/env python3
"""
Upload Japanese Culture Radio directly to YouTube
"""

import sys
import json
from pathlib import Path

# Set up path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from src.youtube_uploader import YouTubeUploader`nfrom src.utils import setup_logger`n`nlogger = setup_logger("upload_radio_safe")


def upload_radio():
    """Upload Japanese Culture Radio to YouTube."""
    video_file = Path("output/videos/Japanese_Culture_Radio_Vol1.mp4")
    thumbnail_file = Path("output/thumbnails/radio_thumbnail.jpg")
    description_file = Path("output/radio_description.txt")
    
    log_file = Path("output/radio_upload.log")
    
    def log_msg(msg: str):
        """Print and log message."""
        print(msg, flush=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    
    if not video_file.exists():
        log_msg(f"Error: Video file not found: {video_file}")
        return False
    
    # Read description
    description = ""
    if description_file.exists():
        with open(description_file, "r", encoding="utf-8") as f:
            description = f.read()
    
    # Create metadata
    script_data = {
        "title": "Japanese Culture Radio - Learn About Japan While You Work/Study | Vol.1",
        "description": description,
        "tags": [
            "JapaneseCulture",
            "JapanRadio",
            "StudyWithMe",
            "WorkWithMe",
            "JapanBGM",
            "LearnAboutJapan",
            "AIJapan",
            "JapanFacts",
            "Relaxing"
        ],
        "category_id": "27",  # Education
    }
    
    try:
        log_msg("Uploading Japanese Culture Radio to YouTube...")
        uploader = YouTubeUploader()
        video_id = uploader.upload(str(video_file), script_data)
        
        if video_id:
            log_msg(f"\nUpload successful!")
            log_msg(f"Video ID: {video_id}")
            log_msg(f"URL: https://www.youtube.com/watch?v={video_id}")
            
            # Upload thumbnail if available
            if thumbnail_file.exists():
                log_msg(f"\nUploading thumbnail...")
                try:
                    uploader.youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=str(thumbnail_file),
                    ).execute()
                    log_msg(f"Thumbnail uploaded successfully!")
                except Exception as e:
                    log_msg(f"Thumbnail upload failed: {e}")
            
            return True
        else:
            log_msg(f"\nUpload failed")
            return False
            
    except Exception as e:
        error_str = str(e)
        if "uploadLimitExceeded" in error_str or "too many" in error_str.lower():
            log_msg(f"\nYouTube upload limit reached: {e}")
            log_msg("Skipping upload as requested.")
            return False
        elif "quotaExceeded" in error_str:
            log_msg(f"\nYouTube quota exceeded: {e}")
            log_msg("Skipping upload as requested.")
            return False
        else:
            log_msg(f"\nUpload error: {e}")
            raise


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    success = upload_radio()
    sys.exit(0 if success else 1)

