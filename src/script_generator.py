import os
import json
import random
import re
from pathlib import Path
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils import (
    get_config,
    get_all_topics,
    setup_logger,
    save_script,
    parse_script_output,
    PROJECT_ROOT,
)

METADATA_FILE = PROJECT_ROOT / "output" / "scripts" / "latest_metadata.json"
SCRIPT_FILE  = PROJECT_ROOT / "output" / "scripts" / "latest_script.txt"
TOPIC_HISTORY_FILE = PROJECT_ROOT / "output" / "scripts" / "used_topics.json"

logger = setup_logger("script_generator")

NARRATION_SECTION_LABELS = [
    "hook",
    "intro",
    "introduction",
    "main content",
    "summary",
    "outro",
    "cta",
    "chapter",
    "section",
    "part",
]


class ScriptGenerator:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set in environment variables.")
        # For full script generation we intentionally do not enforce a network
        # timeout (the script step is allowed to take as long as necessary).
        # Pass `timeout=None` to the Anthropic client so the call may run until
        # completion.
        self.client = anthropic.Anthropic(api_key=api_key, timeout=None)
        self.config = get_config()
        self.script_config = self.config["script"]
        self._load_template()

    def _load_template(self):
        template_path = PROJECT_ROOT / "templates" / "script_template.txt"
        with open(template_path, "r", encoding="utf-8") as f:
            self.template = f.read()

    def _build_prompt(self, topic: str) -> str:
        duration = self.script_config["target_duration_minutes"]
        # Target ~10 minutes of natural narration pacing
        min_words = 1100
        max_words = 1500
        return self.template.format(
            topic=topic,
            duration=duration,
            min_words=min_words,
            max_words=max_words,
            style=self.script_config["style"],
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=30),
    )
    def generate(self, topic: str) -> dict:
        """Generate a full script for the given topic. Returns a parsed dict."""
        logger.info(f"Generating script for topic: {topic}")
        prompt = self._build_prompt(topic)

        # For the script command we do not enforce a wrapping timeout — allow
        # the LLM call to complete naturally so long-form scripts can finish.
        message = self.client.messages.create(
            model=self.script_config["model"],
            max_tokens=self.script_config["max_tokens"],
            messages=[{"role": "user", "content": prompt}],
        )

        raw_output = message.content[0].text
        parsed = parse_script_output(raw_output)
        parsed["script"] = self._clean_narration_text(parsed.get("script", ""))
        parsed["topic"] = topic

        script_path = save_script(topic, raw_output)
        parsed["saved_path"] = str(script_path)
        logger.info(f"Script saved to: {script_path}")

        # Save metadata for use by the upload command
        metadata = {
            "title": parsed.get("title", ""),
            "description": parsed.get("description", ""),
            "tags": parsed.get("tags", []),
            "topic": topic,
            "saved_path": str(script_path),
        }
        # write metadata atomically to avoid corrupting the file if the process is killed mid‑write
        METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = METADATA_FILE.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, METADATA_FILE)
        logger.info(f"Metadata saved to: {METADATA_FILE}")

        # Save narration-only script for use by the video/audio pipeline (no markers or metadata)
        narration = parsed.get("script", "").strip()
        with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
            f.write(narration)
        logger.info(f"Narration script saved to: {SCRIPT_FILE}")

        return parsed

    def generate_random(self) -> dict:
        """Pick a random topic, preferring unseen topics until pool is exhausted."""
        topics = get_all_topics()
        used_topics = self._load_used_topics()

        available_topics = [t for t in topics if t not in used_topics]
        if not available_topics:
            logger.info("All topics have been used. Resetting topic history.")
            used_topics = []
            available_topics = topics[:]

        topic = random.choice(available_topics)
        logger.info(f"Randomly selected topic: {topic}")
        used_topics.append(topic)
        self._save_used_topics(used_topics)
        return self.generate(topic)

    def _load_used_topics(self) -> list[str]:
        if not TOPIC_HISTORY_FILE.exists():
            return []
        try:
            with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [str(x) for x in data]
            return []
        except Exception:
            return []

    def _save_used_topics(self, used_topics: list[str]) -> None:
        TOPIC_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = TOPIC_HISTORY_FILE.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(used_topics, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, TOPIC_HISTORY_FILE)

    def _clean_narration_text(self, script_text: str) -> str:
        if not script_text:
            return ""

        section_pattern = r"(?:" + "|".join(re.escape(item) for item in NARRATION_SECTION_LABELS) + r")"
        cleaned_lines: list[str] = []

        for raw_line in script_text.replace("\r\n", "\n").split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            line = re.sub(rf"^\s*(?:{section_pattern})(?:\s+\d+)?\s*[:\-–—]\s*", "", line, flags=re.IGNORECASE)

            if re.match(rf"^(?:{section_pattern})(?:\s+\d+)?\s*[:\-–—]?\s*$", line, flags=re.IGNORECASE):
                continue

            if re.match(r"^[A-Z][A-Z\s]{2,30}:\s*$", line):
                continue

            line = re.sub(r"\s+", " ", line).strip()
            if line:
                cleaned_lines.append(line)

        cleaned = "\n".join(cleaned_lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def generate_batch(self, topics: list[str]) -> list[dict]:
        """Generate scripts for multiple topics."""
        results = []
        for topic in topics:
            try:
                result = self.generate(topic)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to generate script for '{topic}': {e}")
                results.append({"topic": topic, "error": str(e)})
        return results
