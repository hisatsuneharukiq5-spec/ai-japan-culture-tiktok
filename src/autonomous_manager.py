"""Autonomous manager: orchestrates one autonomous cycle.

Design: free-first. Uses trend_research and topic_selector, then calls
the existing pipeline (`src.scheduler.run_pipeline`) to build and publish videos.
Logs decisions and rationale to `output/logs/autonomous_log.txt` and stores artifacts
under `output/autonomous/{timestamp}/`.
"""
from datetime import datetime
from src.utils import setup_logger, PROJECT_ROOT
from src.trend_research import get_candidate_topics
from src.topic_selector import select_topic
import subprocess
import json
from pathlib import Path
import traceback

logger = setup_logger("autonomous")
ARTIFACTS_DIR = PROJECT_ROOT / "output" / "autonomous"
LOG_FILE = PROJECT_ROOT / "output" / "logs" / "autonomous_log.txt"


def _append_log(entry: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow().isoformat()}Z {entry}\n")


def run_cycle(dry_run: bool = True):
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_dir = ARTIFACTS_DIR / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    _append_log("Starting autonomous cycle")
    logger.info("Starting autonomous cycle (dry_run=%s)", dry_run)

    try:
        candidates = get_candidate_topics(limit=8)
        with open(run_dir / "candidates.json", "w", encoding="utf-8") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=2)
        _append_log(f"Candidates generated: {[c['topic'] for c in candidates]}")

        choice = select_topic(candidates)
        chosen_topic = choice["topic"]
        reason = choice.get("reason", "")
        detail = choice.get("reason_detail", "")
        _append_log(f"Chosen topic: {chosen_topic} | reason: {reason} | detail: {detail}")

        if dry_run:
            _append_log("Dry-run mode: not executing pipeline")
            logger.info("Dry-run: would run pipeline with topic: %s", chosen_topic)
            return {"status": "dry-run", "topic": chosen_topic}

        # Execute the existing pipeline (this will generate, assemble, upload)
        from src.scheduler import run_pipeline
        _append_log(f"Executing pipeline for topic: {chosen_topic}")
        video_id = run_pipeline(topic=chosen_topic)
        _append_log(f"Pipeline result video_id: {video_id}")

        # After upload, kick off thumbnail variants and AB tests (existing scripts)
        try:
            subprocess.run(["py", "-u", str(PROJECT_ROOT / "scripts" / "generate_thumbnail_variants.py")], check=False)
            subprocess.run(["py", "-u", str(PROJECT_ROOT / "scripts" / "start_ab_tests_all.py")], check=False)
            _append_log("Triggered thumbnail variants and AB test start scripts")
        except Exception as e:
            _append_log(f"Failed to start AB test scripts: {e}")

        _append_log("Autonomous cycle complete")
        return {"status": "completed", "topic": chosen_topic, "video_id": video_id}

    except Exception as e:
        tb = traceback.format_exc()
        logger.error("Autonomous cycle failed: %s", e)
        _append_log(f"Autonomous cycle failed: {e}\n{tb}")
        # Attempt simple self-heal (not implemented advanced heuristics yet)
        # If persistent, send notification via existing alerts_runner path
        try:
            subprocess.run(["py", "-u", str(PROJECT_ROOT / "scripts" / "alerts_runner.py")], check=False)
        except Exception:
            pass
        return {"status": "error", "error": str(e)}
