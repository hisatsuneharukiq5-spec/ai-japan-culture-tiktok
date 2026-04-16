#!/usr/bin/env python
"""Apply YouTube modified/synthetic content disclosure flags to all Obscura videos.

Targets videos found in:
- output/analytics/obscura_upload_registry.jsonl
- output/analytics/obscura_shorts_upload_registry.json

For each video ID, updates status fields:
- containsSyntheticMedia = True
- selfDeclaredAsModifiedContent = True
- selfDeclaredMadeForKids = False
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent.parent
LONG_REGISTRY = ROOT / "output" / "analytics" / "obscura_upload_registry.jsonl"
SHORTS_REGISTRY = ROOT / "output" / "analytics" / "obscura_shorts_upload_registry.json"
REPORT_PATH = ROOT / "output" / "analytics" / "obscura_modified_content_apply_report.json"
TOKEN_FILE = ROOT / "config" / "youtube_token_obscura.json"
CLIENT_SECRETS = ROOT / "config" / "youtube_client_secrets_obscura.json"
FALLBACK_CLIENT_SECRETS = ROOT / "config" / "youtube_client_secrets.json"

SCOPES = ["https://www.googleapis.com/auth/youtube"]


READ_ONLY_STATUS_KEYS = {
    "uploadStatus",
    "failureReason",
    "rejectionReason",
    "madeForKids",
    "containsSyntheticMedia",  # overwritten explicitly below
    "selfDeclaredAsModifiedContent",  # overwritten explicitly below
}


def _load_video_ids() -> list[str]:
    ids: list[str] = []

    if LONG_REGISTRY.exists():
        with open(LONG_REGISTRY, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    vid = row.get("video_id")
                    if vid:
                        ids.append(str(vid))
                except Exception:
                    continue

    if SHORTS_REGISTRY.exists():
        try:
            data = json.loads(SHORTS_REGISTRY.read_text(encoding="utf-8"))
            uploads = data.get("uploads", []) if isinstance(data, dict) else []
            for item in uploads:
                vid = item.get("video_id")
                if vid:
                    ids.append(str(vid))
        except Exception:
            pass

    # De-duplicate while preserving order
    seen = set()
    deduped: list[str] = []
    for vid in ids:
        if vid in seen:
            continue
        seen.add(vid)
        deduped.append(vid)

    return deduped


def _authenticate():
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secrets = CLIENT_SECRETS if CLIENT_SECRETS.exists() else FALLBACK_CLIENT_SECRETS
            if not secrets.exists():
                raise RuntimeError(
                    "Client secrets not found. Expected one of: "
                    f"{CLIENT_SECRETS} or {FALLBACK_CLIENT_SECRETS}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
            creds = flow.run_local_server(port=8090)

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)


def _sanitize_status(status: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in status.items():
        if key in READ_ONLY_STATUS_KEYS:
            continue
        cleaned[key] = value

    cleaned["selfDeclaredMadeForKids"] = False
    cleaned["containsSyntheticMedia"] = True
    cleaned["selfDeclaredAsModifiedContent"] = True
    return cleaned


def main() -> int:
    video_ids = _load_video_ids()
    if not video_ids:
        print("No Obscura video IDs found in registries.")
        return 1

    youtube = _authenticate()

    results: list[dict[str, Any]] = []
    success = 0

    print(f"Applying disclosure flags to {len(video_ids)} Obscura videos...")

    for vid in video_ids:
        row: dict[str, Any] = {"video_id": vid, "ok": False}
        try:
            resp = youtube.videos().list(part="status,snippet", id=vid).execute()
            items = resp.get("items", [])
            if not items:
                row["error"] = "Video not found or inaccessible"
                results.append(row)
                print(f"[WARN] {vid}: not found/inaccessible")
                continue

            current_status = items[0].get("status", {})
            new_status = _sanitize_status(current_status)

            body = {
                "id": vid,
                "status": new_status,
            }

            youtube.videos().update(part="status", body=body).execute()

            row["ok"] = True
            row["applied_status"] = new_status
            results.append(row)
            success += 1
            print(f"[OK]   {vid}: disclosure applied")
        except Exception as e:
            row["error"] = str(e)
            results.append(row)
            print(f"[FAIL] {vid}: {e}")

    report = {
        "total": len(video_ids),
        "success": success,
        "failed": len(video_ids) - success,
        "results": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("---")
    print(f"Done. success={success}/{len(video_ids)}")
    print(f"Report: {REPORT_PATH}")
    return 0 if success == len(video_ids) else 2


if __name__ == "__main__":
    raise SystemExit(main())
