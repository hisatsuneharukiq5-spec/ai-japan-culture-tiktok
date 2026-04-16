#!/usr/bin/env python3
"""
Premium Video Generator
Uses FFmpeg for high-quality video composition
Uses Whisper for subtitles with custom styling
Uses Pexels + Pixabay video clips (60+ clips for premium quality)
"""

import os
import logging
from pathlib import Path
from typing import Optional
import tempfile
import json
import asyncio
import subprocess
import requests
import shutil
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Import edge_tts at module level
try:
    import edge_tts
except ImportError:
    edge_tts = None

logger = logging.getLogger(__name__)

# ============================================================================
# VIDEO DURATION CONSTRAINTS
# ============================================================================
SCRIPT_SYSTEM_PROMPT = """
あなたはYouTube動画の台本を書くプロです。

【必須ルール】
- 動画の長さ：必ず8〜10分（台本は1500〜2000文字）
- 10分を絶対に超えないこと
- 外部リンク・URL・サイト名を一切記載しない
- 「詳しくはこちら」「リンクから」などの誘導も禁止
- 自己完結した内容にすること

【構成】
- イントロ：1分
- メイン：6〜7分（3〜4セクション）
- まとめ：1〜2分
"""

MAX_VIDEO_DURATION = 660   # 11分 = 660秒（10分前後OK）
TARGET_DURATION = 540      # 目標9分 = 540秒

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

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
    
    # Remove [Show ...] visual directions
    text = re.sub(r'\[Show .+?\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[Close-up .+?\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[Time-lapse .+?\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[Split-screen .+?\]', '', text, flags=re.DOTALL)
    
    return text.strip()


def _audio_duration(path: Path) -> float:
    """Get audio/video duration using ffprobe"""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.warning(f"ffprobe failed: {res.stderr}")
        return 0.0
    try:
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def _download_url(url: str, out_path: Path):
    """Download file from URL"""
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def _search_pexels(query: str, per_page: int = 8):
    """Search Pexels for video clips (premium: 8 per query)"""
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
        if files:
            # Prefer HD quality (sort by height)
            files_sorted = sorted(files, key=lambda f: (f.get('height') or 0), reverse=True)
            results.append(files_sorted[0].get("link"))
    return results


def _search_pixabay(query: str, per_page: int = 8):
    """Search Pixabay for video clips (premium: 8 per query)"""
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
        # Choose highest resolution
        best = None
        best_h = 0
        for k, v in videos.items():
            if v.get("height", 0) > best_h:
                best_h = v.get("height", 0)
                best = v.get("url")
        if best:
            results.append(best)
    return results


def _prepare_clip(in_path: Path, out_path: Path):
    """Transcode and pad clip to 1920x1080, 30fps"""
    cmd = [
        "ffmpeg", "-y", "-i", str(in_path),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-r", "30",  # Force 30fps for consistency
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", 
        str(out_path)
    ]
    subprocess.run(cmd, check=True)


def _concat_clips(clips: list[Path], out_path: Path):
    """Concatenate video clips using ffmpeg"""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding='utf-8') as tf:
        for c in clips:
            # Escape single quotes for concat demuxer
            tf.write(f"file '{str(c).replace(chr(39), chr(39)+chr(92)+chr(92)+chr(92)+chr(39))}'\n")
        list_path = Path(tf.name)

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), 
           "-c", "copy", str(out_path)]
    subprocess.run(cmd, check=True)
    
    try:
        list_path.unlink()
    except Exception:
        pass


def _whisper_transcribe(audio_path: Path, srt_out: Path, model_name: str = "base"):
    """Generate SRT subtitles using Whisper (premium: base model for speed/quality balance)"""
    try:
        import whisper
    except Exception:
        raise RuntimeError("whisper package not installed. Install with: pip install -U openai-whisper")
    
    logger.info(f"Loading Whisper model: {model_name}")
    model = whisper.load_model(model_name)
    
    logger.info("Transcribing audio...")
    res = model.transcribe(str(audio_path))
    
    # Write SRT format
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
    
    logger.info(f"Generated {len(segments)} subtitle segments")


def _burn_subtitles(in_video: Path, srt_path: Path, out_video: Path):
    """Burn subtitles with premium styling (larger font, better outline)"""
    # Copy SRT to temp location with simple name (Windows path fix)
    temp_srt = in_video.parent / "temp_subs.srt"
    shutil.copy(srt_path, temp_srt)
    
    try:
        # Premium subtitle style: 24pt bold, white text, 3px black outline
        style = "FontName=Arial,FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=3,Bold=1,Alignment=2"
        vf = f"subtitles={temp_srt.name}:force_style='{style}'"
        
        cmd = [
            "ffmpeg", "-y", 
            "-i", str(in_video.absolute()), 
            "-vf", vf, 
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",  # Higher quality
            "-c:a", "copy", 
            str(out_video.absolute())
        ]
        subprocess.run(cmd, check=True, cwd=str(in_video.parent))
    finally:
        if temp_srt.exists():
            temp_srt.unlink()



