#!/usr/bin/env python
"""Send experiment alerts via Slack webhook and/or email.

Environment variables supported:
- SLACK_WEBHOOK_URL
- ALERT_EMAIL_TO
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_EMAIL_FROM
"""
import os
import json
import smtplib
from pathlib import Path
from email.message import EmailMessage

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))

from src.utils import setup_logger, PROJECT_ROOT
logger = setup_logger("notify_alerts")


def send_slack(webhook_url: str, text: str):
    try:
        import requests
    except Exception:
        logger.error("requests library required for Slack notifications")
        return False
    payload = {"text": text}
    resp = requests.post(webhook_url, json=payload, timeout=10)
    if resp.status_code == 200:
        logger.info("Slack notification sent")
        return True
    else:
        logger.warning(f"Slack webhook failed: {resp.status_code} {resp.text}")
        return False


def send_email(smtp_host, smtp_port, smtp_user, smtp_pass, frm, to, subject, body):
    msg = EmailMessage()
    msg["From"] = frm
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(smtp_host, int(smtp_port)) as s:
            s.starttls()
            if smtp_user and smtp_pass:
                s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        logger.info(f"Email sent to: {to}")
        return True
    except Exception as e:
        logger.warning(f"Email send failed: {e}")
        return False


def main():
    alerts_file = PROJECT_ROOT / "output" / "experiment_alerts.json"
    if not alerts_file.exists():
        logger.info("No alerts file found; nothing to send.")
        return 0
    with open(alerts_file, "r", encoding="utf-8") as f:
        alerts = json.load(f)

    if not alerts:
        logger.info("No alerts to send.")
        return 0

    slack = os.getenv("SLACK_WEBHOOK_URL")
    email_to = os.getenv("ALERT_EMAIL_TO")

    text_lines = [f"Experiment alerts ({len(alerts)}):"]
    for a in alerts:
        text_lines.append(f"- {a['video_id']}: {a['prev_views']} -> {a['latest_views']} (delta={a['delta']}, pct={a['pct']})")
    text = "\n".join(text_lines)

    sent = False
    if slack:
        sent = send_slack(slack, text) or sent

    if email_to:
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = os.getenv("SMTP_PORT", "587")
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASS")
        frm = os.getenv("ALERT_EMAIL_FROM", smtp_user or f"no-reply@{os.uname().nodename}") if hasattr(os, 'uname') else os.getenv("ALERT_EMAIL_FROM", smtp_user or "no-reply@example.com")
        send_email(smtp_host, smtp_port, smtp_user, smtp_pass, frm, email_to, "AIJapan Experiment Alerts", text)
        sent = True

    if not sent:
        logger.info("No notification method configured. Alerts saved at: %s", alerts_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
