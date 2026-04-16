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
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from src.utils import PROJECT_ROOT, setup_logger

load_dotenv()

# Import Obscura config
try:
    import src.config_obscura as config_obscura
except ImportError:
    config_obscura = None

logger = setup_logger("obscura_pipeline")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

TARGET_MIN_DURATION = 480
TARGET_MAX_DURATION = 720
OBSCURA_RECENT_TOPIC_AVOID_COUNT = 6

OBSCURA_BASE_KEYWORDS = [
    "dark forest",
    "abandoned building",
    "fog",
    "mystery",
    "old documents",
    "shadows",
    "night city",
    "cemetery",
    "rain",
    "empty road",
    "candle",
    "old photo",
    "vintage",
    "crime scene",
    "newspaper",
    "clock",
    "door",
    "window",
    "fire",
]

OBSCURA_TOPICS = [
    "The Disappearance of the Sodder Children",
    "The Hinterkaifeck Murders",
    "The Isdal Woman Mystery",
    "The Axeman of New Orleans",
    "The Somerton Man Case",
    "The Princes in the Tower",
    "The Beaumont Children Disappearance",
    "The Black Dahlia Investigation",
    # Extended topic pool — added 2026-03-21
    "The Zodiac Killer's Unsolved Identity",
    "The D.B. Cooper Skyjacking Mystery",
    "The Mary Celeste Ghost Ship",
    "The Flannan Isles Lighthouse Vanishing",
    "The Villisca Axe Murders",
    "The Dyatlov Pass Incident",
    "The Isabella Stewart Gardner Museum Heist",
    "The Springfield Three Disappearance",
    "The Circleville Letters Mystery",
    "The Max Headroom Broadcast Intrusion",
    "The Lady of the Dunes Mystery",
    "The Skeleton Lake of Roopkund",
    "The Yuba County Five",
    "The Salish Sea Severed Feet Mystery",
    "The Highway of Tears Disappearances",
    "The Oakville Blobs Mystery",
    "The Bog Bodies of Northern Europe",
    "The Madrid Codex and Maya Collapse",
    "The Tamam Shud Case",
    "The Amber Room Disappearance",
    "The Voynich Manuscript Mystery",
    "The Lost Colony of Roanoke",
    "The Oakland County Child Killer",
    "The West Mesa Bone Collector",
    "The Zodiac Cipher 340 Solution",
    "The Eko Atlantic Mysterious Disappearances",
    "The Cicada 3301 Unsolved Puzzle",
    "The Rendlesham Forest UFO Incident",
    "The Wallace Murder Case 1931",
    "The Papin Sisters Crime",
    "The Keddie Cabin Murders",
    "The Delphi Murders Mystery",
    "The Brandon Lawson Vanishing",
    "The Boy in the Box Philadelphia",
    "The Original Night Stalker Case",
    "The Texarkana Moonlight Murders",
    "The Brabant Killers Mystery",
    "The Lisbon Ripper Unsolved Case",
    "The Body in Room 1046",
    "The Torso Murders of Cleveland",
]

STOPWORDS = {
    "the", "and", "that", "with", "from", "this", "have", "were", "they", "their", "into",
    "about", "there", "after", "before", "would", "which", "when", "where", "what", "your",
    "just", "than", "then", "them", "been", "over", "under", "while", "because", "through",
}

OBSCURA_GROWTH_TAGS = [
    "unsolved mysteries",
    "dark history",
    "true crime documentary",
    "mystery documentary",
    "cold case",
    "historical mystery",
]

OBSCURA_TITLE_HOOK_WORDS = {
    "unsolved", "mystery", "haunting", "vanished", "killer", "murder", "secret", "cold case", "missing"
}

SHOCK_KEYWORDS = {
    "died", "murdered", "disappeared", "vanished", "never found", "shocking",
    "mysterious", "terrifying", "secret", "suddenly", "cursed", "executed",
    "buried", "trapped", "escaped",
}

PLACE_HINTS = {
    "street", "city", "village", "town", "island", "bay", "port", "mount", "mountain",
    "river", "forest", "county", "province", "district", "station", "airport", "hotel",
}

NARRATION_SECTION_LABELS = [
    "hook",
    "outro",
    "unresolved ending",
    "background",
    "mystery",
    "core mystery",
    "conclusion",
    "section",
    "chapter",
    "part",
    "opening",
    "intro",
]

OBSCURA_GENERIC_TOPIC_TOKENS = {
    "case",
    "children",
    "disappearance",
    "eight",
    "files",
    "five",
    "four",
    "history",
    "investigation",
    "killer",
    "killing",
    "killings",
    "man",
    "murder",
    "murders",
    "mystery",
    "new",
    "nine",
    "none",
    "of",
    "once",
    "one",
    "puzzle",
    "seven",
    "six",
    "solved",
    "stolen",
    "ten",
    "the",
    "three",
    "tower",
    "true",
    "two",
    "unknown",
    "unsolved",
    "vanished",
    "woman",
    "zero",
}

