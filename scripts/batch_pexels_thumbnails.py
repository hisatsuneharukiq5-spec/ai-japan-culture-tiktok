#!/usr/bin/env python3
"""Generate and upload Pexels-based thumbnails one by one with delays."""

import os
import sys
import time
import requests
import io
import urllib.parse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from src.youtube_uploader import YouTubeUploader
from src.utils import setup_logger

logger = setup_logger("batch_pexels_thumbnails")

W, H = 1280, 720
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# Target videos with their IDs and search queries
VIDEOS = [
    {
        "id": "B8mewBpmCc4",
        "title": "Hanami — Why Japan Goes Crazy for Cherry Blossoms 🌸",
        "search": "cherry blossom japan tourists spring",
        "filename": "hanami_pexels.jpg"
    },
    {
        "id": "SzztC4iR7mI",
        "title": "Japan Etiquette Guide — 5 Rules Tourists Must Know",
        "search": "japan tourist shibuya crossing tokyo",
        "filename": "etiquette_pexels.jpg"
    },
    {
        "id": "TTZON3PzeyU",
        "title": "How to Make Friends in Japan as a Foreigner",
        "search": "japanese friends izakaya restaurant laughing",
        "filename": "friends_pexels.jpg"
    },
    {
        "id": "OF3wwKby0Xk",
        "title": "Why Tipping is RUDE in Japan (Service Culture Explained)",
        "search": "japanese restaurant server traditional",
        "filename": "tipping_pexels.jpg"
    },
    {
        "id": "lED2InG7_Xo",
        "title": "How Japan Keeps Its Streets So Incredibly Clean",
        "search": "tokyo street clean pristine japan cityscape",
        "filename": "clean_streets_pexels.jpg"
    },
    {
        "id": "b0Tz9PiLRL8",
        "title": "Why Japanese Convenience Stores Are World — Class",
        "search": "japanese convenience store interior bright",
        "filename": "convenience_pexels.jpg"
    },
]


