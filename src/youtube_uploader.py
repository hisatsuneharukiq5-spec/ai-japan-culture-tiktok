import os
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils import get_config, setup_logger, PROJECT_ROOT

logger = setup_logger("youtube_uploader")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
TOKEN_FILE = PROJECT_ROOT / "config" / "youtube_token.json"
CLIENT_SECRETS_FILE = PROJECT_ROOT / "config" / "youtube_client_secrets.json"


class YouTubeUploader:
    def __init__(self):
        self.config = get_config()
        self.channel_config = self.config["channel"]
        self.youtube = self._authenticate()

    def _authenticate(self):
        """
        Authenticate with YouTube Data API using OAuth2.
        On first run, opens a browser for the user to authorize.
        Saves the token for subsequent runs.
        """
        creds = None

        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing YouTube access token...")
                creds.refresh(Request())
            else:
                if CLIENT_SECRETS_FILE.exists():
                    logger.info("Starting OAuth2 flow. A browser window will open...")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(CLIENT_SECRETS_FILE), SCOPES
                    )
                else:
                    client_id = os.getenv("YOUTUBE_CLIENT_ID")
                    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
                    if not client_id or not client_secret:
                        raise ValueError(
                            "YouTube credentials not found. Set YOUTUBE_CLIENT_ID and "
                            "YOUTUBE_CLIENT_SECRET in .env, or place youtube_client_secrets.json "
                            f"at: {CLIENT_SECRETS_FILE}"
                        )
                    logger.info(
                        "Using YOUTUBE_CLIENT_ID/SECRET from .env. A browser window will open..."
                    )
                    client_config = {
                        "installed": {
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "redirect_uris": ["http://localhost:8080/"],
                        }
                    }
                    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                creds = flow.run_local_server(port=8080)

            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            logger.info(f"Token saved to: {TOKEN_FILE}")

        return build("youtube", "v3", credentials=creds)

    def check_for_duplicate(
        self,
        title: str,
        short_only: bool = False,
        long_only: bool = False,
    ) -> str | None:
        """
        Check if a video with the same title already exists on the channel.
        When short_only=True, only compare against existing videos that include
        '#shorts' in the title.
        When long_only=True, ignore existing videos that include '#shorts'.
        Returns the video ID if a duplicate is found, None otherwise.
        """
        try:
            logger.info(f"🔍 Checking for duplicate videos with title: '{title}'")
            
            request = self.youtube.search().list(
                part='snippet',
                forMine=True,
                type='video',
                maxResults=50,
                order='date'
            )
            response = request.execute()
            
            if not response.get('items'):
                logger.info("✓ No existing videos found")
                return None
            
            for item in response['items']:
                existing_title = item['snippet']['title']
                video_id = item['id']['videoId']
                
                # Check for exact or partial match (to catch reupload attempts)
                title_lower = title.lower().strip()
                existing_lower = existing_title.lower().strip()

                if short_only and "#shorts" not in existing_lower:
                    continue
                if long_only and "#shorts" in existing_lower:
                    continue
                
                # Exact match
                if title_lower == existing_lower:
                    logger.warning(f"⚠️  EXACT DUPLICATE DETECTED!")
                    logger.warning(f"   Existing: '{existing_title}'")
                    logger.warning(f"   ID: {video_id}")
                    return video_id
                
                # Partial match (video title contains search term)
                if len(title_lower) > 10 and (title_lower in existing_lower or existing_lower in title_lower):
                    logger.warning(f"⚠️  SIMILAR VIDEO ALREADY EXISTS!")
                    logger.warning(f"   Existing: '{existing_title}'")
                    logger.warning(f"   ID: {video_id}")
                    return video_id
            
            logger.info("✓ No duplicates found - safe to upload")
            return None
            
        except Exception as e:
            logger.warning(f"⚠️  Could not check for duplicates: {e}")
            # Allow upload to proceed if check fails
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=10, max=60),
    )
    def upload(self, video_path: Path, script_data: dict) -> str:
        """
        Upload a video to YouTube.
        Returns the YouTube video ID.
        """
        title = script_data.get("title", "AI Japan Video")
        
        # Check for duplicates before uploading
        duplicate_id = self.check_for_duplicate(title, long_only=True)
        if duplicate_id:
            logger.error(f"❌ ABORT: Duplicate video already exists!")
            logger.error(f"   Existing video: https://www.youtube.com/watch?v={duplicate_id}")
            logger.error(f"   Not uploading to avoid duplication")
            raise ValueError(f"Duplicate video already exists: {duplicate_id}")
        
        logger.info("✓ Duplicate check passed - proceeding with upload")
        substack_url = os.getenv("SUBSTACK_PUBLICATION_URL", "").rstrip("/")
        substack_cta = (
            "\n\n---\n"
            "📧 Want the full breakdown + my Claude Code automation prompts?\n"
            "Get exclusive guides on how I build this system:\n"
            f"👉 {substack_url}\n\n"
            "🆓 Free subscribers get weekly Japan insights\n"
            "💎 Paid subscribers get my exact prompts & error fixes\n\n"
            "#Japan #AIJapan #JapanTravel"
            if substack_url else ""
        )
        description = script_data.get("description", "") + substack_cta
        raw_tags = script_data.get("tags", []) + self.channel_config["default_tags"]
        # Sanitize: strip whitespace, remove # prefix, drop empty or invalid tags
        sanitized = []
        for t in raw_tags:
            t = t.strip().lstrip("#")
            if t and "<" not in t and ">" not in t and len(t) <= 500:
                sanitized.append(t)
        # Deduplicate while preserving order
        seen = set()
        deduped = [t for t in sanitized if not (t in seen or seen.add(t))]
        # YouTube measures tags as JSON array representation: ["tag1","tag2",...]
        # Limit is 500 chars for the JSON-serialized array
        tags = []
        for t in deduped:
            candidate = tags + [t]
            if len(json.dumps(candidate)) > 500:
                break
            tags = candidate
        total = len(json.dumps(tags)) if tags else 0

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "categoryId": self.channel_config["default_category_id"],
                "defaultLanguage": self.channel_config["language"],
                "defaultAudioLanguage": self.channel_config["language"],
            },
            "status": {
                "privacyStatus": self.channel_config["default_privacy"],
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": True,
                "selfDeclaredAsModifiedContent": True,
            },
        }
        if tags:
            body["snippet"]["tags"] = tags

        status = body.setdefault("status", {})
        status["containsSyntheticMedia"] = True
        status["selfDeclaredAsModifiedContent"] = True

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=2 * 1024 * 1024,  # 2 MB chunks (smaller chunks improve reliability)
        )

        logger.info(f"Uploading video: {title}")
        request = self.youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info(f"Upload progress: {progress}%")

        video_id = response["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(f"Upload complete! Video ID: {video_id}")
        logger.info(f"Video URL: {video_url}")

        return video_id

    def upload_short(self, video_path: Path, metadata: dict) -> str:
        """Upload a vertical video as a YouTube Short.

        Title = original title + ' #Shorts' (capped at 100 chars).
        Description = Substack CTA + hashtags.
        Returns the YouTube video ID.
        """
        base_title = metadata.get("title", "Japan Short")
        title = (base_title[:91].rstrip() + " #Shorts")[:100]
        
        # Check for duplicates before uploading
        duplicate_id = self.check_for_duplicate(title, short_only=True)
        if duplicate_id:
            logger.error(f"❌ ABORT: Short video already exists!")
            logger.error(f"   Existing video: https://www.youtube.com/watch?v={duplicate_id}")
            logger.error(f"   Not uploading to avoid duplication")
            raise ValueError(f"Duplicate video already exists: {duplicate_id}")

        substack_url = os.getenv("SUBSTACK_PUBLICATION_URL", "").rstrip("/")
        description = (
            f"Full story👉 {substack_url}\n\n" if substack_url else ""
        ) + "#Japan #AIJapan #JapanTravel #Shorts"

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": self.channel_config["default_category_id"],
                "defaultLanguage": self.channel_config["language"],
                "defaultAudioLanguage": self.channel_config["language"],
                "tags": ["Shorts", "YouTubeShorts", "Japan", "AIJapan", "JapanTravel"],
            },
            "status": {
                "privacyStatus": self.channel_config["default_privacy"],
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": True,
                "selfDeclaredAsModifiedContent": True,
            },
        }

        status = body.setdefault("status", {})
        status["containsSyntheticMedia"] = True
        status["selfDeclaredAsModifiedContent"] = True

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,
        )

        logger.info(f"Uploading Short: {title}")
        request = self.youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Short upload progress: {int(status.progress() * 100)}%")

        video_id = response["id"]
        logger.info(f"Short upload complete! Video ID: {video_id}")
        logger.info(f"Short URL: https://www.youtube.com/shorts/{video_id}")
        return video_id

    def update_channel_description(self, substack_url: str) -> None:
        """Append the Substack URL to the channel's About description (once-only setup)."""
        # Fetch current channel info
        resp = self.youtube.channels().list(
            part="brandingSettings",
            mine=True,
        ).execute()

        if not resp.get("items"):
            raise RuntimeError("Could not fetch channel info. Check OAuth scopes.")

        channel = resp["items"][0]
        branding = channel.get("brandingSettings", {})
        current_desc = branding.get("channel", {}).get("description", "")

        substack_line = f"📰 Read our articles on Substack: {substack_url}"

        if substack_url in current_desc:
            logger.info("Substack URL already present in channel description. No update needed.")
            return

        new_desc = (current_desc.rstrip() + "\n\n" + substack_line).strip()

        self.youtube.channels().update(
            part="brandingSettings",
            body={
                "id": channel["id"],
                "brandingSettings": {
                    "channel": {
                        "description": new_desc[:1000],  # YouTube limit: 1000 chars
                    }
                },
            },
        ).execute()
        logger.info(f"Channel description updated with Substack URL: {substack_url}")

    def update_video_languages(
        self,
        video_id: str,
        default_language: str,
        default_audio_language: str,
        remove_localizations: list[str] | None = None,
    ) -> dict:
        """Update language metadata for an existing video."""
        resp = self.youtube.videos().list(
            part="snippet,localizations",
            id=video_id,
            maxResults=1,
        ).execute()

        items = resp.get("items") or []
        if not items:
            raise ValueError(f"Video not found: {video_id}")

        item = items[0]
        snippet = item.get("snippet", {})
        localizations = item.get("localizations", {}) or {}

        snippet["defaultLanguage"] = default_language
        snippet["defaultAudioLanguage"] = default_audio_language

        for lang in (remove_localizations or []):
            localizations.pop(lang, None)

        body = {
            "id": video_id,
            "snippet": snippet,
            "localizations": localizations,
        }

        self.youtube.videos().update(
            part="snippet,localizations",
            body=body,
        ).execute()

        return {
            "video_id": video_id,
            "defaultLanguage": default_language,
            "defaultAudioLanguage": default_audio_language,
            "removed_localizations": remove_localizations or [],
        }

    def fix_recent_shorts_languages(
        self,
        limit: int = 5,
        default_language: str | None = None,
        default_audio_language: str | None = None,
        remove_japanese_localization: bool = False,
    ) -> list[dict]:
        """Fix language metadata for recent Shorts uploads on the authenticated channel."""
        target_lang = default_language or self.channel_config.get("language", "en")
        target_audio_lang = default_audio_language or target_lang

        request = self.youtube.search().list(
            part="snippet",
            forMine=True,
            type="video",
            maxResults=50,
            order="date",
        )
        response = request.execute()

        shorts = []
        for item in response.get("items", []):
            title = (item.get("snippet") or {}).get("title", "")
            if "#shorts" in title.lower():
                shorts.append(item)
            if len(shorts) >= max(1, limit):
                break

        results: list[dict] = []
        for item in shorts:
            video_id = (item.get("id") or {}).get("videoId")
            if not video_id:
                continue
            remove = ["ja"] if remove_japanese_localization else []
            result = self.update_video_languages(
                video_id=video_id,
                default_language=target_lang,
                default_audio_language=target_audio_lang,
                remove_localizations=remove,
            )
            result["title"] = (item.get("snippet") or {}).get("title", "")
            results.append(result)

        return results
