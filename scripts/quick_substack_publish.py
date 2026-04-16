#!/usr/bin/env python3
"""
Publish latest article to Substack - Direct execution
"""

import sys
import os
from pathlib import Path

# Ensure paths
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.substack_publisher import SubstackPublisher
import json

def get_latest_article():
    """Get the latest article from output/articles"""
    articles_dir = ROOT / "output" / "articles"
    articles = list(articles_dir.glob("*.md"))
    if not articles:
        raise FileNotFoundError("No articles found in output/articles")
    
    latest = sorted(articles, key=lambda x: x.stat().st_mtime, reverse=True)[0]
    return latest

def extract_metadata_and_content(md_file):
    """Extract title, subtitle, and content from markdown"""
    with open(md_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    lines = content.split("\n")
    title = ""
    subtitle = ""
    body = ""
    
    # First line usually title
    if lines and lines[0].startswith("#"):
        title = lines[0].lstrip("#").strip()
        body_start = 1
    else:
        title = md_file.stem
        body_start = 0
    
    # Find subtitle or use first paragraph
    sub_idx = None
    for i in range(body_start, min(body_start + 5, len(lines))):
        if lines[i].strip() and not lines[i].startswith("#"):
            subtitle = lines[i].strip()[:150]  # First 150 chars
            sub_idx = i
            break
    
    body = "\n".join(lines[sub_idx+1:] if sub_idx else lines[body_start:])
    body = body.replace("[[", "[").replace("]]", "]")  # Cleanup wiki links
    
    return {
        "title": title,
        "subtitle": subtitle,
        "content": body,
        "file": str(md_file)
    }

def main():
    try:
        print("【Substack Publication】")
        print("=" * 70)
        
        # Get latest article
        latest_md = get_latest_article()
        print(f"\n✓ Latest article: {latest_md.name}")
        
        # Extract metadata
        article = extract_metadata_and_content(latest_md)
        print(f"✓ Title: {article['title']}")
        print(f"✓ Subtitle: {article['subtitle'][:80]}...")
        
        # Publish to Substack
        print("\n⏳ Publishing to Substack...")
        publisher = SubstackPublisher()
        
        result = publisher.publish(
            title=article["title"],
            content=article["content"],
            subtitle=article["subtitle"],
            tags=["AI", "YouTube", "Automation"]
        )
        
        print(f"\n✅ Published successfully!")
        print(f"📄 URL: {result.get('url', 'N/A')}")
        print(f"📝 Lookup ID: {result.get('id', 'N/A')}")
        
        print("\n" + "=" * 70)
        print("投稿完了 | Publication Complete")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
