"""Free video generator: uses Edge TTS, Pexels, Pixabay, ffmpeg, and Whisper.

Command entry: `python main.py generate` will call `FreeVideoGenerator.generate_from_latest()`
which reads `output/scripts/latest_script.txt` and `output/scripts/latest_metadata.json`.

Notes:
- Requires `edge-tts` (pip), `ffmpeg` on PATH, `whisper` package + model, and PEXELS_API_KEY/PIXABAY_API_KEY env vars.
"""
import os
import asyncio
import subprocess
import json
from pathlib import Path
from src.utils import PROJECT_ROOT, setup_logger
import requests
import math
import tempfile
import shlex

logger = setup_logger("free_video_generator")

SCRIPT_FILE = PROJECT_ROOT / "output" / "scripts" / "latest_script.txt"
METADATA_FILE = PROJECT_ROOT / "output" / "scripts" / "latest_metadata.json"
VIDEOS_DIR = PROJECT_ROOT / "output" / "videos"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)


def _clean_script_text(text: str) -> str:
    """Remove script markup that shouldn't be read aloud"""
    import re
    
    # Remove timing markers: [HOOK — 0:00–0:15], etc.
    text = re.sub(r'\[\w+\s*—\s*[\d:–]+\]', '', text)
    
    # Remove bold markers (** ** or __)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    
    # Remove leading brackets at start of lines: **[INTRO] → INTRO
    text = re.sub(r'^\s*\*\*?\[', '', text, flags=re.MULTILINE)
    text = re.sub(r'\]\*\*?\s*$', '', text, flags=re.MULTILINE)
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Remove [Show ...] visual directions (in brackets)
    text = re.sub(r'\[Show .+?\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[Close-up .+?\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[Time-lapse .+?\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[Split-screen .+?\]', '', text, flags=re.DOTALL)
    
    return text.strip()


async def _synthesize_edge_tts(text: str, out_path: Path, voice: str = "en-US-AriaNeural"):
    try:
        import edge_tts
    except Exception:
        raise RuntimeError("edge-tts package not installed. Install with: pip install edge-tts")

    # Clean script text before synthesis
    cleaned_text = _clean_script_text(text)
    
    communicate = edge_tts.Communicate(cleaned_text, voice)
    await communicate.save(str(out_path))


def _audio_duration(path: Path) -> float:
    # Use ffprobe to get duration
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.warning("ffprobe failed: %s", res.stderr)
        return 0.0
    try:
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def _download_url(url: str, out_path: Path):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def _is_landscape_dims(width: int | None, height: int | None) -> bool:
    if not width or not height:
        return False
    return int(width) >= int(height)


def _probe_video_dimensions(path: Path) -> tuple[int, int] | None:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return None
    try:
        payload = json.loads(res.stdout or "{}")
        stream = (payload.get("streams") or [{}])[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        if width <= 0 or height <= 0:
            return None
        return width, height
    except Exception:
        return None


def _search_pexels(query: str, per_page: int = 5):
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        logger.warning("PEXELS_API_KEY not set; skipping Pexels search")
        return []
    headers = {"Authorization": key}
    params = {"query": query, "per_page": per_page}
    resp = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for v in data.get("videos", []):
        files = v.get("video_files", [])
        if not files:
            continue

        landscape_files = [
            item for item in files
            if _is_landscape_dims(item.get("width"), item.get("height")) and item.get("link")
        ]
        if not landscape_files:
            continue

        best = sorted(
            landscape_files,
            key=lambda item: ((item.get("height") or 0), (item.get("width") or 0)),
            reverse=True,
        )[0]
        results.append(best.get("link"))
    return results


def _search_pixabay(query: str, per_page: int = 5):
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        logger.warning("PIXABAY_API_KEY not set; skipping Pixabay search")
        return []
    params = {"key": key, "q": query, "per_page": per_page}
    resp = requests.get("https://pixabay.com/api/videos/", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for hit in data.get("hits", []):
        videos = hit.get("videos", {})
        # choose the highest resolution available
        best = None
        best_k = 0
        for k, v in videos.items():
            if not _is_landscape_dims(v.get("width"), v.get("height")):
                continue
            if v.get("height", 0) > best_k:
                best_k = v.get("height", 0)
                best = v.get("url")
        if best:
            results.append(best)
    return results


def _prepare_clip(in_path: Path, out_path: Path):
    # Transcode and pad to 1920x1080, remove original audio
    cmd = [
        "ffmpeg", "-y", "-i", str(in_path),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-an",  # Remove audio track from clips
        str(out_path)
    ]
    subprocess.run(cmd, check=True)


def _concat_clips(clips: list[Path], out_path: Path):
    # Create concat file
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
        for c in clips:
            tf.write(f"file '{str(c).replace("'","'\\\''")}'\n")
        list_path = Path(tf.name)

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)]
    subprocess.run(cmd, check=True)
    try:
        list_path.unlink()
    except Exception:
        pass


