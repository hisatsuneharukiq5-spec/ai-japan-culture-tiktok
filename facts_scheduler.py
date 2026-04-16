"""Facts & Wonders shorts pipeline and autonomous scheduler."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from xml.etree import ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config_facts

load_dotenv()

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
FACTS_DIR = OUTPUT_DIR / "facts"
FACTS_DIR.mkdir(parents=True, exist_ok=True)
FACTS_CTA = "Subscribe for daily 60-second science facts!"
(OUTPUT_DIR / "analytics").mkdir(parents=True, exist_ok=True)
(ROOT / "logs").mkdir(parents=True, exist_ok=True)

FACTS_LOG_PATH = ROOT / "logs" / "facts_schedule.log"
ERROR_LOG_PATH = ROOT / "logs" / "error.log"

logger = logging.getLogger("facts_scheduler")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(FACTS_LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [facts_scheduler] %(levelname)s: %(message)s"))
    logger.addHandler(handler)

error_logger = logging.getLogger("facts_scheduler.error")
if not error_logger.handlers:
    error_logger.setLevel(logging.ERROR)
    _err_handler = logging.FileHandler(ERROR_LOG_PATH, encoding="utf-8")
    _err_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    error_logger.addHandler(_err_handler)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
TOKEN_FILE = ROOT / "config" / "youtube_token_facts.json"
CLIENT_SECRETS_FILE = ROOT / "config" / "youtube_client_secrets.json"

REGISTRY_PATH = OUTPUT_DIR / "analytics" / "facts_upload_registry.jsonl"
SCHEDULE_PATH = OUTPUT_DIR / "analytics" / "facts_daily_schedule.json"
CYCLE_REPORT_PATH = OUTPUT_DIR / "analytics" / "facts_cycle_latest.json"

MIN_SOURCE_HEIGHT = 720
MAX_SOURCE_HEIGHT = 1280
MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024  # 30MB
MAX_SOURCE_DURATION_SEC = 45.0
SEARCH_TIMEOUT_SEC = 15
MAX_SEARCH_KEYWORDS = 6
MAX_SEARCH_URLS = 24
FACTS_SUBTITLE_MAX_WORDS = 4
POST_JITTER_MIN_SEC = 120    # 2 min minimum — more human-like
POST_JITTER_MAX_SEC = 900   # up to 15 min — harder for YouTube to fingerprint
FACTS_DUPLICATE_LOOKBACK_DAYS = 90
FACTS_SCRIPT_ATTEMPTS = 5
RECENT_TOPIC_AVOID_COUNT = 20


def _active_facts_hashtags() -> list[str]:
    learned = getattr(config_facts, "LEARNED_HASHTAGS", None)
    if isinstance(learned, list):
        cleaned = [str(tag).strip() for tag in learned if str(tag).strip()]
        if cleaned:
            return cleaned
    return config_facts.SHORTS_HASHTAGS


def _optimize_title_for_growth(title: str) -> str:
    candidate = (title or "").strip()
    if not candidate:
        return candidate

    if not any(ch.isdigit() for ch in candidate):
        if len(candidate) <= 86:
            candidate = f"{candidate} (3 Facts)"
        else:
            candidate = f"{candidate[:82].rstrip()} (3 Facts)"

    if "#shorts" not in candidate.lower() and len(candidate) <= 92:
        candidate = f"{candidate} #Shorts"

    return candidate[:100].strip()


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _safe_name(text: str, max_len: int = 60) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")[:max_len] or "facts_short"


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-500:] or "Command failed")
    return result


def _ffprobe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, text=True).strip()
        return float(out)
    except Exception:
        return 57.0


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _wrap_caption_words(sentence: str, max_words: int = 4) -> str:
    words = sentence.split()
    lines = [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]
    return "\\N".join(lines)


def _apply_highlight_markup(text: str) -> str:
    out = text
    for word in config_facts.HIGHLIGHT_WORDS:
        pattern = re.compile(rf"\b({re.escape(word)})\b", re.IGNORECASE)
        out = pattern.sub(r"{\\c&H00FFFF&\\fs90}\\1{\\r}", out)
    return out


def _build_ass_subtitles(script_text: str, duration: float, out_path: Path) -> None:
    sentences = _split_sentences(script_text)
    if not sentences:
        sentences = [script_text]

    duration = max(0.5, float(duration))
    word_counts = [max(1, len(re.findall(r"[A-Za-z0-9']+", sentence))) for sentence in sentences]
    total_words = sum(word_counts) or len(sentences)

    raw_durations = [duration * (count / total_words) for count in word_counts]
    min_per_sentence = min(1.2, max(0.4, duration / (len(sentences) * 2.0)))

    if sum(max(value, min_per_sentence) for value in raw_durations) <= duration:
        segment_durations = [max(value, min_per_sentence) for value in raw_durations]
        scale = duration / sum(segment_durations)
        segment_durations = [value * scale for value in segment_durations]
    else:
        segment_durations = raw_durations
    styles = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,4,0,5,40,40,960,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def fmt(seconds: float) -> str:
        seconds = max(0.0, seconds)
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines: list[str] = [styles]
    cursor = 0.0
    for idx, sentence in enumerate(sentences):
        start = cursor
        if idx == len(sentences) - 1:
            end = duration
        else:
            end = min(duration, cursor + segment_durations[idx])
            if end <= start:
                end = min(duration, start + 0.2)
        wrapped = _wrap_caption_words(sentence, 4)
        highlighted = _apply_highlight_markup(wrapped)
        lines.append(f"Dialogue: 0,{fmt(start)},{fmt(end)},Default,,0,0,0,,{highlighted}")
        cursor = end

    out_path.write_text("\n".join(lines), encoding="utf-8")


def _group_word_timings_to_captions(word_timings: list[dict], max_words: int = FACTS_SUBTITLE_MAX_WORDS) -> list[dict]:
    if not word_timings:
        return []

    captions: list[dict] = []
    for i in range(0, len(word_timings), max_words):
        chunk = word_timings[i : i + max_words]
        if not chunk:
            continue

        text_chunk = " ".join(str(item.get("text", "")).strip() for item in chunk).strip()
        if not text_chunk:
            continue

        start_sec = float(chunk[0].get("start", 0.0))
        end_sec = float(chunk[-1].get("end", start_sec))
        if end_sec <= start_sec:
            end_sec = start_sec + 0.05

        captions.append(
            {
                "text": text_chunk,
                "start": start_sec,
                "end": end_sec,
            }
        )

    return captions


def _chunk_timed_text(text: str, start: float, end: float, max_words: int = FACTS_SUBTITLE_MAX_WORDS) -> list[dict]:
    words = [w for w in text.split() if w.strip()]
    if not words:
        return []

    total_duration = max(0.1, end - start)
    chunks = [words[i : i + max_words] for i in range(0, len(words), max_words)]
    unit = total_duration / max(1, len(chunks))

    results: list[dict] = []
    for idx, chunk in enumerate(chunks):
        chunk_start = start + unit * idx
        chunk_end = end if idx == len(chunks) - 1 else start + unit * (idx + 1)
        if chunk_end <= chunk_start:
            chunk_end = chunk_start + 0.05
        results.append(
            {
                "text": " ".join(chunk),
                "start": chunk_start,
                "end": chunk_end,
            }
        )
    return results


def _build_ass_subtitles_from_captions(captions: list[dict], duration: float, out_path: Path) -> None:
    if not captions:
        return _build_ass_subtitles("", duration, out_path)

    duration = max(0.5, float(duration))
    styles = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,4,0,5,40,40,960,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def fmt(seconds: float) -> str:
        seconds = max(0.0, seconds)
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines: list[str] = [styles]
    for idx, caption in enumerate(captions):
        start = max(0.0, float(caption.get("start", 0.0)))
        end = max(start + 0.05, float(caption.get("end", start + 0.05)))
        if start > duration:
            break
        end = min(duration, end)
        if idx == len(captions) - 1:
            end = duration

        text = str(caption.get("text", "")).strip()
        if not text:
            continue
        wrapped = _wrap_caption_words(text, FACTS_SUBTITLE_MAX_WORDS)
        highlighted = _apply_highlight_markup(wrapped)
        lines.append(f"Dialogue: 0,{fmt(start)},{fmt(end)},Default,,0,0,0,,{highlighted}")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def _get_active_channel_info(youtube: Any) -> dict[str, str]:
    resp = youtube.channels().list(part="id,snippet", mine=True, maxResults=1).execute()
    items = resp.get("items") or []
    if not items:
        raise RuntimeError("No YouTube channel found for authenticated account")
    item = items[0]
    return {
        "id": item.get("id", ""),
        "name": (item.get("snippet") or {}).get("title", ""),
    }


def _validate_facts_channel(youtube: Any) -> None:
    info = _get_active_channel_info(youtube)
    expected_id = (config_facts.CHANNEL_ID or "").strip()
    expected_name = (config_facts.CHANNEL_NAME or "").strip()

    if expected_id and info["id"] != expected_id:
        raise RuntimeError(
            "Authenticated channel mismatch for Facts upload. "
            f"Expected channel_id={expected_id}, got channel_id={info['id']} ({info['name']})."
        )

    if (not expected_id) and expected_name and info["name"].strip().lower() != expected_name.lower():
        raise RuntimeError(
            "Authenticated channel mismatch for Facts upload. "
            f"Expected channel_name='{expected_name}', got '{info['name']}' (id={info['id']}). "
            "Set YOUTUBE_CHANNEL_ID_FACTS in .env for strict ID-based validation."
        )


def _authenticate_youtube() -> Any:
    from google.auth.exceptions import RefreshError
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                logger.warning(f"Token refresh failed (revoked/expired): {e}. Deleting token file and re-authenticating...")
                TOKEN_FILE.unlink(missing_ok=True)
                # Retry authentication flow
                if not CLIENT_SECRETS_FILE.exists():
                    raise ValueError(f"Missing client secrets: {CLIENT_SECRETS_FILE}")
                flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
                creds = flow.run_local_server(port=8090)
        else:
            if not CLIENT_SECRETS_FILE.exists():
                raise ValueError(f"Missing client secrets: {CLIENT_SECRETS_FILE}")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
            creds = flow.run_local_server(port=8090)

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    youtube = build("youtube", "v3", credentials=creds)
    _validate_facts_channel(youtube)
    return youtube


def _search_pexels_videos(keywords: list[str], max_urls: int = 40) -> list[str]:
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        raise ValueError("PEXELS_API_KEY is required")

    headers = {"Authorization": key}
    urls: list[str] = []
    avoid_terms = {"dark", "night", "moody", "black"}

    def _is_bright(avg_color: str) -> bool:
        if not avg_color or not avg_color.startswith("#") or len(avg_color) != 7:
            return True
        try:
            r = int(avg_color[1:3], 16)
            g = int(avg_color[3:5], 16)
            b = int(avg_color[5:7], 16)
            # Perceived luminance heuristic.
            luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
            return luminance >= 90
        except Exception:
            return True

    for kw in keywords[:MAX_SEARCH_KEYWORDS]:
        params = {
            "query": kw,
            "orientation": "portrait",
            "per_page": 10,
            "page": random.randint(1, 5),
            "locale": "en-US",
        }
        try:
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params=params,
                timeout=SEARCH_TIMEOUT_SEC,
            )
        except requests.RequestException as exc:
            logger.warning("Pexels query failed for '%s': %s", kw, exc)
            continue
        if resp.status_code != 200:
            continue
        for video in resp.json().get("videos", []):
            tags_text = " ".join(t.get("title", "") for t in video.get("tags", []))
            if any(t in tags_text.lower() for t in avoid_terms):
                continue
            if not _is_bright(video.get("avg_color", "")):
                continue
            files = video.get("video_files", [])
            files = sorted(files, key=lambda f: (f.get("height", 0), f.get("width", 0)), reverse=True)
            picked = None
            for vf in files:
                h = int(vf.get("height", 0) or 0)
                w = int(vf.get("width", 0) or 0)
                if w <= 0 or h <= 0:
                    continue
                if h >= w and MIN_SOURCE_HEIGHT <= h <= MAX_SOURCE_HEIGHT:
                    picked = vf
                    break
            if picked and picked.get("link"):
                urls.append(picked["link"])

            if len(urls) >= max_urls:
                break
        if len(urls) >= max_urls:
            break

    unique_urls = list(dict.fromkeys(urls))
    return unique_urls


def _search_pixabay_videos(keywords: list[str], max_urls: int = 40) -> list[str]:
    key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not key:
        logger.warning("PIXABAY_API_KEY not set; skipping Pixabay fallback")
        return []

    urls: list[str] = []
    for kw in keywords[:MAX_SEARCH_KEYWORDS]:
        params = {
            "key": key,
            "q": kw,
            "video_type": "film",
            "orientation": "vertical",
            "per_page": 10,
        }
        try:
            resp = requests.get("https://pixabay.com/api/videos/", params=params, timeout=SEARCH_TIMEOUT_SEC)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Pixabay search failed for '%s': %s", kw, exc)
            continue
        for hit in resp.json().get("hits", []):
            videos = hit.get("videos", {})
            best_url = None
            best_h = -1
            for _, value in videos.items():
                w = int(value.get("width", 0) or 0)
                h = int(value.get("height", 0) or 0)
                if w <= 0 or h <= 0:
                    continue
                if h < w:
                    continue
                if not (MIN_SOURCE_HEIGHT <= h <= MAX_SOURCE_HEIGHT):
                    continue
                if h > best_h:
                    best_h = h
                    best_url = value.get("url")
            if best_url:
                urls.append(best_url)
        if len(urls) >= max_urls:
            break

    return list(dict.fromkeys(urls))


def _download(url: str, path: Path) -> None:
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            with requests.get(url, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                content_length = int(resp.headers.get("Content-Length") or 0)
                if content_length > MAX_DOWNLOAD_BYTES:
                    raise ValueError(
                        f"Source too large ({content_length / (1024 * 1024):.1f}MB > {MAX_DOWNLOAD_BYTES / (1024 * 1024):.0f}MB)"
                    )
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
            return
        except ValueError as exc:
            logger.info("Skipping oversized clip: %s — %s", url, exc)
            if path.exists():
                path.unlink(missing_ok=True)
            raise
        except (requests.ConnectionError, requests.Timeout, OSError) as exc:
            if attempt == max_retries:
                error_logger.error("Download failed after %d attempts: %s — %s", max_retries, url, exc)
                raise
            wait = 2 ** attempt
            logger.warning("Download attempt %d/%d failed (%s); retrying in %ds", attempt, max_retries, exc, wait)
            time.sleep(wait)


def _generate_bgm(duration: float, out_path: Path) -> None:
    # Generated tone-based track is copyright-free and always available.
    cmd = [
        _ffmpeg(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=523:sample_rate=44100:duration={duration}",
        "-filter:a",
        "volume=0.25",
        str(out_path),
    ]
    _run(cmd)


def _compose_vertical_track(clips: list[Path], clip_duration: int, out_path: Path) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        concat_list = Path(tf.name)
        for clip in clips:
            safe = str(clip.resolve()).replace("'", "''")
            tf.write(f"file '{safe}'\n")

    try:
        cmd = [
            _ffmpeg(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-vf",
            (
                f"fps={config_facts.FPS},"
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920"
            ),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            str(out_path),
        ]
        _run(cmd)
    finally:
        try:
            concat_list.unlink()
        except Exception:
            pass


def _slice_clip(input_path: Path, out_path: Path, seconds: float) -> None:
    cmd = [
        _ffmpeg(),
        "-y",
        "-i",
        str(input_path),
        "-t",
        f"{seconds:.2f}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        str(out_path),
    ]
    _run(cmd)


def _trim_to_duration(input_video: Path, out_path: Path, duration: float) -> None:
    cmd = [
        _ffmpeg(),
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(input_video),
        "-t",
        f"{duration:.2f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-an",
        str(out_path),
    ]
    _run(cmd)


def _apply_subtitles(video_path: Path, ass_path: Path, out_path: Path) -> None:
    subtitle_path = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
    cmd = [
        _ffmpeg(),
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"ass='{subtitle_path}'",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-an",
        str(out_path),
    ]
    _run(cmd)


def _mix_audio(video_path: Path, narration_mp3: Path, bgm_mp3: Path, out_path: Path, duration: float) -> None:
    cmd = [
        _ffmpeg(),
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(narration_mp3),
        "-stream_loop",
        "-1",
        "-i",
        str(bgm_mp3),
        "-filter_complex",
        "[1:a]volume=1.0[a1];[2:a]volume=0.2[a2];[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map",
        "0:v:0",
        "-map",
        "[aout]",
        "-t",
        f"{duration:.2f}",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    _run(cmd)


def _build_script(topic: str | None = None, excluded_topics: set[str] | None = None) -> dict[str, Any]:
    learned_topic_style = getattr(config_facts, "LEARNED_TOPIC_STYLE", config_facts.TOPIC_STYLE)
    learned_topics = [t.strip() for t in learned_topic_style.split(",") if t.strip()]
    fallback_topics = [
        "space mysteries",
        "human body facts",
        "animal records",
        "nature extremes",
        "science surprises",
    ]
    source_topics = learned_topics or fallback_topics
    excluded_topics = excluded_topics or set()
    available_topics = [candidate for candidate in source_topics if _normalize_topic(candidate) not in excluded_topics]
    selected_topic = topic or random.choice(available_topics or source_topics)

    try:
        import anthropic

        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        client = anthropic.Anthropic(api_key=key)
        avoided_topics = ", ".join(sorted(excluded_topics)) if excluded_topics else "N/A"
        prompt = f"""Write a YouTube Shorts narration for channel '{config_facts.CHANNEL_NAME}'.

