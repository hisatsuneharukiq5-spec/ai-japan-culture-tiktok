import csv
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from src.utils import setup_logger, PROJECT_ROOT

logger = setup_logger("outreach_researcher")

OUTREACH_DIR = PROJECT_ROOT / "output" / "outreach"
OUTPUT_CSV = OUTREACH_DIR / "candidates.csv"

# Substack categories to scan (id, label)
CATEGORIES = [
    (96,    "Culture"),
    (109,   "Travel"),
    (51282, "International"),
    (4,     "Technology"),
    (18,    "History"),
]
PAGES_PER_CATEGORY = 4  # 4 × 25 = 100 pubs per category

# Keyword sets for filtering
_JAPAN_KEYWORDS = [
    "japan", "japanese", "tokyo", "osaka", "kyoto", "expat",
    "anime", "manga", "nihon", "nippon", "living in japan",
    "life in japan", "move to japan",
]
_AI_KEYWORDS = [
    "ai automation", "ai content", "llm", "gpt", "claude",
    "no-code", "build in public", "automation",
]
_ALL_KEYWORDS = _JAPAN_KEYWORDS + _AI_KEYWORDS

MIN_POSTS_IN_31_DAYS = 2

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_MY_PUB_NAME = "AI Japan Culture"
_MY_PUB_URL_DEFAULT = "https://aijapanculture.substack.com"


class OutreachResearcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = _UA
        self.my_pub_url = os.getenv("SUBSTACK_PUBLICATION_URL", _MY_PUB_URL_DEFAULT).rstrip("/")
        OUTREACH_DIR.mkdir(parents=True, exist_ok=True)

    def run(self) -> Path:
        """Search Substack categories, filter, and save candidates CSV.

        Returns the path to output/outreach/candidates.csv.
        """
        # ── Step 1: collect publications from all target categories ──────
        all_pubs: dict[str, dict] = {}  # subdomain → pub data

        for cat_id, cat_name in CATEGORIES:
            logger.info(f"Scanning category: {cat_name} (id={cat_id})")
            for page in range(PAGES_PER_CATEGORY):
                pubs = self._fetch_category_page(cat_id, page)
                if not pubs:
                    break
                new = 0
                for p in pubs:
                    sd = p.get("subdomain", "")
                    if sd and sd not in all_pubs:
                        all_pubs[sd] = p
                        new += 1
                logger.info(f"  page {page}: +{new} new  (total unique: {len(all_pubs)})")
                time.sleep(0.5)
                if len(pubs) < 25:
                    break  # reached last page

        logger.info(f"Total unique publications collected: {len(all_pubs)}")

        # ── Step 2: keyword filter ────────────────────────────────────────
        keyword_matches = [p for p in all_pubs.values() if self._matches_keywords(p)]
        logger.info(f"Keyword-matched publications: {len(keyword_matches)}")

        # ── Step 3: post-frequency filter ────────────────────────────────
        candidates: list[dict] = []
        for pub in keyword_matches:
            sd = pub.get("subdomain", "")
            custom = pub.get("custom_domain") or ""
            pub_url = f"https://{custom}" if custom else f"https://{sd}.substack.com"

            posts = self._fetch_recent_posts(sd, custom)
            recent = self._count_recent_posts(posts, days=31)
            latest = self._latest_post_date(posts)

            if recent >= MIN_POSTS_IN_31_DAYS:
                candidates.append({
                    "name": pub.get("name", sd),
                    "url": pub_url,
                    "description": (pub.get("hero_text") or "")[:200].replace("\n", " "),
                    "latest_post": latest,
                    "posts_last_31_days": recent,
                    "dm_template": self._dm_template(pub.get("name", sd)),
                })
                logger.info(f"  OK  {pub.get('name')} — {recent} posts in last 31 days")
            else:
                logger.info(f"  --  {sd} — only {recent} post(s) in last 31 days, skip")

            time.sleep(0.3)

        candidates.sort(key=lambda x: x["posts_last_31_days"], reverse=True)
        csv_path = self._save_csv(candidates)
        return csv_path

    # ── private helpers ───────────────────────────────────────────────────

    def _fetch_category_page(self, cat_id: int, page: int) -> list[dict]:
        try:
            resp = self.session.get(
                f"https://substack.com/api/v1/category/public/{cat_id}/publications",
                params={"page": page},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("publications", [])
        except Exception as e:
            logger.warning(f"Category fetch failed (cat={cat_id}, page={page}): {e}")
        return []

    def _matches_keywords(self, pub: dict) -> bool:
        text = " ".join([
            pub.get("name") or "",
            pub.get("hero_text") or "",
            pub.get("subdomain") or "",
            pub.get("author_name") or "",
        ]).lower()
        return any(kw in text for kw in _ALL_KEYWORDS)

    def _fetch_recent_posts(self, subdomain: str, custom_domain: str) -> list[dict]:
        base = f"https://{custom_domain}" if custom_domain else f"https://{subdomain}.substack.com"
        try:
            resp = self.session.get(
                f"{base}/api/v1/posts",
                params={"limit": 10},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.debug(f"Posts fetch failed for {subdomain}: {e}")
        return []

    def _count_recent_posts(self, posts: list[dict], days: int = 31) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        count = 0
        for p in posts:
            raw = p.get("post_date") or ""
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt >= cutoff:
                    count += 1
            except ValueError:
                pass
        return count

    def _latest_post_date(self, posts: list[dict]) -> str:
        for p in posts:
            raw = p.get("post_date") or ""
            if raw:
                return raw[:10]
        return ""

    def _dm_template(self, pub_name: str) -> str:
        return (
            f"Hi! I run {_MY_PUB_NAME} ({self.my_pub_url}), "
            f"a newsletter about Japan culture, travel, and AI content automation. "
            f"I've been enjoying {pub_name} and think our audiences would really enjoy each other's work. "
            f"Would you be open to a mutual shoutout or cross-promotion? "
            f"I'd be happy to feature you first — just reply and we can work out the details!"
        )

    def _save_csv(self, candidates: list[dict]) -> Path:
        fieldnames = [
            "name", "url", "description",
            "latest_post", "posts_last_31_days", "dm_template",
        ]
        with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(candidates)
        logger.info(f"Saved {len(candidates)} candidates → {OUTPUT_CSV}")
        return OUTPUT_CSV
