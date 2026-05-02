#!/usr/bin/env python3
"""
AI Japan YouTube Automation Tool
Usage:
  python main.py run                              # Run full pipeline (script → video → upload)
  python main.py run --topic "Your topic"         # Run full pipeline with a specific topic
    python main.py upload                           # Generate script + upload (dummy video, skips video generation)
  python main.py upload --topic "Your topic"      # Upload with specific topic
  python main.py upload --video path/to/vid.mp4   # Upload with an existing video file
  python main.py script                           # Generate script only (random topic)
  python main.py script --topic "Your topic"      # Generate script only
  python main.py channel-update                   # Add Substack URL to YouTube channel description (one-time)
  python main.py substack-setup                   # One-time Substack auth (magic link → saves session)
  python main.py article                          # Generate Substack article from latest script and publish
  python main.py article --topic "Your topic"     # Generate script → article → publish (full article flow)
  python main.py short-script                     # Generate 60-sec short video script from latest_script.txt
  python main.py short --video path/to/video.mp4  # Convert to 9:16 vertical and upload as YouTube Short
  python main.py outreach                         # Research Substack cross-promotion candidates → output/outreach/candidates.csv
  python main.py error-log                        # Latest output/error_logs/*.txt → paywalled Substack article
  python main.py error-log --log-file path/to/error.txt  # Use a specific error log file
  python main.py tweet --video-url URL            # Tweet a video announcement
  python main.py thumbnail --video-id VIDEO_ID    # Regenerate & upload thumbnail for existing video
  python main.py schedule                         # Start the automated scheduler
  python main.py topics                           # List all available topics
  python main.py radio                            # Generate Japanese Culture Radio (1-2 hour compilation from all videos)
    python main.py obscura --topic "Your topic"    # Generate/upload Obscura Files dark mystery video
    python main.py obscura-run                      # Fully automated Obscura run (random topic)  python main.py obscura-short                    # Generate YouTube Shorts for Obscura (random topic, 55-59s, 9:16)
  python main.py obscura-short --topic "Topic"   # Generate Obscura Shorts with specific topic"""

import argparse
import sys
import io
from pathlib import Path
from dotenv import load_dotenv

# Fix Unicode output on Windows terminals
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Load environment variables from .env file
load_dotenv()


def cmd_run(topic: str | None):
    from src.scheduler import run_pipeline
    video_id = run_pipeline(topic=topic)
    if video_id:
        print(f"\nSuccess! Video published: https://www.youtube.com/watch?v={video_id}")
    else:
        print("\nPipeline failed. Check logs/ for details.")
        sys.exit(1)


def cmd_script(topic: str | None):
    from src.script_generator import ScriptGenerator
    generator = ScriptGenerator()
    if topic:
        result = generator.generate(topic)
    else:
        result = generator.generate_random()

    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)

    print(f"\nTitle:   {result.get('title')}")
    print(f"Topic:   {result.get('topic')}")
    print(f"Tags:    {', '.join(result.get('tags', []))}")
    print(f"Saved:   {result.get('saved_path')}")
    print("\n--- DESCRIPTION ---")
    print(result.get("description"))


def cmd_upload(topic: str | None, video_path: str | None):
    from src.scheduler import run_pipeline_upload_only
    video_id = run_pipeline_upload_only(topic=topic, video_path=video_path)
    if video_id:
        print(f"\nSuccess! Video published: https://www.youtube.com/watch?v={video_id}")
    else:
        print("\nUpload failed. Check logs/ for details.")
        sys.exit(1)


def cmd_tweet(video_url: str | None, article_url: str | None):
    import json, os
    from pathlib import Path
    from src.x_poster import XPoster
    from src.script_generator import METADATA_FILE

    if not METADATA_FILE.exists():
        print("Error: No metadata found. Run 'py main.py script' first.")
        sys.exit(1)

    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    title = meta.get("title", "New Japan Video")
    substack_url = os.getenv("SUBSTACK_PUBLICATION_URL", "").rstrip("/")
    poster = XPoster()

    if article_url:
        data = poster.tweet_article_published(title, article_url, video_url or "")
    elif video_url:
        data = poster.tweet_video_published(title, video_url, substack_url)
    else:
        print("Error: provide --video-url or --article-url")
        sys.exit(1)

    tweet_id = data.get("id", "")
    print(f"\nTweet posted: https://x.com/i/web/status/{tweet_id}")


