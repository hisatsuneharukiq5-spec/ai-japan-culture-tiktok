#!/usr/bin/env python3
"""
Generate AI-powered thumbnails for all YouTube videos with proper titles and content.
Maps video filenames to their actual titles and generates matching thumbnails.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.thumbnail_generator import create_thumbnail
from src.utils import setup_logger

logger = setup_logger("generate_video_thumbnails")

# Video filename → (title, topic/description)
VIDEO_THUMBNAILS = {
    "Why Japanese Convenience Store.mp4": (
        "Why Japanese Convenience Stores Are Amazing",
        "Japanese culture, convenience store culture, daily life in Japan"
    ),
    "5 Temple Rules Every Visitor t.mp4": (
        "5 Temple Rules Every Visitor Should Know",
        "Japanese temples, etiquette, traditions, visiting Japan"
    ),
    "invideo-ai-1080-japanese-train-rules-2026-03-02.mp4": (
        "Japanese Train Etiquette: 5 Rules You Must Know",
        "Japanese trains, etiquette, public transportation, customs"
    ),
    "Japanese tea ceremony.mp4": (
        "Japanese Tea Ceremony - A Guide",
        "Japanese tea ceremony, traditions, culture, etiquette"
    ),
    "Untitled_Project.mp4": (
        "Why Tipping Is RUDE in Japan",
        "Japanese culture, tipping, etiquette, customs, cultural differences"
    ),
    "Untitled_Project (1).mp4": (
        "How Japan Keeps Its Streets Clean",
        "Japanese culture, cleanliness, public spaces, daily habits"
    ),
    "Untitled_Project (2).mp4": (
        "Tokyo vs Osaka: Escalator Rules",
        "Japanese culture, Tokyo, Osaka, cultural differences, etiquette"
    ),
}

def generate_all_thumbnails():
    """Generate thumbnails for all main videos."""
    video_dir = Path("output/videos")
    thumbnail_dir = Path("output/thumbnails")
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    
    successfully_generated = []
    failed = []
    skipped = []
    
    for video_file, (title, topic) in VIDEO_THUMBNAILS.items():
        video_path = video_dir / video_file
        
        # Check if video exists
        if not video_path.exists():
            logger.warning(f"Video not found: {video_file}")
            skipped.append(video_file)
            continue
        
        # Generate thumbnail filename from video name
        thumb_filename = video_path.stem + "_thumbnail.jpg"
        
        try:
            logger.info(f"\nGenerating thumbnail for: {title}")
            logger.info(f"Topic: {topic}")
            
            result_path = create_thumbnail(
                title=title,
                topic=topic,
                output_filename=thumb_filename
            )
            
            logger.info(f"✓ Thumbnail saved: {result_path}")
            successfully_generated.append((video_file, title, result_path))
            
        except Exception as e:
            logger.error(f"✗ Failed to generate thumbnail for {video_file}: {e}")
            failed.append((video_file, str(e)))
    
    # Summary
    print("\n" + "="*80)
    print("THUMBNAIL GENERATION SUMMARY")
    print("="*80)
    print(f"\nSuccessfully generated: {len(successfully_generated)}")
    for video, title, path in successfully_generated:
        print(f"  ✓ {title}")
        print(f"    → {path}")
    
    if failed:
        print(f"\nFailed: {len(failed)}")
        for video, error in failed:
            print(f"  ✗ {video}: {error}")
    
    if skipped:
        print(f"\nSkipped: {len(skipped)}")
        for video in skipped:
            print(f"  ~ {video}")
    
    print("\n" + "="*80)
    
    return len(failed) == 0

if __name__ == "__main__":
    success = generate_all_thumbnails()
    sys.exit(0 if success else 1)
