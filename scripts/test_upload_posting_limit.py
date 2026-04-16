#!/usr/bin/env python3
"""
Test upload for posting limit detection.
Creates 8-minute dummy video and uploads to YouTube without external links.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.dummy_video import create_dummy_video
from src.youtube_uploader import YouTubeUploader
from src.utils import setup_logger
from datetime import datetime

logger = setup_logger("test_upload_posting_limit")


def main():
    """Create and upload 8-minute test video."""
    
    logger.info("=" * 80)
    logger.info("YouTube POSTING LIMIT TEST")
    logger.info("=" * 80)
    logger.info("")
    
    # Step 1: Create 8-minute dummy video
    output_dir = Path("output/test_videos")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    video_path = output_dir / "test_8min_dummy.mp4"
    
    logger.info("📹 Creating 8-minute dummy video...")
    logger.info(f"Duration: 8 minutes (480 seconds)")
    
    try:
        create_dummy_video(video_path, duration_seconds=480)
        logger.info(f"✅ Video created: {video_path}")
        logger.info(f"📊 File size: {video_path.stat().st_size / 1024 / 1024:.1f} MB")
    except Exception as e:
        logger.error(f"❌ Failed to create video: {e}")
        return
    
    # Step 2: Upload to YouTube
    logger.info("")
    logger.info("📤 Uploading to YouTube...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = f"Test Upload {timestamp} - 8 Minutes Dummy Video"
    description = "This is a test video to check posting limits. No external links."
    
    logger.info(f"Title: {title}")
    logger.info(f"Description: {description}")
    logger.info("")
    
    try:
        uploader = YouTubeUploader()
        
        # Upload using the correct method signature
        script_data = {
            "title": title,
            "description": description,
            "tags": ["test", "dummy"],
        }
        
        video_id = uploader.upload(
            video_path=video_path,
            script_data=script_data
        )
        
        if video_id:
            logger.info("")
            logger.info("✅ VIDEO UPLOADED SUCCESSFULLY!")
            logger.info("")
            logger.info("📊 Upload Details:")
            logger.info(f"   Video ID: {video_id}")
            logger.info(f"   Title: {title}")
            logger.info(f"   Duration: 8 minutes")
            logger.info(f"   External Links: None")
            logger.info("")
            logger.info("🎯 Result: No posting limit error detected!")
            logger.info("")
            logger.info("📱 Watch at:")
            logger.info(f"   https://youtu.be/{video_id}")
            logger.info(f"   https://www.youtube.com/watch?v={video_id}")
            
        else:
            logger.error("❌ Upload failed - no video ID returned")
            
    except Exception as e:
        error_msg = str(e)
        logger.error("")
        logger.error("❌ UPLOAD ERROR DETECTED!")
        logger.error("")
        logger.error(f"Error Type: {type(e).__name__}")
        logger.error(f"Error Message: {error_msg}")
        
        # Get detailed traceback
        import traceback
        logger.error("")
        logger.error("詳細なエラー:")
        logger.error(traceback.format_exc())
        logger.error("")
        
        # Check for posting limit error
        if "quotaExceeded" in error_msg or "uploadLimitExceeded" in error_msg:
            logger.error("⚠️  POSTING LIMIT EXCEEDED!")
            logger.error("   → チャンネルが投稿制限に達している可能性があります")
        elif "forbidden" in error_msg.lower() or "403" in error_msg:
            logger.error("⚠️  PERMISSION DENIED (403)")
            logger.error("   → チャンネル確認が必要な可能性があります")
        elif "resourceInUse" in error_msg or "duplicate" in error_msg.lower():
            logger.error("⚠️  DUPLICATE/RESOURCE IN USE")
            logger.error("   → 同じ動画が既に存在する可能性があります")
        elif "retryerror" in error_msg.lower() or "typeerror" in error_msg.lower():
            logger.error("⚠️  RETRY/TYPE ERROR")
            logger.error("   → 動画ファイルまたはメタデータに問題があり可能性があります")
        
        logger.error("")
    
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