def cmd_channel_update():
    """Add Substack URL to the YouTube channel's About description."""
    import os
    substack_url = os.getenv("SUBSTACK_PUBLICATION_URL", "").rstrip("/")
    if not substack_url:
        print("Error: SUBSTACK_PUBLICATION_URL is not set in .env")
        sys.exit(1)
    from src.youtube_uploader import YouTubeUploader
    uploader = YouTubeUploader()
    uploader.update_channel_description(substack_url)
    print(f"\nDone! Substack URL added to channel description: {substack_url}")


def cmd_substack_setup():
    from src.substack_publisher import setup_substack_auth
    setup_substack_auth()


def cmd_article(topic: str | None):
    from src.script_generator import ScriptGenerator
    from src.article_generator import ArticleGenerator
    from src.substack_publisher import SubstackPublisher

    if topic:
        print(f"Generating script for topic: {topic}")
        generator = ScriptGenerator()
        result = generator.generate(topic)
        if "error" in result:
            print(f"Script generation error: {result['error']}")
            sys.exit(1)
        print(f"Script saved: {result.get('saved_path')}")

    print("Generating Substack article from latest script...")
    article_gen = ArticleGenerator()
    article = article_gen.generate_from_script()
    print(f"Article saved: {article['saved_path']}")

    print("Publishing to Substack...")
    publisher = SubstackPublisher()
    data = publisher.publish(
        title=article["title"],
        content=article["content"],
        tags=article["tags"],
        subtitle=article.get("subtitle", ""),
    )
    article_url = data.get("url", "")
    print(f"\nSuccess! Article published: {article_url}")

    # Auto-tweet the article if X credentials are configured
    try:
        from src.x_poster import XPoster
        poster = XPoster()
        tweet_data = poster.tweet_article_published(article["title"], article_url)
        tweet_id = tweet_data.get("id", "")
        print(f"Tweet posted:  https://x.com/i/web/status/{tweet_id}")
    except Exception:
        pass  # X credentials not set or API plan insufficient — skip silently


