import os
from datetime import datetime
from pathlib import Path
import anthropic

from src.utils import setup_logger, PROJECT_ROOT

logger = setup_logger("error_article_generator")

ERROR_LOGS_DIR = PROJECT_ROOT / "output" / "error_logs"
ARTICLES_DIR = PROJECT_ROOT / "output" / "articles"

ERROR_ARTICLE_PROMPT = """You are a technical blogger who writes engaging "how I solved it" articles about software development and API automation.

Below is an error log / resolution notes from a developer building an AI-powered YouTube/Substack automation system:

{error_log}

Write a paid newsletter article in English that:
1. **FREE section** (before paywall): Hooks readers with the problem context, explains WHY this automation matters, teases the solution without revealing it
2. **PAID section** (after paywall): Gives the full technical solution — exact error messages, root causes, step-by-step fixes, working code snippets, and "magic prompts" used with Claude Code

Use engaging, conversational English. Target audience: developers and content creators building automation tools.

Respond in EXACTLY this format (do not add any text outside these sections):

[TITLE]
Your attention-grabbing article title (e.g., "The One Setting That Broke My X API OAuth — And How I Fixed It")

[SUBTITLE]
A one-sentence subtitle that creates curiosity

[TAGS]
tag1, tag2, tag3, tag4, tag5

[FREE_CONTENT]
(400-600 words of Markdown)
- Introduction: What this automation system does and why it's valuable
- The problem: "I hit a frustrating error that stopped everything..."
- Tease: "The fix turned out to be surprisingly simple — but only once you know where to look"
- CTA: "The full solution, working code, and the exact Claude prompts I used are below for paid subscribers"

[PAID_CONTENT]
(600-900 words of Markdown)
- Exact error message and what it means
- Root cause analysis
- Step-by-step fix with code examples
- Correct configuration / settings
- Working code snippet or .env example
- "Magic prompts" used with Claude Code (if applicable)
- Summary: What you learned and what to watch out for
"""


def _find_latest_log() -> Path:
    """Return the most recently modified .txt file in output/error_logs/."""
    ERROR_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    txt_files = sorted(ERROR_LOGS_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not txt_files:
        raise FileNotFoundError(
            f"No .txt files found in {ERROR_LOGS_DIR}\n"
            "Place your error log / resolution notes there as a .txt file first."
        )
    return txt_files[0]


class ErrorArticleGenerator:
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
        ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    def generate(self, log_file: str | None = None) -> dict:
        """Generate a paywalled article from an error log file.

        Args:
            log_file: Path to a .txt file. Uses the latest file in
                      output/error_logs/ if None.

        Returns:
            dict with title, subtitle, tags, free_content, paid_content,
            and saved_path.
        """
        if log_file:
            log_path = Path(log_file)
        else:
            log_path = _find_latest_log()

        if not log_path.exists():
            raise FileNotFoundError(f"Log file not found: {log_path}")

        logger.info(f"Reading error log: {log_path}")
        with open(log_path, "r", encoding="utf-8") as f:
            error_log = f.read().strip()

        if not error_log:
            raise ValueError(f"Error log file is empty: {log_path}")

        prompt = ERROR_ARTICLE_PROMPT.format(error_log=error_log)
        logger.info("Generating paywalled article via Claude API...")
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        parsed = self._parse_output(raw)

        saved_path = self._save_article(
            parsed["title"], parsed["free_content"], parsed["paid_content"]
        )
        parsed["saved_path"] = str(saved_path)

        logger.info(f"Article saved to: {saved_path}")
        return parsed

    def _parse_output(self, raw: str) -> dict:
        result = {
            "title": "",
            "subtitle": "",
            "tags": [],
            "free_content": "",
            "paid_content": "",
        }
        sections = {
            "[TITLE]": "title",
            "[SUBTITLE]": "subtitle",
            "[TAGS]": "tags",
            "[FREE_CONTENT]": "free_content",
            "[PAID_CONTENT]": "paid_content",
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

    def _save_article(self, title: str, free_content: str, paid_content: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
        safe_title = safe_title[:60].strip()
        filename = f"{timestamp}_{safe_title}_paywalled.md"
        file_path = ARTICLES_DIR / filename
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("# FREE SECTION (Before Paywall)\n\n")
            f.write(free_content)
            f.write("\n\n---\n# PAID SECTION (After Paywall)\n\n")
            f.write(paid_content)
        return file_path
