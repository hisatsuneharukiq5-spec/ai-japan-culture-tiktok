#!/usr/bin/env python3
"""
Upload Japanese Culture Radio with deduplication check to prevent duplicates.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from src.youtube_uploader import YouTubeUploader
from src.utils import setup_logger

logger = setup_logger("upload_radio_safe")

def video_exists_on_channel(youtube, title_keyword: str) -> bool:
    """Check if a video with similar title already exists on channel."""
    request = youtube.search().list(
        part="id,snippet",
        forMine=True,
        type="video",
        maxResults=50,
        order="date",
    )
    
    while request:
        response = request.execute()
        for item in response.get("items", []):
            existing_title = item["snippet"]["title"].lower()
            if title_keyword.lower() in existing_title:
                logger.info(f"Found existing video: {item['snippet']['title']}")
                return True
        request = youtube.search().list_next(request, response)
    
    return False

def upload_radio():
    """Upload Japanese Culture Radio to YouTube with deduplication check."""
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
        "category_id": "27",
    }
    
    try:
        log_msg("Checking for existing Japanese Culture Radio videos...")
        uploader = YouTubeUploader()
        
        # Check for duplicates
        if video_exists_on_channel(uploader.youtube, "Japanese Culture Radio"):
            log_msg("Duplicate video detected! Skipping upload.")
            return False
        
        log_msg("No duplicates found. Uploading Japanese Culture Radio to YouTube...")
        video_id = uploader.upload(str(video_file), script_data)
        
        if video_id:
            log_msg(f"\nUpload successful!")
            log_msg(f"Video ID: {video_id}")
            log_msg(f"URL: https://www.youtube.com/watch?v={video_id}")
            
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
            log_msg(f"\nYouTube upload limit reached")
            return False
        elif "quotaExceeded" in error_str:
            log_msg(f"\nYouTube quota exceeded")
            return False
        else:
            log_msg(f"\nUpload error: {e}")
            raise


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    success = upload_radio()
    sys.exit(0 if success else 1)
