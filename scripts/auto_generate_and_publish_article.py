#!/usr/bin/env python3
"""
Auto-generate and publish articles on popular Japan topics for international audience.
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load environment variables first
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.script_generator import ScriptGenerator
from src.article_generator import ArticleGenerator
from src.substack_publisher import SubstackPublisher
from src.utils import setup_logger

logger = setup_logger("auto_article_generator")

# Popular Japan topics for international audience
INTERNATIONAL_TOPICS = [
    "Why Japanese People Are So Respectful_ The Deep Cultural Roots",
    "How Japan's School System Creates High Achievers",
    "The Hidden Meaning Behind Japanese Bowing Customs",
    "Why Green Tea Is Central to Japanese Culture and Health",
    "The Psychology Behind Japanese Minimalism and Organization",
    "How Sumo Wrestling Preserves Ancient Japanese Traditions",
    "The Business of Anime: How Japan Captured Global Markets",
    "Why Japanese Trains Are the World's Most Punctual",
    "The Art of Japanese Calligraphy: More Than Just Writing",
    "How Karaoke Became Japan's Most Social Entertainment",
]

def generate_article_for_topic(topic: str) -> dict:
    """Generate and save article for given topic"""
    
    print(f"\n【Generating Article】 Topic: {topic}")
    print("=" * 70)
    
    try:
        # Step 1: Generate script
        print("⏳ Generating script...")
        gen = ScriptGenerator()
        script_data = gen.generate(topic=topic)
        
        if not script_data or not script_data.get("narration"):
            print(f"❌ Script generation failed for topic: {topic}")
            return None
        
        print(f"✓ Script generated")
        
        # Step 2: Generate article from script
        print("⏳ Generating article...")
        article_gen = ArticleGenerator()
        article = article_gen.generate_from_data(
            metadata=script_data,
            narration=script_data["narration"]
        )
        
        if not article or not article.get("content"):
            print(f"❌ Article generation failed")
            return None
        
        print(f"✓ Article generated: {article['title']}")
        
        return {
            "topic": topic,
            "title": article.get("title", topic),
            "subtitle": article.get("subtitle", ""),
            "content": article.get("content", ""),
            "tags": article.get("tags", ["Japan", "Culture"]),
            "saved_path": article.get("saved_path", "")
        }
        
    except Exception as e:
        logger.error(f"Error generating article for {topic}: {e}")
        print(f"❌ Error: {e}")
        return None

def publish_article(article: dict) -> bool:
    """Publish article to Substack"""
    
    if not article:
        return False
    
    try:
        print(f"\n【Publishing Article】 {article['title']}")
        print("=" * 70)
        
        print("⏳ Publishing to Substack...")
        pub = SubstackPublisher()
        
        result = pub.publish(
            title=article["title"],
            content=article["content"],
            subtitle=article["subtitle"],
            tags=article.get("tags", ["Japan", "Culture"])
        )
        
        if result and result.get("url"):
            print(f"✅ Published successfully!")
            print(f"📄 URL: {result['url']}")
            print(f"📝 ID: {result.get('id', 'N/A')}")
            return True
        else:
            print(f"⚠️  Publish returned no URL: {result}")
            return False
            
    except Exception as e:
        logger.error(f"Error publishing article: {e}")
        print(f"❌ Error: {e}")
        return False

def main():
    import random
    
    print("=" * 70)
    print("Auto-Generate & Publish Article on Popular Japan Topic")
    print("=" * 70)
    
    # Select random topic from international topics
    selected_topic = random.choice(INTERNATIONAL_TOPICS)
    print(f"\n🎯 Selected Topic: {selected_topic}")
    
    # Generate article
    article = generate_article_for_topic(selected_topic)
    
    if not article:
        print("\n❌ Failed to generate article")
        return 1
    
    # Publish article
    if publish_article(article):
        print("\n" + "=" * 70)
        print("✅ Article successfully generated and published!")
        print("=" * 70)
        return 0
    else:
        print("\n❌ Failed to publish article")
        return 1

if __name__ == "__main__":
    sys.exit(main())
