#!/usr/bin/env python3
"""Check actual thumbnails on YouTube videos"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.youtube_uploader import YouTubeUploader

def check_video_thumbnails():
    """Check what thumbnails are actually set on YouTube"""
    uploader = YouTubeUploader()
    
    # Get videos
    request = uploader.youtube.search().list(
        part="id,snippet",
        forMine=True,
        type="video",
        maxResults=10,
    )
    
    response = request.execute()
    
    print("\n" + "="*80)
    print("CURRENT YOUTUBE VIDEO THUMBNAILS")
    print("="*80 + "\n")
    
    for item in response.get("items", []):
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        
        # Get video details with thumbnails
        video_response = uploader.youtube.videos().list(
            part="snippet",
            id=video_id
        ).execute()
        
        if video_response["items"]:
            thumbnails = video_response["items"][0]["snippet"]["thumbnails"]
            
            print(f"📹 {title}")
            print(f"   ID: {video_id}")
            
            # Check if custom thumbnail exists
            if "maxres" in thumbnails:
                print(f"   ✅ Custom thumbnail: {thumbnails['maxres']['url']}")
            elif "standard" in thumbnails:
                print(f"   ⚠️  Standard thumbnail: {thumbnails['standard']['url']}")
            elif "high" in thumbnails:
                print(f"   ⚠️  Auto-generated: {thumbnails['high']['url']}")
            else:
                print(f"   ❌ Default only: {thumbnails.get('default', {}).get('url', 'N/A')}")
            print()
    
    print("="*80)

if __name__ == "__main__":
    check_video_thumbnails()
