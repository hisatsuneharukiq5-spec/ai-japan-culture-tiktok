"""
Configuration for AI Japan Channel
- Channel: AI Japan
- Language: English
- Topics: Japanese culture, history, traditions explained in English
- Tone: Educational, cultural, calm
- Voice: Giuseppe Neural (calm, measured tone)
- Duration: max 600 seconds
"""

import os

# Channel Identity
CHANNEL_NAME = "AI Japan"
CHANNEL_ID = None  # Will be resolved from YouTube API

# API Authentication
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    raise ValueError("YOUTUBE_API_KEY is not set in environment variables")

# Language & Voice
LANGUAGE = "en"
VOICE = "en-US-GiuseppeNeural"  # Calm, measured tone for educational content
VOICE_RATE = "0%"
VOICE_PITCH = "0Hz"

# Content Style
TONE = "educational, cultural, calm"
TOPIC_STYLE = "Japanese culture and history explained in English"
TOPICS_FOCUS = [
    "Japanese traditions",
    "Travel guides to Japan",
    "Japanese customs and etiquette",
    "Historical events in Japan",
    "Japanese food and cuisine",
    "Japanese arts and crafts"
]

# Video Settings
VIDEO_DURATION_MAX = 600  # 10 minutes
TARGET_CLIP_COUNT = 60  # Premium video generator target
CLIP_DURATION_MIN = 5  # seconds
CLIP_DURATION_MAX = 8  # seconds
CROSSFADE_DURATION = 0.5  # seconds between clips

# Image/Video Sources
KEYWORDS_STYLE = "japan, culture, tradition, nature, street, people"
PEXELS_CLIPS_PER_QUERY = 15
PIXABAY_CLIPS_PER_QUERY = 15
TARGET_TOTAL_CLIPS = 80  # Before deduplication

# Subtitle Settings
SUBTITLE_FONT_SIZE = 24
SUBTITLE_OUTLINE_WIDTH = 3
SUBTITLE_COLOR = (255, 255, 255)  # White
SUBTITLE_OUTLINE_COLOR = (0, 0, 0)  # Black

# Encoding
VIDEO_CODEC = "libx264"
VIDEO_PRESET = "medium"  # medium quality
VIDEO_CRF = 20  # Higher quality
AUDIO_CODEC = "aac"
RESOLUTION = "1920x1080"
FPS = 30

# Script Generation
SCRIPT_MIN_WORDS = 1100
SCRIPT_MAX_WORDS = 1500
SCRIPT_STYLE = "informative, engaging, suitable for English-speaking audience interested in Japanese culture"

# Output Directories
OUTPUT_DIR = "output"
SCRIPTS_DIR = "output/scripts"
VIDEOS_DIR = "output/videos"
THUMBNAILS_DIR = "output/thumbnails"
LOGS_DIR = "logs"
