#!/usr/bin/env python
"""Run experiment tracker (if desired) and send alerts via `notify_alerts.py`.

This script is intended to be lightweight and safe to call from scheduled tasks.
"""
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.utils import PROJECT_ROOT, setup_logger
logger = setup_logger("alerts_runner")


def main():
    # experiment_tracker already writes `output/experiment_alerts.json`.
    # Run it to ensure alerts file is up to date.
    subprocess.run([sys.executable, "scripts/experiment_tracker.py"], check=False)
    # Call notifier
    subprocess.run([sys.executable, "scripts/notify_alerts.py"], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
