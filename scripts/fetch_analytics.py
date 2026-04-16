#!/usr/bin/env python
"""Fetch YouTube Analytics metrics for videos listed in
`output/metadata_verification.json` and write `output/analytics_report.json`.

This attempts to use the YouTube Analytics API and falls back to the
YouTube Data API statistics if Analytics is unavailable.
"""
from pathlib import Path
import json
import sys
from datetime import datetime, timedelta

# Ensure repo root on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils import PROJECT_ROOT, setup_logger
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = setup_logger("fetch_analytics")


def load_credentials():
    token_file = PROJECT_ROOT / "config" / "youtube_token.json"
    if not token_file.exists():
        raise FileNotFoundError(f"YouTube token not found: {token_file}")
    creds = Credentials.from_authorized_user_file(str(token_file))
    return creds


def fetch_with_analytics(creds, video_id, start_date, end_date):
    analytics = build("youtubeAnalytics", "v2", credentials=creds)
    try:
        # Use a conservative set of metrics supported for most channels.
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics=','.join([
                'views',
                'estimatedMinutesWatched',
                'averageViewDuration',
                'averageViewPercentage',
            ]),
            filters=f"video=={video_id}",
        ).execute()
        # resp contains columnHeaders and rows
        headers = [h['name'] for h in resp.get('columnHeaders', [])]
        rows = resp.get('rows') or []
        if rows:
            # Sum/average where appropriate (report usually returns one-row aggregate)
            row = rows[0]
            return dict(zip(headers, row))
        return {}
    except Exception as e:
        logger.warning(f"Analytics API query failed for {video_id}: {e}")
        return None


def fetch_with_data_api(creds, video_id):
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.videos().list(part="statistics,contentDetails", id=video_id).execute()
    items = resp.get('items') or []
    if not items:
        return {}
    stats = items[0].get('statistics', {})
    return {
        'views': stats.get('viewCount'),
        'likeCount': stats.get('likeCount'),
        'commentCount': stats.get('commentCount'),
    }


def main():
    in_file = PROJECT_ROOT / "output" / "metadata_verification.json"
    if not in_file.exists():
        logger.error(f"Input file not found: {in_file}")
        return 1

    with open(in_file, 'r', encoding='utf-8') as f:
        items = json.load(f)

    creds = load_credentials()
    end = datetime.utcnow().date()
    start = end - timedelta(days=7)
    start_s = start.isoformat()
    end_s = end.isoformat()

    out = []
    for it in items:
        vid = it.get('video_id')
        if not vid:
            continue
        logger.info(f"Fetching analytics for: {vid}")
        data = fetch_with_analytics(creds, vid, start_s, end_s)
        if data is None:
            data = fetch_with_data_api(creds, vid)
            fallback = True
        else:
            fallback = False

        out.append({
            'video_id': vid,
            'fetched_at': datetime.utcnow().isoformat() + 'Z',
            'start_date': start_s,
            'end_date': end_s,
            'analytics': data,
            'fallback_to_data_api': fallback,
        })

    out_file = PROJECT_ROOT / 'output' / 'analytics_report.json'
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    logger.info(f"Wrote analytics report: {out_file}")
    print(out_file)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
