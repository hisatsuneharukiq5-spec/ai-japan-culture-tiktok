import subprocess
from pathlib import Path

from src.utils import get_config, setup_logger, PROJECT_ROOT

logger = setup_logger("dummy_video")


def create_dummy_video(output_path: Path, duration_seconds: int = 5) -> Path:
    """
    Create a minimal black-screen MP4 for testing YouTube uploads.
    Tries system ffmpeg first, then imageio-ffmpeg as a fallback.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if _try_system_ffmpeg(output_path, duration_seconds):
        logger.info(f"Dummy video created via ffmpeg: {output_path}")
        return output_path

    if _try_imageio(output_path, duration_seconds):
        logger.info(f"Dummy video created via imageio: {output_path}")
        return output_path

    raise RuntimeError(
        "Could not create dummy video. "
        "Install ffmpeg (https://ffmpeg.org/download.html) or run: "
        "pip install imageio imageio-ffmpeg numpy"
    )


def _try_system_ffmpeg(output_path: Path, duration: int) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, timeout=5, check=True,
        )
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=black:size=1280x720:rate=30",
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                "-shortest",
                str(output_path),
            ],
            check=True, capture_output=True, timeout=60,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _try_imageio(output_path: Path, duration: int) -> bool:
    try:
        import imageio
        import numpy as np

        fps = 30
        black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        with imageio.get_writer(
            str(output_path), fps=fps, codec="libx264", quality=5, macro_block_size=16
        ) as writer:
            for _ in range(fps * duration):
                writer.append_data(black_frame)
        return True
    except ImportError:
        logger.warning(
            "imageio/numpy not available. Run: pip install imageio imageio-ffmpeg numpy"
        )
        return False
    except Exception as e:
        logger.error(f"imageio video creation failed: {e}")
        return False
