#!/usr/bin/env python3
"""
Simple article generation from latest video metadata + publish to Substack.
"""

import sys
import os
from pathlib import Path

# Setup paths
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load env before imports
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# Now safe to import
import json
from src.article_generator import ArticleGenerator
from src.substack_publisher import SubstackPublisher
from src.utils import setup_logger

logger = setup_logger("simple_article_gen")

def main():
    print("\n" + "=" * 70)
    print("SIMPLE ARTICLE GENERATION & PUBLICATION")
    print("=" * 70 + "\n")
    
    # Load latest metadata
    ROOT = Path(__file__).parent.parent
    metadata_file = ROOT / "output" / "metadata_verification.json"
    
    if not metadata_file.exists():
        print("❌ No metadata file found")
        return 1
    
    try:
        with open(metadata_file, encoding='utf-8') as f:
            all_metadata = json.load(f)
        
        if not all_metadata:
            print("❌ No metadata records")
            return 1
        
        latest_meta = all_metadata[-1]  # Last one is most recent
        
        print(f"📝 Latest Video Title: {latest_meta.get('title', 'Unknown')}")
        desc = latest_meta.get('description', '')[:200]
        print(f"   Description: {desc}...")
        
        # Generate article directly from narration if it exists
        narration_file = ROOT / "output" / "narration.txt"
        if narration_file.exists():
            with open(narration_file, encoding='utf-8') as f:
                narration = f.read()
            print(f"✓ Using narration from file")
        else:
            # Use description as narration fallback
            narration = latest_meta.get('description', '')
            if narration:
                print(f"✓ Using description as narration ({len(narration)} chars)")
        
        if not narration or len(narration) < 50:
            print(f"⚠️  Available narration: {len(narration) if narration else 0} chars")
            print(f"✓ Proceeding with best available content...")
            # Use title as fallback
            narration = f"{latest_meta.get('title', '')}. {latest_meta.get('description', '')}"
        
        # Generate article
        print("\n⏳ Generating article...")
        gen = ArticleGenerator()
        article = gen.generate_from_data(latest_meta, narration)
        
        if not article:
            print("❌ Article generation failed")
            return 1
        
        print(f"✅ Article generated: {article['title']}")
        print(f"   Path: {article.get('saved_path', 'N/A')}")
        
        # Publish to Substack
        print("\n⏳ Publishing to Substack...")
        pub = SubstackPublisher()
        
        result = pub.publish(
            title=article["title"],
            content=article["content"],
            subtitle=article.get("subtitle", ""),
            tags=["Japan", "Culture", "Automation"]
        )
        
        if result and result.get("url"):
            print(f"\n✅ Published successfully!")
            print(f"📄 URL: {result['url']}")
            print(f"📝 ID: {result.get('id', 'N/A')}")
            
            print("\n" + "=" * 70)
            print("✅ ARTICLE SUCCESSFULLY GENERATED AND PUBLISHED")
            print("=" * 70 + "\n")
            return 0
        else:
            print(f"⚠️  Publish returned: {result}")
            return 1
            
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