def get_pexels_photo(search_query: str, output_path: Path) -> Path | None:
    """Download a relevant photo from Pexels."""
    if not PEXELS_API_KEY:
        logger.error("PEXELS_API_KEY not set")
        return None
    
    try:
        headers = {"Authorization": PEXELS_API_KEY}
        url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(search_query)}&per_page=5&orientation=landscape"
        
        logger.info(f"🔍 Searching Pexels for: {search_query}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        if not data.get("photos"):
            logger.warning(f"No photos found for: {search_query}")
            return None
        
        # Get the first high-quality photo
        photo = data["photos"][0]
        image_url = photo["src"]["large2x"]
        
        logger.info(f"📥 Downloading photo from Pexels...")
        img_response = requests.get(image_url, timeout=60)
        img_response.raise_for_status()
        
        # Load and resize image
        img = Image.open(io.BytesIO(img_response.content)).convert("RGB")
        img = img.resize((W, H), Image.LANCZOS)
        
        # Save background image
        img.save(str(output_path), "JPEG", quality=95)
        logger.info(f"✅ Photo saved: {output_path.name}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error downloading Pexels photo: {e}")
        return None


def add_text_overlay(img_path: Path, title: str, output_path: Path) -> Path:
    """Add text overlay to Pexels photo."""
    img = Image.open(img_path).convert("RGBA")
    
    # Dark gradient overlay on left for text readability
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    # Left side gradient
    fade_w = int(W * 0.65)
    for x in range(fade_w):
        t = x / fade_w
        alpha = int(200 * (1 - t ** 0.5))
        ov_draw.line([(x, 0), (x, H)], fill=(0, 0, 0, alpha))
    
    # Bottom gradient
    for y in range(H - 100, H):
        t = (y - (H - 100)) / 100
        alpha = int(180 * t)
        ov_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    
    img = Image.alpha_composite(img, overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    
    # Load fonts
    font_paths = [
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    
    title_font = None
    for fp in font_paths:
        try:
            title_font = ImageFont.truetype(fp, 90)
            break
        except:
            continue
    
    if not title_font:
        title_font = ImageFont.load_default()
    
    # Split title into lines
    words = title.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=title_font)
        if bbox[2] - bbox[0] < 700:  # Max width
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(" ".join(current_line))
    
    # Draw text with outline
    y_pos = 50
    line_height = 100
    
    for line in lines:
        # Gold text with black outline
        outline_color = (0, 0, 0)  # Black
        text_color = (255, 215, 0)  # Gold
        
        # Draw outline
        for dx in [-4, -2, 0, 2, 4]:
            for dy in [-4, -2, 0, 2, 4]:
                if dx != 0 or dy != 0:
                    draw.text((50 + dx, y_pos + dy), line, font=title_font, fill=outline_color)
        
        # Draw main text
        draw.text((50, y_pos), line, font=title_font, fill=text_color)
        y_pos += line_height
    
    # Save final thumbnail
    img.save(str(output_path), "JPEG", quality=95)
    logger.info(f"✨ Text overlay added: {output_path.name}")
    
    return output_path


def upload_to_youtube(video_id: str, thumbnail_path: Path) -> bool:
    """Upload thumbnail to YouTube."""
    try:
        uploader = YouTubeUploader()
        
        logger.info(f"📤 Uploading thumbnail to YouTube (Video ID: {video_id})...")
        
        uploader.youtube.thumbnails().set(
            videoId=video_id,
            media_body=str(thumbnail_path)
        ).execute()
        
        logger.info(f"✅ Successfully uploaded thumbnail to YouTube!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to upload thumbnail: {e}")
        return False


def main():
    """Generate and upload thumbnails one by one."""
    logger.info("=" * 80)
    logger.info("BATCH PEXELS THUMBNAIL GENERATION & UPLOAD")
    logger.info("=" * 80)
    logger.info(f"Target videos: {len(VIDEOS)}")
    logger.info(f"Delay between uploads: 60 seconds")
    logger.info("=" * 80)
    
    output_dir = Path("output/thumbnails")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    fail_count = 0
    
    for i, video in enumerate(VIDEOS, 1):
        logger.info("")
        logger.info(f"[{i}/{len(VIDEOS)}] Processing: {video['title']}")
        logger.info(f"Video ID: {video['id']}")
        logger.info("-" * 80)
        
        try:
            # Step 1: Download Pexels photo
            bg_path = output_dir / f"_bg_{video['filename']}"
            photo_path = get_pexels_photo(video['search'], bg_path)
            
            if not photo_path:
                logger.error(f"❌ Failed to download Pexels photo")
                fail_count += 1
                continue
            
            # Step 2: Add text overlay
            final_path = output_dir / video['filename']
            thumbnail_path = add_text_overlay(photo_path, video['title'], final_path)
            
            # Step 3: Upload to YouTube
            upload_success = upload_to_youtube(video['id'], thumbnail_path)
            
            if upload_success:
                success_count += 1
                logger.info(f"✅ [{i}/{len(VIDEOS)}] COMPLETED: {video['title']}")
            else:
                fail_count += 1
                logger.error(f"❌ [{i}/{len(VIDEOS)}] FAILED: {video['title']}")
            
            # Step 4: Wait before next upload (except for last video)
            if i < len(VIDEOS):
                logger.info(f"⏳ Waiting 60 seconds before next upload...")
                logger.info("")
                time.sleep(60)
                
        except KeyboardInterrupt:
            logger.warning("⚠️  Process interrupted by user")
            break
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            fail_count += 1
            # Wait even on error to avoid rate limits
            if i < len(VIDEOS):
                time.sleep(60)
    
    # Final summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("BATCH PROCESSING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"✅ Successful: {success_count}/{len(VIDEOS)}")
    logger.info(f"❌ Failed: {fail_count}/{len(VIDEOS)}")
    logger.info(f"📁 Output directory: {output_dir}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