OBSCURA_TOPIC_ALIASES = {
    "The Beaumont Children Disappearance": [
        "beaumont children",
        "three children vanished australia",
        "australia darkest mystery",
        "australia brightest day",
    ],
}


def _audio_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return 0.0
    try:
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def _normalize_topic_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").strip().lower()).strip()


def _clean_metadata_text(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", (value or "").strip())


def _optimize_obscura_title(title: str, topic: str = "") -> str:
    base = re.sub(r"\s+", " ", (title or topic or "Obscura Files Mystery")).strip()
    lowered = base.lower()
    if not any(word in lowered for word in OBSCURA_TITLE_HOOK_WORDS):
        if len(base) <= 78:
            base = f"{base} | Unsolved Mystery"
        else:
            base = f"Unsolved Mystery: {base}"
    return base[:100].strip()


def _merge_obscura_tags(tags: list[str] | None, topic: str = "") -> list[str]:
    merged: list[str] = []
    for tag in (tags or []) + OBSCURA_GROWTH_TAGS + ([topic] if topic else []):
        clean = re.sub(r"\s+", " ", str(tag or "").strip())
        if clean and clean.lower() not in {item.lower() for item in merged}:
            merged.append(clean)
    return merged[:15]


def _build_obscura_description(description: str, topic: str = "", title: str = "") -> str:
    parts: list[str] = []
    base = _clean_metadata_text(description)
    if base:
        parts.append(base)
    if topic:
        parts.append(f"This episode investigates {topic}, one of the most disturbing unresolved cases in dark history.")
    parts.append("What do you think really happened? Share your theory in the comments.")
    parts.append(getattr(config_obscura, "SUBSCRIBE_CTA", "Subscribe to The Obscura Files for weekly unsolved mysteries, dark history, and true crime documentaries."))
    hashtag_line = " ".join(getattr(config_obscura, "DEFAULT_HASHTAGS", []))
    if hashtag_line:
        parts.append(hashtag_line)
    return _clean_metadata_text("\n\n".join(part for part in parts if part))[:5000]


def _build_obscura_comment(title: str, topic: str = "") -> str:
    case_name = topic or title or "this case"
    return (
        f"What is your theory about {case_name}? Comment below. "
        "If you want more unsolved cases, dark history, and cold case documentaries, subscribe to The Obscura Files."
    )[:10000]


def _topic_signature(topic: str) -> set[str]:
    tokens = [
        token
        for token in _normalize_topic_text(topic).split()
        if len(token) >= 4 and token not in OBSCURA_GENERIC_TOPIC_TOKENS
    ]
    signatures = set(tokens) or set(_normalize_topic_text(topic).split())
    for alias in OBSCURA_TOPIC_ALIASES.get(topic, []):
        alias_tokens = [
            token
            for token in _normalize_topic_text(alias).split()
            if len(token) >= 4 and token not in OBSCURA_GENERIC_TOPIC_TOKENS
        ]
        signatures.update(alias_tokens or _normalize_topic_text(alias).split())
    return signatures


def _history_matches_topic(topic: str, history_text: str) -> bool:
    """Return True if history_text describes the same case as topic.

    Each candidate (main topic + each alias) is checked independently using
    ALL-tokens logic so that a single common word cannot trigger a false positive,
    while alias phrases can still match even when the canonical topic name differs.
    """
    normalized_history = _normalize_topic_text(history_text)
    if not normalized_history:
        return False

    def _tokens(text: str) -> list[str]:
        raw = [t for t in _normalize_topic_text(text).split()
               if len(t) >= 4 and t not in OBSCURA_GENERIC_TOPIC_TOKENS]
        return raw or _normalize_topic_text(text).split()

    # Check main topic tokens (all must match)
    main_tokens = _tokens(topic)
    if main_tokens and all(t in normalized_history for t in main_tokens):
        return True

    # Check each alias independently (all tokens within an alias must match)
    for alias in OBSCURA_TOPIC_ALIASES.get(topic, []):
        alias_tokens = _tokens(alias)
        if alias_tokens and all(t in normalized_history for t in alias_tokens):
            return True

    return False


def _recent_registry_topics(limit: int | None = None) -> list[str]:
    registry_path = PROJECT_ROOT / "output" / "analytics" / "obscura_upload_registry.jsonl"
    if not registry_path.exists():
        return []

    recent_topics: list[str] = []
    seen: set[str] = set()
    try:
        lines = registry_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue

        history_text = str(row.get("topic") or row.get("title") or "")
        if not history_text:
            continue

        for candidate in OBSCURA_TOPICS:
            if _history_matches_topic(candidate, history_text):
                normalized_candidate = _normalize_topic_text(candidate)
                if normalized_candidate not in seen:
                    seen.add(normalized_candidate)
                    recent_topics.append(candidate)
                break

        if limit is not None and len(recent_topics) >= limit:
            break

    return recent_topics


def _find_obscura_registry_duplicate(topic: str) -> str | None:
    """Return the video_id from the local registry if the topic was already uploaded, else None.

    Used for early duplicate detection before expensive video generation starts.
    """
    registry_path = PROJECT_ROOT / "output" / "analytics" / "obscura_upload_registry.jsonl"
    if not registry_path.exists():
        return None
    try:
        lines = registry_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        history_text = str(row.get("topic") or row.get("title") or "").strip()
        if history_text and _history_matches_topic(topic, history_text):
            vid = row.get("video_id")
            if vid:
                return str(vid)
    return None


def _safe_filename(text: str, limit: int = 60) -> str:
    value = re.sub(r"[^\w\- ]+", "_", text).strip().replace(" ", "_")
    return value[:limit] or "obscura_video"


def _clean_narration_text(script_text: str) -> str:
    if not script_text:
        return ""

    text = script_text.replace("\r\n", "\n")

    section_pattern = r"(?:" + "|".join(re.escape(item) for item in NARRATION_SECTION_LABELS) + r")"

    # Remove stage-direction wrappers and parenthetical blocks
    text = re.sub(r"\[.*?\]", " ", text, flags=re.DOTALL)
    text = re.sub(r"\(.*?\)", " ", text, flags=re.DOTALL)
    text = re.sub(r"\*+.*?\*+", " ", text, flags=re.DOTALL)

    cleaned_lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        # Remove known section label prefixes
        line = re.sub(rf"^\s*(?:{section_pattern})\s*:\s*", "", line, flags=re.IGNORECASE)

        # Remove standalone section title lines (e.g., "Chapter 1:", "Section:")
        if re.match(rf"^(?:{section_pattern})(?:\s+\d+)?\s*:??\s*$", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^[A-Za-z][A-Za-z\s\-]{1,40}:\s*$", line):
            continue

        # Remove stage directions / production cues
        if re.match(
            r"^(?:sfx|music|scene|camera|cut to|fade in|fade out|voiceover|narrator|visual|shot|direction)\b",
            line,
            flags=re.IGNORECASE,
        ):
            continue

        line = re.sub(r"\s+", " ", line).strip()
        if line:
            cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _download_url(url: str, out_path: Path, timeout: int = 60, max_retries: int = 3):
    """Download URL with exponential backoff retry logic for network resilience."""
    import time
    last_error = None
    
    for attempt in range(max_retries):
        try:
            with requests.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return  # Success
        except requests.exceptions.ConnectionError as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s exponential backoff
                logger.warning(f"Download attempt {attempt + 1}/{max_retries} failed for {url[:60]}... Retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                logger.warning(f"Failed to download {url} after {max_retries} attempts: {e}")
        except Exception as e:
            last_error = e
            logger.warning(f"Failed to download {url}: {e}")
            break  # Don't retry on non-network errors
    
    if out_path.exists():
        out_path.unlink()
    raise last_error if last_error else RuntimeError(f"Failed to download {url}")


def _search_pexels(query: str, per_page: int = 10) -> list[str]:
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return []
    headers = {"Authorization": key}
    params = {"query": query, "per_page": per_page}
    resp = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results: list[str] = []
    for video in data.get("videos", []):
        files = video.get("video_files", [])
        if not files:
            continue
        best = sorted(files, key=lambda item: (item.get("height") or 0), reverse=True)[0]
        link = best.get("link")
        if link:
            results.append(link)
    return results


def _search_pixabay(query: str, per_page: int = 10) -> list[str]:
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        return []
    params = {"key": key, "q": query, "per_page": per_page}
    resp = requests.get("https://pixabay.com/api/videos/", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results: list[str] = []
    for hit in data.get("hits", []):
        videos = hit.get("videos", {})
        best_url = None
        best_h = -1
        for _, value in videos.items():
            h = int(value.get("height", 0) or 0)
            if h > best_h:
                best_h = h
                best_url = value.get("url")
        if best_url:
            results.append(best_url)
    return results


def _search_freesound_music(query: str, per_page: int = 8) -> list[str]:
    token = os.getenv("FREESOUND_API_KEY", "").strip()
    if not token:
        return []

    url = "https://freesound.org/apiv2/search/text/"
    params = {
        "query": query,
        "filter": "duration:[30 TO 900] license:\"Creative Commons 0\"",
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


def _search_pixabay_music(query: str, per_page: int = 10) -> list[str]:
    key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not key:
        return []

    # Pixabay music endpoint
    url = "https://pixabay.com/api/audio/"
    params = {
        "key": key,
        "q": query,
        "per_page": per_page,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 403:
            logger.debug(f"Pixabay API rate limit or auth issue (403) for '{query}' - skipping")
            return []
        resp.raise_for_status()
        data = resp.json()

        results: list[str] = []
        for hit in data.get("hits", []):
            audio_url = hit.get("audio")
            if audio_url:
                results.append(audio_url)
        return results
    except Exception as e:
        logger.debug(f"Pixabay music search error for '{query}': {e}")
        return []


def _bgm_queries_for_context(topic: str, script: str) -> list[str]:
    text = f"{topic} {script}".lower()
    if any(word in text for word in ["horror", "ghost", "haunted", "demon", "terror", "paranormal"]):
        return ["dark ambient", "creepy music", "horror atmosphere"]
    if any(word in text for word in ["mystery", "disappearance", "unsolved", "case", "investigation"]):
        return ["suspenseful", "tense cinematic", "mystery soundtrack"]
    return ["dramatic orchestral", "historical cinematic", "dark documentary"]


def _select_and_download_bgm(topic: str, script: str, out_path: Path) -> Path:
    queries = _bgm_queries_for_context(topic, script)

    candidates: list[str] = []
    for query in queries:
        if len(candidates) >= 10:
            break
        try:
            candidates.extend(_search_freesound_music(query, per_page=6))
        except Exception as e:
            logger.warning(f"Freesound music search failed for '{query}': {e}")
        try:
            candidates.extend(_search_pixabay_music(query, per_page=8))
        except Exception as e:
            logger.warning(f"Pixabay music search failed for '{query}': {e}")

    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        logger.warning("No royalty-free BGM found from freesound.org or pixabay.com/music API")
        return None

    random.shuffle(candidates)
    last_error = None
    for url in candidates[:8]:
        try:
            _download_url(url, out_path)
            if out_path.exists() and out_path.stat().st_size > 0:
                logger.info(f"Selected BGM: {url}")
                return out_path
        except Exception as e:
            last_error = e
            continue

    logger.warning(f"Failed to download all BGM candidates: {last_error}")
    return None


def _mix_narration_with_bgm(narration_path: Path, bgm_path: Path, out_path: Path, narration_duration: float):
    fade_out_start = max(0.0, narration_duration - 2.0)
    filter_complex = (
        f"[0:a]volume=1.0[narr];"
        f"[1:a]volume=0.15,afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out_start:.2f}:d=2.0,"
        f"atrim=0:{narration_duration:.2f}[bgm];"
        f"[narr][bgm]amix=inputs=2:duration=first:dropout_transition=2[outa]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(narration_path),
        "-stream_loop", "-1",
        "-i", str(bgm_path),
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        "-c:a", "mp3",
        "-b:a", "192k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _to_ass_time(sec: float) -> str:
    if sec < 0:
        sec = 0
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = int(sec % 60)
    centis = int(round((sec - int(sec)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def _is_shock_text(text: str) -> bool:
    lower = text.lower()
    return any(keyword in lower for keyword in SHOCK_KEYWORDS)


def _has_named_entity_or_place(text: str) -> bool:
    # Simple heuristic: consecutive capitalized words or place hints
    if re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", text):
        return True
    lower = text.lower()
    return any(hint in lower for hint in PLACE_HINTS)


def _build_styled_ass_from_srt(srt_path: Path, ass_path: Path):
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n\s*\n", content.strip())

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Normal,Arial,72,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,32,1
Style: Shock,Arial,85,&H0000FFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,0,2,60,60,32,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

    dialogues: list[str] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue

        # Usually: index, timing, text...
        timing_line = lines[1]
        text = " ".join(lines[2:]).strip()
        if "-->" not in timing_line or not text:
            continue

        start_raw, end_raw = [part.strip() for part in timing_line.split("-->")]

        def parse_srt_time(value: str) -> float:
            hh, mm, rest = value.split(":")
            ss, ms = rest.split(",")
            return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0

        start_sec = parse_srt_time(start_raw)
        end_sec = parse_srt_time(end_raw)
        style = "Shock" if _is_shock_text(text) else "Normal"

        escaped = _escape_ass_text(text)
        escaped = r"{\fad(300,0)}" + escaped
        dialogues.append(
            f"Dialogue: 0,{_to_ass_time(start_sec)},{_to_ass_time(end_sec)},{style},,0,0,0,,{escaped}"
        )

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write("\n".join(dialogues) + "\n")


def _prepare_clip_segment(in_path: Path, out_path: Path, start_sec: float, length_sec: float):
    vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_sec:.2f}",
        "-i", str(in_path),
        "-t", f"{length_sec:.2f}",
        "-vf", vf,
        "-an",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def _build_crossfade_video(clips: list[Path], clip_lengths: list[float], out_path: Path, fade_duration: float = 0.5):
    if len(clips) == 1:
        shutil.copy(str(clips[0]), str(out_path))
        return

    cmd = ["ffmpeg", "-y"]
    for clip in clips:
        cmd.extend(["-i", str(clip)])

    filters = []
    filters.append("[0:v]format=yuv420p[v0]")

    cumulative = clip_lengths[0]
    last_label = "v0"
    for i in range(1, len(clips)):
        out_label = f"v{i}"
        offset = max(0.0, cumulative - fade_duration)
        filters.append(
            f"[{last_label}][{i}:v]xfade=transition=fade:duration={fade_duration}:offset={offset:.3f}[{out_label}]"
        )
        cumulative += max(0.1, clip_lengths[i] - fade_duration)
        last_label = out_label

    cmd.extend([
        "-filter_complex", ";".join(filters),
        "-map", f"[{last_label}]",
        "-an",
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        str(out_path),
    ])
    subprocess.run(cmd, check=True)


def _extend_video_to_duration(in_video: Path, out_video: Path, target_duration: float):
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(in_video),
        "-t", f"{target_duration:.2f}",
        "-an",
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        str(out_video),
    ]
    subprocess.run(cmd, check=True)


def _burn_subtitles(in_video: Path, srt_path: Path, out_video: Path):
    temp_ass = in_video.parent / "obscura_subs.ass"
    _build_styled_ass_from_srt(srt_path, temp_ass)
    try:
        vf = f"subtitles={temp_ass.name}"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(in_video.absolute()),
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-c:a", "copy",
            str(out_video.absolute()),
        ]
        subprocess.run(cmd, check=True, cwd=str(in_video.parent))
    finally:
        if temp_ass.exists():
            temp_ass.unlink()


def _extract_keywords(topic: str, script: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-']{3,}", (topic + " " + script).lower())
    freq: dict[str, int] = {}
    for word in words:
        if word in STOPWORDS:
            continue
        freq[word] = freq.get(word, 0) + 1
    ranked = [word for word, _ in sorted(freq.items(), key=lambda item: item[1], reverse=True)[:20]]

    merged = list(OBSCURA_BASE_KEYWORDS)
    merged.extend(ranked)
    seen = set()
    result = []
    for item in merged:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result[:30]


def _acquire_obscura_run_lock() -> Path | None:
    locks_dir = PROJECT_ROOT / "output" / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    lock_path = locks_dir / "obscura_pipeline.lock"

    while True:
        try:
            # O_EXCL keeps lock acquisition atomic across concurrent processes.
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"pid={os.getpid()} started={datetime.now().isoformat()}\n")
            return lock_path
        except FileExistsError:
            try:
                lock_text = lock_path.read_text(encoding="utf-8").strip()
            except Exception:
                lock_text = ""

            pid = None
            for part in lock_text.split():
                if part.startswith("pid="):
                    try:
                        pid = int(part.split("=", 1)[1])
                    except ValueError:
                        pid = None
                    break

            is_running = False
            if pid:
                try:
                    os.kill(pid, 0)
                    is_running = True
                except ProcessLookupError:
                    is_running = False
                except PermissionError:
                    is_running = True
                except OSError:
                    is_running = False

            if is_running:
                logger.warning("Obscura pipeline lock exists. Another run is already in progress; skipping duplicate start.")
                return None

            logger.warning(f"Removing stale Obscura pipeline lock: {lock_path}")
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def _release_obscura_run_lock(lock_path: Path | None):
    if lock_path and lock_path.exists():
        try:
            lock_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove lock file {lock_path}: {e}")


class ObscuraScriptGenerator:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set.")
        self.client = anthropic.Anthropic(api_key=api_key, timeout=None)

    def generate(self, topic: str) -> dict:
        prompt = f"""
You are writing a YouTube script for the channel "Obscura Files".

Rules:
- Language: English only
- Tone: mysterious, dramatic, suspenseful
- Genre: Dark History / Mystery / Unsolved Crimes
- Must be grounded in real historical facts and known case details.
- Script length target: 1500-2200 words
- Structure:
    1) Hook (~15-30 sec)
  2) Background (~2 min)
  3) Core mystery (~4-5 min)
  4) Unresolved ending (~1-2 min)
  5) Outro (~30 sec)

Mandatory high-retention writing pattern:
- In the first 15 seconds, reveal the single most shocking verified fact.
- End each section with a cliffhanger pull line similar to "You won't believe what happened next...".
- Ask the audience 2-3 direct questions (e.g., "What would you have done?", "But here's where it gets strange...").
- Include concrete numbers/statistics where available to improve credibility.
- Keep each section under 2 minutes in spoken pacing.
- Ensure the script is complete through Outro with no abrupt ending.
- Ending should remain unresolved and thought-provoking, not definitive.

Topic: {topic}

Return strict JSON with these keys only:
title, description, tags, script

Constraints:
- title must be <= 100 chars
- title must use curiosity, stakes, or a shocking fact; avoid generic case-name-only titles
- tags must be a JSON array of 8-15 English tags
- description must be 2-3 short paragraphs and no links
- description should end with a direct audience question and a subscribe prompt
""".strip()

        message = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=7000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        json_text = raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw and "}" in raw else raw
        data = json.loads(json_text)

        data["topic"] = topic
        return data

    def generate_random(self) -> dict:
        used_topics = {_normalize_topic_text(topic) for topic in _recent_registry_topics(limit=None)}
        available_topics = [
            topic for topic in OBSCURA_TOPICS
            if _normalize_topic_text(topic) not in used_topics
        ]
        topic_pool = available_topics or OBSCURA_TOPICS
        topic = random.choice(topic_pool)
        if used_topics:
            logger.info("Avoiding previously used Obscura topics: %s", ", ".join(sorted(used_topics)))
        return self.generate(topic)


class ObscuraYouTubeUploader:
    def __init__(self):
        self.token_file = PROJECT_ROOT / "config" / "youtube_token_obscura.json"
        self.client_secrets = PROJECT_ROOT / "config" / "youtube_client_secrets_obscura.json"
        self.upload_registry = PROJECT_ROOT / "output" / "analytics" / "obscura_upload_registry.jsonl"
        if not self.client_secrets.exists():
            self.client_secrets = PROJECT_ROOT / "config" / "youtube_client_secrets.json"

        self.youtube = self._authenticate()

    def _authenticate(self):
        creds = None
        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
            except Exception as exc:
                logger.warning("Failed to load Obscura token file, reauth required: %s", exc)
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as exc:
                    logger.warning("Obscura token refresh failed, starting fresh OAuth flow: %s", exc)
                    creds = None

            if not creds or not creds.valid:
                if not self.client_secrets.exists():
                    raise ValueError(
                        "YouTube OAuth client secrets not found for Obscura. "
                        "Set config/youtube_client_secrets_obscura.json or config/youtube_client_secrets.json"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secrets), SCOPES)
                creds = flow.run_local_server(port=8090)

            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

        return build("youtube", "v3", credentials=creds)

    def _sha256(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _recent_uploads(self, max_results: int = 25) -> list[dict]:
        try:
            channel = self.youtube.channels().list(part="contentDetails", mine=True).execute()
            items = channel.get("items", [])
            if not items:
                return []

            uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            response = self.youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist,
                maxResults=max_results,
            ).execute()
            return response.get("items", [])
        except Exception as e:
            logger.warning(f"Could not fetch recent uploads for duplicate check: {e}")
            return []

    def _load_registry(self) -> list[dict]:
        if not self.upload_registry.exists():
            return []
        rows: list[dict] = []
        with open(self.upload_registry, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        return rows

    def _record_upload(self, video_path: Path, title: str, video_id: str, sha256: str, topic: str = ""):
        self.upload_registry.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "video_id": video_id,
            "title": title,
            "topic": topic,
            "file_path": str(video_path),
            "file_size": video_path.stat().st_size,
            "sha256": sha256,
        }
        with open(self.upload_registry, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _find_duplicate(self, video_path: Path, title: str, sha256: str, topic: str = "") -> str | None:
        rows = self._load_registry()

        # 1) Strong local check by file hash
        for row in reversed(rows):
            if row.get("sha256") == sha256 and row.get("video_id"):
                return str(row["video_id"])

        # 2) Local check by normalized topic against registry topic/title
        normalized_topic = _normalize_topic_text(topic)
        if normalized_topic:
            for row in reversed(rows):
                history_text = str(row.get("topic") or row.get("title") or "")
                if history_text and _history_matches_topic(topic, history_text) and row.get("video_id"):
                    return str(row["video_id"])

        # 3) Remote check by exact title in recent channel uploads
        normalized = title.strip().lower()
        for item in self._recent_uploads(max_results=30):
            snippet = item.get("snippet", {})
            existing_title = (snippet.get("title") or "").strip().lower()
            if existing_title and existing_title == normalized:
                video_id = item.get("contentDetails", {}).get("videoId")
                if video_id:
                    return video_id
        return None

    def upload(self, video_path: Path, metadata: dict) -> str:
        topic = str(metadata.get("topic", ""))
        title = _optimize_obscura_title(metadata.get("title", "Obscura Files Story"), topic)
        description = _build_obscura_description(metadata.get("description", ""), topic, title)
        tags = _merge_obscura_tags(metadata.get("tags", []), topic)

        file_hash = self._sha256(video_path)
        duplicate_video_id = self._find_duplicate(video_path, title, file_hash, str(metadata.get("topic", "")))
        if duplicate_video_id:
            logger.warning("Duplicate Obscura upload detected. Skipping upload.")
            logger.warning(f"Existing video: https://www.youtube.com/watch?v={duplicate_video_id}")
            return duplicate_video_id

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "27",
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en",
            },
            "status": {
                "privacyStatus": getattr(config_obscura, "UPLOAD_PRIVACY", "public"),
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": True,
                "selfDeclaredAsModifiedContent": True,
            },
        }

        status = body.setdefault("status", {})
        status["containsSyntheticMedia"] = True
        status["selfDeclaredAsModifiedContent"] = True

        media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=2 * 1024 * 1024)
        request = self.youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            _, response = request.next_chunk()
        video_id = response["id"]
        try:
            self.youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": _build_obscura_comment(title, topic)
                            }
                        },
                    }
                },
            ).execute()
            logger.info("Posted initial engagement comment for Obscura upload: %s", video_id)
        except Exception as exc:
            exc_str = str(exc).lower()
            if "forbidden" in exc_str or "403" in exc_str:
                logger.info(
                    "Comment posting skipped for %s: YouTube API requires project audit approval "
                    "for commentThreads.insert. Apply at "
                    "https://support.google.com/youtube/contact/yt_api_form",
                    video_id,
                )
            else:
                logger.warning("Could not post engagement comment for %s: %s", video_id, exc)
        self._record_upload(video_path, title, video_id, file_hash, str(metadata.get("topic", "")))
        return video_id


