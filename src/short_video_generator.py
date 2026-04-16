#!/usr/bin/env python3
"""
Generate short-form video for TikTok/Instagram Reels with:
- Edge TTS audio
- Pexels vertical video clips
- Embedded captions
"""

import os
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional
import logging
import random
import math

from src.utils import setup_logger, PROJECT_ROOT, get_all_topics
from src.short_script_generator import ShortScriptGenerator, SHORTS_DIR

logger = setup_logger("short_video_generator")

SHORTS_DIR.mkdir(parents=True, exist_ok=True)
PEXELS_HISTORY_FILE = SHORTS_DIR / "used_pexels_ids.json"

SHORT_TARGET_DURATION = 60.0
SHORT_CLIP_MIN_COUNT = 8
SHORT_CLIP_MAX_COUNT = 12
SHORT_CLIP_TARGET_SECONDS = 6.0

# Edge TTS Settings
EDGE_TTS_VOICE = "en-US-AriaNeural"  # Professional female voice
EDGE_TTS_RATE = "+10%"  # 10% faster for engaging shorts
SHORT_SUBTITLE_MAX_WORDS = 5
SHORT_SUBTITLE_FONT_SIZE = 65  # ASS units at PlayResY=1920 (65px on 1920px tall video)
SHORT_TOPIC_AVOID_COUNT = 20


