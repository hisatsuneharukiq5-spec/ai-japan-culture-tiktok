#!/usr/bin/env python3
"""
Register smart article generation task using batch file wrapper.
This approach doesn't require admin privileges.
"""

import subprocess
import sys
from datetime import datetime, timedelta
import random
import os

TASK_NAME = "AIJapan_DailyArticleGeneration"
WORKSPACE = r"C:\Users\delio\ai-japan-youtube"
BATCH_FILE = os.path.join(WORKSPACE, r"scripts\run_smart_article_gen.bat")

def get_random_first_run():
    """Get random execution time within next 24 hours"""
    # Random time windows (UTC): 09-11, 13-15, 16-17
    windows = [
        (9, 11),   # 09:00-11:00
        (13, 15),  # 13:00-15:00
        (16, 17),  # 16:00-17:00
    ]
    
    start_hour, end_hour = random.choice(windows)
    random_hour = random.randint(start_hour, end_hour)
    random_minute = random.randint(0, 59)
    
    now = datetime.now()
    first_run = now.replace(hour=random_hour, minute=random_minute, second=0, microsecond=0)
    
    # If time already passed today, schedule for tomorrow
    if first_run <= now:
        first_run += timedelta(days=1)
    
    return first_run

def register_task():
    """Register task using batch file wrapper"""
    try:
        print("=" * 80)
        print("SMART ARTICLE GENERATION TASK REGISTRATION")
        print("=" * 80)
        print()
        
        # Get random first run time
        first_run = get_random_first_run()
        first_run_str = first_run.strftime("%Y/%m/%d %H:%M")
        
        print(f"📋 Task Configuration:")
        print(f"   • Name: {TASK_NAME}")
        print(f"   • Wrapper: {BATCH_FILE}")
        print(f"   • First run: {first_run_str}")
        print(f"   • Interval: Dynamic (20-28 hours)")
        print()
        
        # Delete old task if exists
        print("1. Cleaning up old tasks...")
        subprocess.run(
            f'schtasks /delete /tn "{TASK_NAME}" /f',
            shell=True,
            capture_output=True
        )
        print("   ✓ Cleanup complete")
        
        # Create new task with batch file
        print("2. Registering new task...")
        # Note: Remove /rl HIGHEST as it requires admin privileges
        cmd = f'''schtasks /create /tn "{TASK_NAME}" /tr "{BATCH_FILE}" /sc once /st {first_run.strftime("%H:%M")} /sd {first_run.strftime("%Y/%m/%d")} /f'''
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"   ❌ Registration failed: {result.stderr}")
            return False
        
        print("   ✅ Task registered successfully!")
        
        # Enable WakeToRun
        print("3. Enabling WakeToRun...")
        sys.path.insert(0, os.path.join(WORKSPACE, 'scripts'))
        from enable_wake_to_run import enable_wake_to_run_for_task
        
        if enable_wake_to_run_for_task(TASK_NAME):
            print("   ✅ WakeToRun enabled")
        else:
            print("   ⚠️  WakeToRun may not be enabled")
        
        # Verify
        print("4. Verifying task...")
        result = subprocess.run(
            f'schtasks /query /tn "{TASK_NAME}" /fo list',
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("   ✅ Task verified")
            print()
            print("=" * 80)
            print("✅ REGISTRATION COMPLETE")
            print("=" * 80)
            print()
            print("【Task Details】")
            print(f"  • Task name: {TASK_NAME}")
            print(f"  • First execution: {first_run_str}")
            print(f"  • Working directory: {WORKSPACE}")
            print(f"  • Script: scripts\\smart_article_gen_publish.py")
            print()
            print("【Behavior】")
            print("  • Runs at random times (09-11, 13-15, 16-17 UTC)")
            print("  • Auto-reschedules 20-28 hours after each run")
            print("  • Wakes PC from sleep if needed")
            print("  • Generates article from latest video")
            print("  • Publishes to Substack automatically")
            print()
            print("【Manual Test】")
            print(f"  schtasks /run /tn \"{TASK_NAME}\"")
            print()
            return True
        else:
            print(f"   ❌ Verification failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    if not os.path.exists(BATCH_FILE):
        print(f"❌ Batch file not found: {BATCH_FILE}")
        return 1
    
    if register_task():
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
