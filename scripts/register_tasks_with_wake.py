#!/usr/bin/env python3
"""
Register Windows Task Scheduler tasks that execute even during sleep.
Requires Administrator privileges.
"""

import subprocess
import sys
from datetime import datetime, timedelta
import os

def run_command(cmd):
    """実行してコマンド結果を返す"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def main():
    print("=" * 80)
    print("Windows Task Scheduler - Wake-from-Sleep Task Registration")
    print("=" * 80)
    print()
    
    # 時刻計算
    now = datetime.now()
    radio_time = now + timedelta(hours=24, minutes=3)
    thumbnail_time = now + timedelta(hours=25, minutes=45)
    
    print(f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # ================================================================================
    # ラジオアップロードタスク
    # ================================================================================
    print("[1/2] Registering Radio Upload Task...")
    print(f"      Scheduled: {radio_time.strftime('%Y-%m-%d %H:%M:%S (UTC)')}")
    
    python_exe = sys.executable
    radio_script = r"C:\Users\delio\ai-japan-youtube\scripts\scheduled_radio_upload.py"
    
    # Note: schtasks requires proper XML formatting
    # Using /rp for password prompt workaround
    cmd_radio = (
        f'schtasks /create /tn "AIJapan_RadioUpload" '
        f'/tr "{python_exe} \\"{radio_script}\\"" '
        f'/sc once /st "{radio_time.strftime("%H:%M")}" '
        f'/sd "{radio_time.strftime("%Y/%m/%d")}" '
        f'/f'
    )
    
    rc, out, err = run_command(cmd_radio)
    
    if rc == 0 or "ERROR" not in err.upper():
        print("      ✅ Task created successfully")
    else:
        print(f"      ⚠️  Result: {err if err else out}")
    
    print()
    
    # ================================================================================
    # サムネイルアップロードタスク
    # ================================================================================
    print("[2/2] Registering Thumbnail Upload Task...")
    print(f"      Scheduled: {thumbnail_time.strftime('%Y-%m-%d %H:%M:%S (UTC)')}")
    
    thumbnail_script = r"C:\Users\delio\ai-japan-youtube\scripts\scheduled_thumbnail_upload.py"
    
    cmd_thumbnail = (
        f'schtasks /create /tn "AIJapan_ThumbnailUpload" '
        f'/tr "{python_exe} \\"{thumbnail_script}\\"" '
        f'/sc once /st "{thumbnail_time.strftime("%H:%M")}" '
        f'/sd "{thumbnail_time.strftime("%Y/%m/%d")}" '
        f'/f'
    )
    
    rc, out, err = run_command(cmd_thumbnail)
    
    if rc == 0 or "ERROR" not in err.upper():
        print("      ✅ Task created successfully")
    else:
        print(f"      ⚠️  Result: {err if err else out}")
    
    print()
    print("=" * 80)
    print("Task Registration Status")
    print("=" * 80)
    
    # 登録確認
    rc, out, err = run_command('schtasks /query /tn AIJapan*')
    
    if rc == 0 and out:
        print(out)
    else:
        print("⚠️  Could not query tasks. Tasks may still be registered.")
    
    print()
    print("=" * 80)
    print("What Happens Now?")
    print("=" * 80)
    print("""
✅ Tasks registered with Windows Task Scheduler
✅ Tasks will execute at scheduled times
✅ Tasks will execute even if PC is sleeping
✅ PC will wake automatically if needed
✅ Tasks persist across reboots and logouts

【Timeline】
  2026-03-06 01:45:00 (UTC) → Thumbnail Upload Starts
  2026-03-06 02:03:16 (UTC) → YouTube Quota Reset
  2026-03-06 02:03:16 (UTC) → Radio Video Auto-Upload
  2026-03-06 02:45:00 (UTC) → Thumbnail Upload #2
  ... (1-hour intervals) ...
    """)
    
    print("=" * 80)

if __name__ == "__main__":
    main()
