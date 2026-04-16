#!/usr/bin/env python3
"""
Extract 55-59 second clips from Obscura long-form videos.
Creates high-engagement Shorts for weekly channel posting.
"""

import subprocess
import json
from pathlib import Path
from datetime import datetime

OBSCURA_VIDEOS = {
    "obscura_She_Had_9_Identities_and_No_Name___The_Isdal_Woman_Mystery.mp4": {
        "title": "The Isdal Woman Mystery",
        "video_id": "YfwRY7YGKCg",
        "clips": [
            {"start": "00:30", "duration": 55, "title": "Who Was This Woman?"},
            {"start": "03:45", "duration": 57, "title": "The Mystery Deepens"},
            {"start": "08:00", "duration": 55, "title": "Final Evidence"}
        ]
    },
    "obscura_The_Dead_Man_No_One_Could_Identify___The_Somerton_Man_Mystery.mp4": {
        "title": "The Somerton Man",
        "video_id": "TdGSnFLQmGQ",
        "clips": [
            {"start": "01:00", "duration": 56, "title": "A Body, No Name"},
            {"start": "04:30", "duration": 58, "title": "The Code Nobody Can Crack"},
            {"start": "06:45", "duration": 55, "title": "75 Years Later..."}
        ]
    },
    "obscura_5_Children_Vanished_in_a_Fire_That_Should_Never_Have_Happened.mp4": {
        "title": "The Sodder Children",
        "video_id": "FrKrzumYfNw",
        "clips": [
            {"start": "00:45", "duration": 57, "title": "5 Kids Gone"},
            {"start": "04:00", "duration": 55, "title": "The Warning Before"},
            {"start": "09:15", "duration": 56, "title": "10 Years Later..."}
        ]
    }
}

def find_obscura_video(filename):
    """Find Obscura video file in output/videos/."""
    video_dir = Path("output/videos")
    for f in video_dir.glob("*"):
        if filename in f.name:
            return f
    return None

def extract_clip(video_path: str, start_time: str, duration: int, output_path: str):
    """Extract a clip from video using ffmpeg."""
    try:
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-ss", start_time,
            "-t", str(duration),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-y",
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode == 0
    except Exception as e:
        print(f"   ⚠️ Error extracting clip: {e}")
        return False

def main():
    output_dir = Path("output/shorts/obscura_clips")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*80)
    print("🎬 EXTRACTING SHORTS CLIPS FROM OBSCURA LONG-FORM VIDEOS")
    print("="*80)
    
    extraction_log = []
    total_clips = 0
    successful_clips = 0
    
    for filename, video_info in OBSCURA_VIDEOS.items():
        print(f"\n📹 Processing: {video_info['title']}")
        
        video_path = find_obscura_video(filename)
        if not video_path:
            print(f"   ⚠️ Video file not found: {filename}")
            continue
        
        for clip_idx, clip in enumerate(video_info["clips"], 1):
            total_clips += 1
            
            clip_title = clip["title"]
            start_time = clip["start"]
            duration = clip["duration"]
            
            # Output filename format: {parent_title}_clip{n}__{clip_title}.mp4
            safe_parent_title = video_info["title"].replace(" ", "_")
            safe_clip_title = clip_title.replace(" ", "_").replace("...", "")
            output_filename = f"obscura_{safe_parent_title}_clip{clip_idx}__{safe_clip_title}.mp4"
            output_path = output_dir / output_filename
            
            print(f"   📊 Clip {clip_idx}: {start_time} (+{duration}s) → {clip_title}")
            
            if extract_clip(str(video_path), start_time, duration, str(output_path)):
                print(f"      ✅ Extracted")
                successful_clips += 1
                extraction_log.append({
                    "parent_title": video_info["title"],
                    "parent_video_id": video_info["video_id"],
                    "clip_filename": output_filename,
                    "clip_title": clip_title,
                    "start_time": start_time,
                    "duration": duration,
                    "status": "ready_for_upload",
                    "clip_index": clip_idx
                })
            else:
                print(f"      ❌ Failed")
                extraction_log.append({
                    "parent_title": video_info["title"],
                    "clip_filename": output_filename,
                    "status": "failed"
                })
    
    # Save extraction log
    log_path = output_dir / "extraction_manifest.jsonl"
    with open(log_path, "w", encoding="utf-8") as f:
        for entry in extraction_log:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    print("\n" + "="*80)
    print(f"✅ EXTRACTION COMPLETE: {successful_clips}/{total_clips} clips extracted")
    print("="*80)
    print(f"\n📁 Clips saved to: {output_dir}")
    print(f"📋 Manifest saved to: {log_path}")
    print(f"\n📊 Summary:")
    print(f"   • Total clips extracted: {successful_clips}")
    print(f"   • Ready for upload: {successful_clips} Shorts")
    print(f"   • Each Shorts: 55-59 seconds")
    print(f"\n🚀 Next: Schedule 3x/week posting (Mon/Wed/Fri at 2 PM UTC)")
    print("\n")

if __name__ == "__main__":
    main()
