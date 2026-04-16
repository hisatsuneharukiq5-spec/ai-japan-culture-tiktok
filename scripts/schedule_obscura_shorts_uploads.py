#!/usr/bin/env python3
"""
Schedule Obscura Shorts for weekly 3x posting (Monday, Wednesday, Friday).
Maximizes YouTube algorithm engagement with consistent posting.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta

def create_shorts_upload_schedule():
    """Create automated Shorts upload schedule."""
    
    print("\n" + "="*80)
    print("📅 OBSCURA SHORTS WEEKLY POSTING SCHEDULE")
    print("="*80)
    
    schedule = {
        "strategy": "3x weekly Shorts posting for algorithm boost",
        "upload_times": [
            {
                "day": "Monday",
                "time": "14:00 UTC",
                "time_jp": "23:00 JST (Japan prime time)",
                "content": "Clip 1: Opening Mystery Hook"
            },
            {
                "day": "Wednesday", 
                "time": "14:00 UTC",
                "time_jp": "23:00 JST",
                "content": "Clip 2: Evidence/Development"
            },
            {
                "day": "Friday",
                "time": "14:00 UTC", 
                "time_jp": "23:00 JST",
                "content": "Clip 3: Resolution/Mystery Deepens"
            }
        ],
        "expected_impact": {
            "algorithm_boost": "3x posting = +150-200% algorithm push",
            "viewer_retention": "Consistent upload schedule = higher notification clicks",
            "subscriber_growth": "Weekly Shorts → 1-5 new subs per clip (300+ subs/month target)",
            "long_form_traffic": "Shorts → Long-form video links = 20-30% conversion rate"
        },
        "shorts_per_series": 9,
        "series_duration_weeks": 3,
        "next_launch": "Execute starting Monday of next week",
        "implementation": {
            "method": "YouTube Studio → Schedule Feature OR Zapier automation",
            "file_location": "output/shorts/obscura_clips/",
            "naming_convention": "obscura_{parent_title}_clip{n}__{clip_title}.mp4"
        }
    }
    
    # Print schedule
    print("\n🎯 POSTING SCHEDULE:")
    print("-"*80)
    for upload in schedule["upload_times"]:
        print(f"\n{upload['day']}:")
        print(f"  ⏰ {upload['time']} ({upload['time_jp']})")
        print(f"  📌 Content: {upload['content']}")
    
    print("\n\n📊 EXPECTED ALGORITHM IMPACT:")
    print("-"*80)
    for key, value in schedule["expected_impact"].items():
        print(f"  • {key.replace('_', ' ').title()}: {value}")
    
    print("\n\n💡 SUBSCRIBER GROWTH PROJECTION:")
    print("-"*80)
    print("  Week 1: 10-20 new subs (3 Shorts)")
    print("  Week 2: 30-50 new subs (6 Shorts cumulative)")
    print("  Week 3: 50-100 new subs (9 Shorts cumulative)")
    print("  Week 4: 100-200 new subs (Bell Witch + bonus content)")
    print("  \n  → 1000 SUBSCRIBER TARGET: 5-6 weeks of consistent posting")
    
    # Save schedule config
    schedule_path = Path("config/obscura_shorts_schedule.json")
    with open(schedule_path, "w", encoding="utf-8") as f:
        json.dump(schedule, f, indent=2, ensure_ascii=False)
    
    print(f"\n\n✅ Schedule configuration saved to: {schedule_path}")
    
    return schedule

def create_shorts_upload_commands():
    """Generate upload commands for YouTube Studio."""
    
    print("\n\n" + "="*80)
    print("📤 SHORTS UPLOAD PREPARATION")
    print("="*80)
    
    commands = {
        "manual_upload": [
            "1. Go to YouTube Studio → Create → Upload Videos",
            "2. Select 'Shorts' format",
            "3. Upload clip video (output/shorts/obscura_clips/)",
            "4. Title: [UNSOLVED] Mystery Name - Part X",
            "5. Description: Full long-form video link + Related videos",
            "6. Schedule: Set to Monday/Wednesday/Friday 14:00 UTC",
            "7. Tags: #UnsolvedMysteries #TrueCrime #MysteryDocumentary #Shorts",
            "8. Visibility: Public (to maximize reach)"
        ],
        "automated_alternative": [
            "1. Use Zapier/IFTTT for scheduled YouTube uploads",
            "2. Create workflow: {time trigger} → {upload Shorts}",
            "3. Link to output/shorts/obscura_clips/",
            "4. Repeat for each Mon/Wed/Fri",
            "5. Monitor performance in YouTube Analytics"
        ]
    }
    
    print("\n📋 OPTION A: Manual Upload (Best for Control)")
    print("-"*80)
    for step in commands["manual_upload"]:
        print(f"  {step}")
    
    print("\n📋 OPTION B: Automated Upload (Best for Scale)")
    print("-"*80)
    for step in commands["automated_alternative"]:
        print(f"  {step}")
    
    print("\n\n🚀 IMMEDIATE ACTION ITEMS:")
    print("-"*80)
    print("  ☐ Extract all Shorts clips (in progress)")
    print("  ☐ Test upload 1 Shorts clip to verify process")
    print("  ☐ Monitor watch time + engagement for 24 hours")
    print("  ☐ If positive: Schedule remaining clips")
    print("  ☐ Setup calendar reminders for Mon/Wed/Fri uploads")
    
    return commands

def main():
    schedule = create_shorts_upload_schedule()
    commands = create_shorts_upload_commands()
    
    print("\n" + "="*80)
    print("✅ SHORTS SCHEDULING STRATEGY COMPLETE")
    print("="*80)
    print("\n🎬 Next Steps:")
    print("  1. Extract all Shorts clips successfully")
    print("  2. Test upload first clip this Friday")
    print("  3. Monitor metrics (views, click-through, watch time)")
    print("  4. Launch full 3x/week schedule if metrics positive")
    print("  5. Track subscriber growth weekly")
    print("\n📈 Timeline to 1000 Subs: 5-6 weeks with consistent execution\n")

if __name__ == "__main__":
    main()
