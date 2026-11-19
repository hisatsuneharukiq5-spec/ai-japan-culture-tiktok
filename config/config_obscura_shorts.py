"""
Configuration for Obscura Files YouTube Shorts
"""

# Video Settings
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
VIDEO_FORMAT = "mp4"

# Duration Constraints (seconds)
TARGET_MIN_DURATION = 50
TARGET_MAX_DURATION = 55
ABSOLUTE_MAX_DURATION = 60  # Never exceed this

# Script Settings
SCRIPT_MIN_WORDS = 100
SCRIPT_MAX_WORDS = 115
SCRIPT_MODEL = "claude-opus-4-6"
SCRIPT_MAX_TOKENS = 3000

# Voice Settings
VOICE_NAME = "en-US-GuyNeural"
VOICE_RATE = "+8%"  # Fast, but long enough to land near 50-55s
VOICE_PITCH = "-5Hz"  # Lower, eerie tone

# Clip Settings
CLIP_MIN_DURATION = 3
CLIP_MAX_DURATION = 5
TARGET_CLIP_COUNT_MIN = 15
TARGET_CLIP_COUNT_MAX = 20

# Subtitle Settings
SUBTITLE_FONT_SIZE = 72
SUBTITLE_SHOCK_FONT_SIZE = 90
SUBTITLE_ULTRA_FONT_SIZE = 95
SUBTITLE_MAX_WORDS_PER_LINE = 4
SUBTITLE_POSITION = "middle"  # center of screen

# Emphasis keywords (yellow)
EMPHASIS_KEYWORDS = {
    "died", "murdered", "disappeared", "vanished",
    "never found", "shocking", "mysterious",
    "terrifying", "secret", "suddenly", "cursed",
    "executed", "buried", "trapped", "escaped"
}

# Ultra emphasis keywords (red + zoom-in)
ULTRA_EMPHASIS_KEYWORDS = {
    "killed", "dead", "blood", "horror", "scream",
    "demon", "ghost", "evil", "monster", "corpse"
}

# BGM Settings
BGM_VOLUME_RATIO = 0.20  # 20% of narration volume
BGM_FADE_DURATION = 0.5  # seconds

# Upload Settings
UPLOAD_PRIVACY = "private"
# Scheduled publish (publishAt). Uploads stay private and YouTube makes them public at the
# next PUBLISH_AT_UTC that is at least PUBLISH_MIN_LEAD_HOURS away, which leaves a window to
# check or cancel the video in YouTube Studio. In March-April 2026 most videos went public at
# about 15:00 UTC (00:00 JST). Set PUBLISH_AT_UTC = None to keep uploads private.
# Same slot as the long-form, so the Short never goes public before the long-form it links to.
PUBLISH_AT_UTC = "15:00"
PUBLISH_MIN_LEAD_HOURS = 2
UPLOAD_CATEGORY_ID = "27"  # Education
YOUTUBE_OBSCURA_CLIENT_SECRETS_FILE = "config/youtube_client_secrets.json"
YOUTUBE_OBSCURA_TOKEN_FILE = "config/youtube_token_obscura.json"
YOUTUBE_ALLOWED_CHANNEL_TITLES = ["The Obscura Files"]
YOUTUBE_ALLOWED_CHANNEL_IDS = []
UPLOAD_REGISTRY_FILE = "output/analytics/obscura_shorts_upload_registry.json"
SUBSCRIBE_CTA = "Subscribe to The Obscura Files for more dark history and unsolved mystery Shorts."

# Hashtags
REQUIRED_HASHTAGS = ["#Shorts", "#DarkHistory", "#Mystery"]
OPTIONAL_HASHTAGS = ["#TrueStory", "#Unexplained", "#Horror", "#CriminalMinds", "#Unsolved"]

# Topics (can reuse from main pipeline)
OBSCURA_SHORTS_TOPICS = [
    "The Disappearance of the Sodder Children",
    "The Hinterkaifeck Murders",
    "The Isdal Woman Mystery",
    "The Axeman of New Orleans",
    "The Somerton Man Case",
    "The Princes in the Tower",
    "The Beaumont Children Disappearance",
    "The Black Dahlia Investigation",
    "The Dyatlov Pass Incident",
    "The Tamam Shud Case",
    "The Boy in the Box",
    "The Lead Masks Case",
    "The Yuba County Five",
    "The Villisca Axe Murders",
    "The Zodiac Killer's Unsolved Identity",
    "The D.B. Cooper Skyjacking Mystery",
    "The Mary Celeste Ghost Ship",
    "The Flannan Isles Lighthouse Vanishing",
    "The Lady of the Dunes Mystery",
    "The Highway of Tears Disappearances",
    "The Circleville Letters Mystery",
    "The Body in Room 1046",
    "The Keddie Cabin Murders",
    "The Delphi Murders Mystery",
    "The Lost Colony of Roanoke",
    "The Rendlesham Forest UFO Incident",
    "The Boy in the Box Philadelphia",
]
