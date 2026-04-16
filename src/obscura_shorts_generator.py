import asyncio
import hashlib
import json
import logging
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
from mimetypes import guess_type
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from src.thumbnail_generator import create_obscura_thumbnail
from src.utils import PROJECT_ROOT, setup_logger

load_dotenv()

# Import Obscura Shorts config
try:
    import config.config_obscura_shorts as config_shorts
except ImportError:
    config_shorts = None

logger = setup_logger("obscura_shorts")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

OBSCURA_SHORTS_RECENT_TOPIC_AVOID_COUNT = 6
OBSCURA_SHORTS_GENERIC_TOPIC_TOKENS = {
    "case",
    "children",
    "dark",
    "disappearance",
    "files",
    "history",
    "investigation",
    "man",
    "mystery",
    "new",
    "of",
    "shorts",
    "the",
    "tower",
    "vanished",
    "woman",
}

OBSCURA_SHORTS_TOPIC_ALIASES = {
    "The Beaumont Children Disappearance": [
        "beaumont children",
        "three kids vanished australia",
        "three children vanished australia",
        "australia day vanished",
    ],
}

OBSCURA_SHORTS_GROWTH_TAGS = [
    "unsolved mystery",
    "dark history",
    "true story",
    "cold case",
]


def _clean_shorts_text(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", (value or "").strip())


def _optimize_obscura_shorts_title(title: str, topic: str = "") -> tuple[str, str]:
    """Return (optimized_title, pattern_type) for A/B tracking."""
    import random
    base = re.sub(r"\s+", " ", (title or topic or "Obscura Mystery")).strip()
    lowered = base.lower()
    # パターン分類（A/Bテスト追跡用）
    # Pattern A: emotion_word_present — タイトルに感情ワードが含まれる場合そのまま使用
    emotion_words = [
        "secret", "mystery", "unsolved", "vanished", "killed", "left alive", "never",
        "haunted", "cursed", "bizarre", "chilling", "legendary", "lost", "shocking",
        "forbidden", "hidden", "forgotten", "twisted", "sinister", "dark", "terrifying",
        "dead", "death", "missing", "survived", "escaped", "answered", "remains",
    ]
    if any(word in lowered for word in emotion_words):
        return base[:40].strip(), "emotion_word_present"
    # パターンB/C/D/E — 多様なスタイルをラベル付きで管理
    labeled_patterns = [
        # Pattern B: number_hook — 数字や具体的事実で引き込む
        ("{title} — No One Survived", "number_hook"),
        ("{title} — Never Explained", "number_hook"),
        ("{title} — Zero Witnesses", "number_hook"),
        # Pattern C: question — 疑問形で視聴者を引き込む
        ("What Happened to {title}?", "question"),
        ("Who Killed {title}?", "question"),
        ("How Did {title} Disappear?", "question"),
        # Pattern D: dramatic_statement — 劇的な結末を提示
        ("{title} — Chilling Case", "dramatic_statement"),
        ("{title} — Cursed Story", "dramatic_statement"),
        ("{title} — Forgotten Tale", "dramatic_statement"),
        ("{title} — Twisted Fate", "dramatic_statement"),
        # Pattern E: prefix_label — "Unsolved:"等のプレフィックス
        ("Unsolved: {title}", "prefix_label"),
        ("Cold Case: {title}", "prefix_label"),
        ("Classified: {title}", "prefix_label"),
    ]
    chosen_pattern, pattern_type = random.choice(labeled_patterns)
    result = chosen_pattern.format(title=base)
    return result[:40].strip(), pattern_type


def _build_obscura_shorts_description(description: str, topic: str = "", long_form_url: str | None = None) -> str:
    parts: list[str] = []
    base = _clean_shorts_text(description)
    if base:
        parts.append(base)
    if long_form_url:
        parts.append(f"🔍 Full investigation: {long_form_url}")
    else:
        parts.append("Want the full investigation? Comment FULL CASE below.")
    parts.append(getattr(config_shorts, "SUBSCRIBE_CTA", "Subscribe to The Obscura Files for more dark history and unsolved mystery Shorts."))
    hashtag_line = " ".join(config_shorts.REQUIRED_HASHTAGS + config_shorts.OPTIONAL_HASHTAGS[:3])
    parts.append(hashtag_line)
    return _clean_shorts_text("\n\n".join(part for part in parts if part))


def _merge_obscura_shorts_tags(tags: list[str] | None, topic: str = "") -> list[str]:
    merged: list[str] = []
    for tag in (tags or []) + OBSCURA_SHORTS_GROWTH_TAGS + ([topic] if topic else []):
        clean = re.sub(r"\s+", " ", str(tag or "").strip())
        if clean and clean.lower() not in {item.lower() for item in merged}:
            merged.append(clean)
    return merged[:8]


def _build_obscura_shorts_comment(title: str, topic: str = "") -> str:
    case_name = topic or title or "this case"
    return (
        f"Should we post the full documentary on {case_name}? Comment FULL CASE if you want it next. "
        "Subscribe for more unsolved mystery Shorts."
    )[:10000]


def _download_url(url: str, dest: Path, timeout: int = 60):
    """Download a file from URL to destination."""
    r = requests.get(url, stream=True, timeout=timeout)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


def _search_freesound_music(query: str, per_page: int = 5) -> list[str]:
    """Search Freesound for royalty-free music."""
    token = os.getenv("FREESOUND_API_KEY", "").strip()
    if not token:
        return []

    url = "https://freesound.org/apiv2/search/text/"
    params = {
        "query": query,
        "filter": 'duration:[30 TO 120] license:"Creative Commons 0"',
        "fields": "id,name,previews,license",
        "page_size": per_page,
        "token": token,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results: list[str] = []
    for item in data.get("results", []):
        previews = item.get("previews") or {}
        preview_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
        if preview_url:
            results.append(preview_url)
    return results


def _escape_ffmpeg_filter_path(path: Path) -> str:
    """Escape a filesystem path for use inside ffmpeg filter expressions on Windows/Linux."""
    escaped = str(path.resolve()).replace("\\", "/")
    if re.match(r"^[A-Za-z]:", escaped):
        escaped = escaped[0] + r"\:" + escaped[2:]
    return escaped.replace("'", r"\'")


def _normalize_obscura_topic(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").strip().lower()).strip()


def _obscura_short_topic_signature(topic: str) -> set[str]:
    tokens = [
        token
        for token in _normalize_obscura_topic(topic).split()
        if len(token) >= 4 and token not in OBSCURA_SHORTS_GENERIC_TOPIC_TOKENS
    ]
    signatures = set(tokens) or set(_normalize_obscura_topic(topic).split())
    for alias in OBSCURA_SHORTS_TOPIC_ALIASES.get(topic, []):
        alias_tokens = [
            token
            for token in _normalize_obscura_topic(alias).split()
            if len(token) >= 4 and token not in OBSCURA_SHORTS_GENERIC_TOPIC_TOKENS
        ]
        signatures.update(alias_tokens or _normalize_obscura_topic(alias).split())
    return signatures


def _obscura_short_history_matches_topic(topic: str, history_text: str) -> bool:
    normalized_history = _normalize_obscura_topic(history_text)
    normalized_topic = _normalize_obscura_topic(topic)
    if not normalized_history:
        return False
    # 完全一致またはエイリアス一致のみ除外
    if normalized_topic == normalized_history:
        return True
    for alias in OBSCURA_SHORTS_TOPIC_ALIASES.get(topic, []):
        if _normalize_obscura_topic(alias) == normalized_history:
            return True
    return False


def _recent_obscura_shorts_topics(limit: int | None = None) -> list[str]:
    registry_cfg = getattr(config_shorts, "UPLOAD_REGISTRY_FILE", "output/analytics/obscura_shorts_upload_registry.json")
    registry_path = Path(registry_cfg)
    if not registry_path.is_absolute():
        registry_path = PROJECT_ROOT / registry_path
    if not registry_path.exists():
        return []

    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
    except Exception:
        return []

    recent_topics: list[str] = []
    seen: set[str] = set()
    for item in reversed(registry.get("uploads", [])):
        # topic優先、なければtitle
        history_text = str(item.get("topic") or item.get("title") or "").strip()
        if not history_text:
            continue
        for candidate in config_shorts.OBSCURA_SHORTS_TOPICS:
            normalized = _normalize_obscura_topic(candidate)
            if normalized in seen:
                continue
            if _obscura_short_history_matches_topic(candidate, history_text):
                seen.add(normalized)
                recent_topics.append(candidate)
                break
        if limit is not None and len(recent_topics) >= limit:
            break
    return recent_topics


class ObscuraShortsScriptGenerator:
    """Generate YouTube Shorts scripts for Obscura Files."""

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate(self, topic: str) -> dict:
        """Generate a YouTube Shorts script for given topic."""
        prompt = f"""You are writing a YouTube Shorts script for "Obscura Files".

Rules:
- Language: English only
- Word count: {config_shorts.SCRIPT_MIN_WORDS}-{config_shorts.SCRIPT_MAX_WORDS} words (for 45-55 seconds)
- STRICT LIMIT: Do NOT exceed {config_shorts.SCRIPT_MAX_WORDS} words under any circumstances
- Tone: mysterious, dramatic, fast-paced
- Genre: Dark History / Mystery / Unsolved Crimes

Structure:
0-3 seconds: ULTRA-STRONG HOOK
(Example: "A man disappeared in 1987. His house was found perfectly set for dinner. No one ever came home.")

3-45 seconds: RAPID-FIRE CORE FACTS
- Shocking details
- Concrete numbers/dates
- Unexplained elements
- Each sentence is short and punchy

45-55 seconds: CALL TO ACTION
"Follow for more dark history."

Writing Style:
- Short sentences (max 10-12 words)
- Each sentence on a new line
- Fast tempo, no fluff
- Hook viewer immediately
- Build tension continuously

Topic: {topic}

Return strict JSON with these keys only:
title, description, tags, script

Constraints:
- title must be <= 40 chars (excluding hashtags)
- title must create curiosity or shock; avoid simple case-name-only titles
- tags must be a JSON array of 5-8 English tags
- description must be 2-3 short sentences
- script must be the complete narration text with newlines between sentences"""

        message = self.client.messages.create(
            model=config_shorts.SCRIPT_MODEL,
            max_tokens=config_shorts.SCRIPT_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = message.content[0].text.strip()
        
        # Extract JSON from markdown code blocks if present
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()

        script_data = json.loads(raw_text)
        script_data["topic"] = topic

        # Add #Shorts hashtags to title; track pattern type for A/B analysis
        base_title, pattern_type = _optimize_obscura_shorts_title(script_data["title"], topic)
        script_data["title"] = f"{base_title} #Shorts #DarkHistory #Mystery"
        script_data["title_pattern_type"] = pattern_type

        script_data["description"] = _build_obscura_shorts_description(script_data.get("description", ""), topic)
        script_data["tags"] = _merge_obscura_shorts_tags(script_data.get("tags", []), topic)
        
        logger.info(f"Generated Shorts script: {base_title}")
        return script_data

    def generate_random(self) -> dict:
        """Generate a script with a truly unposted topic."""
        recent_topics = {_normalize_obscura_topic(topic) for topic in _recent_obscura_shorts_topics(limit=None)}
        available_topics = [
            topic for topic in config_shorts.OBSCURA_SHORTS_TOPICS
            if _normalize_obscura_topic(topic) not in recent_topics
        ]
        if not available_topics:
            logger.warning("All topics have been posted. Reusing topics.")
            topic_pool = config_shorts.OBSCURA_SHORTS_TOPICS
        else:
            topic_pool = available_topics
        topic = random.choice(topic_pool)
        if recent_topics:
            logger.info("Avoiding previously used Obscura Shorts topics: %s", ", ".join(sorted(recent_topics)))
        logger.info(f"Selected random Shorts topic: {topic}")
        return self.generate(topic)


class ObscuraShortsVideoGenerator:
    """Generate vertical video (1080x1920) for YouTube Shorts."""

    def __init__(self):
        self.pexels_key = os.getenv("PEXELS_API_KEY", "").strip()
        self.pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()

    def _build_clip_queries(self, keywords: list[str]) -> list[str]:
        """Build diversified search queries from extracted keywords."""
        base = []
        for kw in keywords:
            clean_kw = kw.strip().lower()
            if clean_kw and clean_kw not in base:
                base.append(clean_kw)

        query_pool: list[str] = []
        for kw in base:
            query_pool.append(kw)
            query_pool.append(f"{kw} moody")
            query_pool.append(f"{kw} night")

        # Remove duplicates while preserving order
        deduped = list(dict.fromkeys(query_pool))
        return deduped[:18]

    def _search_portrait_clips(self, keywords: list[str], per_keyword: int = 3) -> list[str]:
        """Search for portrait orientation video clips."""
        clip_urls = []
        queries = self._build_clip_queries(keywords)
        
        logger.info(f"Starting clip search with {len(queries)} keywords...")
        
        for kw in queries:
            # Early exit if we have enough clips
            if len(clip_urls) >= 25:
                logger.info(f"Reached {len(clip_urls)} clips, stopping search")
                break
                
            # Pexels with portrait orientation
            if self.pexels_key:
                try:
                    url = "https://api.pexels.com/videos/search"
                    params = {
                        "query": kw,
                        "orientation": "portrait",
                        "per_page": per_keyword,
                        "page": random.randint(1, 5),
                    }
                    headers = {"Authorization": self.pexels_key}
                    resp = requests.get(url, params=params, headers=headers, timeout=10)
                    resp.raise_for_status()
                    data = resp.json()
                    
                    clips_before = len(clip_urls)
                    for video in data.get("videos", []):
                        files = video.get("video_files", [])
                        # Prefer vertical HD files
                        for vf in files:
                            if vf.get("height", 0) > vf.get("width", 0):
                                clip_urls.append(vf["link"])
                                break
                    logger.info(f"  Pexels '{kw}': +{len(clip_urls) - clips_before} clips")
                except TimeoutError:
                    logger.warning(f"Pexels search timeout for '{kw}' - skipping")
                    continue
                except Exception as e:
                    logger.warning(f"Pexels search failed for '{kw}': {e}")
            
            # Pixabay (no orientation filter, will crop later)
            if self.pixabay_key and len(clip_urls) < 20:
                try:
                    url = "https://pixabay.com/api/videos/"
                    params = {
                        "key": self.pixabay_key,
                        "q": kw,
                        "per_page": per_keyword,
                        "page": random.randint(1, 5),
                    }
                    resp = requests.get(url, params=params, timeout=10)
                    resp.raise_for_status()
                    data = resp.json()
                    
                    clips_before = len(clip_urls)
                    for hit in data.get("hits", []):
                        videos = hit.get("videos", {})
                        # Get medium or large quality
                        for quality in ["medium", "large", "small"]:
                            if quality in videos:
                                clip_urls.append(videos[quality]["url"])
                                break
                    logger.info(f"  Pixabay '{kw}': +{len(clip_urls) - clips_before} clips")
                except TimeoutError:
                    logger.warning(f"Pixabay search timeout for '{kw}' - skipping")
                    continue
                except Exception as e:
                    logger.warning(f"Pixabay search failed for '{kw}': {e}")
        
        return list(dict.fromkeys(clip_urls))  # Remove duplicates

    def _extract_keywords_from_script(self, script: str, topic: str | None = None, title: str | None = None) -> list[str]:
        """Extract visual keywords from script - prioritize content-specific keywords."""
        # Exclude common English stopwords/articles
        stopwords = {"the", "a", "an", "and", "or", "is", "are", "was", "were", "of", "in", "on", "at", "to", "for", "with", "from", "by", "be", "it", "as"}
        
        # Extract capitalized words (likely names/places) - these are topic-specific
        words = script.split()
        capitalized = [w.strip(",.!?;:\"") for w in words if w and len(w) > 3 and w[0].isupper()]

        topic_words: list[str] = []
        context_text = " ".join(x for x in [topic or "", title or ""] if x).strip()
        if context_text:
            cleaned_context = re.sub(r"#\w+", " ", context_text)
            tokens = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", cleaned_context)  # Only 4+ chars
            topic_words = [t.lower() for t in tokens if t.lower() not in stopwords]
        
        # Extract common nouns and meaningful words from script
        script_lower = script.lower()
        meaningful_words = []
        
        # Look for specific relevant words in the script
        relevant_patterns = [
            "disappear", "vanish", "mystery", "murder", "death", "grave", "cemetery",
            "forest", "abandoned", "house", "cabin", "mountain", "island", "cave",
            "dark", "night", "shadow", "fog", "storm", "police", "search", "missing",
            "body", "skull", "bones", "blood", "strange", "bizarre", "unusual",
            "woman", "man", "child", "ancient", "historical", "remains", "disappearance",
            "lost", "trapped", "escape", "discovery", "killed", "murder", "crime"
        ]
        
        for pattern in relevant_patterns:
            if pattern in script_lower:
                meaningful_words.append(pattern)
        
        # Combine: meaningful patterns first, then topic/title words, then capitalized
        all_keywords = meaningful_words + topic_words + capitalized
        extracted = list(dict.fromkeys(all_keywords))  # Remove duplicates, preserve order
        
        # Filter out any remaining stopwords or very short keywords
        extracted = [k for k in extracted if k.lower() not in stopwords and len(k) > 2]
        
        # If we got good keywords, use them; otherwise fallback to patterns
        if len(extracted) >= 5:
            return extracted[:10]
        else:
            # Fallback to specific patterns combined with what we found
            base_keywords = ["dark", "mystery", "abandoned", "historical", "eerie", "mystery"]
            return extracted + base_keywords[:max(0, 10 - len(extracted))]

    def _crop_to_portrait(self, input_path: Path, output_path: Path, duration: float):
        """Convert any source clip to portrait 1080x1920 using safe scale+crop."""
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-t", str(duration),
            "-vf", (
                f"scale={config_shorts.VIDEO_WIDTH}:{config_shorts.VIDEO_HEIGHT}:"
                f"force_original_aspect_ratio=increase,"
                f"crop={config_shorts.VIDEO_WIDTH}:{config_shorts.VIDEO_HEIGHT}"
            ),
            "-r", str(config_shorts.VIDEO_FPS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-an",  # Remove audio
            str(output_path)
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def _synthesize_audio(self, text: str, output_path: Path):
        """Synthesize narration with Edge TTS."""
        clean_text = re.sub(r'[#\[\]\(\)]', '', text)
        
        async def synth():
            import edge_tts
            communicate = edge_tts.Communicate(
                clean_text,
                config_shorts.VOICE_NAME,
                rate=config_shorts.VOICE_RATE,
                pitch=config_shorts.VOICE_PITCH
            )
            await communicate.save(str(output_path))
        
        asyncio.run(synth())
        logger.info(f"Synthesized Shorts narration: {output_path}")

    def _transcribe_with_whisper(self, audio_path: Path, output_srt: Path):
        """Transcribe audio to SRT with Whisper."""
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(str(audio_path), language="en", word_timestamps=True)

        # Generate SRT with max 4 words per line
        srt_lines = []
        idx = 1

        for segment in result["segments"]:
            words = segment["text"].strip().split()
            start_time = segment["start"]
            end_time = segment["end"]

            # Split into chunks of max 4 words
            for i in range(0, len(words), config_shorts.SUBTITLE_MAX_WORDS_PER_LINE):
                chunk = words[i:i + config_shorts.SUBTITLE_MAX_WORDS_PER_LINE]
                chunk_text = " ".join(chunk)

                # Estimate timing
                chunk_start = start_time + (i / len(words)) * (end_time - start_time)
                chunk_end = start_time + ((i + len(chunk)) / len(words)) * (end_time - start_time)

                srt_lines.append(f"{idx}\n")
                srt_lines.append(f"{self._format_srt_time(chunk_start)} --> {self._format_srt_time(chunk_end)}\n")
                srt_lines.append(f"{chunk_text}\n\n")
                idx += 1
        
        with open(output_srt, "w", encoding="utf-8") as f:
            f.writelines(srt_lines)
        
        logger.info(f"Generated SRT subtitles: {output_srt}")

    def _format_srt_time(self, seconds: float) -> str:
        """Format seconds to SRT time format."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def _build_styled_ass_from_srt(self, srt_path: Path, ass_path: Path):
        """Convert SRT to ASS with styled subtitles."""
        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()

        emphasis_keywords = getattr(config_shorts, "EMPHASIS_KEYWORDS", set())
        ultra_keywords = getattr(config_shorts, "ULTRA_EMPHASIS_KEYWORDS", set())
        
        # ASS header
        ass_lines = [
            "[Script Info]\n",
            "ScriptType: v4.00+\n",
            f"PlayResX: {config_shorts.VIDEO_WIDTH}\n",
            f"PlayResY: {config_shorts.VIDEO_HEIGHT}\n",
            "\n",
            "[V4+ Styles]\n",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n",
            f"Style: Normal,Arial,{config_shorts.SUBTITLE_FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,0,5,16,16,0,1\n",
            f"Style: Shock,Arial,{config_shorts.SUBTITLE_SHOCK_FONT_SIZE},&H0000FFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,0,5,16,16,0,1\n",
            f"Style: Ultra,Arial,{config_shorts.SUBTITLE_ULTRA_FONT_SIZE},&H000000FF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,0,5,16,16,0,1\n",
            "\n",
            "[Events]\n",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n",
        ]
        
        # Parse SRT and convert to ASS
        blocks = srt_content.strip().split("\n\n")
        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue
            
            timing = lines[1]
            text = " ".join(lines[2:])
            
            # Convert SRT timing to ASS timing
            start, end = timing.split(" --> ")
            start_ass = self._srt_to_ass_time(start)
            end_ass = self._srt_to_ass_time(end)
            
            # Select subtitle style by keyword priority: Ultra > Shock > Normal
            lower_text = text.lower()
            has_ultra = any(kw in lower_text for kw in ultra_keywords)
            has_shock = any(kw in lower_text for kw in emphasis_keywords)
            if has_ultra:
                style = "Ultra"
            elif has_shock:
                style = "Shock"
            else:
                style = "Normal"
            
            # Add effects: default fade + ultra 0.1s zoom-in
            if style == "Ultra":
                text_with_fade = "{\\fad(120,0)\\fscx100\\fscy100\\t(0,100,\\fscx112\\fscy112)}" + text
            else:
                text_with_fade = "{\\fad(220,0)}" + text
            
            ass_lines.append(f"Dialogue: 0,{start_ass},{end_ass},{style},,0,0,0,,{text_with_fade}\n")
        
        with open(ass_path, "w", encoding="utf-8") as f:
            f.writelines(ass_lines)
        
        logger.info(f"Generated ASS subtitles: {ass_path}")

    def _srt_to_ass_time(self, srt_time: str) -> str:
        """Convert SRT time to ASS time format."""
        # SRT: 00:00:01,500 -> ASS: 0:00:01.50
        srt_time = srt_time.strip().replace(",", ".")
        parts = srt_time.split(":")
        h, m, s = parts[0], parts[1], parts[2]
        # Remove leading zeros from hour
        h = str(int(h))
        return f"{h}:{m}:{s[:-1]}"  # Remove last digit of centiseconds

    def generate(self, script_data: dict) -> Path:
        """Generate a complete Shorts video."""
        script = script_data["script"]
        title = script_data["title"]
        
        with tempfile.TemporaryDirectory(prefix="obscura_shorts_") as tmpdir:
            tmpdir = Path(tmpdir)
            logger.info(f"Obscura Shorts working directory: {tmpdir}")
            
            # 1. Synthesize narration
            narration_path = tmpdir / "narration.mp3"
            self._synthesize_audio(script, narration_path)
            
            # Get narration duration
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(narration_path)]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            narration_duration = float(result.stdout.strip())
            
            # Check duration constraint
            if narration_duration > config_shorts.ABSOLUTE_MAX_DURATION:
                logger.error(f"Narration duration {narration_duration:.1f}s exceeds 60s limit!")
                raise ValueError(f"Shorts duration must not exceed {config_shorts.ABSOLUTE_MAX_DURATION}s")
            
            if narration_duration < config_shorts.TARGET_MIN_DURATION:
                logger.warning(f"Narration duration {narration_duration:.1f}s is shorter than target {config_shorts.TARGET_MIN_DURATION}s")
            
            logger.info(f"Narration duration: {narration_duration:.1f}s")
            
            # 2. Download BGM
            bgm_path = tmpdir / "bgm.mp3"
            try:
                bgm_candidates = _search_freesound_music("dark ambient", per_page=5)
                if bgm_candidates:
                    _download_url(bgm_candidates[0], bgm_path)
                    logger.info(f"Downloaded BGM: {bgm_candidates[0]}")
                else:
                    bgm_path = None
                    logger.warning("No BGM found, continuing without background music")
            except Exception as e:
                logger.warning(f"BGM download failed: {e}")
                bgm_path = None
            
            # 3. Mix narration with BGM
            audio_final_path = tmpdir / "audio_final.mp3"
            if bgm_path and bgm_path.exists():
                fade_start = max(0.0, narration_duration - config_shorts.BGM_FADE_DURATION)
                filter_complex = (
                    f"[0:a]volume=1.0[narr];"
                    f"[1:a]volume={config_shorts.BGM_VOLUME_RATIO},"
                    f"afade=t=in:st=0:d={config_shorts.BGM_FADE_DURATION},"
                    f"afade=t=out:st={fade_start:.2f}:d={config_shorts.BGM_FADE_DURATION},"
                    f"atrim=0:{narration_duration:.2f}[bgm];"
                    f"[narr][bgm]amix=inputs=2:duration=first:dropout_transition=0[outa]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(narration_path),
                    "-i", str(bgm_path),
                    "-filter_complex", filter_complex,
                    "-map", "[outa]",
                    "-ac", "2",
                    str(audio_final_path)
                ]
                subprocess.run(cmd, check=True, capture_output=True)
            else:
                shutil.copy(narration_path, audio_final_path)
            
            # 4. Generate subtitles
            srt_path = tmpdir / "subtitles.srt"
            self._transcribe_with_whisper(narration_path, srt_path)
            
            ass_path = tmpdir / "subtitles.ass"
            self._build_styled_ass_from_srt(srt_path, ass_path)
            
            # 5. Search and download clips
            keywords = self._extract_keywords_from_script(
                script,
                topic=script_data.get("topic"),
                title=script_data.get("title", ""),
            )
            logger.info(f"Searching portrait clips with keywords: {keywords}")
            
            clip_urls = self._search_portrait_clips(keywords, per_keyword=4)
            logger.info(f"Found {len(clip_urls)} clip URLs")
            
            # Randomize clip order to ensure variety
            random.shuffle(clip_urls)
            
            if len(clip_urls) < config_shorts.TARGET_CLIP_COUNT_MIN:
                logger.warning(f"Only {len(clip_urls)} clips found, target is {config_shorts.TARGET_CLIP_COUNT_MIN}")
            
            # Download and process clips
            processed_clips = []
            target_clip_duration = narration_duration / min(len(clip_urls), config_shorts.TARGET_CLIP_COUNT_MAX)
            target_clip_duration = max(config_shorts.CLIP_MIN_DURATION, 
                                      min(target_clip_duration, config_shorts.CLIP_MAX_DURATION))
            
            for idx, url in enumerate(clip_urls[:config_shorts.TARGET_CLIP_COUNT_MAX]):
                raw_path = tmpdir / f"raw_{idx}.mp4"
                clip_path = tmpdir / f"clip_{idx}.mp4"
                
                try:
                    _download_url(url, raw_path, timeout=120)
                    
                    # Check if clip is portrait or needs cropping
                    probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
                                "-show_entries", "stream=width,height",
                                "-of", "json", str(raw_path)]
                    result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
                    probe_data = json.loads(result.stdout)
                    
                    if probe_data["streams"]:
                        width = probe_data["streams"][0].get("width", 0)
                        height = probe_data["streams"][0].get("height", 0)
                        
                        if height > width:
                            # Already portrait, just trim
                            cmd = [
                                "ffmpeg", "-y", "-i", str(raw_path),
                                "-t", str(target_clip_duration),
                                "-vf", f"scale={config_shorts.VIDEO_WIDTH}:{config_shorts.VIDEO_HEIGHT}",
                                "-r", str(config_shorts.VIDEO_FPS),
                                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                                "-an",
                                str(clip_path)
                            ]
                        else:
                            # Landscape/square: robust convert to portrait
                            self._crop_to_portrait(raw_path, clip_path, target_clip_duration)
                        
                        if not clip_path.exists():
                            subprocess.run(cmd, check=True, capture_output=True)
                        
                        processed_clips.append(clip_path)
                        logger.info(f"Processed clip {idx+1}/{len(clip_urls)}")
                except Exception as e:
                    logger.warning(f"Failed to process clip {idx}: {e}")
                    continue
            
            if not processed_clips:
                raise RuntimeError("No video clips were successfully processed")
            
            # 6. Concatenate clips
            concat_list_path = tmpdir / "concat_list.txt"
            with open(concat_list_path, "w") as f:
                for clip in processed_clips:
                    f.write(f"file '{clip.absolute()}'\n")
            
            video_no_subs = tmpdir / "video_no_subs.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_path),
                "-t", str(narration_duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-r", str(config_shorts.VIDEO_FPS),
                "-vf", f"scale={config_shorts.VIDEO_WIDTH}:{config_shorts.VIDEO_HEIGHT}",
                "-an",
                str(video_no_subs)
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            
            # 7. Burn subtitles and add audio
            output_path = PROJECT_ROOT / "output" / "videos" / f"obscura_short_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy ASS file to working directory with simple name to avoid path escaping issues
            temp_ass_file = tmpdir / "subs.ass"
            shutil.copy(ass_path, temp_ass_file)
            
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_no_subs),
                "-i", str(audio_final_path),
                "-vf", f"ass={temp_ass_file.name}",
                "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                str(output_path)
            ]
            subprocess.run(cmd, check=True, cwd=str(tmpdir), capture_output=True)
            
            logger.info(f"Generated Shorts video: {output_path}")
            
            # Verify final duration
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            final_duration = float(result.stdout.strip())
            
            if final_duration > config_shorts.ABSOLUTE_MAX_DURATION:
                logger.error(f"CRITICAL: Final video duration {final_duration:.1f}s exceeds 60s!")
                raise ValueError("Shorts video exceeded 60 second limit")
            
            logger.info(f"Final Shorts duration: {final_duration:.1f}s")
            
            return output_path


class ObscuraShortsUploader:
    """Upload YouTube Shorts to Obscura Files channel."""

    def __init__(self):
        secrets_cfg = os.getenv("YOUTUBE_OBSCURA_CLIENT_SECRETS_FILE", getattr(config_shorts, "YOUTUBE_OBSCURA_CLIENT_SECRETS_FILE", "config/youtube_client_secrets.json"))
        token_cfg = os.getenv("YOUTUBE_OBSCURA_TOKEN_FILE", getattr(config_shorts, "YOUTUBE_OBSCURA_TOKEN_FILE", "config/youtube_token_obscura.json"))
        registry_cfg = getattr(config_shorts, "UPLOAD_REGISTRY_FILE", "output/analytics/obscura_shorts_upload_registry.json")

        self.credentials_file = self._resolve_project_path(secrets_cfg)
        self.token_file = self._resolve_project_path(token_cfg)
        self.upload_registry_file = self._resolve_project_path(registry_cfg)

    @staticmethod
    def _resolve_project_path(path_value: str) -> Path:
        path = Path(path_value)
        return path if path.is_absolute() else PROJECT_ROOT / path

    def _load_registry(self) -> dict[str, Any]:
        if not self.upload_registry_file.exists():
            return {"uploads": []}
        try:
            with open(self.upload_registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("uploads"), list):
                return data
        except Exception as e:
            logger.warning(f"Failed to read upload registry, creating a new one: {e}")
        return {"uploads": []}

    def _save_registry(self, registry: dict[str, Any]) -> None:
        self.upload_registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.upload_registry_file, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _compute_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _compute_script_hash(metadata: dict) -> str:
        script = metadata.get("script", "")
        if not script:
            return ""
        return hashlib.sha256(script.strip().encode("utf-8")).hexdigest()

    def _validate_obscura_channel(self, youtube) -> tuple[str, str]:
        response = youtube.channels().list(part="id,snippet", mine=True).execute()
        items = response.get("items", [])
        if not items:
            raise RuntimeError("Could not determine authenticated YouTube channel")

        channel_id = items[0].get("id", "")
        channel_title = items[0].get("snippet", {}).get("title", "")

        allowed_titles = set(getattr(config_shorts, "YOUTUBE_ALLOWED_CHANNEL_TITLES", []))
        allowed_ids = set(getattr(config_shorts, "YOUTUBE_ALLOWED_CHANNEL_IDS", []))

        env_title = os.getenv("OBSCURA_YOUTUBE_CHANNEL_TITLE", "").strip()
        env_id = os.getenv("OBSCURA_YOUTUBE_CHANNEL_ID", "").strip()
        if env_title:
            allowed_titles.add(env_title)
        if env_id:
            allowed_ids.add(env_id)

        title_ok = (not allowed_titles) or (channel_title in allowed_titles)
        id_ok = (not allowed_ids) or (channel_id in allowed_ids)

        if not (title_ok and id_ok):
            raise RuntimeError(
                "Authenticated channel does not match Obscura destination. "
                f"Current: {channel_title} ({channel_id}). "
                f"Token file: {self.token_file}. "
                "Use Obscura account OAuth token for uploads."
            )

        logger.info(f"Authenticated Obscura channel: {channel_title} ({channel_id})")
        return channel_id, channel_title

    def _find_duplicate_upload(
        self,
        registry: dict[str, Any],
        channel_id: str,
        file_hash: str,
        script_hash: str,
        metadata: dict,
    ) -> dict[str, Any] | None:
        normalized_title = str(metadata.get("title") or "").strip().lower()
        topic = str(metadata.get("topic") or "").strip()
        for item in reversed(registry.get("uploads", [])):
            if item.get("channel_id") != channel_id:
                continue
            if item.get("status") != "uploaded":
                continue
            if file_hash and item.get("file_sha256") == file_hash:
                return item
            if script_hash and item.get("script_sha256") == script_hash:
                return item
            existing_title = str(item.get("title") or "").strip().lower()
            if normalized_title and existing_title == normalized_title:
                return item
            history_text = str(item.get("topic") or item.get("title") or "")
            if topic and history_text and _obscura_short_history_matches_topic(topic, history_text):
                return item
        return None

    def _record_upload(
        self,
        registry: dict[str, Any],
        *,
        channel_id: str,
        channel_title: str,
        metadata: dict,
        video_path: Path,
        file_hash: str,
        script_hash: str,
        video_id: str,
    ) -> None:
        video_url = f"https://www.youtube.com/shorts/{video_id}"
        registry.setdefault("uploads", []).append(
            {
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "channel_id": channel_id,
                "channel_title": channel_title,
                "video_id": video_id,
                "video_url": video_url,
                "title": metadata.get("title", ""),
                "topic": metadata.get("topic", ""),
                "title_pattern_type": metadata.get("title_pattern_type", "unknown"),
                "video_path": str(video_path),
                "thumbnail_path": metadata.get("thumbnail_path", ""),
                "file_sha256": file_hash,
                "script_sha256": script_hash,
                "status": "uploaded",
            }
        )
        self._save_registry(registry)

    @staticmethod
    def _thumbnail_filename(video_id: str, title: str) -> str:
        safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_")[:60] or "obscura"
        return f"obscura_{video_id}_{safe_title}.jpg"

    @staticmethod
    def _set_thumbnail(youtube, video_id: str, thumbnail_path: Path) -> None:
        mime_type = guess_type(str(thumbnail_path))[0] or "image/jpeg"
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path), mimetype=mime_type),
        ).execute()

    def _authenticate(self):
        """Authenticate with YouTube API."""
        creds = None
        
        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
            except Exception as exc:
                logger.warning(f"Failed to load Obscura token file, reauth required: {exc}")
                creds = None
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as exc:
                    logger.warning(f"Obscura token refresh failed, starting fresh OAuth flow: {exc}")
                    creds = None

            if not creds or not creds.valid:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(f"YouTube client secrets not found: {self.credentials_file}")
                
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_file), SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(self.token_file, "w") as token:
                token.write(creds.to_json())
        
        return build("youtube", "v3", credentials=creds)

    def upload(self, video_path: Path, metadata: dict) -> str:
        """Upload Shorts video to YouTube."""
        youtube = self._authenticate()
        channel_id, channel_title = self._validate_obscura_channel(youtube)

        registry = self._load_registry()
        file_hash = self._compute_sha256(video_path)
        script_hash = self._compute_script_hash(metadata)
        duplicate = self._find_duplicate_upload(registry, channel_id, file_hash, script_hash, metadata)
        if duplicate:
            duplicate_id = duplicate.get("video_id", "")
            logger.warning(
                "Duplicate Shorts detected. Skipping upload. "
                f"Existing: https://www.youtube.com/shorts/{duplicate_id}"
            )
            return duplicate_id
        
        title = metadata["title"][:100]  # YouTube limit
        description = metadata.get("description", "")
        tags = metadata.get("tags", [])
        
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": config_shorts.UPLOAD_CATEGORY_ID,
            },
            "status": {
                "privacyStatus": config_shorts.UPLOAD_PRIVACY,
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": True,
                "selfDeclaredAsModifiedContent": True,
            }
        }

        status = body.setdefault("status", {})
        status["containsSyntheticMedia"] = True
        status["selfDeclaredAsModifiedContent"] = True
        
        media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
        
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Upload progress: {int(status.progress() * 100)}%")
        
        video_id = response["id"]
        video_url = f"https://www.youtube.com/shorts/{video_id}"

        try:
            youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": _build_obscura_shorts_comment(title, str(metadata.get("topic", "")))
                            }
                        },
                    }
                },
            ).execute()
            logger.info(f"Posted initial engagement comment for Obscura short: {video_id}")
        except Exception as exc:
            exc_str = str(exc).lower()
            if "forbidden" in exc_str or "403" in exc_str:
                logger.info(
                    "Comment posting skipped for short %s: YouTube API requires project audit approval "
                    "for commentThreads.insert. To enable this feature, apply at "
                    "https://support.google.com/youtube/contact/yt_api_form — or ensure channel "
                    "comments are enabled in YouTube Studio.",
                    video_id,
                )
            else:
                logger.warning("Could not post engagement comment for short %s: %s", video_id, exc)

        try:
            thumb_filename = self._thumbnail_filename(video_id, title)
            thumbnail_path = create_obscura_thumbnail(
                title=metadata.get("title", title),
                topic=metadata.get("topic", "Obscura Files"),
                output_filename=thumb_filename,
            )
            self._set_thumbnail(youtube, video_id, thumbnail_path)
            metadata["thumbnail_path"] = str(thumbnail_path)
            logger.info(f"Obscura thumbnail uploaded: {thumbnail_path}")
        except Exception as thumb_exc:
            logger.warning(f"Obscura thumbnail generation/upload failed: {thumb_exc}")

        self._record_upload(
            registry,
            channel_id=channel_id,
            channel_title=channel_title,
            metadata=metadata,
            video_path=video_path,
            file_hash=file_hash,
            script_hash=script_hash,
            video_id=video_id,
        )
        
        logger.info(f"✅ Shorts uploaded successfully: {video_url}")
        return video_id


def _is_topic_recently_uploaded(topic: str) -> dict[str, Any] | None:
    """Return the registry entry for a recently uploaded topic, or None if not found."""
    registry_cfg = getattr(
        config_shorts,
        "UPLOAD_REGISTRY_FILE",
        "output/analytics/obscura_shorts_upload_registry.json",
    )
    registry_path = Path(registry_cfg)
    if not registry_path.is_absolute():
        registry_path = PROJECT_ROOT / registry_path
    if not registry_path.exists():
        return None
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    for item in reversed(registry.get("uploads", [])):
        if item.get("status") != "uploaded":
            continue
        history_text = str(item.get("topic") or item.get("title") or "").strip()
        if history_text and _obscura_short_history_matches_topic(topic, history_text):
            return item
    return None


def _find_longform_video_id(topic: str) -> str | None:
    """Check obscura_upload_registry.jsonl for an uploaded long-form video matching the topic."""
    longform_registry = PROJECT_ROOT / "output" / "analytics" / "obscura_upload_registry.jsonl"
    if not longform_registry.exists():
        return None
    try:
        lines = longform_registry.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    normalized = _normalize_obscura_topic(topic)
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        item_topic = str(item.get("topic") or item.get("title") or "").strip()
        if item_topic and _normalize_obscura_topic(item_topic) == normalized:
            return item.get("video_id")
    return None


def _update_shorts_description(youtube, video_id: str, new_description: str, title: str, tags: list[str], category_id: str) -> None:
    """Update an existing Short's description via YouTube API."""
    youtube.videos().update(
        part="snippet",
        body={
            "id": video_id,
            "snippet": {
                "title": title,
                "description": new_description,
                "tags": tags,
                "categoryId": category_id,
            },
        },
    ).execute()


def _try_update_shorts_description_with_longform(
    existing_video_id: str,
    existing: dict,
    long_form_video_id: str,
    topic: str,
) -> None:
    """Update an existing Short's description to include the long-form link, if not already present."""
    long_form_url = f"https://www.youtube.com/watch?v={long_form_video_id}"
    current_desc = existing.get("description", "") or ""
    if long_form_url in current_desc:
        logger.info("Short %s already links to long-form. No update needed.", existing_video_id)
        return
    try:
        uploader = ObscuraShortsUploader()
        youtube = uploader._authenticate()
        # Fetch current snippet to avoid overwriting tags/categoryId
        resp = youtube.videos().list(part="snippet", id=existing_video_id).execute()
        items = resp.get("items", [])
        if not items:
            logger.warning("Could not fetch snippet for short %s", existing_video_id)
            return
        snippet = items[0]["snippet"]
        old_desc = snippet.get("description", "")
        if long_form_url in old_desc:
            return
        new_desc = _build_obscura_shorts_description(old_desc, topic, long_form_url=long_form_url)
        youtube.videos().update(
            part="snippet",
            body={
                "id": existing_video_id,
                "snippet": {
                    "title": snippet.get("title", ""),
                    "description": new_desc,
                    "tags": snippet.get("tags", []),
                    "categoryId": snippet.get("categoryId", "22"),
                },
            },
        ).execute()
        logger.info("Updated Short %s description with long-form link: %s", existing_video_id, long_form_url)
    except Exception as exc:
        logger.warning("Failed to update Short %s description: %s", existing_video_id, exc)


def run_obscura_shorts_pipeline(topic: str | None = None, long_form_video_id: str | None = None) -> dict:
    """Run the complete Obscura Shorts pipeline.

    Args:
        topic: Topic to generate. If None, a random unposted topic is chosen.
        long_form_video_id: If provided, the Short's description will link to this long-form video.
            If None, the long-form registry is checked automatically, and if no match is found,
            the long-form pipeline is triggered for the same topic.
    """
    logger.info("🎬 Starting Obscura Shorts Pipeline")

    generator = ObscuraShortsScriptGenerator()
    video_gen = ObscuraShortsVideoGenerator()

    # Step 1: Generate script / select topic.
    script_data = generator.generate(topic) if topic else generator.generate_random()
    chosen_topic: str = script_data.get("topic", "") or (topic or "")

    # Step 2: Early duplicate check — before spending time on video generation.
    if chosen_topic:
        existing = _is_topic_recently_uploaded(chosen_topic)
        if existing:
            existing_video_id = existing.get("video_id", "")
            existing_url = (
                existing.get("video_url")
                or f"https://www.youtube.com/shorts/{existing_video_id}"
            )
            logger.warning(
                "Topic '%s' was already uploaded. Skipping video generation. Existing: %s",
                chosen_topic,
                existing_url,
            )
            # Even if duplicate, try to update description with long-form link if not already set.
            if existing_video_id and long_form_video_id:
                _try_update_shorts_description_with_longform(
                    existing_video_id=existing_video_id,
                    existing=existing,
                    long_form_video_id=long_form_video_id,
                    topic=chosen_topic,
                )
            return {
                "video_id": existing_video_id,
                "video_url": existing_url,
                "title": existing.get("title", ""),
                "video_path": existing.get("video_path", ""),
            }

    # Step 2b: Resolve long-form video URL for linking in Short description.
    # Priority: caller-supplied ID > registry lookup > auto-generate long-form.
    resolved_longform_id = long_form_video_id
    if not resolved_longform_id and chosen_topic:
        resolved_longform_id = _find_longform_video_id(chosen_topic)
        if resolved_longform_id:
            logger.info("Found existing long-form for topic '%s': %s", chosen_topic, resolved_longform_id)

    if not resolved_longform_id and chosen_topic:
        logger.info("No long-form found for '%s'. Generating long-form video first...", chosen_topic)
        try:
            from src.obscura_pipeline import run_obscura_pipeline
            longform_result = run_obscura_pipeline(topic=chosen_topic)
            resolved_longform_id = longform_result.get("video_id") or None
            if resolved_longform_id:
                logger.info("Long-form generated: https://www.youtube.com/watch?v=%s", resolved_longform_id)
        except Exception as exc:
            logger.warning("Long-form generation failed, continuing without link: %s", exc)

    long_form_url = (
        f"https://www.youtube.com/watch?v={resolved_longform_id}" if resolved_longform_id else None
    )

    # Rebuild description now that long_form_url is known.
    script_data["description"] = _build_obscura_shorts_description(
        script_data.get("description", ""), chosen_topic, long_form_url=long_form_url
    )

    # Step 3: Generate video (retry when narration exceeds the Shorts duration cap).
    max_generation_attempts = 4
    video_path = None
    last_generation_error = None

    for attempt in range(1, max_generation_attempts + 1):
        if attempt > 1:
            # Regenerate a shorter script for the same topic.
            script_data = (
                generator.generate(chosen_topic) if chosen_topic else generator.generate_random()
            )
            script_data["description"] = _build_obscura_shorts_description(
                script_data.get("description", ""), chosen_topic, long_form_url=long_form_url
            )
        try:
            video_path = video_gen.generate(script_data)
            break
        except ValueError as exc:
            if "must not exceed" not in str(exc):
                raise
            last_generation_error = exc
            logger.warning(
                "Narration exceeded %ss cap on attempt %s/%s for topic '%s'. Regenerating script.",
                config_shorts.ABSOLUTE_MAX_DURATION,
                attempt,
                max_generation_attempts,
                chosen_topic,
            )

    if video_path is None or script_data is None:
        raise last_generation_error or RuntimeError(
            "Failed to generate Obscura Shorts video within duration limit"
        )

    # Step 4: Upload to YouTube.
    uploader = ObscuraShortsUploader()
    video_id = uploader.upload(video_path, script_data)

    result = {
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/shorts/{video_id}",
        "title": script_data["title"],
        "topic": chosen_topic,
        "video_path": str(video_path),
        "long_form_url": long_form_url,
    }

    logger.info(f"✅ Obscura Shorts pipeline completed: {result['video_url']}")
    if long_form_url:
        logger.info(f"   Linked to long-form: {long_form_url}")
    return result
