#!/usr/bin/env python3
"""
Japanese Culture Radio Generator
Concatenates all videos from output/videos/ into a long-format radio-style video.
"""

import json
import os
import subprocess
from pathlib import Path
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class RadioGenerator:
    def __init__(self):
        self.videos_dir = Path("output/videos")
        self.output_file = Path("output/videos/Japanese_Culture_Radio_Vol1.mp4")
        self.description_file = Path("output/radio_description.txt")
        self.thumbnail_file = Path("output/thumbnails/radio_thumbnail.jpg")
        
    def get_video_duration(self, video_path: Path) -> float:
        """Get video duration in seconds using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(video_path)
                ],
                capture_output=True,
                text=True,
                check=True
            )
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError) as e:
            logger.error(f"Failed to get duration for {video_path}: {e}")
            return 0.0
    
    def format_timestamp(self, seconds: float) -> str:
        """Convert seconds to H:MM:SS or MM:SS format."""
        td = timedelta(seconds=int(seconds))
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"
    
    def get_video_title(self, video_path: Path) -> str:
        """Extract title from video filename (without extension)."""
        return video_path.stem
    
    def collect_videos(self) -> list[tuple[Path, str, float]]:
        """
        Collect all valid videos from output/videos/.
        Returns list of (path, title, duration) tuples.
        Excludes files with 'dummy', 'Radio', 'test' in name.
        """
        videos = []
        exclude_keywords = ["dummy", "radio", "test", "placeholder"]
        
        if not self.videos_dir.exists():
            logger.error(f"Videos directory not found: {self.videos_dir}")
            return videos
        
        for video_file in sorted(self.videos_dir.glob("*.mp4")):
            # Skip excluded files
            if any(keyword in video_file.name.lower() for keyword in exclude_keywords):
                logger.info(f"Skipping excluded file: {video_file.name}")
                continue
            
            duration = self.get_video_duration(video_file)
            if duration <= 0:
                logger.warning(f"Skipping {video_file.name} (invalid duration)")
                continue
            
            title = self.get_video_title(video_file)
            videos.append((video_file, title, duration))
            logger.info(f"Added: {title} ({self.format_timestamp(duration)})")
        
        return videos
    
    def generate_description(self, videos: list[tuple[Path, str, float]]) -> str:
        """Generate YouTube description with timestamps."""
        description_parts = [
            "🎌 Japanese Culture Radio - Learn About Japan While You Work or Study!",
            "",
            "Sit back, relax, and explore the fascinating world of Japanese culture.",
            "Perfect background for work, study, or relaxation.",
            "",
            "📋 TIMESTAMPS:",
            "0:00 - Introduction"
        ]
        
        current_time = 0.0
        for video_path, title, duration in videos:
            current_time += duration
            timestamp = self.format_timestamp(current_time)
            description_parts.append(f"{timestamp} - {title}")
        
        description_parts.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🎌 AI-powered Japanese culture insights",
            "✅ New episodes every week",
            "📧 Newsletter: aijapanculture.substack.com",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "#JapaneseCulture #JapanRadio #StudyWithMe #WorkWithMe #JapanBGM #LearnAboutJapan #AIJapan #JapanFacts #Relaxing"
        ])
        
        return "\n".join(description_parts)
    
    def concatenate_videos(self, videos: list[tuple[Path, str, float]]) -> Path:
        """Concatenate videos using ffmpeg."""
        if not videos:
            raise ValueError("No videos to concatenate")
        
        # Create concat file list
        concat_file = Path("output/radio_concat_list.txt")
        with open(concat_file, "w", encoding="utf-8") as f:
            for video_path, _, _ in videos:
                # ffmpeg concat requires absolute paths or proper escaping
                abs_path = video_path.resolve()
                # Escape single quotes in path
                escaped_path = str(abs_path).replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")
        
        logger.info(f"Concatenating {len(videos)} videos...")
        logger.info(f"Output: {self.output_file}")
        
        # Run ffmpeg concat
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output file
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",  # Copy streams without re-encoding (fast)
            str(self.output_file)
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info(f"✓ Radio video created: {self.output_file}")
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg concat failed: {e.stderr}")
            raise
        finally:
            # Clean up concat file
            if concat_file.exists():
                concat_file.unlink()
        
        return self.output_file
    
    def generate_thumbnail(self) -> Path:
        """Generate thumbnail for Japanese Culture Radio."""
        from src.thumbnail_generator import create_thumbnail
        
        title = "Japanese Culture Radio 🎌"
        topic = "Learn About Japan While You Work/Study"
        
        logger.info("Generating Radio thumbnail...")
        thumbnail_path = create_thumbnail(
            title=title,
            topic=topic,
            output_filename="radio_thumbnail.jpg"
        )
        logger.info(f"✓ Thumbnail saved: {thumbnail_path}")
        
        return thumbnail_path
    
    def generate(self) -> dict:
        """
        Main entry point: collect videos, concatenate, generate description.
        Returns metadata dict with file paths and stats.
        """
        logger.info("Starting Japanese Culture Radio generation...")
        
        # Collect videos
        videos = self.collect_videos()
        if not videos:
            raise ValueError("No valid videos found in output/videos/")
        
        total_duration = sum(duration for _, _, duration in videos)
        logger.info(f"Collected {len(videos)} videos, total duration: {self.format_timestamp(total_duration)}")
        
        # Generate description
        description = self.generate_description(videos)
        self.description_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.description_file, "w", encoding="utf-8") as f:
            f.write(description)
        logger.info(f"✓ Description saved: {self.description_file}")
        
        # Concatenate videos
        output_path = self.concatenate_videos(videos)
        
        # Generate thumbnail
        thumbnail_path = self.generate_thumbnail()
        
        # Return metadata
        return {
            "title": "Japanese Culture Radio 🎌 Learn About Japan While You Work/Study | Vol.1",
            "output_file": str(output_path),
            "description_file": str(self.description_file),
            "thumbnail_file": str(thumbnail_path),
            "video_count": len(videos),
            "total_duration": total_duration,
            "total_duration_formatted": self.format_timestamp(total_duration),
            "videos": [{"title": title, "duration": duration} for _, title, duration in videos]
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    generator = RadioGenerator()
    result = generator.generate()
    print(json.dumps(result, indent=2, ensure_ascii=False))