Rules:
- 100 to 130 words
- Start with: Did you know that...
- 3 to 50 sec: include 3 to 5 related facts
- End with exactly: {FACTS_CTA}
- Keep sentences short and fast paced
- Include concrete numbers/statistics
- Topic focus: {selected_topic}
- Avoid repeating any recent topic phrased like: {avoided_topics}
- Tone: {config_facts.TONE}
- Return strict JSON keys: title, script, topic
"""
        model_candidates = list(dict.fromkeys(getattr(config_facts, "ANTHROPIC_MODELS", [])))
        if not model_candidates:
            model_candidates = ["claude-3-5-sonnet-latest", "claude-3-haiku-20240307"]

        last_exc: Exception | None = None
        message = None
        for model_name in model_candidates:
            try:
                message = client.messages.create(
                    model=model_name,
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}],
                )
                logger.info("Facts script generated with model: %s", model_name)
                break
            except Exception as model_exc:
                last_exc = model_exc
                logger.warning("Anthropic model failed (%s): %s", model_name, model_exc)

        if message is None:
            raise RuntimeError(f"All configured Anthropic models failed: {last_exc}")

        text = message.content[0].text.strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        data = json.loads(text)
        script = data.get("script", "")
        if not script.lower().startswith("did you know that"):
            script = "Did you know that " + script[0].lower() + script[1:]
        if FACTS_CTA not in script:
            script = script.rstrip() + f" {FACTS_CTA}"
        words = script.split()
        if len(words) < config_facts.SCRIPT_MIN_WORDS:
            extra = " Earth's core is about 5,200 C, hotter than some stars."
            while len(words) < config_facts.SCRIPT_MIN_WORDS:
                script += extra
                words = script.split()
        if len(words) > config_facts.SCRIPT_MAX_WORDS:
            script = " ".join(words[: config_facts.SCRIPT_MAX_WORDS - 5]) + f" {FACTS_CTA}"

        title = data.get("title", f"Did You Know: {selected_topic.title()} Facts")
        return {"title": title, "script": script, "topic": data.get("topic", selected_topic)}
    except Exception as exc:
        logger.warning("Falling back to template script: %s", exc)

    script = (
        "Did you know that your brain uses about 20% of your oxygen? "
        "Your heart beats around 100,000 times every day. "
        "A single lightning bolt can heat air to 30,000 C, five times hotter than the Sun surface. "
        "Octopuses have three hearts and around 500 million neurons. "
        "Only 8 minutes and 20 seconds after leaving the Sun, light reaches Earth. "
        f"{FACTS_CTA}"
    )
    return {
        "title": f"Did You Know: {selected_topic.title()} In 59 Seconds #Shorts",
        "script": script,
        "topic": selected_topic,
    }


async def _edge_tts_save(text: str, output_path: Path) -> list[dict]:
    import edge_tts

    communicator = edge_tts.Communicate(
        text=text,
        voice=config_facts.VOICE,
        rate=config_facts.VOICE_RATE,
        pitch=config_facts.VOICE_PITCH,
    )
    word_timings: list[dict] = []
    sentence_timings: list[dict] = []

    with open(output_path, "wb") as audio_file:
        async for chunk in communicator.stream():
            chunk_type = chunk.get("type")
            if chunk_type == "audio":
                audio_file.write(chunk["data"])
            elif chunk_type == "WordBoundary":
                text_piece = str(chunk.get("text", "")).strip()
                if not text_piece:
                    continue
                offset = int(chunk.get("offset", 0))
                duration = int(chunk.get("duration", 0))
                start_sec = offset / 10_000_000
                end_sec = (offset + duration) / 10_000_000
                word_timings.append({"text": text_piece, "start": start_sec, "end": end_sec})
            elif chunk_type == "SentenceBoundary":
                text_piece = str(chunk.get("text", "")).strip()
                if not text_piece:
                    continue
                offset = int(chunk.get("offset", 0))
                duration = int(chunk.get("duration", 0))
                start_sec = offset / 10_000_000
                end_sec = (offset + duration) / 10_000_000
                sentence_timings.append({"text": text_piece, "start": start_sec, "end": end_sec})

    if word_timings:
        return _group_word_timings_to_captions(word_timings, max_words=FACTS_SUBTITLE_MAX_WORDS)

    if sentence_timings:
        fallback_captions: list[dict] = []
        for sentence in sentence_timings:
            fallback_captions.extend(
                _chunk_timed_text(
                    text=str(sentence.get("text", "")),
                    start=float(sentence.get("start", 0.0)),
                    end=float(sentence.get("end", 0.0)),
                    max_words=FACTS_SUBTITLE_MAX_WORDS,
                )
            )
        return fallback_captions

    return []


def _generate_audio(script_text: str, out_path: Path) -> list[dict]:
    return asyncio.run(_edge_tts_save(script_text, out_path))


def _keywords_from_topic(topic: str) -> list[str]:
    base = [w for w in re.findall(r"[A-Za-z]{3,}", topic.lower())]
    base.extend(["science", "nature", "space", "colorful", "bright", "macro"])
    unique = list(dict.fromkeys(base))
    return unique[:MAX_SEARCH_KEYWORDS]


def _build_description() -> str:
    hooks = (
        "Amazing facts you can learn in under 60 seconds. "
        "Subscribe for daily science, space, and nature surprises. "
        "Comment your favorite fact for the next video."
    )
    return hooks + "\n\n" + " ".join(_active_facts_hashtags())


def _strip_cta(script_text: str) -> str:
    text = script_text.strip()
    if text.endswith(FACTS_CTA):
        return text[: -len(FACTS_CTA)].rstrip(" .!?")
    return text


def _ensure_cta(script_text: str) -> str:
    base = _strip_cta(script_text)
    if not base:
        return FACTS_CTA
    end = base[-1]
    if end not in ".!?":
        base += "."
    return f"{base} {FACTS_CTA}"


def _extend_script_for_duration(script_text: str, min_duration_sec: float, words_per_sec: float = 2.8) -> str:
    target_words = max(1, int(math.ceil(min_duration_sec * words_per_sec)))
    body = _strip_cta(script_text)
    words = body.split()

    if len(words) >= target_words:
        return _ensure_cta(body)

    filler_sentences = [
        "Your body also creates around twenty-five million new cells every second.",
        "Scientists estimate that a single teaspoon of neutron-star matter would weigh billions of tons on Earth.",
        "Lightning can superheat air to nearly thirty thousand degrees Celsius in a fraction of a second.",
        "Some deep-sea creatures survive under pressure hundreds of times stronger than at sea level.",
        "Even tiny changes in temperature can affect how fast chemical reactions happen inside living cells.",
    ]

    sentence_index = 0
    while len(words) < target_words and sentence_index < 12:
        sentence = filler_sentences[sentence_index % len(filler_sentences)]
        body = f"{body} {sentence}".strip()
        words = body.split()
        sentence_index += 1

    return _ensure_cta(body)


def _shorten_script_for_duration(script_text: str, max_duration_sec: float, words_per_sec: float = 2.8) -> str:
    target_words = max(12, int(math.floor(max_duration_sec * max(1.5, words_per_sec))))
    body = _strip_cta(script_text)
    sentences = _split_sentences(body)

    if not sentences:
        words = body.split()
        shortened = " ".join(words[:target_words]).strip()
        return _ensure_cta(shortened)

    kept = sentences[:]
    while len(" ".join(kept).split()) > target_words and len(kept) > 2:
        kept.pop()

    reduced_body = " ".join(kept).strip()
    reduced_words = reduced_body.split()
    if len(reduced_words) > target_words:
        reduced_body = " ".join(reduced_words[:target_words]).strip()

    return _ensure_cta(reduced_body)


def _upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    publish_at: datetime | None = None,
) -> str:
    youtube = _authenticate_youtube()
    status_payload: dict[str, Any] = {
        "privacyStatus": config_facts.DEFAULT_PRIVACY,
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
        "selfDeclaredAsModifiedContent": True,
    }

    if publish_at is not None:
        publish_utc = publish_at.astimezone(timezone.utc).replace(microsecond=0)
        status_payload["privacyStatus"] = "private"
        status_payload["publishAt"] = publish_utc.isoformat().replace("+00:00", "Z")

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "categoryId": "27",
            "defaultLanguage": config_facts.LANGUAGE,
            "tags": [t.lstrip("#") for t in tags],
        },
        "status": status_payload,
    }

    status = body.setdefault("status", {})
    status["containsSyntheticMedia"] = True
    status["selfDeclaredAsModifiedContent"] = True

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=2 * 1024 * 1024)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = req.next_chunk()

    return response["id"]


def _append_registry(entry: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _normalize_title(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"#\w+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_topic(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _recent_registry_topics(limit: int = RECENT_TOPIC_AVOID_COUNT) -> list[str]:
    if limit <= 0 or not REGISTRY_PATH.exists():
        return []

    topics: list[str] = []
    seen: set[str] = set()
    for line in reversed(REGISTRY_PATH.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue

        normalized = _normalize_topic(str(item.get("topic", "")))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        topics.append(normalized)
        if len(topics) >= limit:
            break

    return topics


def _find_registry_duplicate(title: str, lookback_days: int = FACTS_DUPLICATE_LOOKBACK_DAYS) -> dict[str, Any] | None:
    normalized = _normalize_title(title)
    if not normalized or not REGISTRY_PATH.exists():
        return None

    threshold = datetime.now() - timedelta(days=lookback_days)
    for line in reversed(REGISTRY_PATH.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue

        created_at = str(item.get("created_at", ""))
        try:
            created_dt = datetime.fromisoformat(created_at)
            if created_dt < threshold:
                break
        except Exception:
            pass

        existing_title = str(item.get("title", ""))
        if _normalize_title(existing_title) == normalized:
            return item
    return None


def _find_youtube_duplicate_id(youtube: Any, title: str) -> str | None:
    normalized = _normalize_title(title)
    if not normalized:
        return None

    request = youtube.search().list(
        part="snippet",
        forMine=True,
        type="video",
        maxResults=50,
        order="date",
    )

    while request:
        response = request.execute()
        for item in response.get("items", []):
            snippet = item.get("snippet") or {}
            existing_title = str(snippet.get("title", ""))
            if _normalize_title(existing_title) == normalized:
                return (item.get("id") or {}).get("videoId")

        request = youtube.search().list_next(request, response)

    return None


def _ensure_not_duplicate_title(youtube: Any, title: str) -> tuple[bool, str]:
    reg_dup = _find_registry_duplicate(title)
    if reg_dup:
        return False, f"registry duplicate: {reg_dup.get('video_id', 'unknown')}"

    yt_dup = _find_youtube_duplicate_id(youtube, title)
    if yt_dup:
        return False, f"youtube duplicate: {yt_dup}"

    return True, ""


def _load_today_posts() -> list[dict[str, Any]]:
    today = date.today().isoformat()
    if not REGISTRY_PATH.exists():
        return []

    rows: list[dict[str, Any]] = []
    for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue

        created_at = str(item.get("created_at", ""))
        if created_at.startswith(today):
            rows.append(item)
    return rows


def run_facts_short(topic: str | None = None, publish_after_hours: float | None = None) -> dict[str, Any]:
    started = datetime.now()
    logger.info("Facts short generation started (topic=%s)", topic or "random")

    youtube = _authenticate_youtube()
    script_data: dict[str, Any] | None = None
    title = ""
    script_text = ""
    topic_used = ""
    duplicate_reason = ""
    recent_topics = set(_recent_registry_topics()) if topic is None else set()

    for attempt in range(1, FACTS_SCRIPT_ATTEMPTS + 1):
        script_data = _build_script(topic=topic, excluded_topics=recent_topics)
        title = str(script_data.get("title", "")).strip()
        script_text = str(script_data.get("script", "")).strip()
        topic_used = str(script_data.get("topic", "")).strip()

        normalized_topic_used = _normalize_topic(topic_used)
        if topic is None and normalized_topic_used and normalized_topic_used in recent_topics:
            duplicate_reason = f"recent topic duplicate: {topic_used}"
            logger.warning(
                "Duplicate FACTS topic candidate rejected (attempt %d/%d): %s",
                attempt,
                FACTS_SCRIPT_ATTEMPTS,
                topic_used,
            )
            continue

        title = _optimize_title_for_growth(title)
        ok, reason = _ensure_not_duplicate_title(youtube, title)
        if ok:
            duplicate_reason = ""
            break

        duplicate_reason = reason
        logger.warning("Duplicate FACTS title candidate rejected (attempt %d/%d): %s | %s", attempt, FACTS_SCRIPT_ATTEMPTS, title, reason)

    if duplicate_reason:
        raise RuntimeError(f"Could not generate non-duplicate FACTS video title after {FACTS_SCRIPT_ATTEMPTS} attempts: {duplicate_reason}")

    script_text = _extend_script_for_duration(script_text, config_facts.DURATION_MIN_SEC)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = _safe_name(title)

    audio_path = FACTS_DIR / f"{timestamp}_{safe}_narration.mp3"
    captions = _generate_audio(script_text, audio_path)
    audio_duration = _ffprobe_duration(audio_path)

    if audio_duration < (config_facts.DURATION_MIN_SEC - 0.5):
        script_text = _extend_script_for_duration(script_text, config_facts.DURATION_MIN_SEC + 4)
        captions = _generate_audio(script_text, audio_path)
        audio_duration = _ffprobe_duration(audio_path)

    max_duration_adjustments = 4
    adjust_attempt = 0
    while audio_duration > (config_facts.DURATION_MAX_SEC - 0.1) and adjust_attempt < max_duration_adjustments:
        adjust_attempt += 1
        estimated_words_per_sec = max(2.0, len(_strip_cta(script_text).split()) / max(1.0, audio_duration))
        script_text = _shorten_script_for_duration(
            script_text,
            max_duration_sec=max(1.0, config_facts.DURATION_MAX_SEC - 0.6),
            words_per_sec=estimated_words_per_sec,
        )
        captions = _generate_audio(script_text, audio_path)
        audio_duration = _ffprobe_duration(audio_path)
        logger.info(
            "Shortened FACTS narration to fit duration (attempt %d/%d): %.2fs",
            adjust_attempt,
            max_duration_adjustments,
            audio_duration,
        )

    if audio_duration < (config_facts.DURATION_MIN_SEC - 0.5):
        logger.warning(
            "Narration remains short (%.2fs); using narration duration for final render to keep sync",
            audio_duration,
        )
        target_duration = max(1.0, min(config_facts.DURATION_MAX_SEC, float(audio_duration)))
    else:
        target_duration = max(config_facts.DURATION_MIN_SEC, min(config_facts.DURATION_MAX_SEC, float(audio_duration)))

    if audio_duration > config_facts.DURATION_MAX_SEC:
        raise RuntimeError(
            f"Facts narration still exceeds max duration after shortening ({audio_duration:.2f}s > {config_facts.DURATION_MAX_SEC}s)"
        )

    target_duration = round(target_duration, 2)
    subtitle_duration = max(0.5, min(float(audio_duration), target_duration))

    keywords = _keywords_from_topic(topic_used)
    try:
        clip_urls = _search_pexels_videos(keywords, max_urls=MAX_SEARCH_URLS)
    except Exception as exc:
        error_logger.error("Pexels search failed: %s — falling back to Pixabay", exc)
        logger.warning("Pexels search failed (%s); falling back to Pixabay", exc)
        clip_urls = []

    if len(clip_urls) < config_facts.CLIP_COUNT_MIN:
        logger.info("Not enough Pexels clips (%d); trying Pixabay fallback", len(clip_urls))
        pixabay_urls = _search_pixabay_videos(keywords, max_urls=MAX_SEARCH_URLS)
        clip_urls = list(dict.fromkeys(clip_urls + pixabay_urls))[:MAX_SEARCH_URLS]

    if len(clip_urls) < config_facts.CLIP_COUNT_MIN:
        error_logger.error(
            "Insufficient clips after Pexels+Pixabay: %d found, %d required",
            len(clip_urls), config_facts.CLIP_COUNT_MIN,
        )
        raise RuntimeError(
            f"Not enough clips found from Pexels or Pixabay ({len(clip_urls)} < {config_facts.CLIP_COUNT_MIN})"
        )

    clip_count = min(config_facts.CLIP_COUNT_MAX, max(config_facts.CLIP_COUNT_MIN, math.ceil(target_duration / 3.5)))
    candidate_urls = clip_urls[:]
    random.shuffle(candidate_urls)

    downloaded: list[Path] = []
    while candidate_urls and len(downloaded) < clip_count:
        url = candidate_urls.pop()
        path = FACTS_DIR / f"{timestamp}_{safe}_clip_{len(downloaded) + 1:02d}.mp4"
        try:
            _download(url, path)
        except ValueError:
            # Oversized assets are intentionally skipped.
            continue
        except Exception as exc:
            logger.warning("Clip download failed, trying next source: %s", exc)
            if path.exists():
                path.unlink(missing_ok=True)
            continue

        src_duration = _ffprobe_duration(path)
        if src_duration <= 0 or src_duration > MAX_SOURCE_DURATION_SEC:
            logger.info("Skipping long/invalid clip (%.1fs): %s", src_duration, path.name)
            path.unlink(missing_ok=True)
            continue

        downloaded.append(path)

    if len(downloaded) < config_facts.CLIP_COUNT_MIN:
        error_logger.error(
            "Insufficient valid clips after size/duration filtering: %d found, %d required",
            len(downloaded),
            config_facts.CLIP_COUNT_MIN,
        )
        raise RuntimeError(
            f"Not enough usable clips after filtering ({len(downloaded)} < {config_facts.CLIP_COUNT_MIN})"
        )

    # Enforce per-clip duration of 3-5 seconds before composition.
    sliced: list[Path] = []
    for idx, src in enumerate(downloaded, start=1):
        segment = FACTS_DIR / f"{timestamp}_{safe}_seg_{idx:02d}.mp4"
        clip_seconds = random.uniform(config_facts.CLIP_DURATION_MIN, config_facts.CLIP_DURATION_MAX)
        _slice_clip(src, segment, clip_seconds)
        sliced.append(segment)

    base_track = FACTS_DIR / f"{timestamp}_{safe}_base.mp4"
    _compose_vertical_track(sliced, clip_duration=4, out_path=base_track)

    trimmed_track = FACTS_DIR / f"{timestamp}_{safe}_trim.mp4"
    _trim_to_duration(base_track, trimmed_track, duration=target_duration)

    ass_path = FACTS_DIR / f"{timestamp}_{safe}.ass"
    if captions:
        _build_ass_subtitles_from_captions(captions, duration=subtitle_duration, out_path=ass_path)
    else:
        _build_ass_subtitles(script_text, duration=subtitle_duration, out_path=ass_path)

    captioned = FACTS_DIR / f"{timestamp}_{safe}_captioned.mp4"
    _apply_subtitles(trimmed_track, ass_path, captioned)

    bgm_path = FACTS_DIR / f"{timestamp}_{safe}_bgm.wav"
    _generate_bgm(duration=target_duration, out_path=bgm_path)

    final_video = FACTS_DIR / f"{timestamp}_{safe}_final.mp4"
    _mix_audio(captioned, audio_path, bgm_path, final_video, duration=target_duration)

    description = _build_description()
    ok_final, reason_final = _ensure_not_duplicate_title(youtube, title)
    if not ok_final:
        raise RuntimeError(f"Duplicate detected before upload; aborting post: {reason_final}")

    publish_at: datetime | None = None
    if publish_after_hours is not None and publish_after_hours > 0:
        publish_at = datetime.now(timezone.utc) + timedelta(hours=float(publish_after_hours))

    video_id = _upload_to_youtube(
        video_path=final_video,
        title=title,
        description=description,
        tags=_active_facts_hashtags(),
        publish_at=publish_at,
    )

    entry = {
        "created_at": started.isoformat(timespec="seconds"),
        "video_id": video_id,
        "title": title,
        "topic": topic_used,
        "duration": target_duration,
        "video_path": str(final_video),
        "scheduled_time": datetime.now().strftime("%H:%M"),
        "scheduled_publish_at": publish_at.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if publish_at else "",
        "view_count": 0,
        "containsSyntheticMedia": True,
        "selfDeclaredMadeForKids": False,
    }
    _append_registry(entry)

    logger.info("Facts short upload complete: %s", video_id)
    return entry


def run_facts_batch(count: int = 5) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    # Schedule each video 2 hours apart, starting from now
    for i in range(count):
        try:
            logger.info("Batch upload %s/%s (scheduled +%dh)", i + 1, count, i * 2)
            # Each video is scheduled i*2 hours after now
            results.append(run_facts_short(publish_after_hours=i * 2))
        except Exception as exc:
            logger.exception("facts-run item failed")
            results.append({"ok": False, "error": str(exc), "index": i + 1})
    return results


def generate_schedule(day: date | None = None, preferred_hours: list[int] | None = None) -> list[str]:
    day = day or date.today()
    rng = random.Random(f"{day.isoformat()}-facts")

    learned_hours = getattr(config_facts, "PREFERRED_POST_HOURS", None)
    default_hours = learned_hours if isinstance(learned_hours, list) and learned_hours else [3, 7, 11, 15, 19]
    allowed_hours = preferred_hours[:] if preferred_hours else default_hours
    allowed_hours = [h for h in allowed_hours if 0 <= h <= 23]
    if len(allowed_hours) < 3:
        allowed_hours = [3, 7, 11, 15, 19]

    # Randomize daily post count (3–6) — avoids a fixed "bot-like" cadence
    target_count = rng.randint(3, 6)

    times: list[tuple[int, int]] = []
    attempts = 0
    while len(times) < target_count and attempts < 500:
        attempts += 1
        hour = rng.choice(allowed_hours)
        minute = rng.randint(0, 59)
        candidate = hour * 60 + minute
        if all(abs(candidate - (h * 60 + m)) >= 120 for h, m in times):
            times.append((hour, minute))

    if len(times) < 3:
        # Guaranteed fallback with 2h gaps.
        times = [(3, 12), (11, 18), (19, 14)]

    times_sorted = sorted(times)
    return [f"{h:02d}:{m:02d}" for h, m in times_sorted]


def today_schedule() -> dict[str, Any]:
    today_str = date.today().isoformat()
    preferred = getattr(config_facts, "PREFERRED_POST_HOURS", [3, 7, 11, 15, 19])
    payload = {
        "date": today_str,
        "times": generate_schedule(date.today(), preferred_hours=preferred),
        "rules": {
            "min_interval_minutes": 120,
            "window": "03:00-19:59",
            "no_consecutive_posts": True,
        },
    }

    if SCHEDULE_PATH.exists():
        try:
            current = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
            if current.get("date") == today_str:
                return current
        except Exception:
            pass

    SCHEDULE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Generated new daily schedule: %s", payload["times"])
    return payload


def run_daily_autonomous_cycle() -> dict[str, Any]:
    logger.info("Starting autonomous daily facts cycle")
    cycle_result: dict[str, Any] = {"started_at": datetime.now().isoformat(timespec="seconds")}

    try:
        import facts_brain

        cycle_result["analysis"] = facts_brain.run_daily_analysis_safe()
    except Exception as exc:
        cycle_result["analysis"] = {"ok": False, "error": str(exc)}

    schedule_payload = today_schedule()
    cycle_result["schedule"] = schedule_payload
    cycle_result["errors"] = []

    posted: list[dict[str, Any]] = []
    now = datetime.now()

    today_posts = _load_today_posts()
    due_now = 0
    for t in schedule_payload["times"]:
        h, m = map(int, t.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            due_now += 1

    already_posted = len(today_posts)
    missed_count = max(0, due_now - already_posted)
    catchup_runs = 1 if missed_count > 0 else 0
    cycle_result["catchup"] = {
        "due_now": due_now,
        "already_posted_today": already_posted,
        "missed_count": missed_count,
        "executed_now": catchup_runs,
    }

    if catchup_runs:
        jitter = random.randint(POST_JITTER_MIN_SEC, POST_JITTER_MAX_SEC)
        logger.info("Missed scheduled Facts upload(s) detected (%d). Running 1 catch-up in %ds", missed_count, jitter)
        time.sleep(jitter)
        try:
            posted.append(run_facts_short())
        except Exception as exc:
            logger.exception("Catch-up post failed")
            cycle_result["errors"].append({"phase": "catchup", "error": str(exc)})
            try:
                logger.info("Retrying catch-up post once after failure")
                posted.append(run_facts_short())
            except Exception as retry_exc:
                logger.exception("Catch-up retry failed")
                posted.append({"ok": False, "phase": "catchup", "error": str(retry_exc)})
                cycle_result["errors"].append({"phase": "catchup-retry", "error": str(retry_exc)})

    for t in schedule_payload["times"]:
        h, m = map(int, t.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= datetime.now():
            continue

        wait_sec = (target - datetime.now()).total_seconds()
        if wait_sec > 0:
            logger.info("Waiting %.1f sec until scheduled upload %s", wait_sec, t)
            time.sleep(wait_sec)

        jitter = random.randint(POST_JITTER_MIN_SEC, POST_JITTER_MAX_SEC)
        logger.info("Applying anti-pattern jitter before upload: %ds", jitter)
        time.sleep(jitter)

        try:
            posted.append(run_facts_short())
        except Exception as exc:
            logger.exception("Scheduled post failed at %s", t)
            cycle_result["errors"].append({"phase": "scheduled", "time": t, "error": str(exc)})
            try:
                logger.info("Retrying scheduled post once at %s", t)
                posted.append(run_facts_short())
            except Exception as retry_exc:
                logger.exception("Retry failed at %s", t)
                posted.append({"ok": False, "time": t, "error": str(retry_exc)})
                cycle_result["errors"].append({"phase": "scheduled-retry", "time": t, "error": str(retry_exc)})

    cycle_result["posted"] = posted
    cycle_result["finished_at"] = datetime.now().isoformat(timespec="seconds")
    CYCLE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CYCLE_REPORT_PATH.write_text(json.dumps(cycle_result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Autonomous daily cycle finished")
    return cycle_result


def setup_windows_scheduler() -> dict[str, Any]:
    task_name = config_facts.FACTS_SCHEDULER_TASK_NAME
    start_time = config_facts.FACTS_SCHEDULER_START_TIME
    workdir = str(ROOT)
    py_cmd = "py"
    command = f"{py_cmd} main.py facts-scheduler-execute"

    primary_ps = f"""
