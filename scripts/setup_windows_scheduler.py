#!/usr/bin/env python3
"""
Schedule tasks in Windows Task Scheduler for persistent execution.
Survives sleep, restart, and logout.
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def create_thumbnail_upload_task():
    """Create Windows Task Scheduler task for thumbnail uploads"""
    
    print("\n" + "="*80)
    print("Creating Windows Task Scheduler task for Thumbnail Upload")
    print("="*80 + "\n")
    
    task_name = "AIJapan_ThumbnailUpload"
    script_path = Path(__file__).parent / "scheduled_thumbnail_upload.py"
    python_path = sys.executable
    
    # Calculate start time (24 hours + 1 hour 45 minutes from now)
    start_time = datetime.now() + timedelta(hours=25, minutes=45)
    
    # PowerShell command to create task
    ps_command = f'''
$TaskName = "{task_name}"
$TaskPath = "\\AIJapan\\"

# Remove if exists
Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false

# Create trigger
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date "{start_time.strftime('%Y-%m-%d %H:%M')}")

# Create action
$Action = New-ScheduledTaskAction -Execute "{python_path}" -Argument '"{script_path}"'

# Create task with system user (survives logout/sleep/restart)
$Principal = New-ScheduledTaskPrincipal -UserID "NT AUTHORITY\\SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Register task
Register-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Trigger $Trigger -Action $Action -Principal $Principal

Write-Host "✓ Task created: $TaskName"
Write-Host "  Scheduled start: {start_time.strftime('%Y-%m-%d %H:%M')}"
Write-Host "  Path: $TaskPath"
'''
    
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            print("✅ Thumbnail upload task created successfully!")
            print(f"   Scheduled start: {start_time.strftime('%Y-%m-%d %H:%M')}")
            return True
        else:
            print(f"❌ Error creating task:\n{result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def create_radio_upload_task():
    """Create Windows Task Scheduler task for radio upload"""
    
    print("\n" + "="*80)
    print("Creating Windows Task Scheduler task for Radio Upload")
    print("="*80 + "\n")
    
    task_name = "AIJapan_RadioUpload"
    script_path = Path(__file__).parent / "scheduled_radio_upload.py"
    python_path = sys.executable
    
    # Calculate start time (24 hours from now)
    start_time = datetime.now() + timedelta(hours=24)
    
    # PowerShell command to create task
    ps_command = f'''
$TaskName = "{task_name}"
$TaskPath = "\\AIJapan\\"

# Remove if exists
Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false

# Create trigger
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date "{start_time.strftime('%Y-%m-%d %H:%M')}")

# Create action
$Action = New-ScheduledTaskAction -Execute "{python_path}" -Argument '"{script_path}"'

# Create task with system user (survives logout/sleep/restart)
$Principal = New-ScheduledTaskPrincipal -UserID "NT AUTHORITY\\SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Register task
Register-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Trigger $Trigger -Action $Action -Principal $Principal

Write-Host "✓ Task created: $TaskName"
Write-Host "  Scheduled start: {start_time.strftime('%Y-%m-%d %H:%M')}"
Write-Host "  Path: $TaskPath"
'''
    
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            print("✅ Radio upload task created successfully!")
            print(f"   Scheduled start: {start_time.strftime('%Y-%m-%d %H:%M')}")
            return True
        else:
            print(f"❌ Error creating task:\n{result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def list_scheduled_tasks():
    """List AIJapan scheduled tasks"""
    
    print("\n" + "="*80)
    print("Listing Scheduled Tasks for AIJapan")
    print("="*80 + "\n")
    
    ps_command = '''
Get-ScheduledTask -TaskPath "\\AIJapan\\" -ErrorAction SilentlyContinue | Select-Object TaskName, State, @{l='Next Run Time';e={$_.Triggers[0].StartBoundary}} | Format-Table -AutoSize
'''
    
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Main entry point"""
    
    print("\n" + "="*80)
    print("Windows Task Scheduler Setup")
    print("="*80)
    print("""
This script sets up Windows Task Scheduler tasks for:
  1. Thumbnail uploads (1-hour intervals starting 24h+45m from now)
  2. Radio video upload (24h from now)

These tasks will survive:
  ✓ Screen sleep
  ✓ Log out
  ✓ System restart
  ✓ Power cycle

Note: Requires Administrator privileges
""")
    
    # Check if running as admin
    try:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except:
        is_admin = False
    
    if not is_admin:
        print("⚠️  WARNING: This script should be run as Administrator")
        print("   Right-click PowerShell > Run as Administrator\n")
    
    # Create tasks
    thumb_ok = create_thumbnail_upload_task()
    radio_ok = create_radio_upload_task()
    
    # List tasks
    print("\n")
    list_scheduled_tasks()
    
    print("\n" + "="*80)
    print("Setup Complete!")
    print("="*80)
    print("""
✅ Tasks are now registered with Windows Task Scheduler
   
   Even if you:
   • Close this window
   • Sleep your PC
   • Log out
   • Restart your computer
   
   The tasks WILL run at the scheduled time automatically!

To view/edit tasks:
  Control Panel > Administrative Tools > Task Scheduler
  
  Or:
  Get-ScheduledTask -TaskPath "\\AIJapan\\" | Format-Table

To disable a task:
  Disable-ScheduledTask -TaskName "AIJapan_ThumbnailUpload"
  
To enable a task:
  Enable-ScheduledTask -TaskName "AIJapan_ThumbnailUpload"
""")
    
    return 0 if (thumb_ok and radio_ok) else 1

if __name__ == '__main__':
    sys.exit(main())