class ObscuraVideoGenerator:
    def __init__(self):
        self.output_dir = PROJECT_ROOT / "output" / "videos"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def _synthesize_audio(self, text: str, output_path: Path):
        try:
            import edge_tts
        except Exception as e:
            raise RuntimeError("edge-tts is not installed. Install with: pip install edge-tts") from e

        communicate = edge_tts.Communicate(
            text=text,
            voice="en-US-GuyNeural",
            rate="-10%",
            pitch="-5Hz",
        )
        await communicate.save(str(output_path))

    def _whisper_transcribe(self, audio_path: Path, srt_out: Path):
        try:
            import whisper
        except Exception as e:
            raise RuntimeError("openai-whisper is not installed. Install with: pip install openai-whisper") from e

        model = whisper.load_model("base")
        result = model.transcribe(str(audio_path), language="en")
        segments = result.get("segments", [])

        with open(srt_out, "w", encoding="utf-8") as f:
            subtitle_index = 1
            for seg in segments:
                start = float(seg["start"])
                end = float(seg["end"])

                def fmt(t: float) -> str:
                    ms = int((t - int(t)) * 1000)
                    h = int(t // 3600)
                    m = int((t % 3600) // 60)
                    s = int(t % 60)
                    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

                text = seg.get("text", "").strip()
                if not text:
                    continue

                words = text.split()
                max_words = 6
                if not words:
                    continue

                for offset in range(0, len(words), max_words):
                    chunk = words[offset:offset + max_words]
                    chunk_text = " ".join(chunk)
                    chunk_start = start + (offset / len(words)) * (end - start)
                    chunk_end = start + ((offset + len(chunk)) / len(words)) * (end - start)
                    f.write(f"{subtitle_index}\n{fmt(chunk_start)} --> {fmt(chunk_end)}\n{chunk_text}\n\n")
                    subtitle_index += 1

    def generate(self, script_data: dict) -> Path:
        title = script_data.get("title", "Obscura Story")
        topic = script_data.get("topic", "Obscura")
        script_text = script_data.get("script", "")
        narration_text = _clean_narration_text(script_text)

        if not narration_text.strip():
            raise ValueError("script is empty")

        tmpdir = Path(tempfile.mkdtemp(prefix="obscura_"))
        logger.info(f"Obscura working directory: {tmpdir}")

        try:
            audio_path = tmpdir / "narration.mp3"
            asyncio.run(self._synthesize_audio(narration_text, audio_path))

            duration = _audio_duration(audio_path)
            if duration < TARGET_MIN_DURATION or duration > TARGET_MAX_DURATION:
                logger.warning(
                    f"Narration duration is {duration:.1f}s. Preferred range is 8-12 minutes, "
                    "but full script completion is prioritized."
                )

            bgm_path = tmpdir / "bgm_track.mp3"
            bgm_result = _select_and_download_bgm(topic, script_text, bgm_path)

            if bgm_result:
                mixed_audio = tmpdir / "narration_with_bgm.mp3"
                _mix_narration_with_bgm(audio_path, bgm_path, mixed_audio, duration)
                audio_path = mixed_audio
                duration = _audio_duration(audio_path)
            else:
                logger.warning("Continuing without background music due to API unavailability")

            keywords = _extract_keywords(topic, script_text)
            logger.info(f"Searching clips with {len(keywords)} keywords")

            urls: list[str] = []
            for kw in keywords:
                if len(urls) >= 140:
                    break
                urls.extend(_search_pexels(kw, per_page=8))
                urls.extend(_search_pixabay(kw, per_page=8))

            urls = list(dict.fromkeys(urls))
            logger.info(f"Found {len(urls)} unique clip URLs")
            if len(urls) < 100:
                raise RuntimeError(f"Need at least 100 clips, found {len(urls)}")

            effective_len = 6.0  # 5-8 sec with 0.5 sec crossfade roughly averages this
            needed_segments = max(100, int(math.ceil(duration / effective_len)) + 2)

            max_capacity = len(urls) * 3
            if max_capacity < needed_segments:
                raise RuntimeError(
                    f"Not enough capacity with 3x reuse cap. Need {needed_segments}, capacity {max_capacity}"
                )

            random.shuffle(urls)
            usage_count = {url: 0 for url in urls}
            sequence: list[str] = []
            index = 0
            while len(sequence) < needed_segments:
                url = urls[index % len(urls)]
                index += 1
                if usage_count[url] >= 3:
                    continue
                usage_count[url] += 1
                sequence.append(url)

            processed_clips: list[Path] = []
            clip_lengths: list[float] = []
            skipped_count = 0
            for i, url in enumerate(sequence):
                try:
                    raw_path = tmpdir / f"raw_{i}.mp4"
                    logger.info(f"Downloading clip {i + 1}/{len(sequence)}")
                    _download_url(url, raw_path, timeout=90, max_retries=3)
                    
                    raw_dur = _audio_duration(raw_path)
                    if raw_dur <= 0:
                        logger.warning(f"Invalid clip duration at {i}: {raw_dur}s, skipping")
                        raw_path.unlink(missing_ok=True)
                        skipped_count += 1
                        continue

                    clip_len = random.uniform(5.0, 8.0)
                    if raw_dur > clip_len + 0.4:
                        start_sec = random.uniform(0.0, max(0.0, raw_dur - clip_len - 0.1))
                    else:
                        start_sec = 0.0
                        clip_len = max(5.0, min(8.0, raw_dur))

                    out_clip = tmpdir / f"clip_{i}.mp4"
                    _prepare_clip_segment(raw_path, out_clip, start_sec, clip_len)
                    actual_clip_len = _audio_duration(out_clip)
                    if actual_clip_len <= 0:
                        logger.warning(f"Prepared clip {i} has invalid duration, skipping")
                        out_clip.unlink(missing_ok=True)
                        raw_path.unlink(missing_ok=True)
                        skipped_count += 1
                        continue

                    processed_clips.append(out_clip)
                    clip_lengths.append(actual_clip_len)
                    raw_path.unlink(missing_ok=True)  # Clean up raw file
                except Exception as e:
                    logger.warning(f"Clip {i} processing failed: {e}")
                    skipped_count += 1
                    if (tmpdir / f"raw_{i}.mp4").exists():
                        (tmpdir / f"raw_{i}.mp4").unlink(missing_ok=True)
                    if len(processed_clips) >= 100:  # Minimum clips collected
                        logger.info(f"Collected {len(processed_clips)} clips, continuing despite {skipped_count} failures")
                        break
                    continue

            if len(processed_clips) < 80:
                raise RuntimeError(f"Only {len(processed_clips)} clips successfully processed (need at least 80)")
            logger.info(f"Clip processing complete: {len(processed_clips)} clips, {skipped_count} skipped")

            crossfaded = tmpdir / "crossfaded.mp4"
            _build_crossfade_video(processed_clips, clip_lengths, crossfaded, fade_duration=0.5)

            crossfaded_duration = _audio_duration(crossfaded)
            logger.info(f"Narration duration: {duration:.1f}s, visual duration: {crossfaded_duration:.1f}s")

            merge_video_source = crossfaded
            if crossfaded_duration + 0.5 < duration:
                extended_video = tmpdir / "crossfaded_extended.mp4"
                logger.warning(
                    f"Visual track shorter than narration ({crossfaded_duration:.1f}s < {duration:.1f}s). Extending visuals."
                )
                _extend_video_to_duration(crossfaded, extended_video, duration)
                merge_video_source = extended_video

            merged = tmpdir / "merged.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(merge_video_source), "-i", str(audio_path),
                    "-c:v", "copy", "-c:a", "aac", "-shortest", str(merged)
                ],
                check=True,
            )

            srt_path = tmpdir / "subs_en.srt"
            self._whisper_transcribe(audio_path, srt_path)

            subtitled = tmpdir / "subtitled.mp4"
            _burn_subtitles(merged, srt_path, subtitled)

            out_name = f"obscura_{_safe_filename(title)}.mp4"
            output_path = self.output_dir / out_name
            shutil.copy(str(subtitled), str(output_path))
            return output_path
        finally:
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass


