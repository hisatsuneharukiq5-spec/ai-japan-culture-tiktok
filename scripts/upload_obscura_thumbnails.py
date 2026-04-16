#!/usr/bin/env python3
"""
Upload generated thumbnails to YouTube videos (Variant A).
Tests the best-performing thumbnail format.
"""

import os
from pathlib import Path
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

THUMBNAILS_TO_UPLOAD = {
    "YfwRY7YGKCg": "output/thumbnails/obscura_variants/YfwRY7YGKCg_variant_a.png",
    "TdGSnFLQmGQ": "output/thumbnails/obscura_variants/TdGSnFLQmGQ_variant_a.png",
    "FrKrzumYfNw": "output/thumbnails/obscura_variants/FrKrzumYfNw_variant_a.png"
}

def get_youtube_service():
    """Initialize YouTube Data API v3 service."""
    token_file = Path("config/youtube_token.json")
    if not token_file.exists():
        print("❌ YouTube token not found.")
        return None
    
    creds = Credentials.from_authorized_user_file(str(token_file))
    if creds.expired:
        creds.refresh(Request())
    
    return build("youtube", "v3", credentials=creds)

def upload_thumbnail(youtube, video_id, thumbnail_path):
    """Upload a custom thumbnail to a YouTube video."""
    try:
        # Check if file exists
        if not os.path.exists(thumbnail_path):
            print(f"   ⚠️ Thumbnail file not found: {thumbnail_path}")
            return False
        
        # Upload thumbnail
        request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype="image/png")
        )
        response = request.execute()
        return True
    except Exception as e:
        print(f"   ⚠️ Error uploading thumbnail: {e}")
        return False

def main():
    youtube = get_youtube_service()
    if not youtube:
        return
    
    print("\n" + "="*80)
    print("📤 UPLOADING OBSCURA THUMBNAILS TO YOUTUBE")
    print("="*80)
    
    success_count = 0
    
    for video_id, thumbnail_path in THUMBNAILS_TO_UPLOAD.items():
        print(f"\n🎯 Uploading to {video_id}...")
        print(f"   File: {thumbnail_path}")
        
        if upload_thumbnail(youtube, video_id, thumbnail_path):
            print(f"   ✅ Successfully uploaded!")
            success_count += 1
        else:
            print(f"   ❌ Upload failed")
    
    print("\n" + "="*80)
    print(f"✅ UPLOAD COMPLETE: {success_count}/3 successful")
    print("="*80)
    print("\n📊 Next Steps:")
    print("1. Monitor CTR for 48 hours")
    print("2. If CTR improves by >20%, continue with Variant A")
    print("3. If CTR is flat, switch to Variant B or C")
    print("4. Create Shorts from this content for viral multiplier effect")
    print("\n🚀 Expected impact: +20-50% increase in click-through rate\n")

if __name__ == "__main__":
    main()
