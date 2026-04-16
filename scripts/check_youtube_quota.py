#!/usr/bin/env python3
"""
YouTube Quota Checker - Monitor upload quota and rate limits
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.youtube_uploader import YouTubeUploader

def check_youtube_quota():
    """Check current YouTube channel upload quota"""
    
    print("\n" + "="*80)
    print("YouTube Upload Quota Checker 📊")
    print("="*80)
    print(f"Check Time: {datetime.now().isoformat()}\n")
    
    try:
        uploader = YouTubeUploader()
        
        # Get channel statistics
        print("【チャネル統計情報】CHANNEL STATISTICS")
        print("-" * 80)
        
        request = uploader.youtube.channels().list(
            part='statistics,snippet',
            mine=True
        )
        response = request.execute()
        
        if response['items']:
            channel = response['items'][0]
            stats = channel['statistics']
            snippet = channel['snippet']
            
            print(f"Channel Title: {snippet['title']}")
            print(f"Channel ID: {channel['id']}")
            video_count = stats.get('videoCount', 'N/A')
            view_count = stats.get('viewCount', 'N/A')
            sub_count = stats.get('subscriberCount', 'hidden')
            
            print(f"Total Videos Uploaded: {video_count}")
            if view_count != 'N/A':
                print(f"Total Views: {int(view_count):,}")
            else:
                print(f"Total Views: {view_count}")
            print(f"Total Subscribers: {sub_count}")
        
        # Get recent uploads
        print("\n【最近のアップロード】RECENT UPLOADS")
        print("-" * 80)
        
        uploads_request = uploader.youtube.search().list(
            part='snippet',
            forMine=True,
            type='video',
            maxResults=20,
            order='date'
        )
        uploads_response = uploads_request.execute()
        
        if uploads_response['items']:
            print(f"\nFound {len(uploads_response['items'])} recent videos:\n")
            
            upload_times = []
            for i, item in enumerate(uploads_response['items'][:10], 1):
                published_at = item['snippet']['publishedAt']
                title = item['snippet']['title']
                
                # Parse timestamp
                pub_datetime = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                upload_times.append(pub_datetime)
                
                # Calculate time ago
                time_diff = datetime.now(pub_datetime.tzinfo) - pub_datetime
                hours_ago = time_diff.total_seconds() / 3600
                
                print(f"{i}. {title}")
                print(f"   Published: {pub_datetime.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                print(f"   Time ago: {hours_ago:.1f} hours\n")
            
            # Calculate quota reset time
            if upload_times:
                first_upload_time = min(upload_times)
                quota_reset_time = first_upload_time + timedelta(hours=24)
                time_until_reset = quota_reset_time - datetime.now(first_upload_time.tzinfo)
                hours_until_reset = time_until_reset.total_seconds() / 3600
                
                print("-" * 80)
                print("【アップロード クォータ 情報】UPLOAD QUOTA INFO")
                print("-" * 80)
                print(f"Daily Limit: 50 videos per 24 hours")
                print(f"First upload (today): {first_upload_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                print(f"Quota reset time: {quota_reset_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                
                if hours_until_reset > 0:
                    print(f"⏳ Time until reset: {hours_until_reset:.1f} hours (~{int(hours_until_reset)}h {int((hours_until_reset % 1) * 60)}m)")
                else:
                    print(f"✓ Quota reset is available!")
        
        # Get quota info
        print("\n【API クォータ使用量】API QUOTA USAGE")
        print("-" * 80)
        
        # YouTube API typically has a daily quota of 10,000 units
        # Each call costs a certain number of units
        print("""
Typical API Unit Costs:
  - Search request: 100 units
  - Videos insert (upload): 1,700 units
  - Thumbnails set: 50 units
  
Daily Limit: 10,000,000 units (for most accounts)
Daily Limit: 1,000,000 units (if verified)

Your Account Status: Check YouTube Studio > Settings > Channel > Uploads
        """)
        
        # Save report
        report = {
            'check_time': datetime.now().isoformat(),
            'status': 'success',
            'quota_limit': 50,
            'quota_period': '24_hours',
            'video_count': stats.get('videoCount', 'N/A')
        }
        
        report_file = Path('output/quota_check_latest.json')
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Report saved to: {report_file}")
        
    except Exception as e:
        print(f"❌ Error checking quota: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*80 + "\n")

if __name__ == '__main__':
    check_youtube_quota()
