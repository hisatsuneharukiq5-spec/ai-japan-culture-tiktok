import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.utils import setup_logger, PROJECT_ROOT
from src.script_generator import METADATA_FILE

logger = setup_logger("shorts_uploader")

SHORTS_DIR = PROJECT_ROOT / "output" / "shorts"
AIJAPAN_SHORTS_REGISTRY = PROJECT_ROOT / "output" / "analytics" / "aijapan_shorts_upload_registry.jsonl"


def _ffmpeg_exe() -> str:
    """Return the path to the bundled ffmpeg binary."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"  # fall back to system PATH


def convert_to_vertical(input_path: str | Path) -> Path:
    """Crop and scale a video to 9:16 (1080×1920) for YouTube Shorts.

    - Crops the centre of the frame to 9:16 aspect ratio
    - Caps duration at 60 seconds
    - Saves to output/shorts/{timestamp}_..._vertical.mp4
    Returns the path to the converted file.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Video not found: {input_path}")

    SHORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in input_path.stem)[:40]
    output_path = SHORTS_DIR / f"{timestamp}_{safe}_vertical.mp4"

    # Centre-crop to 9:16, then scale to 1080×1920
    vf = "crop=min(iw\\,ih*9/16):min(ih\\,iw*16/9),scale=1080:1920,setsar=1"
    cmd = [
        _ffmpeg_exe(), "-y",
        "-i", str(input_path),
        "-t", "60",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    logger.info(f"Converting to vertical 9:16: {input_path.name}")
    # Use Popen.wait() instead of subprocess.run(capture_output=True, timeout=...)
    # to avoid a Python 3.14 threading bug where join(timeout) raises KeyboardInterrupt.
    with subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as proc:
        try:
            returncode = proc.wait(timeout=600)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError("ffmpeg vertical conversion timed out after 10 minutes")
    if returncode != 0:
        raise RuntimeError(f"ffmpeg vertical conversion failed (exit code {returncode})")

    size_mb = output_path.stat().st_size / 1_048_576
    logger.info(f"Conversion done: {output_path.name} ({size_mb:.1f} MB)")
    return output_path


def _append_shorts_registry(*, video_id: str, title: str, topic: str) -> None:
    """Append a JSONL entry to the AIJapan shorts upload registry."""
    AIJAPAN_SHORTS_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "video_id": video_id,
        "title": title,
        "topic": topic,
    }
    with open(AIJAPAN_SHORTS_REGISTRY, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.info("Registry updated: %s (%s)", title, video_id)


class ShortsUploader:
    def __init__(self):
        if not METADATA_FILE.exists():
            raise FileNotFoundError(
                f"No metadata found at {METADATA_FILE}\n"
                "Run 'py main.py script' first."
            )
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

    def run(self, video_path: str | Path) -> str:
        """Convert video to vertical and upload as YouTube Short.

        Returns the YouTube video ID.
        """
        # Step 1: ffmpeg conversion
        vertical_path = convert_to_vertical(video_path)

        # Step 2: upload
        from src.youtube_uploader import YouTubeUploader
        uploader = YouTubeUploader()
        video_id = uploader.upload_short(vertical_path, self.metadata)

        # Step 3: append to registry so topic deduplication can use it
        if video_id:
            _append_shorts_registry(
                video_id=video_id,
                title=self.metadata.get("title", ""),
                topic=self.metadata.get("topic", ""),
            )

        return video_id
