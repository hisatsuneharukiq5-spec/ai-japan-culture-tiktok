#!/usr/bin/env python3
"""
Generate thumbnails for all videos that don't have them yet.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.thumbnail_generator import create_thumbnail
from src.utils import setup_logger

logger = setup_logger("generate_missing_thumbnails")

# Videos needing thumbnails (excluding Radio)
VIDEOS_NEEDING_THUMBNAILS = [
    {
        "filename": "japan_etiquette_guide_thumbnail.jpg",
        "title": "Japan Etiquette Guide: 5 Rules Tourists Must Know",
        "topic": "Japanese etiquette, cultural rules, tourist tips, social customs"
    },
    {
        "filename": "make_friends_japan_thumbnail.jpg",
        "title": "How to Make Friends in Japan as a Foreigner",
        "topic": "Making friends in Japan, social connections, expat life, Japanese friendships"
    },
    {
        "filename": "hanami_cherry_blossoms_thumbnail.jpg",
        "title": "Hanami - Why Japan Goes Crazy for Cherry Blossoms",
        "topic": "Hanami festival, cherry blossoms, sakura, Japanese spring tradition"
    },
]

def main():
    """Generate thumbnails for all missing videos."""
    thumbnail_dir = Path("output/thumbnails")
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    
    successfully_generated = []
    failed = []
    
    for video_info in VIDEOS_NEEDING_THUMBNAILS:
        filename = video_info["filename"]
        title = video_info["title"]
        topic = video_info["topic"]
        
        try:
            logger.info(f"\nGenerating thumbnail for: {title}")
            logger.info(f"Topic: {topic}")
            
            result_path = create_thumbnail(
                title=title,
                topic=topic,
                output_filename=filename
            )
            
            logger.info(f"✓ Thumbnail saved: {result_path}")
            successfully_generated.append((title, result_path))
            
        except Exception as e:
            logger.error(f"✗ Failed to generate thumbnail for {title}: {e}")
            failed.append((title, str(e)))
    
    # Summary
    print("\n" + "="*80)
    print("THUMBNAIL GENERATION SUMMARY")
    print("="*80)
    print(f"\nSuccessfully generated: {len(successfully_generated)}")
    for title, path in successfully_generated:
        print(f"  ✓ {title}")
        print(f"    → {path}")
    
    if failed:
        print(f"\nFailed: {len(failed)}")
        for title, error in failed:
            print(f"  ✗ {title}: {error}")
    
    print("\n" + "="*80)
    
    return len(failed) == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
