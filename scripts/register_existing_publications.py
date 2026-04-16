"""Register already published articles to prevent duplicate publishing"""
import sys
import os
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_FILE = Path(ROOT) / "output" / "analytics" / "substack_publish_registry.json"

def compute_content_hash(content):
    """Compute SHA256 hash of article content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def main():
    # Articles that were already published
    published_articles = [
        {
            "filename": "20260307_180751_Hanami_ Why Japan Goes Absolutely_ Beautifully Crazy for Che.md",
            "url": "https://aijapanculture.substack.com/p/hanami-why-japan-goes-absolutely-16f",
            "title": "Hanami  Why Japan Goes Absolutely  Beautifully Crazy for Che",
            "published_at": "2026-03-07T22:27:30"
        },
        {
            "filename": "20260307_222903_Why Pointing Is Rude in Japan _ And What It Reveals About an.md",
            "url": "https://aijapanculture.substack.com/p/why-pointing-is-rude-in-japan-and-823",
            "title": "Why Pointing Is Rude in Japan   And What It Reveals About an",
            "published_at": "2026-03-07T22:29:30"
        }
    ]
    
    # Load existing registry or create new
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            registry = json.load(f)
    else:
        registry = {"published": []}
    
    # Add content hashes for each article
    articles_dir = Path(ROOT) / "output" / "articles"
    
    for article in published_articles:
        article_path = articles_dir / article["filename"]
        
        if article_path.exists():
            with open(article_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Clean up content like the publish script does
            content = re.sub(r'\n---\n\n## Watch It on YouTube.*$', '', content, flags=re.DOTALL)
            content = content.strip()
            
            article["content_hash"] = compute_content_hash(content)
            print(f"✓ Added hash for: {article['filename']}")
        else:
            print(f"⚠️  File not found: {article['filename']}")
        
        registry["published"].append(article)
    
    # Save registry
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Registry created: {REGISTRY_FILE}")
    print(f"   Total entries: {len(registry['published'])}")

if __name__ == '__main__':
    main()