$Action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c cd /d "{workdir}" && {command}'
$Trigger = New-ScheduledTaskTrigger -Daily -At {start_time}
$Settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 20) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15)
$Settings.DisallowStartIfOnBatteries = $false
$Settings.StopIfGoingOnBatteries = $false
$principalUser = "{os.getenv('USERDOMAIN', '')}\\{os.getenv('USERNAME', '')}".Trim('\\')
if (-not $principalUser) {{
    $principalUser = $env:UserName
}}
$Principal = New-ScheduledTaskPrincipal -UserId $principalUser -LogonType S4U -RunLevel Highest
Register-ScheduledTask -TaskName '{task_name}' -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
""".strip()

    fallback_ps = f"""
$Action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c cd /d "{workdir}" && {command}'
$Trigger = New-ScheduledTaskTrigger -Daily -At {start_time}
$Settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -MultipleInstances IgnoreNew
$Settings.DisallowStartIfOnBatteries = $false
$Settings.StopIfGoingOnBatteries = $false
Register-ScheduledTask -TaskName '{task_name}' -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
""".strip()

    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", primary_ps],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("Primary scheduler registration failed, trying fallback mode: %s", result.stderr.strip())
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", fallback_ps],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Failed to register scheduled task")

    logger.info("Windows task scheduler registered: %s at %s", task_name, start_time)
    return {"ok": True, "task": task_name, "start_time": start_time}


def scheduler_status() -> dict[str, Any]:
    payload = today_schedule()
    task_name = config_facts.FACTS_SCHEDULER_TASK_NAME
    query = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name],
        capture_output=True,
        text=True,
    )
    payload["task_registered"] = query.returncode == 0
    return payload


def remove_windows_scheduler() -> dict[str, Any]:
    task_name = config_facts.FACTS_SCHEDULER_TASK_NAME
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", task_name, "/F"],
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0
    if ok:
        logger.info("Removed scheduled task: %s", task_name)
    else:
        logger.warning("Failed to remove task %s: %s", task_name, result.stderr.strip())
    return {"ok": ok, "task": task_name, "stderr": result.stderr.strip()}