class PremiumVideoGenerator:
    """Premium video generator with video clips and subtitles"""
    
    def __init__(self):
        self.output_dir = Path('output/videos')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def generate(self, script_data: dict) -> Path:
        """
        Generate premium quality video with:
        - Edge TTS narration
        - 60+ video clips from Pexels + Pixabay
        - Whisper subtitles with premium styling
        - 1080p 30fps output
        
        Args:
            script_data: Dict with 'title', 'script', 'topic', 'tags'
            
        Returns:
            Path to generated video file
        """
        title = script_data.get('title', 'video')
        script_text = script_data.get('script', '')
        topic = script_data.get('topic', '')
        tags = script_data.get('tags', [])
        
        if not script_text:
            raise ValueError("No script text provided")
        
        logger.info(f"🎬 Generating PREMIUM video: {title}")
        
        # Check edge_tts
        if edge_tts is None:
            logger.info("Installing edge-tts...")
            subprocess.run(['py', '-m', 'pip', 'install', 'edge-tts'], check=True)
            import edge_tts as _edge_tts
            globals()['edge_tts'] = _edge_tts
        
        tmpdir = Path(tempfile.mkdtemp(prefix="ai_japan_premium_"))
        logger.info(f"Working directory: {tmpdir}")
        
        try:
            # 1. Generate narration with Edge TTS
            logger.info("🎙️ Synthesizing narration with Edge TTS...")
            audio_path = tmpdir / "narration.mp3"
            asyncio.run(self._synthesize_audio(script_text, audio_path))
            
            # 2. Get audio duration
            duration = _audio_duration(audio_path)
            logger.info(f"⏱️ Audio duration: {duration:.1f}s ({duration/60:.1f} min)")
            
            # Check duration constraints
            if duration > MAX_VIDEO_DURATION:
                logger.warning(f"⚠️ Audio exceeds maximum: {duration:.1f}s > {MAX_VIDEO_DURATION}s")
            elif duration > TARGET_DURATION:
                logger.warning(f"⚠️ Audio exceeds target: {duration:.1f}s > {TARGET_DURATION}s")
            else:
                logger.info(f"✅ Duration OK: {duration:.1f}s (Target: {TARGET_DURATION}s)")
            
            # 3. Search for video clips (PREMIUM: more queries, more clips per query)
            queries = []
            if topic:
                queries.append(topic)
            queries.append(title)
            queries.extend(tags[:30])  # Premium: use up to 30 tags for more variety
            
            # Add broad search terms for more diversity
            broad_terms = ["Japan", "Tokyo", "Japanese culture", "Japanese people", 
                          "Japanese tradition", "Japanese city", "Japanese street",
                          "Asia culture", "Tokyo street", "Japanese daily life"]
            queries.extend(broad_terms)
            
            clip_urls = []
            logger.info(f"🔍 Searching for video clips with {len(queries)} queries...")
            
            for q in queries:
                if len(clip_urls) >= 120:  # Premium: aim for 120 clips (increased from 80)
                    break
                
                # Premium: 15 clips per query (increased from 8 for more variety)
                pexels_results = _search_pexels(q, per_page=15)
                clip_urls.extend(pexels_results)
                logger.info(f"  - Pexels '{q}': {len(pexels_results)} clips")
                
                pixabay_results = _search_pixabay(q, per_page=15)
                clip_urls.extend(pixabay_results)
                logger.info(f"  - Pixabay '{q}': {len(pixabay_results)} clips")
            
            # Deduplicate URLs
            clip_urls = list(dict.fromkeys(clip_urls))
            logger.info(f"📊 Found {len(clip_urls)} unique video clips")
            
            if len(clip_urls) < 10:
                raise RuntimeError(
                    f"❌ Only found {len(clip_urls)} clips (minimum: 10 for premium). "
                    "Check PEXELS_API_KEY and PIXABAY_API_KEY."
                )
            
            # 4. Download and process clips
            clips = []
            total_dur = 0.0
            target_clips = min(len(clip_urls), 80)  # Premium: use up to 80 clips (increased from 60)
            
            logger.info(f"⬇️ Downloading and processing up to {target_clips} clips...")
            
            for i, url in enumerate(clip_urls[:target_clips]):
                try:
                    raw_clip = tmpdir / f"clip_{i}.mp4"
                    logger.info(f"  [{i+1}/{target_clips}] Downloading: {url[:60]}...")
                    _download_url(url, raw_clip)
                    
                    proc_clip = tmpdir / f"clip_{i}_proc.mp4"
                    _prepare_clip(raw_clip, proc_clip)
                    
                    clip_dur = _audio_duration(proc_clip)
                    clips.append(proc_clip)
                    total_dur += clip_dur
                    
                    logger.info(f"  ✅ Processed: {clip_dur:.1f}s (total: {total_dur:.1f}s / {duration:.1f}s)")
                    
                    if total_dur >= duration * 1.1:  # 10% buffer
                        break
                        
                except Exception as e:
                    logger.warning(f"  ⚠️ Failed clip {i}: {e}")
                    continue
            
            if not clips:
                raise RuntimeError("❌ Failed to download any video clips")
            
            # Loop clips if needed
            if total_dur < duration:
                logger.info(f"⚠️ Looping clips to reach duration ({total_dur:.1f}s < {duration:.1f}s)")
                original_clips = clips.copy()
                idx = 0
                while total_dur < duration:
                    dup = tmpdir / f"clip_loop_{len(clips)}.mp4"
                    shutil.copy(str(original_clips[idx % len(original_clips)]), str(dup))
                    dup_dur = _audio_duration(original_clips[idx % len(original_clips)])
                    clips.append(dup)
                    total_dur += dup_dur
                    idx += 1
            
            logger.info(f"🎞️ Using {len(clips)} video clips (total: {total_dur:.1f}s)")
            
            # 5. Concatenate clips
            logger.info("🔗 Concatenating video clips...")
            concat_video = tmpdir / "concat.mp4"
            _concat_clips(clips, concat_video)
            
            # 6. Merge audio
            logger.info("🎵 Merging audio with video...")
            merged_video = tmpdir / "merged.mp4"
            cmd = [
                "ffmpeg", "-y", 
                "-i", str(concat_video), 
                "-i", str(audio_path), 
                "-c:v", "copy", 
                "-c:a", "aac", 
                "-shortest", 
                str(merged_video)
            ]
            subprocess.run(cmd, check=True)
            
            # 7. Generate and burn subtitles
            srt_path = tmpdir / "subs.srt"
            try:
                logger.info("📝 Generating subtitles with Whisper...")
                _whisper_transcribe(audio_path, srt_path, model_name="base")
                
                logger.info("🔥 Burning subtitles with premium styling...")
                subtitled_video = tmpdir / "subtitled.mp4"
                _burn_subtitles(merged_video, srt_path, subtitled_video)
                
            except Exception as e:
                logger.warning(f"⚠️ Subtitle generation failed: {e}")
                subtitled_video = merged_video
            
            # 8. Save final video
            safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:50].strip()
            output_path = self.output_dir / f"{safe_title}.mp4"
            
            logger.info(f"💾 Saving final video to: {output_path}")
            shutil.copy(str(subtitled_video), str(output_path))
            
            file_size = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"✅ Premium video generated: {output_path}")
            logger.info(f"📊 Size: {file_size:.1f} MB | Duration: {duration:.1f}s | Clips: {len(clips)}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Video generation failed: {e}")
            raise
        finally:
            # Cleanup temp directory
            try:
                shutil.rmtree(tmpdir)
                logger.info("🧹 Cleaned up temporary files")
            except Exception as e:
                logger.warning(f"⚠️ Cleanup failed: {e}")
    
    async def _synthesize_audio(self, text: str, output_path: Path):
        """Synthesize speech using Edge TTS"""
        cleaned_text = _clean_script_text(text)
        
        # Premium: Use high-quality voice
        voice = "en-US-JennyNeural"  # High quality, natural English voice
        communicate = edge_tts.Communicate(cleaned_text, voice)
        await communicate.save(str(output_path))



