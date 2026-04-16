#!/usr/bin/env python3
"""Generate AI-powered thumbnails for existing videos."""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.thumbnail_generator import create_thumbnail
from src.utils import setup_logger

logger = setup_logger("regenerate_thumbnails_ai")

# Videos to regenerate with AI backgrounds
VIDEOS_TO_REGENERATE = [
    {
        "title": "Hanami — Why Japan Goes Crazy for Cherry Blossoms",
        "topic": "Cherry blossom viewing tradition, hanami culture, sakura season in Japan",
        "output_filename": "hanami_cherry_blossoms_thumbnail.jpg"
    },
    {
        "title": "Japan Etiquette Guide — 5 Rules Tourists Must Know",
        "topic": "Japanese manners, cultural etiquette, tourist rules, respectful behavior",
        "output_filename": "japan_etiquette_guide_thumbnail.jpg"
    },
    {
        "title": "How to Make Friends in Japan as a Foreigner",
        "topic": "Social life in Japan, making Japanese friends, expat community, cultural exchange",
        "output_filename": "make_friends_japan_thumbnail.jpg"
    },
    {
        "title": "Why Tipping is RUDE in Japan",
        "topic": "Japanese tipping culture, service etiquette, cultural differences, omotenashi",
        "output_filename": "Untitled_Project_thumbnail.jpg"
    },
    {
        "title": "How Japan Keeps Its Streets So Incredibly Clean",
        "topic": "Japanese cleanliness culture, public spaces, daily habits, street cleaning",
        "output_filename": "Untitled_Project (1)_thumbnail.jpg"
    },
    {
        "title": "Why Japanese Convenience Stores Are World Class",
        "topic": "Japanese konbini culture, 24-hour stores, amazing service, unique products",
        "output_filename": "Why Japanese Convenience Store_thumbnail.jpg"
    },
]

def main():
    """Regenerate thumbnails with AI backgrounds."""
    print("\n" + "="*80)
    print("🎨 AI THUMBNAIL REGENERATION")
    print("="*80 + "\n")
    
    successfully_generated = []
    failed = []
    
    for i, video in enumerate(VIDEOS_TO_REGENERATE, 1):
        title = video["title"]
        topic = video["topic"]
        output_filename = video["output_filename"]
        
        try:
            print(f"\n[{i}/{len(VIDEOS_TO_REGENERATE)}] Generating: {title}")
            print(f"Topic: {topic}")
            
            result_path = create_thumbnail(
                title=title,
                topic=topic,
                output_filename=output_filename
            )
            
            print(f"✅ Success: {result_path}")
            successfully_generated.append((title, result_path))
            
        except Exception as e:
            print(f"❌ Failed: {e}")
            logger.error(f"Failed to generate thumbnail for {title}: {e}")
            failed.append((title, str(e)))
    
    # Summary
    print("\n" + "="*80)
    print("REGENERATION SUMMARY")
    print("="*80)
    print(f"✅ Successfully generated: {len(successfully_generated)}")
    print(f"❌ Failed: {len(failed)}")
    print(f"📊 Total: {len(VIDEOS_TO_REGENERATE)}")
    print("="*80 + "\n")
    
    if successfully_generated:
        print("✅ Successfully generated:")
        for title, path in successfully_generated:
            print(f"  • {title}")
            print(f"    {path}")
    
    if failed:
        print("\n❌ Failed:")
        for title, error in failed:
            print(f"  • {title}")
            print(f"    Error: {error}")
    
    return len(failed) == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
