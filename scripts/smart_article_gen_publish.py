#!/usr/bin/env python3
"""
Smart article generation with randomized scheduling to avoid bot detection.

Features:
- Random time windows (09:00-17:00 UTC)
- Minimum 20-hour interval between posts
- Dynamic task rescheduling
- Human-like posting patterns
"""

import sys
import os
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
import subprocess
import xml.etree.ElementTree as ET
import tempfile

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load environment first
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.article_generator import ArticleGenerator
from src.substack_publisher import SubstackPublisher
from src.utils import setup_logger

logger = setup_logger("smart_article_gen")

# Configuration
STATE_FILE = ROOT / "output" / "article_schedule_state.json"
TASK_NAME = "AIJapan_DailyArticleGeneration"

# Posting time windows (UTC hours)
POSTING_WINDOWS = [
    (9, 11),   # Morning: 09:00-11:00
    (13, 15),  # Afternoon: 13:00-15:00
    (16, 17),  # Evening: 16:00-17:00
]

MIN_INTERVAL_HOURS = 20  # Minimum 20 hours between posts
MAX_INTERVAL_HOURS = 28  # Maximum 28 hours between posts


def load_state() -> dict:
    """Load last execution state"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def save_state(state: dict):
    """Save execution state"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def should_execute() -> tuple[bool, str]:
    """Check if enough time has passed since last execution"""
    state = load_state()
    last_run = state.get("last_execution")
    
    if not last_run:
        return True, "First execution"
    
    try:
        last_dt = datetime.fromisoformat(last_run)
        now = datetime.now()
        hours_since = (now - last_dt).total_seconds() / 3600
        
        if hours_since >= MIN_INTERVAL_HOURS:
            return True, f"Interval OK ({hours_since:.1f}h since last run)"
        else:
            remaining = MIN_INTERVAL_HOURS - hours_since
            return False, f"Too soon ({remaining:.1f}h remaining)"
    except:
        return True, "Invalid last run timestamp"


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
        logger.error(f"Error enabling WakeToRun: {e}")
        return False


def get_next_random_time() -> datetime:
    """Calculate next random execution time"""
    now = datetime.now()
    
    # Random interval: 20-28 hours from now
    interval_hours = random.uniform(MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS)
    next_time = now + timedelta(hours=interval_hours)
    
    # Adjust to random posting window
    window = random.choice(POSTING_WINDOWS)
    target_hour = random.randint(window[0], window[1])
    target_minute = random.randint(0, 59)
    
    next_time = next_time.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # If calculated time is in the past, add 1 day
    if next_time <= now:
        next_time += timedelta(days=1)
    
    return next_time


def reschedule_task(next_time: datetime) -> bool:
    """Update Windows Task Scheduler with new random time (with WakeToRun enabled)"""
    try:
        # Use batch file wrapper (no admin privileges required)
        batch_file = str(ROOT / "scripts" / "run_smart_article_gen.bat")
        
        # Delete existing task
        subprocess.run(
            f'schtasks /delete /tn "{TASK_NAME}" /f',
            shell=True,
            capture_output=True,
            timeout=10
        )
        
        # Create new task using schtasks (no admin required)
        cmd = f'''schtasks /create /tn "{TASK_NAME}" /tr "{batch_file}" /sc once /st {next_time.strftime("%H:%M")} /sd {next_time.strftime("%Y/%m/%d")} /f'''
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            # Enable WakeToRun using XML modification
            enable_wake_to_run(TASK_NAME)
            logger.info(f"Task rescheduled for {next_time.strftime('%Y-%m-%d %H:%M:%S')} (WakeToRun enabled)")
            return True
        else:
            logger.warning(f"Task reschedule failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error rescheduling task: {e}")
        return False


def generate_and_publish_article() -> bool:
    """Main article generation and publication logic"""
    
    # Load latest metadata
    metadata_file = ROOT / "output" / "metadata_verification.json"
    
    if not metadata_file.exists():
        logger.error("No metadata file found")
        return False
    
    try:
        with open(metadata_file, encoding='utf-8') as f:
            all_metadata = json.load(f)
        
        if not all_metadata:
            logger.error("No metadata records")
            return False
        
        latest_meta = all_metadata[-1]
        
        logger.info(f"Latest video: {latest_meta.get('title', 'Unknown')}")
        
        # Get narration
        narration_file = ROOT / "output" / "narration.txt"
        if narration_file.exists():
            with open(narration_file, encoding='utf-8') as f:
                narration = f.read()
        else:
            narration = f"{latest_meta.get('title', '')}. {latest_meta.get('description', '')}"
        
        if not narration or len(narration) < 50:
            logger.warning(f"Limited narration: {len(narration)} chars")
            narration = f"{latest_meta.get('title', '')}. {latest_meta.get('description', '')}"
        
        # Generate article
        logger.info("Generating article...")
        gen = ArticleGenerator()
        article = gen.generate_from_data(latest_meta, narration)
        
        if not article:
            logger.error("Article generation failed")
            return False
        
        logger.info(f"Article generated: {article['title']}")
        
        # Publish to Substack
        logger.info("Publishing to Substack...")
        pub = SubstackPublisher()
        
        result = pub.publish(
            title=article["title"],
            content=article["content"],
            subtitle=article.get("subtitle", ""),
            tags=["Japan", "Culture", "Travel"]
        )
        
        if result and result.get("url"):
            logger.info(f"Published: {result['url']}")
            return True
        else:
            logger.error(f"Publish failed: {result}")
            return False
            
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "=" * 70)
    print("SMART ARTICLE GENERATION (Anti-Bot Detection)")
    print("=" * 70 + "\n")
    
    # Check if we should execute
    should_run, reason = should_execute()
    
    print(f"📋 Execution Check: {reason}")
    
    if not should_run:
        print("⏸️  Skipping execution (too soon)")
        print(f"   {reason}")
        
        # Still reschedule for next random time
        next_time = get_next_random_time()
        print(f"\n🔄 Next execution scheduled: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
        reschedule_task(next_time)
        return 0
    
    print("✅ Proceeding with article generation\n")
    
    # Execute article generation
    success = generate_and_publish_article()
    
    if success:
        # Update state
        state = {
            "last_execution": datetime.now().isoformat(),
            "last_success": True
        }
        save_state(state)
        
        print("\n✅ Article successfully generated and published!")
        
        # Schedule next random execution
        next_time = get_next_random_time()
        hours_until = (next_time - datetime.now()).total_seconds() / 3600
        
        print(f"\n🔄 Next execution:")
        print(f"   Time: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Interval: {hours_until:.1f} hours from now")
        
        reschedule_task(next_time)
        
        print("\n" + "=" * 70)
        print("✅ COMPLETE - Task rescheduled with random timing")
        print("=" * 70 + "\n")
        
        return 0
    else:
        print("\n❌ Article generation or publication failed")
        
        # Still reschedule even on failure
        next_time = get_next_random_time()
        print(f"\n🔄 Rescheduling retry: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
        reschedule_task(next_time)
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
