import json
import os
import re
from datetime import datetime
from pathlib import Path
import anthropic

from src.utils import setup_logger, PROJECT_ROOT
from src.script_generator import METADATA_FILE, SCRIPT_FILE

logger = setup_logger("short_script_generator")

SHORTS_DIR = PROJECT_ROOT / "output" / "shorts"
SHORT_SCRIPT_FILE = SHORTS_DIR / "latest_short_script.txt"

SHORT_SCRIPT_PROMPT = """You are an expert short-form video scriptwriter for TikTok, Instagram Reels, and YouTube Shorts.

Below is a full YouTube video script about Japan:

**Topic:** {topic}
**Title:** {title}

**Full script:**
{narration}

Write a punchy 60-second short video script (around 130–150 words) using this structure:

[HOOK] — First 3 seconds
One single sentence that creates instant curiosity, surprise, or shock.
Start with "Did you know", "Nobody tells you", "Here's why", or a bold statement.
No warm-up, no intro. Hook the viewer immediately.

[BODY] — 15–45 seconds
The most interesting single fact or story from the script.
Short sentences. Fast tempo. One idea only — do NOT try to cover everything.
Each sentence should make the viewer want to hear the next one.
Write as if you're talking to a friend, not reading an essay.

[CTA] — Last 10 seconds
End with a surprising twist, a "wait, there's more" tease, OR a relatable reaction.
Close with exactly this line (customise the topic word only):
"Follow for more Japan secrets you won't find in guidebooks."

Output ONLY the three sections using these exact markers, nothing else:

[HOOK]
(hook line here)

[BODY]
(body lines here)

[CTA]
(closing lines here)

CRITICAL LANGUAGE REQUIREMENT:
- Write the entire output in natural English only.
- Do not use Japanese script characters (Hiragana, Katakana, Kanji).
"""


class ShortScriptGenerator:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set in environment variables.")
        # configure timeout for network requests
        timeout = None
        try:
            timeout_val = float(os.getenv("ANTHROPIC_TIMEOUT", "15"))
            timeout = timeout_val
        except ValueError:
            timeout = None
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        SHORTS_DIR.mkdir(parents=True, exist_ok=True)

    def generate_from_latest(self) -> dict:
        """Read latest_script.txt + latest_metadata.json and generate a short script.

        Returns dict with hook, body, cta, full_script, saved_path.
        """
        if not SCRIPT_FILE.exists():
            raise FileNotFoundError(
                f"No script found at {SCRIPT_FILE}\n"
                "Run 'py main.py script' first."
            )
        if not METADATA_FILE.exists():
            raise FileNotFoundError(
                f"No metadata found at {METADATA_FILE}\n"
                "Run 'py main.py script' first."
            )

        with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
            narration = f.read().strip()

        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        topic = metadata.get("topic", "Japan")
        title = metadata.get("title", "Japan Video")

        logger.info(f"Generating short script for: {title}")

        prompt = SHORT_SCRIPT_PROMPT.format(
            topic=topic,
            title=title,
            narration=narration,
        )

        raw = self._request_short_script(prompt)
        parsed = self._parse_output(raw)

        script_blob = "\n".join([
            parsed.get("hook", ""),
            parsed.get("body", ""),
            parsed.get("cta", ""),
        ])

        if self._contains_japanese(script_blob):
            logger.warning("Short script contained Japanese text; retrying with stricter English constraint")
            strict_prompt = prompt + "\n\nRETRY INSTRUCTION: Rewrite in ENGLISH ONLY. No Japanese characters allowed."
            raw = self._request_short_script(strict_prompt)
            parsed = self._parse_output(raw)

            retry_blob = "\n".join([
                parsed.get("hook", ""),
                parsed.get("body", ""),
                parsed.get("cta", ""),
            ])
            if self._contains_japanese(retry_blob):
                raise RuntimeError("Short script generation failed language guard: output still contains Japanese characters")

        saved_path = self._save(title, parsed)
        parsed["saved_path"] = str(saved_path)

        logger.info(f"Short script saved to: {saved_path}")
        return parsed

    def _request_short_script(self, prompt: str) -> str:
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def _contains_japanese(self, text: str) -> bool:
        return bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text or ""))

    def _parse_output(self, raw: str) -> dict:
        result = {"hook": "", "body": "", "cta": ""}
        sections = {"[HOOK]": "hook", "[BODY]": "body", "[CTA]": "cta"}

        current_key = None
        current_lines: list[str] = []

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

        if all(result[k] for k in ("hook", "body", "cta")):
            result["full_script"] = "\n\n".join([
                f"[HOOK]\n{result['hook']}",
                f"[BODY]\n{result['body']}",
                f"[CTA]\n{result['cta']}",
            ])
        else:
            result["full_script"] = raw.strip()

        return result

    def _save(self, title: str, parsed: dict) -> Path:
        content = (
            f"[HOOK]\n{parsed['hook']}\n\n"
            f"[BODY]\n{parsed['body']}\n\n"
            f"[CTA]\n{parsed['cta']}\n"
        )

        # Save as latest (always overwritten)
        with open(SHORT_SCRIPT_FILE, "w", encoding="utf-8") as f:
            f.write(content)

        # Save timestamped archive copy
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:50].strip()
        archive = SHORTS_DIR / f"{timestamp}_{safe_title}.txt"
        with open(archive, "w", encoding="utf-8") as f:
            f.write(content)

        return SHORT_SCRIPT_FILE