def cmd_short(
    topic: str | None = None,
    video_path: str | None = None,
    tiktok: bool = False,
    instagram: bool = False,
    youtube: bool = True
):
    """Generate and upload short videos to SNS.
    
    If video_path is provided: Upload existing video to selected SNS
    If video_path is None: Generate complete short video (script + audio + clips + captions)
    """
    
    # If no video path: generate full short video pipeline
    if not video_path:
        print("\n" + "=" * 70)
        print("GENERATING SHORT VIDEO FOR SNS")
        print("=" * 70)
        
        from src.short_video_generator import ShortVideoGenerator
        generator = ShortVideoGenerator()
        result = generator.generate_full_short(topic=topic)
        
        if not result:
            print("\n❌ Failed to generate short video")
            sys.exit(1)
        
        video_path = str(result["video_path"])
        title = result.get("title", "Japan Short Video")
        script = result.get("script", {})
    else:
        # Use existing video
        title = Path(video_path).stem
        script = {}
    
    # Upload to selected platforms
    print(f"\n📤 Uploading to SNS...")
    results = {}
    
    # YouTube Shorts
    if youtube:
        print("\n▶️ YouTube Shorts...")
        try:
            from src.shorts_uploader import ShortsUploader
            uploader = ShortsUploader()
            video_id = uploader.run(video_path)
            results["youtube"] = f"https://www.youtube.com/shorts/{video_id}"
            print(f"✅ Published: {results['youtube']}")
        except Exception as e:
            print(f"⚠️ YouTube upload failed: {e}")
            results["youtube"] = None
    
    # TikTok
    if tiktok:
        print("\n🎵 TikTok...")
        try:
            from src.tiktok_reels_uploader import TikTokReelsUploader
            uploader = TikTokReelsUploader()
            video_id = uploader.upload_video(
                video_path,
                title=title,
                description=script.get("body", "")[:100] + "...",
                add_hashtags=True
            )
            if video_id:
                results["tiktok"] = f"https://www.tiktok.com/video/{video_id}"
                print(f"✅ Published: {results['tiktok']}")
            else:
                results["tiktok"] = None
        except Exception as e:
            print(f"⚠️ TikTok upload failed: {e}")
            results["tiktok"] = None
    
    # Instagram Reels
    if instagram:
        print("\n📸 Instagram Reels...")
        try:
            from src.instagram_reels_uploader import InstagramReelsUploader
            uploader = InstagramReelsUploader()
            post_id = uploader.upload_reel(
                video_path,
                title=title,
                description=script.get("body", "")[:100] + "...",
                add_hashtags=True
            )
            if post_id:
                results["instagram"] = f"https://instagram.com/reel/{post_id}/"
                print(f"✅ Published: {results['instagram']}")
            else:
                results["instagram"] = None
        except Exception as e:
            print(f"⚠️ Instagram upload failed: {e}")
            results["instagram"] = None
    
    # Summary
    print(f"\n" + "=" * 70)
    print("UPLOAD SUMMARY")
    print("=" * 70)
    for platform, url in results.items():
        if url:
            print(f"✅ {platform.upper()}: {url}")
        else:
            print(f"⚠️  {platform.upper()}: Failed")


def cmd_short_script():
    from src.short_script_generator import ShortScriptGenerator
    print("Generating short video script from latest script...")
    gen = ShortScriptGenerator()
    result = gen.generate_from_latest()

    print(f"\nSaved: {result['saved_path']}")
    print("\n" + "=" * 50)
    print("[HOOK]")
    print(result["hook"])
    print("\n[BODY]")
    print(result["body"])
    print("\n[CTA]")
    print(result["cta"])
    print("=" * 50)


def cmd_outreach():
    from src.outreach_researcher import OutreachResearcher
    print("Scanning Substack categories for cross-promotion candidates...")
    researcher = OutreachResearcher()
    csv_path = researcher.run()
    print(f"\nDone! Candidates saved to: {csv_path}")


def cmd_error_log(log_file: str | None):
    from src.error_article_generator import ErrorArticleGenerator
    from src.substack_publisher import SubstackPublisher

    print("Generating paywalled article from error log...")
    generator = ErrorArticleGenerator()
    article = generator.generate(log_file=log_file)
    print(f"Article saved: {article['saved_path']}")

    print("Publishing to Substack (with paywall)...")
    publisher = SubstackPublisher()
    data = publisher.publish_paywalled(
        title=article["title"],
        free_content=article["free_content"],
        paid_content=article["paid_content"],
        tags=article["tags"],
        subtitle=article.get("subtitle", ""),
    )
    print(f"\nSuccess! Paywalled article published: {data.get('url', '')}")


def cmd_thumbnail(video_id: str, title: str | None, topic: str | None):
    import re
    from datetime import datetime
    from src.thumbnail_generator import create_thumbnail, upload_thumbnail
    from src.youtube_uploader import YouTubeUploader

    # Resolve from YouTube video metadata if title/topic not provided
    if not title or not topic:
        try:
            uploader = YouTubeUploader()
            resp = uploader.youtube.videos().list(part="snippet", id=video_id).execute()
            items = resp.get("items") or []
            if items:
                snippet = items[0].get("snippet", {})
                title = title or snippet.get("title", "Japan Video")
                topic = topic or snippet.get("description", "Japan")
            else:
                title = title or "Japan Video"
                topic = topic or "Japan"
        except Exception:
            title = title or "Japan Video"
            topic = topic or "Japan"

    safe_title = re.sub(r"[^\w\-]+", "_", title).strip("_")[:60] or "japan_video"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"thumb_{video_id}_{safe_title}_{timestamp}.jpg"

    print(f"Generating thumbnail for: {title}")
    thumb_path = create_thumbnail(title, topic, output_filename=output_filename)
    print(f"Thumbnail saved: {thumb_path}")

    print(f"Uploading thumbnail to video: {video_id}")
    upload_thumbnail(video_id, thumb_path)
    print(f"Done! Thumbnail updated: https://www.youtube.com/watch?v={video_id}")


