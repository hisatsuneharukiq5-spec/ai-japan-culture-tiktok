"""
Configuration for Obscura Files Channel
- Channel: Obscura Files
- Language: English
- Topics: Dark history, unsolved crimes, mysteries, real events
- Tone: Mysterious, dramatic, suspenseful
- Voice: Guy Neural (deeper, dramatic tone)
- Duration: max 600 seconds (8-10 minutes)
"""

import os

# Channel Identity
CHANNEL_NAME = "Obscura Files"
CHANNEL_ID = None  # Will be resolved from YouTube API

# API Authentication
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY_OBSCURA")
if not YOUTUBE_API_KEY:
    raise ValueError("YOUTUBE_API_KEY_OBSCURA is not set in environment variables")

# Language & Voice
LANGUAGE = "en"
VOICE = "en-US-GuyNeural"  # Deep, dramatic tone for dark/mystery content
VOICE_RATE = "-10%"  # Slightly slower for dramatic effect
VOICE_PITCH = "-5Hz"  # Slightly deeper pitch

# Content Style
TONE = "mysterious, dramatic, suspenseful"
TOPIC_STYLE = "dark history, unsolved crimes, real events, mysteries, strange happenings"
TOPICS_FOCUS = [
    "Unsolved murders",
    "Missing persons cases",
    "Mysterious disappearances",
    "Paranormal events",
    "Historical conspiracies",
    "Strange phenomena",
    "Unexplained deaths",
    "Dark historical events"
]

# Video Settings
VIDEO_DURATION_MAX = 600  # 10 minutes absolute limit
TARGET_DURATION = 480  # Target 8 minutes
TARGET_CLIP_COUNT = 100  # High clip count for dark/atmospheric feel
CLIP_DURATION_MIN = 5  # seconds
CLIP_DURATION_MAX = 8  # seconds
CROSSFADE_DURATION = 0.5  # seconds between clips

# Image/Video Sources - Dark/Atmospheric Keywords
KEYWORDS_STYLE = "dark, mystery, abandoned, fog, shadow, night, rain, cemetery"
BASE_KEYWORDS = [
    "dark forest",
    "abandoned building",
    "fog",
    "mystery",
    "old documents",
    "shadows",
    "night city",
    "cemetery",
    "rain",
    "empty road",
    "candle",
    "old photo",
    "vintage",
    "crime scene",
    "newspaper",
    "clock",
    "door",
    "window",
    "fire",
    "darkness",
    "abandoned house",
    "old files",
    "vintage photo",
    "dim light",
    "dark corridor"
]
PEXELS_CLIPS_PER_QUERY = 15
PIXABAY_CLIPS_PER_QUERY = 15
TARGET_TOTAL_CLIPS = 120  # Before deduplication (high count for atmospheric content)
MAX_CLIP_REUSE = 3  # Maximum times same clip can be reused

# Subtitle Settings
SUBTITLE_FONT_SIZE = 16  # Smaller than fancy thumbnails
SUBTITLE_OUTLINE_WIDTH = 2
SUBTITLE_COLOR = (255, 255, 255)  # White
SUBTITLE_OUTLINE_COLOR = (0, 0, 0)  # Black

# Encoding
VIDEO_CODEC = "libx264"
VIDEO_PRESET = "medium"
VIDEO_CRF = 20  # High quality for dark atmosphere
AUDIO_CODEC = "aac"
RESOLUTION = "1920x1080"
FPS = 30

# Script Generation
SCRIPT_MIN_WORDS = 1800
SCRIPT_MAX_WORDS = 2200
SCRIPT_STYLE = "mysterious, dramatic, suspenseful; based on real events and historical facts"
SCRIPT_STRUCTURE = {
    "hook": "30 seconds - Dramatic opening to grab attention",
    "background": "2 minutes - Historical/background context",
    "mystery": "4-5 minutes - The core mystery or unsolved aspect",
    "conclusion": "1-2 minutes - What remains unsolved or implications",
    "outro": "30 seconds - Closing with call-to-action or thought-provoking statement"
}

# Output Directories
OUTPUT_DIR = "output"
SCRIPTS_DIR = "output/scripts"
VIDEOS_DIR = "output/videos"
THUMBNAILS_DIR = "output/thumbnails"
LOGS_DIR = "logs"

# Upload Growth Settings
UPLOAD_PRIVACY = "private"
SUBSCRIBE_CTA = "Subscribe to The Obscura Files for weekly unsolved mysteries, dark history, and true crime documentaries."
DEFAULT_HASHTAGS = [
    "#UnsolvedMysteries",
    "#DarkHistory",
    "#TrueCrime",
    "#MysteryDocumentary",
]

# Transcription Settings (Whisper)
WHISPER_MODEL = "base"  # For accurate English transcription
TRANSCRIPTION_LANGUAGE = "en"
