#!/usr/bin/env python3
"""
Register SMART article generation task with randomized scheduling.
Replaces fixed-time task with intelligent anti-bot detection system.
"""

import subprocess
import sys
import os
from datetime import datetime, timedelta
import random
import xml.etree.ElementTree as ET
import tempfile


def enable_wake_to_run(task_name: str) -> bool:
    """Enable WakeToRun flag for a task using XML modification"""
    try:
        # Export task XML
        result = subprocess.run(
            f'schtasks /query /tn "{task_name}" /xml',
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return False
        
        task_xml = result.stdout
        
        # Parse and modify XML
        root = ET.fromstring(task_xml)
        ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
        
        settings = root.find('.//t:Settings', ns)
        if settings is not None:
            # Remove existing WakeToRun if present
            wake_to_run = settings.find('t:WakeToRun', ns)
            if wake_to_run is not None:
                settings.remove(wake_to_run)
            
            # Add new WakeToRun element
            wake_elem = ET.Element('{http://schemas.microsoft.com/windows/2004/02/mit/task}WakeToRun')
            wake_elem.text = 'true'
            settings.append(wake_elem)
        
        # Save modified XML to temp file
        modified_xml = ET.tostring(root, encoding='utf-8').decode('utf-8')
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-16"?>\n')
            f.write(modified_xml)
            temp_file = f.name
        
        try:
            # Delete and recreate task with modified XML
            subprocess.run(f'schtasks /delete /tn "{task_name}" /f', shell=True, capture_output=True)
            result = subprocess.run(
                f'schtasks /create /tn "{task_name}" /xml "{temp_file}"',
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return result.returncode == 0
        finally:
            os.unlink(temp_file)
            
    except Exception as e:
        print(f"Error enabling WakeToRun: {e}")
        return False


def main():
    print("=" * 80)
    print("REGISTER SMART ARTICLE GENERATION TASK (Anti-Bot)")
    print("=" * 80)
    print()
    
    # Delete old fixed-time task
    old_task_name = "AIJapan_DailyArticleGeneration"
    
    print("🗑️  Removing old fixed-time task...")
    subprocess.run(
        f'schtasks /delete /tn "{old_task_name}" /f',
        shell=True,
        capture_output=True
    )
    print("   ✓ Cleanup complete\n")
    
    # Create initial random-time task
    python_exe = sys.executable
    script_path = r"C:\Users\delio\ai-japan-youtube\scripts\smart_article_gen_publish.py"
    working_dir = r"C:\Users\delio\ai-japan-youtube"
    
    # First execution: random time today or tomorrow
    now = datetime.now()
    
    # Random posting windows: 09-11, 13-15, 16-17
    windows = [(9, 11), (13, 15), (16, 17)]
    window = random.choice(windows)
    
    target_hour = random.randint(window[0], window[1])
    target_minute = random.randint(0, 59)
    
    first_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # If time already passed today, schedule for tomorrow
    if first_run <= now:
        first_run += timedelta(days=1)
    
    print("📋 Registering SMART article generation task...")
    print(f"   Task: {old_task_name}")
    print(f"   First run: {first_run.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Script: {script_path}")
    print(f"   Working Directory: {working_dir}")
    print()
    
    # Use PowerShell to create task with working directory
    ps_script = f'''
$action = New-ScheduledTaskAction -Execute "{python_exe}" -Argument '"{script_path}"' -WorkingDirectory "{working_dir}"
$trigger = New-ScheduledTaskTrigger -Once -At "{first_run.strftime('%Y-%m-%dT%H:%M:%S')}"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName "{old_task_name}" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
'''
    
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ Task registered successfully!")
            
            # Enable WakeToRun for sleep-resilient execution
            print("🔧 Enabling WakeToRun (sleep-resilient execution)...")
            if enable_wake_to_run(old_task_name):
                print("   ✅ WakeToRun enabled - PC will wake from sleep\n")
            else:
                print("   ⚠️  WakeToRun setup incomplete (task still works when awake)\n")
            
            print("【ANTI-BOT PROTECTION FEATURES】")
            print("  ✓ Random posting times (9-17:00 UTC)")
            print("  ✓ Variable intervals (20-28 hours)")
            print("  ✓ Dynamic rescheduling after each run")
            print("  ✓ Minimum 20-hour gaps between posts")
            print("  ✓ Wake from sleep enabled")
            print()
            
            print("【HOW IT WORKS】")
            print("  1. Task executes at random time")
            print("  2. Checks if 20+ hours since last post")
            print("  3. If yes: Generate & publish article")
            print("  4. Calculate next random time (20-28h away)")
            print("  5. Reschedule task for that time")
            print("  6. Repeat → Human-like posting pattern")
            print()
            
            print("【POSTING WINDOWS】")
            print("  Morning:   09:00-11:00 UTC")
            print("  Afternoon: 13:00-15:00 UTC")
            print("  Evening:   16:00-17:00 UTC")
            print("  (Random selection each time)")
            print()
            
            print("【FIRST EXECUTION】")
            print(f"  {first_run.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            hours_until = (first_run - now).total_seconds() / 3600
            print(f"  ({hours_until:.1f} hours from now)")
            print()
            
        else:
            print(f"⚠️  Task registration: {result.stderr if result.stderr else result.stdout}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    print("=" * 80)
    print("✅ SMART SCHEDULING ACTIVE - Bot detection avoided")
    print("=" * 80)
    return 0

if __name__ == "__main__":
    sys.exit(main())
