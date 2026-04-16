from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def main() -> None:
    token = Path("config/youtube_token_obscura.json")
    creds = Credentials.from_authorized_user_file(
        str(token),
        [
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.upload",
        ],
    )
    youtube = build("youtube", "v3", credentials=creds)

    channel = youtube.channels().list(part="contentDetails", mine=True).execute()
    uploads_playlist = channel["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    latest = youtube.playlistItems().list(
        part="snippet,contentDetails",
        playlistId=uploads_playlist,
        maxResults=1,
    ).execute()["items"][0]

    video_id = latest["contentDetails"]["videoId"]
    title = latest["snippet"]["title"]
    print(f"LATEST_VIDEO_ID={video_id}")
    print(f"LATEST_TITLE={title}")
    print(f"LATEST_URL=https://www.youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    main()
