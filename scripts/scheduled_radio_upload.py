#!/usr/bin/env python3
"""
Scheduled Radio Video Upload
Automatically uploads the Radio video after 24-hour quota reset.
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.youtube_uploader import YouTubeUploader

# Setup logging
log_file = Path(__file__).parent.parent / 'logs' / f'{datetime.now().strftime("%Y-%m-%d")}.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('scheduled_radio_upload')

# Radio video metadata file
RADIO_VIDEO_PATH = Path(__file__).parent.parent / 'output' / 'videos' / 'Japanese_Culture_Radio_Vol1.mp4'
RADIO_METADATA_FILE = Path(__file__).parent.parent / 'output' / 'scripts' / 'latest_metadata.json'

# First upload time (when quota was exhausted) - Update this based on your first upload
FIRST_UPLOAD_TIME = datetime(2026, 3, 5, 2, 3, 16)  # UTC time

def wait_for_quota_reset():
    """Wait until quota resets (24 hours after first upload)"""
    
    quota_reset_time = FIRST_UPLOAD_TIME + timedelta(hours=24)
    current_time = datetime.utcnow()
    
    logger.info(f"Quota System Reset Calculator")
    logger.info(f"First upload: {FIRST_UPLOAD_TIME.isoformat()} UTC")
    logger.info(f"Quota reset: {quota_reset_time.isoformat()} UTC")
    logger.info(f"Current time: {current_time.isoformat()} UTC")
    
    if current_time >= quota_reset_time:
        logger.info("✓ Quota already reset! Ready to upload.")
        return True
    
    wait_seconds = (quota_reset_time - current_time).total_seconds()
    wait_hours = wait_seconds / 3600
    wait_minutes = (wait_seconds % 3600) / 60
    
    logger.info(f"⏳ Waiting {int(wait_hours):02d}h {int(wait_minutes):02d}m for quota reset...")
    
    # Wait with progress updates
    while datetime.utcnow() < quota_reset_time:
        remaining = (quota_reset_time - datetime.utcnow()).total_seconds()
        
        if remaining <= 0:
            logger.info("✓ Quota reset time reached!")
            break
        
        # Log progress every hour
        if int(remaining) % 3600 == 0 or remaining < 60:
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            logger.info(f"⏳ Time until reset: {hours:02d}h {minutes:02d}m")
        
        # Sleep in 60-second intervals to allow responsive checking
        time.sleep(min(60, remaining))
    
    logger.info("✓ Quota reset complete! Starting upload...")
    return True

def load_radio_metadata():
    """Load Radio video metadata"""
    
    if not RADIO_METADATA_FILE.exists():
        logger.error(f"❌ Metadata file not found: {RADIO_METADATA_FILE}")
        return None
    
    try:
        with open(RADIO_METADATA_FILE, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        logger.info(f"✓ Loaded metadata: {metadata.get('title', 'Unknown')}")
        return metadata
    except Exception as e:
        logger.error(f"❌ Error loading metadata: {e}")
        return None

def check_for_duplicates(uploader, title):
    """Check if a video with the same title already exists on the channel"""
    
    try:
        logger.info(f"🔍 Checking for existing videos with title: '{title}'")
        
        request = uploader.youtube.search().list(
            part='snippet',
            forMine=True,
            type='video',
            maxResults=50,
            order='date'
        )
        response = request.execute()
        
        if not response.get('items'):
            logger.info("✓ No existing videos found")
            return None
        
        for item in response['items']:
            existing_title = item['snippet']['title']
            video_id = item['id']['videoId']
            
            # Check for exact or partial match (to catch reupload attempts)
            if title.lower() in existing_title.lower() or existing_title.lower() in title.lower():
                logger.warning(f"⚠️  DUPLICATE DETECTED!")
                logger.warning(f"   Existing title: '{existing_title}'")
                logger.warning(f"   Existing ID: {video_id}")
                logger.warning(f"   URL: https://www.youtube.com/watch?v={video_id}")
                return video_id
        
        logger.info("✓ No duplicates found - safe to upload")
        return None
        
    except Exception as e:
        logger.warning(f"⚠️  Could not check for duplicates: {e}")
        # Allow upload to proceed if check fails
        return None

def upload_radio_video():
    """Upload the Radio video"""
    
    logger.info("="*80)
    logger.info("【ラジオビデオ自動アップロード】SCHEDULED RADIO VIDEO UPLOAD")
    logger.info("="*80)
    
    # Wait for quota reset
    if not wait_for_quota_reset():
        logger.error("❌ Failed to wait for quota reset")
        return False
    
    # Verify video file exists
    if not RADIO_VIDEO_PATH.exists():
        logger.error(f"❌ Radio video file not found: {RADIO_VIDEO_PATH}")
        return False
    
    logger.info(f"✓ Video file confirmed: {RADIO_VIDEO_PATH}")
    
    # Load metadata
    metadata = load_radio_metadata()
    if not metadata:
        logger.error("❌ Could not load metadata")
        return False
    
    # Initialize uploader
    try:
        uploader = YouTubeUploader()
        logger.info("✓ YouTube uploader initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize uploader: {e}")
        return False
    
    # Check for duplicates
    title = metadata.get('title', 'Japanese Culture Radio Vol.1')
    duplicate_id = check_for_duplicates(uploader, title)
    
    if duplicate_id:
        logger.error(f"❌ ABORT: Duplicate video already exists!")
        logger.error(f"   Existing video: https://www.youtube.com/watch?v={duplicate_id}")
        logger.error(f"   Not uploading to avoid duplication")
        return False
    
    logger.info("✓ Duplicate check passed - proceeding with upload")
    
    # Upload video
    logger.info(f"\n📹 Uploading video: {metadata.get('title', 'Radio Video')}")
    logger.info(f"   File: {RADIO_VIDEO_PATH}")
    logger.info(f"   Size: {RADIO_VIDEO_PATH.stat().st_size / (1024*1024):.1f} MB")
    
    try:
        video_id = uploader.upload_video(
            file_path=str(RADIO_VIDEO_PATH),
            title=metadata.get('title', 'Japanese Culture Radio Vol.1'),
            description=metadata.get('description', ''),
            category_id=metadata.get('category_id', '22'),
            tags=metadata.get('tags', []),
            privacy_status='public',
            default_language=metadata.get('language', 'ja'),
            default_audio_language=metadata.get('language', 'ja')
        )
        
        if video_id:
            logger.info(f"\n✅ SUCCESS! Video uploaded with ID: {video_id}")
            logger.info(f"   Watch URL: https://www.youtube.com/watch?v={video_id}")
            logger.info(f"   Studio URL: https://studio.youtube.com/video/{video_id}")
            
            # Save success info
            success_info = {
                'timestamp': datetime.now().isoformat(),
                'video_id': video_id,
                'title': metadata.get('title'),
                'upload_time_seconds': 0
            }
            
            success_file = Path(__file__).parent.parent / 'output' / 'radio_upload_success.json'
            with open(success_file, 'w', encoding='utf-8') as f:
                json.dump(success_info, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✓ Success info saved to: {success_file}")
            return True
        else:
            logger.error("❌ Upload failed or returned no video ID")
            return False
            
    except Exception as e:
        logger.error(f"❌ Upload error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main entry point"""
    
    print("\n" + "="*80)
    print("【スケジュール済みラジオビデオアップロード】")
    print("Scheduled Radio Video Upload Script")
    print("="*80)
    print(f"Start time: {datetime.now().isoformat()}")
    print(f"Radio video: {RADIO_VIDEO_PATH}")
    print(f"Metadata: {RADIO_METADATA_FILE}")
    print(f"\n⏳ This script will:")
    print("  1. Wait 24 hours for YouTube quota to reset")
    print("  2. Upload the Radio video automatically")
    print("  3. Log all results")
    print("\nPress Ctrl+C to cancel\n")
    
    try:
        success = upload_radio_video()
        
        logger.info("\n" + "="*80)
        if success:
            logger.info("✅ RADIO VIDEO UPLOAD COMPLETED SUCCESSFULLY")
        else:
            logger.info("❌ RADIO VIDEO UPLOAD FAILED")
        logger.info("="*80)
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Upload cancelled by user")
        return 2
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
