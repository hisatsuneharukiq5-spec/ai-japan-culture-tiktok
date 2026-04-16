#!/usr/bin/env python3
"""
Analyze Obscura Files video performance and provide recommendations for growth.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Obscura video registry
OBSCURA_VIDEOS = {
    "YfwRY7YGKCg": "She Had 9 Identities and No Name — The Isdal Woman Mystery",
    "TdGSnFLQmGQ": "The Dead Man No One Could Identify — The Somerton Man Mystery",
    "FrKrzumYfNw": "5 Children Vanished in a Fire That Should Never Have Happened | The Sodder Children"
}

def get_youtube_service():
    """Initialize YouTube Data API v3 service."""
    token_file = Path("config/youtube_token.json")
    if not token_file.exists():
        print("❌ YouTube token not found. Run 'python main.py channel-update' first.")
        return None
    
    creds = Credentials.from_authorized_user_file(str(token_file))
    if creds.expired:
        creds.refresh(Request())
    
    return build("youtube", "v3", credentials=creds)

def get_video_stats(youtube, video_id):
    """Get video statistics from YouTube Data API."""
    try:
        request = youtube.videos().list(
            part="statistics,contentDetails,snippet",
            id=video_id,
            fields="items(id,snippet(title,publishedAt,description),contentDetails(duration),statistics(viewCount,likeCount,commentCount))"
        )
        response = request.execute()
        
        if not response["items"]:
            return None
        
        item = response["items"][0]
        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        
        return {
            "video_id": video_id,
            "title": snippet.get("title", "N/A"),
            "published_at": snippet.get("publishedAt", "N/A"),
            "duration": content.get("duration", "PT0S"),
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "description": snippet.get("description", "")
        }
    except Exception as e:
        print(f"⚠️ Error fetching stats for {video_id}: {e}")
        return None

def analyze_performance(videos_data):
    """Analyze performance metrics and identify patterns."""
    
    print("\n" + "="*80)
    print("📊 OBSCURA FILES PERFORMANCE ANALYSIS")
    print("="*80)
    
    # Video-by-video analysis
    print("\n📹 INDIVIDUAL VIDEO METRICS")
    print("-"*80)
    
    for video_data in videos_data:
        video_id = video_data["video_id"]
        title = video_data["title"]
        views = video_data["views"]
        likes = video_data["likes"]
        comments = video_data["comments"]
        
        engagement_rate = (likes + comments) / views * 100 if views > 0 else 0
        like_rate = (likes / views * 100) if views > 0 else 0
        comment_rate = (comments / views * 100) if views > 0 else 0
        
        print(f"\n🎬 {title}")
        print(f"   Video ID: {video_id}")
        print(f"   Published: {video_data['published_at']}")
        print(f"   └─ Views: {views:,}")
        print(f"   └─ Likes: {likes:,} ({like_rate:.2f}%)")
        print(f"   └─ Comments: {comments:,} ({comment_rate:.2f}%)")
        print(f"   └─ Engagement Rate: {engagement_rate:.2f}%")
        print(f"   Facebook URL: https://www.youtube.com/watch?v={video_id}")
    
    # Comparative analysis
    print("\n\n📈 COMPARATIVE ANALYSIS")
    print("-"*80)
    
    total_views = sum(v["views"] for v in videos_data)
    total_likes = sum(v["likes"] for v in videos_data)
    total_comments = sum(v["comments"] for v in videos_data)
    avg_engagement = (total_likes + total_comments) / total_views * 100 if total_views > 0 else 0
    
    print(f"\n✓ Total Views (all 3 videos): {total_views:,}")
    print(f"✓ Total Engagement (likes+comments): {total_likes + total_comments:,}")
    print(f"✓ Average Engagement Rate: {avg_engagement:.2f}%")
    print(f"✓ Average Views per Video: {total_views // len(videos_data):,}")
    
    # Best performer
    best_video = max(videos_data, key=lambda x: x["views"])
    print(f"\n🏆 Best Performer: {best_video['title']}")
    print(f"   Views: {best_video['views']:,}")
    
    return {
        "total_views": total_views,
        "avg_engagement": avg_engagement,
        "videos": videos_data
    }

def generate_recommendations(analysis):
    """Generate actionable recommendations based on analysis."""
    
    print("\n\n" + "="*80)
    print("💡 RECOMMENDATIONS FOR GROWTH")
    print("="*80)
    
    avg_engagement = analysis["avg_engagement"]
    videos = analysis["videos"]
    
    # Engage rate benchmarks
    recommendations = []
    
    # 1. Engagement optimization
    if avg_engagement < 2:
        recommendations.append({
            "priority": "🔴 HIGH",
            "category": "Engagement Optimization",
            "issue": f"Average engagement rate is only {avg_engagement:.2f}% (industry benchmark: 3-5% for mystery content)",
            "solutions": [
                "✓ Add call-to-action in video (\"Like if you believe...\" at key moments)",
                "✓ Pin comment asking for viewer theories/opinions in first 5 minutes",
                "✓ Create Discord/community post for longer discussions",
                "✓ Add end-screen cards linking to related Obscura videos"
            ]
        })
    elif avg_engagement < 3:
        recommendations.append({
            "priority": "🟡 MEDIUM",
            "category": "Engagement Boost",
            "issue": f"Engagement at {avg_engagement:.2f}% - room for improvement",
            "solutions": [
                "✓ Test different CTA timing in video",
                "✓ Update pinned comment with mystery-solving contest",
                "✓ Create 30-second teaser clips for TikTok/Shorts"
            ]
        })
    else:
        recommendations.append({
            "priority": "🟢 GOOD",
            "category": "Engagement Performance",
            "issue": f"Engagement rate at {avg_engagement:.2f}% - above average!",
            "solutions": [
                "✓ Replicate high-engagement patterns in new videos",
                "✓ Analyze comments to understand what drives reactions"
            ]
        })
    
    # 2. Title & Metadata optimization
    recommendations.append({
        "priority": "🟠 MEDIUM",
        "category": "Title & SEO Optimization",
        "issue": "Mystery titles with numbers/dashes perform differently",
        "solutions": [
            "✓ A/B test titles: Compare current format vs 'SOLVED' / 'UNSOLVED' markers",
            "✓ Add emotional keywords: 'Haunted', 'Cursed', 'Mysterious'",
            "✓ Include [FULL INVESTIGATION] or [DOCUMENTARY] tags",
            "✓ Test timestamps: 'Case #1', 'Cold Case', 'Supernatural' in title"
        ]
    })
    
    # 3. Thumbnail optimization
    recommendations.append({
        "priority": "🟡 HIGH",
        "category": "Thumbnail Strategy",
        "issue": "Mystery/Obscura content benefits from high-impact thumbnails",
        "solutions": [
            "✓ Add red circles/arrows pointing to key elements",
            "✓ Use high-contrast faces (shocked/intrigued expressions)",
            "✓ Test question marks, exclamation points, '?' emojis",
            "✓ A/B test: Current design vs alternative with text overlay",
            "✓ Example: High-engagement mystery YouTubers use bold, contrasting colors"
        ]
    })
    
    # 4. Description & Tags
    recommendations.append({
        "priority": "🟡 MEDIUM",
        "category": "Description & Tags",
        "issue": "Mystery content thrives on keyword precision",
        "solutions": [
            "✓ Add timestamps for key moments (\"3:15 - The evidence\", \"5:22 - Witness account\")",
            "✓ Include related queries: \"unsolved mysteries\", \"true crime\", \"paranormal\"",
            "✓ Link to related Obscura videos in description",
            "✓ Add hashtags: #UnsolvedMysteries #MysteryDocumentary #TrueStories",
            "✓ Cross-reference similar cases in description"
        ]
    })
    
    # 5. Audience retention strategy
    recommendations.append({
        "priority": "🔴 CRITICAL",
        "category": "Audience Retention",
        "issue": "Long-form mystery content needs pacing strategy",
        "solutions": [
            "✓ Hook viewer in first 15 seconds with shocking statement",
            "✓ Add 'plot twist' moments every 2-3 minutes to maintain tension",
            "✓ Include dramatic music crescendos before revelations",
            "✓ Test intro length: Shorten intro significantly for mystery genre",
            "✓ Add on-screen text highlighting key clues (viewers stay longer)"
        ]
    })
    
    # 6. Upload timing & frequency
    recommendations.append({
        "priority": "🟡 MEDIUM",
        "category": "Upload Strategy",
        "issue": "Consistency drives algorithm favorability",
        "solutions": [
            "✓ Establish weekly release schedule (e.g., every Friday 2 PM UTC)",
            "✓ Create 'series' feeling: 'Obscura Files Ep. 1, 2, 3...'",
            "✓ Use community tab to tease next episode",
            "✓ Cross-promote with Shorts (clips from long-form in Reels)"
        ]
    })
    
    # 7. Shorts strategy
    recommendations.append({
        "priority": "🟢 HIGH",
        "category": "Shorts Multiplier Effect",
        "issue": "YouTube Shorts can drive long-form viewership",
        "solutions": [
            "✓ Extract 55-59s mystery cliffhangers from long-form videos",
            "✓ Create series: 'Mystery Shorts - Unsolved Cases'",
            "✓ Link Shorts to full videos (use Cards/End screens)",
            "✓ Post 3x per week on Shorts for maximum algorithm boost",
            "✓ Shorts success = more long-form recommendations"
        ]
    })
    
    # 8. Comment strategy
    recommendations.append({
        "priority": "🟡 MEDIUM",
        "category": "Community Engagement",
        "issue": "High comment engagement signals quality to algorithm",
        "solutions": [
            "✓ Pin thought-provoking question within first hour (\"What's your theory?\")",
            "✓ Reply to top comments with follow-up mystery questions",
            "✓ Create 'Best Theory' thread in comments",
            "✓ Monitor for conspiracy theories and engage respectfully"
        ]
    })
    
    # Print recommendations
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['priority']} {rec['category']}")
        print(f"   Issue: {rec['issue']}")
        print(f"   Solutions:")
        for solution in rec['solutions']:
            print(f"   {solution}")
    
    return recommendations

def main():
    """Main analysis pipeline."""
    youtube = get_youtube_service()
    if not youtube:
        return
    
    print("\n🔍 Fetching Obscura Files video statistics...")
    
    videos_data = []
    for video_id, title in OBSCURA_VIDEOS.items():
        print(f"   Analyzing: {title[:50]}...")
        stats = get_video_stats(youtube, video_id)
        if stats:
            videos_data.append(stats)
    
    if not videos_data:
        print("❌ No video data retrieved. Check API credentials and video IDs.")
        return
    
    # Perform analysis
    analysis = analyze_performance(videos_data)
    
    # Generate recommendations
    recommendations = generate_recommendations(analysis)
    
    # Save detailed report
    report = {
        "timestamp": datetime.now().isoformat(),
        "analysis": analysis,
        "recommendations": recommendations
    }
    
    report_path = Path("output/obscura_performance_analysis.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Detailed report saved to: {report_path}")
    print("\n" + "="*80)
    print("🚀 ACTION ITEMS (Immediate)")
    print("="*80)
    print("1. Test new title format with emotional keywords")
    print("2. Regenerate thumbnails with A/B testing")
    print("3. Create 3x Shorts from existing long-form content")
    print("4. Update video descriptions with timestamps & cross-links")
    print("5. Pin engagement-driving comment in first hour of upload")
    print("\n")

if __name__ == "__main__":
    main()