def cmd_schedule():
    from src.scheduler import start_scheduler
    start_scheduler()


def cmd_topics():
    from src.utils import get_topics
    topics_data = get_topics()
    for category, topic_list in topics_data["topics"].items():
        print(f"\n[{category.upper()}]")
        for i, topic in enumerate(topic_list, 1):
            print(f"  {i:2}. {topic}")


def cmd_radio():
    """Generate Japanese Culture Radio long-format video."""
    from src.radio_generator import RadioGenerator
    print("Generating Japanese Culture Radio...")
    generator = RadioGenerator()
    result = generator.generate()
    
    print(f"\n✓ Radio video created successfully!")
    print(f"Title:          {result['title']}")
    print(f"Output file:    {result['output_file']}")
    print(f"Thumbnail:      {result['thumbnail_file']}")
    print(f"Description:    {result['description_file']}")
    print(f"Videos used:    {result['video_count']}")
    print(f"Total duration: {result['total_duration_formatted']}")
    print(f"\nVideos included:")
    for video in result['videos']:
        from datetime import timedelta
        duration_str = str(timedelta(seconds=int(video['duration']))).lstrip('0:')
        print(f"  - {video['title']} ({duration_str})")


def cmd_obscura(topic: str | None):
    from src.obscura_pipeline import run_obscura_pipeline
    result = run_obscura_pipeline(topic=topic)
    if not result or not result.get('video_id'):
        if result and result.get('skipped'):
            print("\nObscura upload skipped.")
            print(f"Reason: {result.get('reason', 'unknown')}")
        else:
            print("\nObscura upload failed. Check logs/ for details.")
        sys.exit(1)
    print("\nObscura upload complete!")
    print(f"Title: {result.get('title', '')}")
    print(f"Topic: {result.get('topic', '')}")
    print(f"Video: {result.get('video_path', '')}")
    print(f"URL:   https://www.youtube.com/watch?v={result.get('video_id', '')}")


def cmd_obscura_run():
    from src.obscura_pipeline import run_obscura_pipeline
    from src.obscura_shorts_generator import run_obscura_shorts_pipeline
    
    # Generate long-form video
    result = run_obscura_pipeline(topic=None)
    print("\nObscura automated run complete!")
    print(f"Title: {result.get('title', '')}")
    print(f"Topic: {result.get('topic', '')}")
    print(f"Video: {result.get('video_path', '')}")
    print(f"URL:   https://www.youtube.com/watch?v={result.get('video_id', '')}")
    
    # Generate YouTube Shorts from same topic
    print("\n=" * 60)
    print("Starting Obscura Shorts generation...")
    print("=" * 60)
    shorts_result = run_obscura_shorts_pipeline(
        topic=result.get('topic'),
        long_form_video_id=result.get('video_id'),
    )
    print("\nObscura Shorts upload complete!")
    print(f"Title: {shorts_result.get('title', '')}")
    print(f"Topic: {shorts_result.get('topic', '')}")
    print(f"Video: {shorts_result.get('video_path', '')}")
    print(f"Duration: {shorts_result.get('duration', 0):.1f}s")
    print(f"URL:   https://www.youtube.com/watch?v={shorts_result.get('video_id', '')}")


def cmd_obscura_short(topic: str | None = None):
    from src.obscura_shorts_generator import run_obscura_shorts_pipeline
    result = run_obscura_shorts_pipeline(topic=topic)
    print("\nObscura Shorts upload complete!")
    print(f"Title: {result.get('title', '')}")
    print(f"Topic: {result.get('topic', '')}")
    print(f"Video: {result.get('video_path', '')}")
    print(f"Duration: {result.get('duration', 0):.1f}s")
    print(f"URL:   https://www.youtube.com/watch?v={result.get('video_id', '')}")


