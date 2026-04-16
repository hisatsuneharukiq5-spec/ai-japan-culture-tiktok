#!/usr/bin/env python3
"""
Publish Japanese Culture Radio introduction article to Substack.
With paywall: free content + paid content ($10/month).
"""

from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.substack_publisher import SubstackPublisher
from src.utils import setup_logger

logger = setup_logger("publish_radio_article")

# Article metadata
TITLE = "Introducing Japanese Culture Radio: Learn About Japan While You Work"
SUBTITLE = "Your new favorite study/work companion 🎌"
TAGS = ["Japanese Culture", "YouTube", "Radio", "Learning"]

# Free content
FREE_CONTENT = """
## What is Japanese Culture Radio?

**Japanese Culture Radio** is a new long-form video series that combines our most popular videos into a continuous audio/video experience — perfect for background listening while you work, study, or relax.

Each episode features 1-2 hours of content exploring different aspects of Japanese culture:
- Japanese etiquette and social customs
- Temple and shrine traditions
- Urban vs. rural Japan
- Tokyo culture and lifestyle
- And much more!

## Why It's Perfect for Work/Study

Unlike traditional podcasts or Spotify playlists, **Japanese Culture Radio** gives you:

- **Continuous learning**: Absorb authentic cultural insights without interruption
- **No ads or music changes**: Pure educational content for 60+ minutes
- **Visual context** (when watching): Authentic footage and examples from Japan
- **Perfect pace**: Designed to inform without overwhelming

Whether you're learning Japanese, researching the culture, or just want something meaningful in the background — this is designed for you.

## New Episodes Coming Weekly

We're committed to releasing new **Japanese Culture Radio** episodes every week, covering new topics:

- ✓ Vol. 1: "Japanese Etiquette & Social Customs" (Live now!)
- 🔜 Vol. 2: "Tokyo vs Osaka: Regional Differences"
- 🔜 Vol. 3: "Traditional Japanese Arts & Crafts"
- 🔜 Vol. 4: "Modern Japan: Tech & Innovation"
- And more...

## Watch Now

👉 **YouTube**: [Japanese Culture Radio Vol. 1](https://www.youtube.com/watch?v=dQw4w9WgXcQ)

Prefer audio-only? Subscribe to our newsletter and we'll share audio versions soon.
"""

# Paid content
PAID_CONTENT = """
## How We Created Japanese Culture Radio

Behind every episode is a production process combining AI tools, automation, and careful curation.

### The Production Workflow

1. **Script Generation**: AI-powered research and writing
2. **Video Creation**: Mix of AI-generated visuals and authentic stock footage
3. **Concatenation**: Seamless combining of multiple videos
4. **Quality Assurance**: Manual review for accuracy and flow

### Tools We Used

- **FFmpeg**: Video concatenation and encoding
- **Python**: Automation scripting
- **HuggingFace FLUX**: AI thumbnail generation
- **YouTube API v3**: Publishing and distribution
- **Claude/GPT**: Content research and scripting

### FFmpeg Video Concatenation Code

Here's the actual command used to combine multiple videos into one seamless radioformat episode:

```bash
ffmpeg -f concat -safe 0 -i filelist.txt -c copy output.mp4
```

**Creating the file list (`filelist.txt`)**:

```text
file '/path/to/video1.mp4'
file '/path/to/video2.mp4'
file '/path/to/video3.mp4'
file '/path/to/video4.mp4'
```

This uses the **concat demuxer** with `-c copy` for:
- ⚡ **Fast processing**: No re-encoding (literally copies streams)
- 📁 **Small file size**: Original quality preserved
- 🎯 **Perfect transitions**: Seamless concatenation

### Python Automation Code

Here's the Python code we use to automate video collection and concatenation:

    def collect_videos(video_dir):
        videos = []
        for video_file in Path(video_dir).glob("*.mp4"):
            if any(x in video_file.name for x in ["dummy", "radio", "test"]):
                continue
            duration = get_video_duration(str(video_file))
            videos.append({
                "path": str(video_file),
                "title": video_file.stem,
                "duration": duration
            })
        return videos
    
    def get_video_duration(video_path):
        import subprocess
        result = subprocess.run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1:nokey=1",
            video_path
        ], capture_output=True, text=True)
        return float(result.stdout.strip())
    
    def concatenate_videos(videos, output_path):
        import subprocess
        concat_file = "concat_list.txt"
        with open(concat_file, "w") as f:
            for v in videos:
                f.write(f"file '{v['path']}'\n")
        
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path
        ])

### Full Automation Prompt

When generating new episodes, we use this prompt template:

**Task**: Generate a script for a 60-minute Japanese Culture Radio episode about [TOPIC].

**Requirements**:
- 8-10 segments, each 5-8 minutes
- Include authentic examples and facts
- Mix engaging storytelling with educational content
- Use clear transitions between segments
- Suitable for background listening
- Accurate to Japanese sources

**Output Format**:
- [SEGMENT] TITLE (estimated duration)
- Script content here...
- Include 8-10 main segments plus intro/conclusion

### Next Steps

1. **Subscribe & support**: Help us create more episodes by subscribing
2. **Suggest topics**: Comment below with episodes you want to see
3. **Share feedback**: Email us ideas@aijapanculture.substack.com
4. **Join the community**: Get early access to new episodes and raw materials

---

**Questions about the production process?** Reply to this email — we love hearing from our audience!

Happy learning! 🎌
"""

def main():
    """Publish radio introduction article with paywall."""
    try:
        publisher = SubstackPublisher()
        
        logger.info("Publishing Japanese Culture Radio introduction article...")
        result = publisher.publish_paywalled(
            title=TITLE,
            subtitle=SUBTITLE,
            free_content=FREE_CONTENT,
            paid_content=PAID_CONTENT,
            tags=TAGS,
        )
        
        logger.info(f"✅ Article published successfully!")
        logger.info(f"URL: {result['url']}")
        
        return True
        
    except FileNotFoundError as e:
        logger.error(f"❌ Session not found: {e}")
        logger.error("Run: py main.py substack-setup")
        return False
    except Exception as e:
        logger.error(f"❌ Publication failed: {e}")
        raise

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
