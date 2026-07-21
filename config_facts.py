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
LEARNED_TOPIC_STYLE = "science, didn, experiment, tricks, physics, unbelievable, could, save"
LEARNED_TITLE_TEMPLATES = [
  "Did you know that {fact}? #Shorts",
  "Only {number}% of people know this about {topic} #Shorts",
  "Scientists just discovered {topic} and it changes everything #Shorts",
  "The real reason {topic} does this will shock you #Shorts",
  "What happens to your body when {scenario}? #Shorts",
  "Why {topic} is more {adjective} than you think #Shorts",
  "{number} {topic} facts that will blow your mind #Shorts",
  "{topic} is SO cool #Shorts"
]
LEARNED_HOOK_PHRASES = [
  "This is SO cool",
  "What Is The Real Shape",
  "This can help make Artificial",
  "How Deep Do Humans Have",
  "Did You Notice This In",
  "Did You Know This Fact",
  "did you know that Toph",
  "Did You Know: Titanic Fun"
]
LEARNED_HASHTAGS = [
  "#shorts",
  "#facts",
  "#science",
  "#experiment",
  "#education",
  "#youtubeshorts",
  "#viral",
  "#short",
  "#knowledge",
  "#top",
  "#fact",
  "#science experiments",
  "#viralshorts",
  "#trending",
  "#youtube shorts",
  "#didyouknow"
]
PREFERRED_POST_HOURS = [0, 11, 12, 19, 20]
# FACTS_BRAIN_MANAGED_END