def _ffmpeg_exe() -> str:
    """Get ffmpeg executable path."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _group_word_timings_to_captions(word_timings: list[dict], max_words: int = SHORT_SUBTITLE_MAX_WORDS) -> list[dict]:
    """Group Edge TTS word-level timings into short subtitle caption chunks."""
    if not word_timings:
        return []

    captions: list[dict] = []
    for i in range(0, len(word_timings), max_words):
        chunk = word_timings[i:i + max_words]
        if not chunk:
            continue
        text_chunk = " ".join(str(item.get("text", "")).strip() for item in chunk).strip()
        if not text_chunk:
            continue

        start_sec = float(chunk[0].get("start", 0.0))
        end_sec = float(chunk[-1].get("end", start_sec))
        if end_sec <= start_sec:
            end_sec = start_sec + 0.05

        captions.append({
            "text": text_chunk,
            "start": start_sec,
            "end": end_sec,
        })

    return captions


def generate_audio_edge_tts(text: str, output_audio: Path) -> tuple[bool, list[dict]]:
    """Generate audio using Edge TTS (Windows built-in).
    
    Args:
        text: Speech text
        output_audio: Path to save MP3 audio
        
    Returns:
        (success, captions) where captions are word-timed subtitle chunks
    """
    try:
        import edge_tts
        import asyncio

        async def tts():
            communicator = edge_tts.Communicate(text=text, voice=EDGE_TTS_VOICE, rate=EDGE_TTS_RATE)
            word_timings: list[dict] = []
            sentence_timings: list[dict] = []

            with open(output_audio, "wb") as audio_file:
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
                        word_timings.append(
                            {
                                "text": text_piece,
                                "start": start_sec,
                                "end": end_sec,
                            }
                        )
                    elif chunk_type == "SentenceBoundary":
                        text_piece = str(chunk.get("text", "")).strip()
                        if not text_piece:
                            continue
                        offset = int(chunk.get("offset", 0))
                        duration = int(chunk.get("duration", 0))
                        start_sec = offset / 10_000_000
                        end_sec = (offset + duration) / 10_000_000
                        sentence_timings.append(
                            {
                                "text": text_piece,
                                "start": start_sec,
                                "end": end_sec,
                            }
                        )

            if word_timings:
                return _group_word_timings_to_captions(word_timings, max_words=SHORT_SUBTITLE_MAX_WORDS)

            if sentence_timings:
                captions: list[dict] = []
                for sentence in sentence_timings:
                    captions.extend(
                        _chunk_text_for_shorts(
                            sentence["text"],
                            start=float(sentence["start"]),
                            end=float(sentence["end"]),
                            max_words=SHORT_SUBTITLE_MAX_WORDS,
                        )
                    )
                return captions

            return []

        captions = asyncio.run(tts())
        logger.info(f"✓ Audio generated: {output_audio.name}")
        return True, captions
    except ImportError:
        logger.error("edge_tts not installed. Install with: pip install edge-tts")
        return False, []
    except Exception as e:
        logger.error(f"Edge TTS failed: {e}")
        return False, []


def _contains_japanese(text: str) -> bool:
    import re
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text or ""))


def _normalize_topic(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _recent_shorts_topics(limit: int = SHORT_TOPIC_AVOID_COUNT) -> set[str]:
    from src.shorts_uploader import AIJAPAN_SHORTS_REGISTRY

    recent: set[str] = set()
    if not AIJAPAN_SHORTS_REGISTRY.exists():
        return recent

    try:
        lines = AIJAPAN_SHORTS_REGISTRY.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                topic = str(json.loads(line).get("topic", ""))
            except Exception:
                continue
            normalized = _normalize_topic(topic)
            if not normalized:
                continue
            recent.add(normalized)
            if len(recent) >= limit:
                break
    except Exception:
        return set()

    return recent


def _load_used_pexels_ids() -> list[int]:
    """Load previously used Pexels video IDs to reduce reuse across runs."""
    if not PEXELS_HISTORY_FILE.exists():
        return []
    try:
        with open(PEXELS_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [int(x) for x in data if str(x).isdigit()]
    except Exception:
        pass
    return []


def _save_used_pexels_ids(ids: list[int]) -> None:
    """Persist recently used Pexels IDs (bounded history)."""
    PEXELS_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    bounded = ids[-500:]
    with open(PEXELS_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(bounded, f, ensure_ascii=False, indent=2)


def _recommended_clip_count(target_duration: float = SHORT_TARGET_DURATION) -> int:
    """Recommended clip count for shorts: dynamic but bounded for speed/variety balance."""
    estimated = int(round(target_duration / SHORT_CLIP_TARGET_SECONDS))
    return max(SHORT_CLIP_MIN_COUNT, min(SHORT_CLIP_MAX_COUNT, estimated))


def _pick_best_vertical_file(video_files: list[dict]) -> Optional[dict]:
    """Pick the best portrait clip candidate from Pexels video_files."""
    portrait_candidates = [
        vf for vf in video_files
        if vf.get("width", 0) <= vf.get("height", 0)
    ]

    ranked = sorted(
        portrait_candidates or video_files,
        key=lambda vf: (vf.get("height", 0), vf.get("width", 0)),
        reverse=True,
    )
    return ranked[0] if ranked else None


def _search_pexels_candidates(query: str, api_key: str, per_page: int = 10) -> list[dict]:
    """Search Pexels and return normalized vertical video candidates."""
    import requests

    search_url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "per_page": per_page,
        "orientation": "portrait",
    }

    resp = requests.get(search_url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    candidates = []
    for video in data.get("videos", []):
        best_file = _pick_best_vertical_file(video.get("video_files", []))
        if not best_file or not best_file.get("link"):
            continue
        candidates.append(
            {
                "id": int(video.get("id", 0)),
                "duration": float(video.get("duration", 10) or 10),
                "link": best_file["link"],
            }
        )
    return candidates


def _download_pexels_clip(url: str, output_path: Path) -> bool:
    """Download one Pexels clip."""
    try:
        import requests

        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        logger.warning(f"Clip download failed: {e}")
        return False


def _compose_clips_to_background(
    clips: list[dict],
    output_video: Path,
    target_duration: float,
) -> bool:
    """Compose multiple clips into one vertical background video."""
    if not clips:
        return False

    try:
        ffmpeg = _ffmpeg_exe()
        per_clip = max(4.0, target_duration / max(1, len(clips)))

        cmd = [ffmpeg, "-y"]
        filter_parts = []

        for index, clip in enumerate(clips):
            clip_duration = float(clip.get("duration", per_clip) or per_clip)
            max_start = max(0.0, clip_duration - per_clip)
            start_at = random.uniform(0, max_start) if max_start > 0 else 0.0

            cmd += ["-ss", f"{start_at:.2f}", "-t", f"{per_clip:.2f}", "-i", str(clip["path"])]
            filter_parts.append(
                f"[{index}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,setsar=1,trim=duration={per_clip:.2f},setpts=PTS-STARTPTS[v{index}]"
            )

        if len(clips) == 1:
            filter_complex = f"{filter_parts[0]};[v0]format=yuv420p[v]"
        else:
            concat_inputs = "".join(f"[v{i}]" for i in range(len(clips)))
            filter_complex = ";".join(filter_parts) + f";{concat_inputs}concat=n={len(clips)}:v=1:a=0[v]"

        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-an",
            "-t", str(target_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-movflags", "+faststart",
            str(output_video),
        ]

        # Use Popen.wait() instead of subprocess.run(capture_output=True, timeout=...)
        # to avoid a Python 3.14 threading bug where join(timeout) raises KeyboardInterrupt.
        with subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as proc:
            try:
                returncode = proc.wait(timeout=420)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise RuntimeError("ffmpeg multi-clip composition timed out after 7 minutes")
        
        if returncode != 0:
            raise RuntimeError(f"ffmpeg compose failed with exit code {returncode}")

        size_mb = output_video.stat().st_size / 1_048_576
        logger.info(f"✓ Multi-clip background composed: {output_video.name} ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        logger.error(f"Multi-clip compose failed: {e}")
        return False


def get_pexels_vertical_video(keyword: str, output_video: Path, clip_count: Optional[int] = None) -> bool:
    """Download and compose multiple vertical clips from Pexels for richer shorts visuals."""
    try:
        desired_clip_count = clip_count or _recommended_clip_count(SHORT_TARGET_DURATION)

        api_key = os.getenv("PEXELS_API_KEY")
        if not api_key:
            logger.error("PEXELS_API_KEY not set in .env")
            return False

        query_parts = [part.strip() for part in keyword.split("|") if part.strip()]
        if not query_parts:
            query_parts = ["Japan culture"]

        logger.info(f"Searching Pexels for diverse clips: {' | '.join(query_parts)}")

        candidates: list[dict] = []
        seen_ids: set[int] = set()
        for query in query_parts[:3]:
            for item in _search_pexels_candidates(query, api_key=api_key, per_page=18):
                candidate_id = item.get("id", 0)
                if candidate_id and candidate_id not in seen_ids:
                    candidates.append(item)
                    seen_ids.add(candidate_id)

        if not candidates:
            logger.warning(f"No videos found for queries: {query_parts}")
            return False

        used_ids_list = _load_used_pexels_ids()
        used_ids = set(used_ids_list)

        fresh_candidates = [c for c in candidates if c.get("id") not in used_ids]
        selection_pool = fresh_candidates if len(fresh_candidates) >= min(3, desired_clip_count) else candidates

        selected: list[dict] = []
        chosen_count = min(desired_clip_count, len(selection_pool))
        if chosen_count > 0:
            selected = random.sample(selection_pool, chosen_count)

        if not selected:
            return False

        logger.info(f"Selected {len(selected)} unique clips (target={desired_clip_count})")

        downloaded = []
        temp_files = []
        for i, item in enumerate(selected, start=1):
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
                temp_file = Path(tf.name)
            temp_files.append(temp_file)
            logger.info(f"Downloading clip {i}/{len(selected)}: {item.get('link')}")
            if _download_pexels_clip(item["link"], temp_file):
                downloaded.append({"path": temp_file, "duration": item.get("duration", 10), "id": item.get("id")})

        if not downloaded:
            logger.error("Failed to download any Pexels clips")
            return False

        success = _compose_clips_to_background(downloaded, output_video, target_duration=SHORT_TARGET_DURATION)
        if success:
            new_ids = [int(item.get("id", 0)) for item in downloaded if item.get("id")]
            new_history = used_ids_list + [vid for vid in new_ids if vid not in used_ids]
            _save_used_pexels_ids(new_history)
        return success
        
    except Exception as e:
        logger.error(f"Pexels download failed: {e}")
        return False
    finally:
        # cleanup temporary clip files
        try:
            for item in locals().get("temp_files", []):
                if item and Path(item).exists():
                    Path(item).unlink()
        except Exception:
            pass


def _chunk_text_for_shorts(text: str, start: float, end: float, max_words: int = 4) -> list[dict]:
    """Split captions into fast-paced chunks for shorts-style subtitles."""
    words = [word for word in text.replace("\n", " ").split(" ") if word.strip()]
    if not words:
        return []

    # Keep chunk durations readable but energetic
    total_duration = max(0.5, end - start)
    ideal_chunks = max(1, int(total_duration / 1.1))
    chunk_count = min(max(1, math.ceil(len(words) / max_words)), ideal_chunks)
    words_per_chunk = max(1, math.ceil(len(words) / chunk_count))
    if len(words) >= 6:
        words_per_chunk = max(2, words_per_chunk)

    chunks = [
        words[i:i + words_per_chunk]
        for i in range(0, len(words), words_per_chunk)
    ]
    while len(chunks) > 1 and len(chunks[-1]) == 1:
        chunks[-2].extend(chunks[-1])
        chunks.pop()
    chunk_duration = total_duration / len(chunks)

    result = []
    for index, chunk_words in enumerate(chunks):
        text_chunk = " ".join(chunk_words).strip()
        if not text_chunk:
            continue
        chunk_start = start + (index * chunk_duration)
        chunk_end = min(end, chunk_start + chunk_duration)
        result.append(
            {
                "text": text_chunk,
                "start": chunk_start,
                "end": chunk_end,
            }
        )
    return result


def add_captions_to_video(
    input_video: Path, 
    captions: list[dict], 
    output_video: Path,
    video_duration: float
) -> bool:
    """Add captions to video using an ASS subtitle file with explicit PlayRes."""
    try:
        # Create subtitle file (SRT format)
        srt_path = SHORTS_DIR / "captions.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, cap in enumerate(captions, 1):
                start_time = _seconds_to_srt(cap.get("start", 0))
                end_time = _seconds_to_srt(cap.get("end", video_duration))
                f.write(f"{i}\n{start_time} --> {end_time}\n{cap['text']}\n\n")
        
        logger.info(f"✓ Subtitle file created: {srt_path.name}")
        
        # Write ASS file with explicit PlayRes for reliable font sizing on vertical video
        temp_ass = input_video.parent / "temp_subs.ass"
        _write_ass_file(temp_ass, captions, video_duration)
        
        # ffmpeg command with subtitle overlay
        cmd = [
            _ffmpeg_exe(), "-y",
            "-i", str(input_video),
            "-vf", f"ass={temp_ass.name}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_video)
        ]
        
        logger.info("Adding captions to video...")
        # Use Popen.wait() instead of subprocess.run(capture_output=True, timeout=...)
        # to avoid a Python 3.14 threading bug where join(timeout) raises KeyboardInterrupt.
        with subprocess.Popen(cmd, cwd=str(input_video.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as proc:
            try:
                returncode = proc.wait(timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise RuntimeError("ffmpeg caption processing timed out after 5 minutes")
        
        # Clean up temp ASS file
        if temp_ass.exists():
            temp_ass.unlink()
        
        if returncode != 0:
            raise RuntimeError(f"ffmpeg failed with exit code {returncode}")
        
        size_mb = output_video.stat().st_size / 1_048_576
        logger.info(f"✓ Video with captions: {output_video.name} ({size_mb:.1f} MB)")
        return True
        
    except Exception as e:
        logger.error(f"Caption generation failed: {e}")
        return False


def _seconds_to_srt(seconds: float) -> str:
    """Convert seconds to SRT timestamp format HH:MM:SS,mmm"""
    ms = int((seconds % 1) * 1000)
    secs = int(seconds)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    seconds_part = secs % 60
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d},{ms:03d}"


def _seconds_to_ass(seconds: float) -> str:
    """Convert seconds to ASS timestamp format H:MM:SS.cs"""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _write_ass_file(path: Path, captions: list[dict], video_duration: float) -> None:
    """Write an ASS subtitle file with explicit PlayResX=1080, PlayResY=1920.

    FontSize is in literal screen pixels on the 1080×1920 canvas, so sizing
    is independent of libass internal defaults.
    """
    fs = SHORT_SUBTITLE_FONT_SIZE
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "Collisions: Normal\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial,{fs},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0,0,1,4,2,5,90,90,0,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        for cap in captions:
            start = _seconds_to_ass(cap.get("start", 0.0))
            end = _seconds_to_ass(cap.get("end", video_duration))
            text = cap["text"].replace("\n", "\\N")
            f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")


def combine_audio_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    target_duration: float = 60.0
) -> bool:
    """Combine video and audio, trimming/looping to target duration.
    
    Args:
        video_path: Input video
        audio_path: Input audio
        output_path: Output combined video
        target_duration: Target duration in seconds
        
    Returns:
        True if successful
    """
    try:
        # Use audio length as reference
        cmd = [
            _ffmpeg_exe(), "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-t", str(target_duration),
            "-movflags", "+faststart",
            str(output_path)
        ]
        
        logger.info("Combining audio and video...")
        # Use Popen.wait() instead of subprocess.run(capture_output=True, timeout=...)
        # to avoid a Python 3.14 threading bug where join(timeout) raises KeyboardInterrupt.
        with subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as proc:
            try:
                returncode = proc.wait(timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise RuntimeError("ffmpeg audio-video combine timed out after 5 minutes")
        
        if returncode != 0:
            raise RuntimeError(f"ffmpeg failed with exit code {returncode}")
        
        size_mb = output_path.stat().st_size / 1_048_576
        logger.info(f"✓ Video combined: {output_path.name} ({size_mb:.1f} MB)")
        return True
        
    except Exception as e:
        logger.error(f"Audio-video combine failed: {e}")
        return False


class ShortVideoGenerator:
    """Generate short-form videos from script."""
    
    def __init__(self):
        self.short_gen = ShortScriptGenerator()
    
    def generate_full_short(self, topic: Optional[str] = None) -> Optional[dict]:
        """Generate complete short video pipeline.
        
        Returns:
            {
                "video_path": Path,
                "title": str,
                "script": dict,  # Hook/Body/CTA
                "duration": float,
                "thumbnail": Path (optional)
            }
        """
        try:
            # Step 1: Generate short script
            logger.info("=" * 60)
            logger.info("GENERATING SHORT VIDEO")
            logger.info("=" * 60)

            from src.script_generator import ScriptGenerator, METADATA_FILE
            gen = ScriptGenerator()

            selected_topic = topic
            if not selected_topic:
                recent_topics = _recent_shorts_topics(limit=SHORT_TOPIC_AVOID_COUNT)

                topics = get_all_topics()
                pool = [t for t in topics if _normalize_topic(t) not in recent_topics]
                if not pool:
                    pool = topics  # fallback: all topics if everything is "recent"
                if not pool:
                    logger.error("No topics available in config/topics.yaml")
                    return None
                selected_topic = random.choice(pool)
                if recent_topics:
                    logger.info(
                        "Avoiding recent short topics (%d): %s",
                        len(recent_topics),
                        ", ".join(sorted(recent_topics)),
                    )

            logger.info(f"Using short topic: {selected_topic}")
            full_script = gen.generate(selected_topic)
            if "error" in full_script:
                logger.error(f"Script generation failed: {full_script['error']}")
                return None
            
            # Generate short script structure
            short_script = self.short_gen.generate_from_latest()
            script_text = f"{short_script['hook']}\n\n{short_script['body']}\n\n{short_script['cta']}"

            if _contains_japanese(script_text):
                logger.error("Short script contains Japanese characters; aborting to prevent non-English narration upload")
                return None

            title = str(full_script.get("title") or short_script.get("title") or selected_topic or "Japan Short").strip()
            
            logger.info(f"\n📝 Script: {title}")
            logger.info(f"   Length: {len(script_text.split())} words")
            
            # Step 2: Generate audio with Edge TTS
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                audio_path = Path(f.name)

            tts_ok, timed_captions = generate_audio_edge_tts(script_text, audio_path)
            if not tts_ok:
                logger.warning("Falling back to silent video")
                audio_path = None
                timed_captions = []
            
            # Step 3: Get vertical video from Pexels
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                temp_video_path = Path(f.name)
            
            # Use topic + title + hook for diverse video search
            search_keyword = " | ".join([
                (selected_topic or "").strip(),
                str(full_script.get("title", "")).strip(),
                str(short_script.get("hook", "")).strip(),
            ])
            recommended_clip_count = _recommended_clip_count(SHORT_TARGET_DURATION)
            if not get_pexels_vertical_video(search_keyword, temp_video_path, clip_count=recommended_clip_count):
                logger.error("Failed to download video from Pexels")
                return None
            
            # Step 4: Prepare output path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:40]
            output_video = SHORTS_DIR / f"{timestamp}_{safe_title}_short.mp4"

            # Step 5: Build captions from script
            captions = timed_captions or []
            if not captions:
                captions.extend(_chunk_text_for_shorts(short_script["hook"], start=0, end=3, max_words=2))
                captions.extend(_chunk_text_for_shorts(short_script["body"], start=4, end=50, max_words=SHORT_SUBTITLE_MAX_WORDS))
                captions.extend(_chunk_text_for_shorts(short_script["cta"], start=51, end=60, max_words=SHORT_SUBTITLE_MAX_WORDS))
            
            # Step 6: Add captions
            caption_video = SHORTS_DIR / f"{timestamp}_{safe_title}_caption.mp4"
            caption_duration = captions[-1]["end"] if captions else 60.0
            if not add_captions_to_video(temp_video_path, captions, caption_video, caption_duration):
                caption_video = temp_video_path
            
            # Step 7: Combine with audio (if available)
            if audio_path and audio_path.exists():
                if not combine_audio_video(caption_video, audio_path, output_video, target_duration=60.0):
                    output_video = caption_video
            else:
                output_video = caption_video
            
            # Cleanup temp files
            for f in [temp_video_path, audio_path, caption_video]:
                if f and f.exists() and f != output_video:
                    try:
                        f.unlink()
                    except:
                        pass
            
            logger.info(f"\n✅ Short video generated: {output_video.name}")
            
            return {
                "video_path": output_video,
                "title": title,
                "topic": selected_topic,
                "script": short_script,
                "duration": 60.0,
            }
            
        except Exception as e:
            logger.error(f"Short video generation failed: {e}")
            import traceback
            traceback.print_exc()
            return None


if __name__ == "__main__":
    gen = ShortVideoGenerator()
    result = gen.generate_full_short()
    if result:
        print(f"\n✅ Success: {result['video_path']}")
    else:
        print("\n❌ Failed to generate short video")
