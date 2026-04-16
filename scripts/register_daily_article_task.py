#!/usr/bin/env python3
"""
Register article auto-generation task in Windows Task Scheduler.
Runs daily at 09:00 UTC to generate and publish a new article.
"""

import subprocess
import sys
from datetime import datetime, time

def main():
    print("=" * 80)
    print("REGISTER ARTICLE AUTO-GENERATION TASK")
    print("=" * 80)
    print()
    
    python_exe = sys.executable
    script_path = r"C:\Users\delio\ai-japan-youtube\scripts\simple_article_gen_publish.py"
    
    # Create task for daily article generation at 09:00 UTC
    task_name = "AIJapan_DailyArticleGeneration"
    
    cmd = (
        f'schtasks /create /tn "{task_name}" '
        f'/tr "{python_exe} \\"{script_path}\\"" '
        f'/sc daily /st 09:00 '
        f'/f'
    )
    
    print("📋 Registering daily article generation task...")
    print(f"   Task: {task_name}")
    print(f"   Schedule: Daily at 09:00 UTC")
    print(f"   Script: {script_path}")
    print()
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✅ Task registered successfully!")
            print()
            print("【What this means】")
            print("  ✓ Every day at 09:00 UTC:")
            print("    1. Latest video metadata is retrieved")
            print("    2. Article is automatically generated using Claude AI")
            print("    3. Article is published to Substack")
            print("    4. Email notifications sent to subscribers")
            print()
            print("【To verify】")
            print("  • Open Task Scheduler (Windows key → Task Scheduler)")
            print(f'  • Look for task: "{task_name}"')
            print("  • Right-click → Run to execute immediately")
            print()
        else:
            print(f"⚠️  Task creation result: {result.stderr if result.stderr else result.stdout}")
            print()
            if "already exists" in result.stderr.lower():
                print("ℹ️  Task already exists. Skipping creation.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    print("=" * 80)
    return 0

if __name__ == "__main__":
    sys.exit(main())