def cmd_facts_short(publish_after_hours: float | None = None):
    from facts_scheduler import run_facts_short

    result = run_facts_short(publish_after_hours=publish_after_hours)
    print("\nFacts short upload complete!")
    print(f"Title: {result.get('title', '')}")
    print(f"Topic: {result.get('topic', '')}")
    print(f"Duration: {result.get('duration', 0)}s")
    print(f"URL:   https://www.youtube.com/watch?v={result.get('video_id', '')}")
    if result.get("scheduled_publish_at"):
        print(f"Scheduled Publish (UTC): {result.get('scheduled_publish_at')}")


def cmd_facts_run():
    from facts_scheduler import run_facts_batch

    results = run_facts_batch(count=5)
    print("\nFacts batch run complete (5 uploads attempted).")
    success = [r for r in results if r.get("video_id")]
    failed = [r for r in results if not r.get("video_id")]
    print(f"Success: {len(success)}")
    print(f"Failed:  {len(failed)}")


def cmd_facts_run_single():
    """Post exactly one Facts short — used by GitHub Actions cloud runner."""
    from facts_scheduler import run_facts_short

    result = run_facts_short()
    if result.get("video_id"):
        print(f"\nFacts short uploaded: https://www.youtube.com/shorts/{result['video_id']}")
        print(f"Title: {result.get('title', '')}")
    else:
        print(f"\nFacts short upload failed: {result.get('error', 'unknown error')}")
        import sys; sys.exit(1)


def cmd_facts_growth():
    """Post delayed engagement comments on recently uploaded videos — called by facts_growth.yml."""
    from facts_scheduler import _authenticate_youtube
    from src.growth_engine import post_delayed_comments
    from src.quota_guard import status_line

    print(f"Quota status: {status_line()}")
    youtube = _authenticate_youtube()
    result = post_delayed_comments(youtube, lookback_minutes=75)
    print(f"Delayed comment sweep: {result}")


def cmd_facts_scheduler_setup():
    from facts_scheduler import setup_windows_scheduler

    result = setup_windows_scheduler()
    print("\nFacts scheduler setup complete.")
    print(f"Task: {result.get('task', '')}")
    print(f"Daily start: {result.get('start_time', '')}")
    print("Wake-to-run: enabled")


def cmd_facts_scheduler_status():
    from facts_scheduler import scheduler_status

    status = scheduler_status()
    print("\nFacts scheduler status")
    print(f"Date: {status.get('date')}")
    print(f"Task registered: {status.get('task_registered')}")
    print(f"Today's times: {', '.join(status.get('times', []))}")


def cmd_facts_scheduler_remove():
    from facts_scheduler import remove_windows_scheduler

    result = remove_windows_scheduler()
    print("\nFacts scheduler removal")
    print(f"Task: {result.get('task', '')}")
    print(f"Removed: {result.get('ok')}")


def cmd_facts_scheduler_execute():
    from facts_scheduler import run_daily_autonomous_cycle

    result = run_daily_autonomous_cycle()
    print("\nFacts autonomous cycle finished.")
    print(f"Started:  {result.get('started_at', '')}")
    print(f"Finished: {result.get('finished_at', '')}")


def cmd_facts_analyze():
    from facts_brain import run_daily_analysis_safe

    result = run_daily_analysis_safe()
    if result.get("ok"):
        print("\nFacts analysis complete.")
        print("Config auto-updated from latest analysis.")
    else:
        print("\nFacts analysis failed.")
        print(result.get("error", "Unknown error"))
        sys.exit(1)


def cmd_facts_report():
    from facts_brain import format_latest_report

    print(format_latest_report())


def cmd_facts_brain_log():
    from facts_brain import format_brain_log

    print(format_brain_log())


