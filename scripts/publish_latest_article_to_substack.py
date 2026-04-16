import sys
import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime

# Ensure repository root is on sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.substack_publisher import SubstackPublisher

# Registry file to track published articles
REGISTRY_FILE = Path(ROOT) / "output" / "analytics" / "substack_publish_registry.json"

def _load_registry():
    """Load the registry of published articles."""
    if not REGISTRY_FILE.exists():
        return {"published": []}
    
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load registry: {e}")
        return {"published": []}

def _save_registry(registry):
    """Save the registry of published articles."""
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

def _compute_content_hash(content):
    """Compute SHA256 hash of article content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def _is_already_published(filename, content_hash, registry):
    """Check if article has already been published."""
    for entry in registry.get("published", []):
        if entry.get("filename") == filename:
            print(f"⚠️  Article already published: {filename}")
            print(f"   Published on: {entry.get('published_at')}")
            print(f"   URL: {entry.get('url')}")
            return True
        if entry.get("content_hash") == content_hash:
            print(f"⚠️  Identical content already published as: {entry.get('filename')}")
            print(f"   Published on: {entry.get('published_at')}")
            print(f"   URL: {entry.get('url')}")
            return True
    return False

def _record_publication(filename, content_hash, url, title, registry):
    """Record a successful publication in the registry."""
    entry = {
        "filename": filename,
        "content_hash": content_hash,
        "title": title,
        "url": url,
        "published_at": datetime.now().isoformat()
    }
    registry.setdefault("published", []).append(entry)
    _save_registry(registry)

def main():
    # Load registry
    registry = _load_registry()
    
    # Find latest article
    articles_dir = Path(ROOT) / "output" / "articles"
    articles = sorted(articles_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    
    if not articles:
        print("No articles found in output/articles/")
        return
    
    latest = articles[0]
    print(f"Found latest article: {latest.name}")
    
    # Read article content
    with open(latest, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Clean up content - remove YouTube section at the end
    content = re.sub(r'\n---\n\n## Watch It on YouTube.*$', '', content, flags=re.DOTALL)
    content = content.strip()
    
    # Compute content hash
    content_hash = _compute_content_hash(content)
    
    # Check for duplicates
    if _is_already_published(latest.name, content_hash, registry):
        print("\n❌ Skipping duplicate publication")
        return
    
    # Extract title from filename (remove timestamp prefix and .md extension)
    # Format: 20260307_180751_Title Here.md
    filename = latest.stem
    parts = filename.split("_", 2)
    if len(parts) >= 3:
        title = parts[2].replace("_", " ")
    else:
        title = filename.replace("_", " ")
    
    # Publish to Substack
    try:
        print(f"\nPublishing: {title}")
        publisher = SubstackPublisher()
        result = publisher.publish(
            title=title,
            content=content,
            tags=["Japan", "Culture"],
            subtitle=""
        )
        
        # Record successful publication
        url = result.get('url')
        _record_publication(latest.name, content_hash, url, title, registry)
        
        print(f"\n✅ Published successfully!")
        print(f"URL: {url}")
    except Exception as e:
        print(f"❌ Publishing failed: {e}")
        raise

if __name__ == '__main__':
    main()
