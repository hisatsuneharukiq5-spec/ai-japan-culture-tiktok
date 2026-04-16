import sys
import os
# Ensure repository root is on sys.path so `src` is importable when running this script
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.article_generator import ArticleGenerator
from src.substack_publisher import SubstackPublisher
from dotenv import load_dotenv

load_dotenv()

def main():
    try:
        print("Starting article generation...")
        gen = ArticleGenerator()
        article = gen.generate_from_script()
        print("Article saved:", article.get("saved_path"))
    except Exception as e:
        print("Article generation failed:", e)
        raise

    try:
        print("Publishing to Substack...")
        pub = SubstackPublisher()
        data = pub.publish(
            title=article["title"],
            content=article["content"],
            tags=article.get("tags", []),
            subtitle=article.get("subtitle", ""),
        )
        print("Published:", data.get("url"))
    except Exception as e:
        print("Substack publish failed:", e)
        raise

if __name__ == '__main__':
    main()