def _burn_subtitles(in_video: Path, srt_path: Path, out_video: Path):
    # Burn subtitles with white text (20pt), black outline (2px) at bottom
    # Due to Windows path escaping complexity, copy SRT to temp location with simple name
    import shutil
    temp_srt = in_video.parent / "temp_subs.srt"
    shutil.copy(srt_path, temp_srt)
    
    try:
        # Use simple relative path for SRT - no escaping needed
        style = "FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Bold=1,Alignment=2"
        vf = f"subtitles={temp_srt.name}:force_style='{style}'"
        
        cmd = [
            "ffmpeg", "-y", 
            "-i", str(in_video.absolute()), 
            "-vf", vf, 
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", 
            "-c:a", "copy", 
            str(out_video.absolute())
        ]
        # Run from the video's directory so relative SRT path works
        subprocess.run(cmd, check=True, cwd=str(in_video.parent))
    finally:
        # Clean up temp file
        if temp_srt.exists():
            temp_srt.unlink()


def _overlay_logo(in_video: Path, logo_path: Path, out_video: Path):
    # Place logo at bottom-right with 10px margin, scale to 150px width
    if not logo_path.exists():
        logger.warning("Logo not found: %s", logo_path)
        # copy input to output
        subprocess.run(["ffmpeg", "-y", "-i", str(in_video), "-c", "copy", str(out_video)])
        return
    vf = f"[1]scale=150:-1[logo];[0][logo]overlay=W-w-10:H-h-10"
    cmd = ["ffmpeg", "-y", "-i", str(in_video), "-i", str(logo_path), "-filter_complex", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "copy", str(out_video)]
    subprocess.run(cmd, check=True)


