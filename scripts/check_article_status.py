#!/usr/bin/env python3
"""
Article generation completion check - Run after waiting
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).parent.parent

def check_completion():
    """Check if article was generated and published in last 5 minutes"""
    
    # Check for recent article files
    articles_dir = ROOT / "output" / "articles"
    recent_articles = []
    
    if articles_dir.exists():
        now = datetime.now()
        for f in articles_dir.glob("*.md"):
            mod_time = datetime.fromtimestamp(f.stat().st_mtime)
            if now - mod_time < timedelta(minutes=5):
                recent_articles.append(f)
    
    # Check Substack session for recent publishes
    session_file = ROOT / "config" / "substack_session.json"
    
    print("\n" + "=" * 70)
    print("ARTICLE GENERATION & PUBLICATION STATUS")
    print("=" * 70 + "\n")
    
    if recent_articles:
        print(f"✅ Recent articles created ({len(recent_articles)}):")
        for article in sorted(recent_articles, key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
            size_kb = article.stat().st_size / 1024
            print(f"   • {article.name} ({size_kb:.1f} KB)")
            print(f"     Modified: {datetime.fromtimestamp(article.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print("⏳ No recent articles detected yet")
    
    print("\n📌 Status Summary:")
    print("   • Article generation: ", end="")
    if recent_articles:
        print("✅ COMPLETE")
    else:
        print("⏳ IN PROGRESS")
    
    print("   • Publication: ", end="")
    if session_file.exists():
        print("✅ Configured")
    else:
        print("⚠️  Not configured")
    
    print("\n" + "=" * 70 + "\n")

if __name__ == "__main__":
    check_completion()
