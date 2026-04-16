#!/usr/bin/env python3
"""Generate and upload thumbnail for latest video using Pexels."""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.youtube_uploader import YouTubeUploader
from src.utils import setup_logger
import json

logger = setup_logger("thumbnail_upload")

# Latest metadata
with open("output/scripts/latest_metadata.json", "r", encoding="utf-8") as f:
    metadata = json.load(f)

title = metadata.get("title", "")
topic = metadata.get("topic", "")

logger.info("=" * 80)
logger.info("PEXELS THUMBNAIL GENERATION & UPLOAD")
logger.info("=" * 80)
logger.info(f"Title: {title}")
logger.info(f"Topic: {topic}")
logger.info("")

# Generate Pexels thumbnail using existing script
import subprocess
result = subprocess.run(
    [sys.executable, "scripts/pexels_thumbnail_generator.py"],
    capture_output=True,
    text=True
)

logger.info(result.stdout)
if result.stderr:
    logger.error(result.stderr)

# Find generated thumbnail
thumb_dir = Path("output/thumbnails")
pexels_thumbs = list(thumb_dir.glob("*_pexels.jpg"))

if not pexels_thumbs:
    logger.error("❌ No Pexels thumbnails found")
    sys.exit(1)

thumb_path = pexels_thumbs[-1]
logger.info(f"✅ Using thumbnail: {thumb_path}")
logger.info("")

# Upload to YouTube - use Video ID from latest upload
video_id = "9TOJVYYExSE"  # From latest upload

logger.info(f"📤 Uploading thumbnail to Video ID: {video_id}")
logger.info(f"   Thumbnail: {thumb_path}")

try:
    uploader = YouTubeUploader()
    
    uploader.youtube.thumbnails().set(
        videoId=video_id,
        media_body=str(thumb_path)
    ).execute()
    
    logger.info("")
    logger.info("✅ THUMBNAIL UPLOADED SUCCESSFULLY!")
    logger.info("")
    logger.info(f"📱 Watch at: https://www.youtube.com/watch?v={video_id}")
    logger.info("=" * 80)
    
except Exception as e:
    logger.error(f"❌ Upload failed: {e}")
    sys.exit(1)
