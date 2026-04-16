import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.obscura_pipeline import ObscuraYouTubeUploader
from src.utils import PROJECT_ROOT


def main():
    videos = sorted((PROJECT_ROOT / "output" / "videos").glob("obscura_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        raise RuntimeError("No obscura video found in output/videos")

    video = videos[0]
    metadata_path = PROJECT_ROOT / "output" / "scripts" / "obscura_latest_metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("Missing output/scripts/obscura_latest_metadata.json")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    print(f"Uploading: {video}")
    uploader = ObscuraYouTubeUploader()
    video_id = uploader.upload(video, metadata)
    print(f"VIDEO_ID={video_id}")
    print(f"URL=https://www.youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    main()
