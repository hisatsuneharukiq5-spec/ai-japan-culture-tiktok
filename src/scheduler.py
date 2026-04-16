import schedule
import time
import os
from src.utils import get_config, setup_logger

logger = setup_logger("scheduler")


def run_pipeline(topic: str | None = None):
    """Import here to avoid circular imports and heavy load at module level.

    This is the full pipeline including upload to YouTube.
    Uses FreeVideoGenerator for video clips + subtitles.
    """
    from src.script_generator import ScriptGenerator
    from src.youtube_uploader import YouTubeUploader

    logger.info("=" * 50)
    logger.info("Starting automated pipeline run")

    try:
        # Step 1: Generate script
        try:
            generator = ScriptGenerator()
            if topic:
                script_data = generator.generate(topic)
            else:
                script_data = generator.generate_random()

            if "error" in script_data:
                # non-exception failure; log and fall back below
                raise RuntimeError(script_data['error'])
            logger.info(f"Script generated: {script_data.get('title')}")
        except Exception as e:
            # Model/API failure; fall back to dummy script so pipeline can continue.
            logger.warning(
                "Script generation failed (%s); using dummy script instead.", e
            )
            from src.utils import create_dummy_script
            script_data = create_dummy_script(topic)
            logger.info(f"Dummy script prepared: {script_data.get('title')}")

        # Step 1.5: Early duplicate check — avoid ~10-15 min video generation if the
        # title already exists on the channel.
        try:
            early_uploader = YouTubeUploader()
            dup_id = early_uploader.check_for_duplicate(
                script_data.get("title", ""), long_only=True
            )
            if dup_id:
                logger.warning(
                    "Duplicate title detected before video generation: '%s' "
                    "(existing: https://www.youtube.com/watch?v=%s). Skipping pipeline.",
                    script_data.get("title", ""),
                    dup_id,
                )
                return None
        except Exception as dup_exc:
            logger.warning("Early duplicate check skipped due to error: %s", dup_exc)

        # Step 2: Generate video (using FreeVideoGenerator with video clips + subtitles)
        try:
            from src.free_video_generator import generate_from_latest
            logger.info("🎬 Generating video with FreeVideoGenerator (video clips + subtitles)...")
            video_path = generate_from_latest()
            logger.info(f"✅ Video generated: {video_path}")
        except Exception as e:
            # If the video service is unavailable (404 or other error), produce a dummy
            # video so the pipeline can continue. This helps when running tests or when
            # the media APIs (Edge TTS / Pexels / ffmpeg) encounter errors or are unreachable.
            logger.warning(
                "Video generation failed (%s); falling back to dummy video.", e
            )
            from src.dummy_video import create_dummy_video
            from pathlib import Path
            # create a safe filename based on title
            safe_title = "".join(
                c if c.isalnum() or c in " -_" else "_"
                for c in script_data.get("title", "video")
            )[:50].strip()
            videos_dir = Path(os.getcwd()) / get_config()["output"]["videos_dir"]
            videos_dir.mkdir(parents=True, exist_ok=True)
            video_path = videos_dir / f"dummy_{safe_title}.mp4"
            create_dummy_video(video_path, duration_seconds=5)
            logger.info(f"Dummy video created: {video_path}")

        # Step 3: Upload to YouTube
        uploader = YouTubeUploader()
        video_id = uploader.upload(video_path, script_data)
        logger.info(f"Video uploaded! YouTube video ID: {video_id}")

        # Step 4: Generate and upload thumbnail
        try:
            from src.thumbnail_generator import create_thumbnail, upload_thumbnail
            logger.info("🖼️ Generating thumbnail...")
            thumb_path = create_thumbnail(
                title=script_data.get("title", ""),
                topic=script_data.get("topic", ""),
            )
            upload_thumbnail(video_id, thumb_path)
            logger.info(f"✅ Thumbnail uploaded for video: {video_id}")
        except Exception as thumb_err:
            logger.warning(f"⚠️ Thumbnail generation/upload failed: {thumb_err}")

        logger.info(f"Pipeline complete! YouTube video ID: {video_id}")
        return video_id

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return None