def run_obscura_pipeline(topic: str | None = None) -> dict:
    lock_path = _acquire_obscura_run_lock()
    if lock_path is None:
        return {
            "video_id": None,
            "video_path": "",
            "title": "",
            "topic": topic or "",
            "skipped": True,
            "reason": "duplicate_run_locked",
        }

    logger.info(f"🎬 Starting Obscura Files Pipeline (Config: {'config_obscura' if config_obscura else 'environment'})")

    try:
        generator = ObscuraScriptGenerator()
        script_data = generator.generate(topic) if topic else generator.generate_random()

        # Persist latest metadata/script for inspection
        scripts_dir = PROJECT_ROOT / "output" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        with open(scripts_dir / "obscura_latest_metadata.json", "w", encoding="utf-8") as f:
            json.dump(script_data, f, ensure_ascii=False, indent=2)
        with open(scripts_dir / "obscura_latest_script.txt", "w", encoding="utf-8") as f:
            f.write(script_data.get("script", ""))

        # Early duplicate check — avoid expensive video generation (~30-45 min) if topic
        # was already uploaded according to the local registry.
        chosen_topic = str(script_data.get("topic") or topic or "").strip()
        if chosen_topic:
            existing_id = _find_obscura_registry_duplicate(chosen_topic)
            if existing_id:
                logger.warning(
                    "Topic '%s' already uploaded. Skipping video generation. "
                    "Existing: https://www.youtube.com/watch?v=%s",
                    chosen_topic,
                    existing_id,
                )
                return {
                    "video_id": existing_id,
                    "video_path": "",
                    "title": script_data.get("title", ""),
                    "topic": chosen_topic,
                    "skipped": True,
                    "reason": "duplicate_topic",
                }

        video_gen = ObscuraVideoGenerator()
        video_path = video_gen.generate(script_data)

        uploader = ObscuraYouTubeUploader()
        video_id = uploader.upload(video_path, script_data)

        return {
            "video_id": video_id,
            "video_path": str(video_path),
            "title": script_data.get("title", ""),
            "topic": script_data.get("topic", topic or ""),
        }
    finally:
        _release_obscura_run_lock(lock_path)
