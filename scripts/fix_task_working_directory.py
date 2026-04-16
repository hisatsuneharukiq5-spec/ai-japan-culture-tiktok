#!/usr/bin/env python3
"""
Fix existing task by adding working directory via XML modification.
"""

import subprocess
import sys
import os
import xml.etree.ElementTree as ET
import tempfile

TASK_NAME = "AIJapan_DailyArticleGeneration"
WORKING_DIR = r"C:\Users\delio\ai-japan-youtube"

def fix_task_working_directory():
    """Add WorkingDirectory to existing task"""
    try:
        print("=" * 80)
        print("TASK WORKING DIRECTORY FIX")
        print("=" * 80)
        print()
        
        # Export current task XML
        print("1. Exporting current task configuration...")
        result = subprocess.run(
            f'schtasks /query /tn "{TASK_NAME}" /xml',
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print(f"❌ Failed to export task: {result.stderr}")
            return False
        
        task_xml = result.stdout
        print("   ✓ Task exported")
        
        # Parse XML
        print("2. Parsing and modifying XML...")
        root = ET.fromstring(task_xml)
        ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
        
        # Find Actions section
        actions = root.find('.//t:Actions', ns)
        if actions is None:
            print("   ❌ Actions section not found")
            return False
        
        # Find Exec action
        exec_action = actions.find('.//t:Exec', ns)
        if exec_action is None:
            print("   ❌ Exec action not found")
            return False
        
        # Check if WorkingDirectory already exists
        working_dir_elem = exec_action.find('t:WorkingDirectory', ns)
        if working_dir_elem is not None:
            print(f"   ℹ️  WorkingDirectory already set: {working_dir_elem.text}")
            if working_dir_elem.text == WORKING_DIR:
                print("   ✓ WorkingDirectory is correct")
                return True
            else:
                # Update it
                working_dir_elem.text = WORKING_DIR
        else:
            # Add WorkingDirectory element
            wd_elem = ET.Element('{http://schemas.microsoft.com/windows/2004/02/mit/task}WorkingDirectory')
            wd_elem.text = WORKING_DIR
            exec_action.append(wd_elem)
        
        print(f"   ✓ WorkingDirectory set to: {WORKING_DIR}")
        
        # Save modified XML to temp file
        print("3. Saving modified configuration...")
        modified_xml = ET.tostring(root, encoding='utf-8').decode('utf-8')
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-16"?>\n')
            f.write(modified_xml)
            temp_file = f.name
        
        print(f"   ✓ Temp file: {temp_file}")
        
        try:
            # Delete and recreate task with modified XML
            print("4. Updating task...")
            subprocess.run(f'schtasks /delete /tn "{TASK_NAME}" /f', shell=True, capture_output=True)
            
            result = subprocess.run(
                f'schtasks /create /tn "{TASK_NAME}" /xml "{temp_file}"',
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print("   ✅ Task updated successfully!")
                return True
            else:
                print(f"   ❌ Failed to update: {result.stderr}")
                return False
        finally:
            os.unlink(temp_file)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_task():
    """Verify task configuration"""
    print()
    print("5. Verifying configuration...")
    
    result = subprocess.run(
        f'schtasks /query /tn "{TASK_NAME}" /xml',
        shell=True,
        capture_output=True,
        text=True
    )
    
    if 'WorkingDirectory' in result.stdout and WORKING_DIR in result.stdout:
        print(f"   ✅ WorkingDirectory confirmed: {WORKING_DIR}")
        return True
    else:
        print("   ⚠️  WorkingDirectory not found in task configuration")
        return False

def main():
    if fix_task_working_directory():
        if verify_task():
            print()
            print("=" * 80)
            print("✅ TASK CONFIGURATION FIXED")
            print("=" * 80)
            print()
            print("【What was fixed】")
            print(f"  • Added WorkingDirectory: {WORKING_DIR}")
            print("  • Task will now execute in the correct directory")
            print("  • .env file will be loaded properly")
            print()
            print("【Next execution】")
            print("  • Task is ready to run")
            print("  • Monitor logs for successful execution")
            print()
            return 0
        else:
            print()
            print("⚠️  Verification failed but task may still work")
            return 1
    else:
        print()
        print("❌ Failed to fix task")
        return 1

if __name__ == "__main__":
    sys.exit(main())