def run_pipeline_generate_only(topic: str | None = None):
    """Generate script and video locally but skip uploading.

    Works similarly to ``run_pipeline`` but returns the path to the generated
    (or dummy) video without calling YouTube APIs.  Useful for testing or
    when upload credentials are unavailable.
    Uses FreeVideoGenerator for video clips + subtitles.
    """
    from src.script_generator import ScriptGenerator

    logger.info("=" * 50)
    logger.info("Starting local generate-only run")

    try:
        # For generate-only we strictly require an existing narration script
        # saved by the `script` command. Do NOT generate a script here.
        from src.script_generator import SCRIPT_FILE, METADATA_FILE

        if not SCRIPT_FILE.exists():
            logger.error(
                "No narration script found. Run `py main.py script` first to create latest_script.txt."
            )
            return None

        # Load the narration-only script
        with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
            narration = f.read().strip()

        # Load metadata if available; otherwise create minimal metadata
        import json
        if METADATA_FILE.exists():
            try:
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except json.JSONDecodeError:
                metadata = None
        else:
            metadata = None

        script_data = {
            "script": narration,
            "title": metadata.get("title") if metadata else (narration[:60] + "...") if narration else "Untitled",
            "description": metadata.get("description") if metadata else "",
            "tags": metadata.get("tags") if metadata else [],
            "topic": metadata.get("topic") if metadata else (topic or ""),
            "saved_path": str(SCRIPT_FILE),
        }

        try:
            from src.free_video_generator import generate_from_latest
            logger.info("🎬 Generating video with FreeVideoGenerator (video clips + subtitles)...")
            video_path = generate_from_latest()
            logger.info(f"✅ Video generated: {video_path}")
        except Exception as e:
            logger.error(f"Video generation failed: {e}", exc_info=True)
            return None

        return video_path

    except Exception as e:
        logger.error(f"Generate-only run failed: {e}", exc_info=True)
        return None


