"""
Configuration for Facts & Wonders channel.
"""

import os

CHANNEL_NAME = "Facts & Wonders"
CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID_FACTS", "").strip()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY_FACTS")
LANGUAGE = "en"
VOICE = "en-US-AriaNeural"
VOICE_RATE = "+20%"
VOICE_PITCH = "+0Hz"
TONE = "energetic, surprising, upbeat"
TOPIC_STYLE = "amazing facts, science, nature, space, human body"

SCRIPT_MIN_WORDS = 100
SCRIPT_MAX_WORDS = 130
DURATION_MIN_SEC = 55
DURATION_MAX_SEC = 59
FPS = 30
RESOLUTION = "1080x1920"
CLIP_DURATION_MIN = 3
CLIP_DURATION_MAX = 5
CLIP_COUNT_MIN = 15
CLIP_COUNT_MAX = 30

SHORTS_DESCRIPTION = "Amazing facts you never knew!\nNew facts every day."
SHORTS_HASHTAGS = [
    "#Facts",
    "#DidYouKnow",
    "#AmazingFacts",
    "#Science",
    "#Nature",
    "#Shorts",
]

HIGHLIGHT_WORDS = [
    "amazing",
    "incredible",
    "never",
    "only",
    "first",
    "largest",
    "smallest",
]

DEFAULT_PRIVACY = "public"

FACTS_SCHEDULER_TASK_NAME = "AIJapanFactsDaily"
FACTS_SCHEDULER_START_TIME = "03:00"

# Anthropic model order for script generation.
# You can override the first one via FACTS_ANTHROPIC_MODEL in .env.
ANTHROPIC_MODELS = [
    os.getenv("FACTS_ANTHROPIC_MODEL", "claude-sonnet-4-5").strip() or "claude-sonnet-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
]

# FACTS_BRAIN_MANAGED_START
LEARNED_TOPIC_STYLE = "science, didn, physics, experiment, amazing, sciencefacts, save, life"
LEARNED_TITLE_TEMPLATES = [
  "Did you know that {fact}? #Shorts",
  "How {topic} Do {topic} Have Dug Inside Earth #Shorts",
  "Only {number}% of people know this about {topic} #Shorts",
  "Scientists just discovered {topic} and it changes everything #Shorts",
  "The real reason {topic} does this will shock you #Shorts",
  "Top - {number} {topic} {topic} 😱 #Shorts",
  "What happens to your body when {scenario}? #Shorts",
  "Why {topic} is more {adjective} than you think #Shorts"
]
LEARNED_HOOK_PHRASES = [
  "Squid Ink Science Experiment",
  "4 Cool Gifts for",
  "#physics #physicsconcept #physicsfacts #shorts",
  "So how many pins",
  "Top - 3 Amazing",
  "Ocean Depth #ocean #science",
  "Balloon Explodes with Orange",
  "From Human to Black"
]
LEARNED_HASHTAGS = [
  "#shorts",
  "#facts",
  "#science",
  "#education",
  "#viral",
  "#new",
  "#sciencefacts",
  "#fact",
  "#youtubeshorts",
  "#knowledge",
  "#experiment",
  "#amazing facts",
  "#short",
  "#trending",
  "#top",
  "#didyouknow"
]
PREFERRED_POST_HOURS = [4, 10, 16, 17, 18]
# FACTS_BRAIN_MANAGED_END