def _whisper_transcribe(audio_path: Path, srt_out: Path, model_name: str = "small"):
    try:
        import whisper
    except Exception:
        raise RuntimeError("whisper package not installed. Install with: pip install -U openai-whisper")
    model = whisper.load_model(model_name)
    res = model.transcribe(str(audio_path))
    # write srt
    segments = res.get("segments", [])
    with open(srt_out, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            start = seg['start']
            end = seg['end']
            def fmt(t):
                ms = int((t - int(t)) * 1000)
                h = int(t // 3600)
                m = int((t % 3600) // 60)
                s = int(t % 60)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            f.write(f"{i}\n{fmt(start)} --> {fmt(end)}\n{seg['text'].strip()}\n\n")


def generate_from_latest(output_name: str | None = None, voice: str = "en-US-AriaNeural") -> Path:
    """Main entry: generate video from latest script and metadata.

    Returns path to final video file.
    """
    if not SCRIPT_FILE.exists() or not METADATA_FILE.exists():
        raise FileNotFoundError("Latest script or metadata not found. Run 'python main.py script' first.")

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        narration = f.read().strip()
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    title = meta.get("title", "AI Japan Video")
    topic = meta.get("topic", "")
    tags = meta.get("tags", [])

    tmpdir = Path(tempfile.mkdtemp(prefix="ai_japan_vid_"))
    audio_path = tmpdir / "narration.mp3"
    logger.info("Synthesizing TTS audio to: %s", audio_path)
    asyncio.run(_synthesize_edge_tts(narration, audio_path, voice=voice))

    duration = _audio_duration(audio_path)
    logger.info("Audio duration: %.2f seconds", duration)
    
    if duration > 660:  # 11 minutes
        logger.warning(f"⚠️ Audio duration {duration}s exceeds maximum 660s (11 min)")

    # Build comprehensive search queries (title, topic, tags)
    queries = []
    if topic:
        queries.append(topic)
    queries.append(title)
    queries.extend(tags[:15])  # Use up to 15 tags for more variety
    
    # Search for video clips (minimum 16 clips required for 8min video, aim for 40)
    clip_urls = []
    logger.info("🔍 Searching for video clips with %d queries", len(queries))
    
    for q in queries:
        if len(clip_urls) >= 40:
            break
        
        # Try Pexels first
        pexels_results = _search_pexels(q, per_page=5)
        clip_urls.extend(pexels_results)
        logger.info(f"  - Pexels '{q}': {len(pexels_results)} clips")
        
        # Then try Pixabay
        pixabay_results = _search_pixabay(q, per_page=5)
        clip_urls.extend(pixabay_results)
        logger.info(f"  - Pixabay '{q}': {len(pixabay_results)} clips")

    # Deduplicate URLs
    clip_urls = list(dict.fromkeys(clip_urls))
    logger.info(f"📊 Found {len(clip_urls)} unique video clips")

    if len(clip_urls) < 3:
        # STRICT REQUIREMENT: Must have at least 3 video clips (no static image fallback)
        raise RuntimeError(
            f"❌ FATAL: Only found {len(clip_urls)} video clips (minimum: 3). "
            "Cannot generate video with static images. "
            "Please check PEXELS_API_KEY and PIXABAY_API_KEY environment variables."
        )

    # Download and process clips until total duration >= audio duration
    clips = []
    total = 0.0
    target_clips = min(len(clip_urls), 40)  # Use up to 40 clips for 8min videos
    
    for i, url in enumerate(clip_urls[:target_clips]):
        try:
            out_clip = tmpdir / f"clip_{i}.mp4"
            logger.info(f"⬇️ Downloading clip {i+1}/{target_clips}: {url[:60]}...")
            _download_url(url, out_clip)

            dims = _probe_video_dimensions(out_clip)
            if not dims or not _is_landscape_dims(dims[0], dims[1]):
                logger.info(f"  ⏭️ Skipping non-landscape clip: {dims}")
                continue
            
            proc_clip = tmpdir / f"clip_{i}_proc.mp4"
            _prepare_clip(out_clip, proc_clip)
            
            clip_dur = _audio_duration(proc_clip)
            clips.append(proc_clip)
            total += clip_dur
            
            logger.info(f"  ✅ Processed: {clip_dur:.1f}s (total: {total:.1f}s / {duration:.1f}s)")
            
            if total >= duration:
                break
        except Exception as e:
            logger.warning(f"  ⚠️ Failed to download/process clip {i}: {e}")
            continue

    if not clips:
        raise RuntimeError("❌ FATAL: Failed to download any video clips")

    # If total duration is less than audio, loop clips
    if total < duration:
        logger.info(f"⚠️ Total clip duration ({total:.1f}s) < audio ({duration:.1f}s), looping clips...")
        original_clips = clips.copy()
        idx = 0
        while total < duration:
            dup = tmpdir / f"clip_loop_{len(clips)}.mp4"
            import shutil
            shutil.copy(str(original_clips[idx % len(original_clips)]), str(dup))
            dup_dur = _audio_duration(original_clips[idx % len(original_clips)])
            clips.append(dup)
            total += dup_dur
            idx += 1

    logger.info(f"🎞️ Using {len(clips)} video clips (total: {total:.1f}s)")

    # Concatenate clips
    concatenated = tmpdir / "concat.mp4"
    _concat_clips(clips, concatenated)

    # Merge audio - explicitly map video from clips and audio from narration
    merged = tmpdir / "merged.mp4"
    cmd = ["ffmpeg", "-y", "-i", str(concatenated), "-i", str(audio_path), 
           "-map", "0:v:0", "-map", "1:a:0",  # Select video from clips, audio from narration
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(merged)]
    subprocess.run(cmd, check=True)

    # Transcribe and burn subtitles
    srt = tmpdir / "subs.srt"
    try:
        logger.info("📝 Generating subtitles with Whisper...")
        _whisper_transcribe(audio_path, srt)
        subtitled = tmpdir / "subtitled.mp4"
        logger.info("🔥 Burning subtitles into video...")
        _burn_subtitles(merged, srt, subtitled)
    except Exception as e:
        logger.warning("⚠️ Subtitle generation failed: %s", e)
        subtitled = merged

    # Overlay logo if available
    logo_path = PROJECT_ROOT / "assets" / "logo.png"
    final = VIDEOS_DIR / (output_name or f"{title[:40].strip().replace(' ', '_')}.mp4")
    _overlay_logo(subtitled, logo_path, final)

    logger.info("✅ Generated video saved to: %s", final)
    return final