def run_pipeline_upload_only(topic: str | None = None, video_path: str | None = None):
    """Generate script and upload to YouTube, skipping video generation.

    Allows you to supply an existing video file (or the routine will create a
    dummy black‑screen clip) while still producing a new script.  Useful for
    testing or when the media pipeline cannot run.
    """
    import json
    from src.script_generator import ScriptGenerator, METADATA_FILE
    from src.youtube_uploader import YouTubeUploader
    from src.dummy_video import create_dummy_video
    from pathlib import Path

    logger.info("=" * 50)
    logger.info("Starting upload-only pipeline (video generation skipped)")

    try:
        # Step 1: Get script metadata
        script_data = None
        
        # If video_path is provided, use existing metadata (don't generate new script)
        if video_path:
            if METADATA_FILE.exists():
                try:
                    with open(METADATA_FILE, "r", encoding="utf-8") as f:
                        script_data = json.load(f)
                    logger.info(f"✓ Using existing metadata from: {METADATA_FILE}")
                    logger.info(f"  Title: {script_data.get('title')}")
                except json.JSONDecodeError as jde:
                    logger.error(
                        f"Failed to parse metadata file {METADATA_FILE}: {jde}. "
                        "Will generate new script."
                    )
                    script_data = None
            else:
                logger.warning(f"No metadata file found. Will generate new script.")
                script_data = None
        
        # If no script_data loaded, generate a new one
        if script_data is None:
            try:
                generator = ScriptGenerator()
                script_data = generator.generate(topic) if topic else generator.generate_random()
                if "error" in script_data:
                    raise RuntimeError(script_data['error'])
                logger.info(f"Script generated: {script_data.get('title')}")
            except Exception as e:
                logger.warning(
                    "Script generation failed during upload-only pipeline (%s); using dummy script.",
                    e,
                )
                from src.utils import create_dummy_script
                script_data = create_dummy_script(topic)
                logger.info(f"Dummy script prepared: {script_data.get('title')}")

        # Step 2: Resolve video file
        if video_path:
            vpath = Path(video_path)
            if not vpath.exists():
                logger.error(f"Video file not found: {video_path}")
                return None
            logger.info(f"Using existing video: {vpath}")
        else:
            config = get_config()
            from src.utils import PROJECT_ROOT
            videos_dir = PROJECT_ROOT / config["output"]["videos_dir"]
            safe_title = "".join(
                c if c.isalnum() or c in " -_" else "_"
                for c in script_data.get("title", "test")
            )[:40].strip()
            vpath = videos_dir / f"dummy_{safe_title}.mp4"
            logger.info(f"No video provided — creating dummy black-screen video: {vpath}")
            create_dummy_video(vpath, duration_seconds=5)
            logger.info(f"Dummy video ready: {vpath}")

        # Step 3: Upload to YouTube
        uploader = YouTubeUploader()
        video_id = uploader.upload(vpath, script_data)
        logger.info(f"Video uploaded! YouTube video ID: {video_id}")

        # Step 4: Generate and set thumbnail
        try:
            from src.thumbnail_generator import create_thumbnail, upload_thumbnail
            thumb_path = create_thumbnail(
                title=script_data.get("title", ""),
                topic=script_data.get("topic", ""),
            )
            upload_thumbnail(video_id, thumb_path)
            logger.info(f"Thumbnail set for video: {video_id}")
        except Exception as thumb_err:
            logger.warning(f"Thumbnail upload skipped: {thumb_err}")

        # Step 5: Generate Substack article from latest script and publish
        try:
            from src.article_generator import ArticleGenerator
            from src.substack_publisher import SubstackPublisher

            article_gen = ArticleGenerator()
            article = article_gen.generate_from_script()
            logger.info(f"Article saved: {article.get('saved_path')}")

            publisher = SubstackPublisher()
            pub_data = publisher.publish(
                title=article["title"],
                content=article["content"],
                tags=article.get("tags", []),
                subtitle=article.get("subtitle", ""),
            )
            article_url = pub_data.get("url", "")
            logger.info(f"Article published: {article_url}")

            # Optionally tweet the article if X credentials are available
            try:
                from src.x_poster import XPoster
                poster = XPoster()
                tweet_data = poster.tweet_article_published(article["title"], article_url)
                logger.info(f"Tweet posted: {tweet_data.get('id', '')}")
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"Substack publish skipped or failed: {e}")

        logger.info(f"Pipeline complete! YouTube video ID: {video_id}")
        return video_id

    except Exception as e:
        logger.error(f"Upload-only pipeline failed: {e}", exc_info=True)
        return None


def start_scheduler():
    config = get_config()
    schedule_config = config["schedule"]

    if not schedule_config.get("enabled", False):
        logger.warning("Scheduler is disabled in config.yaml. Set schedule.enabled: true to enable.")
        return

    hour = int(os.getenv("UPLOAD_SCHEDULE_HOUR", schedule_config.get("upload_hour", 10)))
    minute = int(os.getenv("UPLOAD_SCHEDULE_MINUTE", schedule_config.get("upload_minute", 0)))
    upload_time = f"{hour:02d}:{minute:02d}"
    upload_days = schedule_config.get("upload_days", ["Monday", "Wednesday", "Friday"])

    day_map = {
        "Monday": schedule.every().monday,
        "Tuesday": schedule.every().tuesday,
        "Wednesday": schedule.every().wednesday,
        "Thursday": schedule.every().thursday,
        "Friday": schedule.every().friday,
        "Saturday": schedule.every().saturday,
        "Sunday": schedule.every().sunday,
    }

    for day in upload_days:
        if day in day_map:
            day_map[day].at(upload_time).do(run_pipeline)
            logger.info(f"Scheduled pipeline: every {day} at {upload_time}")

    logger.info("Scheduler started. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(60)
