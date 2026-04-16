import os
import json
from datetime import datetime
from pathlib import Path
import anthropic

from src.utils import setup_logger, PROJECT_ROOT
from src.script_generator import METADATA_FILE, SCRIPT_FILE

logger = setup_logger("article_generator")

ARTICLES_DIR = PROJECT_ROOT / "output" / "articles"

ARTICLE_PROMPT_TEMPLATE = """You are an expert travel and culture writer. Convert the following YouTube video script about Japan into a well-structured Substack article in English.

**Video Title:** {title}
**Topic:** {topic}
**Original Script (narration):**
{narration}

Write an 800–1200 word article that:
- Has an engaging hook in the introduction
- Reorganizes the narration into clear sections with H2/H3 headings
- Uses bullet points where appropriate
- Includes a conclusion that encourages readers to explore Japan
- Is written in a warm, informative tone for travel/culture enthusiasts

Respond in exactly this format (do not add extra text outside these sections):

[ARTICLE_TITLE]
Your compelling article title here

[SUBTITLE]
A one-sentence subtitle or tagline

[TAGS]
tag1, tag2, tag3, tag4, tag5

[CONTENT]
The full Markdown article content here (use ## for H2, ### for H3)
"""

YOUTUBE_CTA_TEMPLATE = """
---

## Watch It on YouTube

This article is based on our latest video. See it come to life with visuals, narration, and real footage from Japan.

**[Watch on our YouTube channel →]({channel_url})**

Subscribe for weekly videos uncovering Japan's unique culture, hidden history, and everyday wonders.
"""


def _get_youtube_channel_url() -> str:
    """Return the YouTube channel URL from env, falling back to channel ID URL."""
    custom = os.getenv("YOUTUBE_CHANNEL_URL", "").strip()
    if custom:
        return custom
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID", "").strip()
    if channel_id:
        return f"https://www.youtube.com/channel/{channel_id}"
    return "https://www.youtube.com"


class ArticleGenerator:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set in environment variables.")
        timeout = None
        try:
            timeout_val = float(os.getenv("ANTHROPIC_TIMEOUT", "15"))
            timeout = timeout_val
        except ValueError:
            timeout = None
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self.channel_url = _get_youtube_channel_url()
        ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    def generate_from_script(self) -> dict:
        """Read latest_metadata.json + latest_script.txt and generate a Medium article."""
        if not METADATA_FILE.exists():
            raise FileNotFoundError(f"Metadata file not found: {METADATA_FILE}\nRun 'py main.py script' first.")
        if not SCRIPT_FILE.exists():
            raise FileNotFoundError(f"Script file not found: {SCRIPT_FILE}\nRun 'py main.py script' first.")

        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
            narration = f.read().strip()

        return self.generate_from_data(metadata, narration)

    def generate_from_data(self, metadata: dict, narration: str) -> dict:
        """Generate a Medium article from metadata dict and narration text."""
        title = metadata.get("title", "Japan Travel Guide")
        topic = metadata.get("topic", "Japan")

        logger.info(f"Generating Medium article for: {title}")

        prompt = ARTICLE_PROMPT_TEMPLATE.format(
            title=title,
            topic=topic,
            narration=narration,
        )

        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text
        parsed = self._parse_article_output(raw)

        # Append YouTube channel CTA
        parsed["content"] += YOUTUBE_CTA_TEMPLATE.format(channel_url=self.channel_url)

        saved_path = self._save_article(parsed["title"] or title, parsed["content"])
        parsed["saved_path"] = str(saved_path)

        logger.info(f"Article saved to: {saved_path}")
        return parsed

    def _parse_article_output(self, raw: str) -> dict:
        result = {"title": "", "subtitle": "", "tags": [], "content": ""}
        sections = {
            "[ARTICLE_TITLE]": "title",
            "[SUBTITLE]": "subtitle",
            "[TAGS]": "tags",
            "[CONTENT]": "content",
        }

        current_key = None
        current_lines = []

        for line in raw.split("\n"):
            matched = False
            for marker, key in sections.items():
                if line.strip() == marker:
                    if current_key:
                        result[current_key] = "\n".join(current_lines).strip()
                    current_key = key
                    current_lines = []
                    matched = True
                    break
            if not matched and current_key is not None:
                current_lines.append(line)

        if current_key:
            result[current_key] = "\n".join(current_lines).strip()

        if isinstance(result["tags"], str):
            result["tags"] = [t.strip() for t in result["tags"].split(",") if t.strip()]

        return result

    def _save_article(self, title: str, content: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
        safe_title = safe_title[:60].strip()
        filename = f"{timestamp}_{safe_title}.md"
        file_path = ARTICLES_DIR / filename
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return file_path