def test_premium_generator():
    """Test the premium video generator"""
    
    # Load latest metadata
    metadata_file = Path('output/scripts/latest_metadata.json')
    if not metadata_file.exists():
        print("❌ No metadata found. Run script generation first.")
        return
    
    with open(metadata_file, encoding='utf-8') as f:
        metadata = json.load(f)
    
    # Load script
    script_file = Path('output/scripts/latest_script.txt')
    if not script_file.exists():
        print("❌ No script found. Run script generation first.")
        return
        
    with open(script_file, encoding='utf-8') as f:
        script_text = f.read().strip()
    
    metadata['script'] = script_text
    
    # Generate video
    print("\n🚀 Starting PREMIUM video generation...")
    print(f"📝 Title: {metadata.get('title', 'N/A')}")
    print(f"🏷️ Topic: {metadata.get('topic', 'N/A')}")
    print(f"🔖 Tags: {len(metadata.get('tags', []))} tags\n")
    
    generator = PremiumVideoGenerator()
    video_path = generator.generate(metadata)
    
    print(f"\n🎉 PREMIUM video generated successfully!")
    print(f"📹 Path: {video_path}")
    print(f"📊 Size: {video_path.stat().st_size / (1024*1024):.1f} MB")
    print(f"\n✨ Features:")
    print(f"  - 60+ high-quality video clips")
    print(f"  - Professional subtitles (24pt, bold, outlined)")
    print(f"  - 1080p 30fps output")
    print(f"  - Edge TTS narration")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
    )
    test_premium_generator()
