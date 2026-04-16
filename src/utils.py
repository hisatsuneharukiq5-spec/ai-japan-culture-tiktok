import logging
import os
import yaml
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path(__file__).parent.parent


def get_config() -> dict:
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_topics() -> dict:
    topics_path = PROJECT_ROOT / "config" / "topics.yaml"
    with open(topics_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_all_topics() -> list[str]:
    topics_data = get_topics()
    all_topics = []
    for category_topics in topics_data["topics"].values():
        all_topics.extend(category_topics)
    return all_topics


def setup_logger(name: str) -> logging.Logger:
    config = get_config()
    logs_dir = PROJECT_ROOT / config["output"]["logs_dir"]
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_file = logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


def save_script(topic: str, content: str) -> Path:
    config = get_config()
    scripts_dir = PROJECT_ROOT / config["output"]["scripts_dir"]
    scripts_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic)
    safe_topic = safe_topic[:50].strip()
    filename = f"{timestamp}_{safe_topic}.txt"

    file_path = scripts_dir / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"TOPIC: {topic}\n")
        f.write(f"GENERATED: {datetime.now().isoformat()}\n")
        f.write("=" * 60 + "\n\n")
        f.write(content)

    return file_path


def create_dummy_script(topic: str | None = None) -> dict:
    """Return a minimal placeholder script dictionary for testing or when
    the real model/API is unavailable.

    The returned dict mimics the structure produced by
    ``parse_script_output`` with keys title, description, tags, script, and
    topic. The content is intentionally simple.
    """
    title = topic or "Test Video"
    description = "This is a dummy video description generated because the script service was unavailable."
    tags = []
    script = (
        "Hello! This is a placeholder narration used for testing purposes. "
        "Replace with a real script once AI model access is restored."
    )
    return {
        "title": title,
        "description": description,
        "tags": tags,
        "script": script,
        "topic": topic or "Test",
    }


def parse_script_output(raw_output: str) -> dict:
    """Parse the structured script output into a dictionary."""
    result = {
        "title": "",
        "description": "",
        "tags": [],
        "thumbnail_concept": "",
        "script": "",
        "raw": raw_output,
    }

    sections = {
        "[TITLE]:": "title",
        "[DESCRIPTION]:": "description",
        "[TAGS]:": "tags",
        "[THUMBNAIL_CONCEPT]:": "thumbnail_concept",
        "[SCRIPT]:": "script",
    }

    lines = raw_output.split("\n")
    current_section = None
    current_content = []

    for line in lines:
        matched = False
        for marker, key in sections.items():
            if line.strip().startswith(marker):
                if current_section:
                    result[current_section] = "\n".join(current_content).strip()
                current_section = key
                remainder = line.strip()[len(marker):].strip()
                current_content = [remainder] if remainder else []
                matched = True
                break
        if not matched and current_section:
            current_content.append(line)

    if current_section:
        result[current_section] = "\n".join(current_content).strip()

    if isinstance(result["tags"], str):
        result["tags"] = [t.strip() for t in result["tags"].split(",") if t.strip()]

    return result
