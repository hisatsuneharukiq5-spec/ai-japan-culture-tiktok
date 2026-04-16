#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.youtube_uploader import YouTubeUploader


def main():
    youtube = YouTubeUploader().youtube
    request = youtube.search().list(
        part="id,snippet",
        forMine=True,
        type="video",
        maxResults=50,
        order="date",
    )

    while request:
        response = request.execute()
        for item in response.get("items", []):
            print(f"{item['id']['videoId']}\t{item['snippet']['publishedAt']}\t{item['snippet']['title']}")
        request = youtube.search().list_next(request, response)


if __name__ == "__main__":
    main()