def cmd_fix_ai_short_languages(limit: int = 5, remove_ja: bool = False):
    from src.youtube_uploader import YouTubeUploader

    uploader = YouTubeUploader()
    results = uploader.fix_recent_shorts_languages(
        limit=limit,
        default_language="en",
        default_audio_language="en",
        remove_japanese_localization=remove_ja,
    )

    print("\nAIJAPAN Shorts language metadata updated.")
    print(f"Updated videos: {len(results)}")
    for item in results:
        print(f"- {item.get('video_id')} | {item.get('title', '')}")


def main():
    parser = argparse.ArgumentParser(
        description="AI Japan YouTube Channel Automation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run the full pipeline (script → video → upload)")
    run_parser.add_argument("--topic", type=str, default=None, help="Topic to generate (random if omitted)")
    # generate-only command: script + video without uploading
    gen_parser = subparsers.add_parser("generate", help="Generate script and video locally (no upload)")
    gen_parser.add_argument("--topic", type=str, default=None, help="Topic to generate (random if omitted)")

    # script command
    script_parser = subparsers.add_parser("script", help="Generate a script only")
    script_parser.add_argument("--topic", type=str, default=None, help="Topic to generate (random if omitted)")

    # upload command (skip video generation, upload script directly with dummy or existing video)
    upload_parser = subparsers.add_parser(
        "upload", help="Generate script and upload to YouTube (skips video generation)"
    )
    upload_parser.add_argument("--topic", type=str, default=None, help="Topic to generate (random if omitted)")
    upload_parser.add_argument("--video", type=str, default=None, help="Path to existing video file (creates dummy black-screen video if omitted)")

    # tweet command
    tweet_parser = subparsers.add_parser("tweet", help="Post an announcement tweet to X")
    tweet_parser.add_argument("--video-url", type=str, default=None, help="YouTube video URL to announce")
    tweet_parser.add_argument("--article-url", type=str, default=None, help="Substack article URL to announce")

    # channel-update command
    subparsers.add_parser("channel-update", help="Add Substack URL to YouTube channel About description (one-time)")

    # substack-setup command
    subparsers.add_parser("substack-setup", help="One-time Substack authentication (magic link flow)")

    # article command
    article_parser = subparsers.add_parser(
        "article", help="Generate a Medium article from the latest script and publish it"
    )
    article_parser.add_argument(
        "--topic", type=str, default=None,
        help="Generate a new script for this topic first, then create and publish the article"
    )

    # short command (generate or upload shorts to SNS)
    short_parser = subparsers.add_parser(
        "short",
        help="Generate and upload short videos to TikTok/Instagram/YouTube",
    )
    short_parser.add_argument(
        "--topic", type=str, default=None,
        help="Generate a brand-new short from this topic (if omitted, auto-selects a fresh topic)",
    )
    short_parser.add_argument(
        "--video", type=str, default=None,
        help="Path to existing video file (auto-generates if omitted)",
    )
    short_parser.add_argument(
        "--tiktok", action="store_true",
        help="Upload to TikTok",
    )
    short_parser.add_argument(
        "--instagram", action="store_true",
        help="Upload to Instagram Reels",
    )
    short_parser.add_argument(
        "--youtube", action="store_true", default=True,
        help="Upload to YouTube Shorts (default: True)",
    )
    short_parser.add_argument(
        "--no-youtube", action="store_false", dest="youtube",
        help="Skip YouTube Shorts",
    )

    # short-script command
    subparsers.add_parser(
        "short-script",
        help="Generate a 60-sec TikTok/Reels/Shorts script from the latest full script",
    )

    # outreach command
    subparsers.add_parser(
        "outreach",
        help="Research Substack cross-promotion candidates and save to CSV",
    )

    # error-log command
    error_log_parser = subparsers.add_parser(
        "error-log",
        help="Generate a paywalled Substack article from an error log file",
    )
    error_log_parser.add_argument(
        "--log-file", type=str, default=None,
        help="Path to error log .txt file (uses latest in output/error_logs/ if omitted)",
    )

    # thumbnail command
    thumb_parser = subparsers.add_parser(
        "thumbnail", help="Regenerate and upload thumbnail for an existing YouTube video"
    )
    thumb_parser.add_argument("--video-id", type=str, required=True, help="YouTube video ID (e.g. dQw4w9WgXcQ)")
    thumb_parser.add_argument("--title", type=str, default=None, help="Video title (uses latest_metadata.json if omitted)")
    thumb_parser.add_argument("--topic", type=str, default=None, help="Video topic (uses latest_metadata.json if omitted)")

    # schedule command
    subparsers.add_parser("schedule", help="Start the automated scheduler")

    # autonomous command
    subparsers.add_parser("autonomous", help="Run one autonomous cycle (decide topic, generate, upload)")

    # topics command
    subparsers.add_parser("topics", help="List all available topics")

    # radio command
    subparsers.add_parser("radio", help="Generate Japanese Culture Radio long-format video from all existing videos")

    # obscura commands
    obscura_parser = subparsers.add_parser("obscura", help="Generate and upload Obscura Files video")
    obscura_parser.add_argument("--topic", type=str, default=None, help="Obscura topic (random if omitted)")
    subparsers.add_parser("obscura-run", help="Run fully automated Obscura pipeline (random topic)")
    obscura_short_parser = subparsers.add_parser("obscura-short", help="Generate YouTube Shorts for Obscura (55-59s, 9:16)")
    obscura_short_parser.add_argument("--topic", type=str, default=None, help="Obscura Shorts topic (random if omitted)")

    # facts commands
    facts_short_parser = subparsers.add_parser("facts-short", help="Generate and upload 1 Facts & Wonders short")
    facts_short_parser.add_argument(
        "--publish-after-hours",
        type=float,
        default=None,
        help="Schedule publish this many hours after upload (sets private + publishAt)",
    )
    subparsers.add_parser("facts-run", help="Generate and upload 5 Facts & Wonders shorts")
    subparsers.add_parser("facts-run-single", help="Generate and upload 1 Facts short (used by GitHub Actions)")
    subparsers.add_parser("facts-scheduler-setup", help="Register autonomous Facts scheduler task")
    subparsers.add_parser("facts-scheduler-status", help="Show today's Facts schedule")
    subparsers.add_parser("facts-scheduler-remove", help="Remove autonomous Facts scheduler task")
    subparsers.add_parser("facts-scheduler-execute", help="Run one autonomous Facts daily cycle")
    subparsers.add_parser("facts-analyze", help="Run Facts AI analysis and auto-evolution")
    subparsers.add_parser("facts-growth", help="Post delayed engagement comments on recent videos (GitHub Actions)")
    heal_parser = subparsers.add_parser("self-heal", help="Diagnose and auto-fix latest pipeline failure")
    heal_parser.add_argument("--channel", default="facts", choices=["facts", "obscura"])
    subparsers.add_parser("facts-report", help="Show latest Facts analysis report")
    subparsers.add_parser("facts-brain-log", help="Show Facts evolution log")

    # AIJAPAN metadata fix command
    fix_lang_parser = subparsers.add_parser(
        "fix-ai-short-languages",
        help="Fix language metadata (default/defaultAudio) on recent AIJAPAN Shorts",
    )
    fix_lang_parser.add_argument("--limit", type=int, default=5, help="How many recent Shorts to fix")
    fix_lang_parser.add_argument(
        "--remove-ja",
        action="store_true",
        help="Also remove Japanese localization entry (ja) from metadata",
    )

    args = parser.parse_args()

    if args.command == "thumbnail":
        cmd_thumbnail(args.video_id, args.title, args.topic)
    elif args.command == "tweet":
        cmd_tweet(args.video_url, args.article_url)
    elif args.command == "channel-update":
        cmd_channel_update()
    elif args.command == "substack-setup":
        cmd_substack_setup()
    elif args.command == "run":
        cmd_run(args.topic)
    elif args.command == "generate":
        # generate video locally for testing
        from src.scheduler import run_pipeline_generate_only
        video_path = run_pipeline_generate_only(topic=args.topic)
        if video_path:
            print(f"\nGenerated video file: {video_path}")
        else:
            print("\nGenerate-only pipeline failed.")
            sys.exit(1)
    elif args.command == "script":
        cmd_script(args.topic)
    elif args.command == "upload":
        cmd_upload(args.topic, args.video)
    elif args.command == "article":
        cmd_article(args.topic)
    elif args.command == "short":
        cmd_short(
            topic=args.topic,
            video_path=args.video,
            tiktok=args.tiktok,
            instagram=args.instagram,
            youtube=args.youtube
        )
    elif args.command == "short-script":
        cmd_short_script()
    elif args.command == "outreach":
        cmd_outreach()
    elif args.command == "error-log":
        cmd_error_log(args.log_file)
    elif args.command == "schedule":
        cmd_schedule()
    elif args.command == "autonomous":
        # Run autonomous cycle (non-interactive)
        from src.autonomous_manager import run_cycle
        # Default: when called via Task Scheduler, run non-dry (perform actions).
        # When called manually, keep safe dry-run by default unless environment variable AUTONOMOUS_RUN=1
        import os
        dry = not (os.getenv("AUTONOMOUS_RUN", "0") == "1")
        res = run_cycle(dry_run=dry)
        print(res)
    elif args.command == "topics":
        cmd_topics()
    elif args.command == "radio":
        cmd_radio()
    elif args.command == "obscura":
        cmd_obscura(args.topic)
    elif args.command == "obscura-run":
        cmd_obscura_run()
    elif args.command == "obscura-short":
        cmd_obscura_short(args.topic)
    elif args.command == "facts-short":
        cmd_facts_short(args.publish_after_hours)
    elif args.command == "facts-run":
        cmd_facts_run()
    elif args.command == "facts-run-single":
        cmd_facts_run_single()
    elif args.command == "facts-scheduler-setup":
        cmd_facts_scheduler_setup()
    elif args.command == "facts-scheduler-status":
        cmd_facts_scheduler_status()
    elif args.command == "facts-scheduler-remove":
        cmd_facts_scheduler_remove()
    elif args.command == "facts-scheduler-execute":
        cmd_facts_scheduler_execute()
    elif args.command == "facts-analyze":
        cmd_facts_analyze()
    elif args.command == "facts-growth":
        cmd_facts_growth()
    elif args.command == "self-heal":
        from src.self_healer import run as heal_run
        import json as _json
        channel = getattr(args, "channel", "facts")
        result = heal_run(channel)
        print(_json.dumps(result, indent=2))
    elif args.command == "facts-report":
        cmd_facts_report()
    elif args.command == "facts-brain-log":
        cmd_facts_brain_log()
    elif args.command == "fix-ai-short-languages":
        cmd_fix_ai_short_languages(limit=args.limit, remove_ja=args.remove_ja)


if __name__ == "__main__":
    # Ensure logs directory exists and enable simple file logging for debugging
    try:
        from pathlib import Path
        Path("logs").mkdir(parents=True, exist_ok=True)
        import logging, sys, traceback
        logging.basicConfig(
            level=logging.DEBUG,
            filename="logs/pipeline_debug.log",
            filemode="a",
            format="%(asctime)s %(levelname)s %(message)s",
        )
        logging.getLogger().info("Starting main with argv: %s", sys.argv)
        try:
            main()
        except SystemExit:
            logging.getLogger().info("Exited via SystemExit")
            raise
        except Exception:
            logging.exception("Unhandled exception in main")
            print("Unhandled exception occurred. See logs/pipeline_debug.log for details.")
            traceback.print_exc()
            sys.exit(1)
        logging.getLogger().info("Finished main")
    except Exception:
        # If logging setup itself fails, fall back to calling main() so we still see console output
        try:
            main()
        except Exception:
            import traceback
            print("Fatal error starting main; see console for traceback")
            traceback.print_exc()
            raise
