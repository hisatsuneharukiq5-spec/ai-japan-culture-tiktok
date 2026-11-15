import base64
import io
import os
import random
import time
import urllib.parse
from pathlib import Path

import requests
from PIL import Image

from src.utils import setup_logger

logger = setup_logger("image_generator")

W, H = 1280, 720
POLLINATIONS_MODEL = "flux"


def _build_facts_prompt(title: str, topic: str) -> str:
    """Build an AI image prompt for Facts & Wonders thumbnails."""
    combined = (title + " " + topic).lower()

    if any(w in combined for w in ["space", "planet", "star", "galaxy", "nasa", "universe", "astronaut", "solar", "cosmos", "orbit"]):
        return (
            "Stunning cinematic photograph of deep space nebula, swirling colorful gas clouds, "
            "bright star clusters, vivid purples blues and oranges, Hubble telescope style, "
            "ultra sharp detail, dramatic cosmic scale, photorealistic, no text, no watermark. "
            "The center and left are slightly darker for text overlay. 16:9 landscape."
        )
    elif any(w in combined for w in ["brain", "neuron", "nerve", "mind", "thought", "consciousness", "memory", "neural"]):
        return (
            "Stunning macro closeup of glowing neural network synapse connections, "
            "electric blue and purple bioluminescent signals, dark background, "
            "cinematic lighting, ultra detailed, sci-fi medical photography, photorealistic, "
            "no text, no watermark, 16:9 landscape."
        )
    elif any(w in combined for w in ["body", "heart", "blood", "cell", "dna", "muscle", "organ", "human", "bone"]):
        return (
            "Dramatic 3D render of human body internal anatomy, glowing organs, "
            "vivid electric blue and warm red lighting, dark background, medical sci-fi style, "
            "ultra detailed, cinematic, photorealistic, no text, no watermark, 16:9 landscape."
        )
    elif any(w in combined for w in ["ocean", "deep", "sea", "marine", "coral", "underwater", "fish", "whale", "shark"]):
        return (
            "Breathtaking underwater photograph of deep ocean, bioluminescent creatures, "
            "rays of blue-green light piercing dark water, coral reef, exotic sea life, "
            "dramatic depth, cinematic, ultra detailed, photorealistic, no text, no watermark, 16:9 landscape."
        )
    elif any(w in combined for w in ["animal", "creature", "insect", "reptile", "predator", "evolution", "bird", "mammal"]):
        return (
            "Stunning wildlife photograph of exotic animal in dramatic natural habitat, "
            "intense golden hour lighting, bokeh background, National Geographic style, "
            "ultra sharp, cinematic, photorealistic, no text, no watermark, 16:9 landscape."
        )
    elif any(w in combined for w in ["volcano", "earthquake", "mountain", "weather", "lightning", "storm", "geology", "lava"]):
        return (
            "Dramatic photograph of massive natural geological phenomenon, "
            "lightning storm over volcanic eruption or towering mountain, "
            "vivid saturated colors, dramatic sky, cinematic, ultra detailed, photorealistic, "
            "no text, no watermark, 16:9 landscape."
        )
    elif any(w in combined for w in ["quantum", "physics", "atom", "particle", "energy", "laser", "light", "wave"]):
        return (
            "Futuristic visualization of quantum physics particle collision, "
            "glowing energy fields, electric arcs, vivid neon colors on black background, "
            "sci-fi laboratory aesthetic, ultra detailed, cinematic, no text, no watermark, 16:9 landscape."
        )
    elif any(w in combined for w in ["history", "ancient", "civilization", "egypt", "rome", "pyramid", "ruins", "fossil"]):
        return (
            "Dramatic cinematic photograph of ancient historic ruins at golden hour, "
            "massive stone architecture, dramatic sky with clouds, epic scale, "
            "warm cinematic grade, ultra detailed, photorealistic, no text, no watermark, 16:9 landscape."
        )
    elif any(w in combined for w in ["chemistry", "molecule", "reaction", "acid", "crystal", "element", "compound"]):
        return (
            "Macro photograph of colorful chemical crystals or molecular reaction, "
            "vivid jewel-like colors, microscope photography style, dark background, "
            "ultra sharp macro detail, cinematic lighting, photorealistic, no text, no watermark, 16:9 landscape."
        )
    elif any(w in combined for w in ["psychology", "brain", "behavior", "illusion", "perception", "emotion", "social"]):
        return (
            "Surreal conceptual photograph of human silhouette with glowing abstract mind visuals, "
            "dramatic gradient lighting, vivid teal and purple, cinematic, ultra detailed, "
            "no text, no watermark, 16:9 landscape."
        )
    else:
        return (
            "Stunning dramatic science photograph, glowing abstract energy patterns, "
            "vivid saturated colors on dark background, cinematic lighting, ultra detailed, "
            "futuristic and educational aesthetic, no text, no watermark, 16:9 landscape."
        )


def _build_prompt(title: str, topic: str) -> str:
    """Build a prompt for thumbnail background generation."""
    combined = (title + " " + topic).lower()

    if any(w in combined for w in ["train", "subway", "metro", "station", "railway"]):
        subject = "amazed Western tourist looking at massive digital departure board in crowded station"
        bg = "Shinjuku Station packed with commuters, neon signs, advertisements, bullet train"
    elif "elevator" in combined or "escalator" in combined:
        subject = "surprised Western tourist following Japanese escalator etiquette rules"
        bg = "sleek Tokyo metro station with bright lights, orderly commuters"
    elif any(w in combined for w in ["food", "ramen", "sushi", "dining", "restaurant", "chopstick", "noodle", "slurp"]):
        subject = "foreign tourist in wide-eyed delight eating steaming ramen at counter seat"
        bg = "cozy Japanese ramen shop with red lanterns, steam rising from bowls, chef cooking"
    elif any(w in combined for w in ["temple", "shrine", "torii", "kyoto", "monk", "buddha"]):
        subject = "Western tourists bowing respectfully before giant vermilion torii gate"
        bg = "Fushimi Inari shrine with thousands of orange torii gates, golden hour light, Kyoto"
    elif any(w in combined for w in ["onsen", "hot spring", "bath", "ryokan"]):
        subject = "foreign tourist relaxing in scenic outdoor onsen surrounded by snow"
        bg = "traditional Japanese ryokan with snowy mountains, cedar trees, steam rising"
    elif any(w in combined for w in ["work", "office", "business", "corporate", "salary", "overtime"]):
        subject = "foreign businessperson looking overwhelmed in busy Japanese office late at night"
        bg = "open-plan Tokyo office with salary workers, computers, Mount Fuji at sunset"
    elif any(w in combined for w in ["night", "nightlife", "bar", "izakaya", "drink"]):
        subject = "smiling foreign tourists discovering glowing izakaya alley entrance at night"
        bg = "Golden Gai alley Shinjuku, warm lantern glow, rain-wet street, neon signs"
    elif any(w in combined for w in ["hanami", "sakura", "cherry", "blossom", "flower"]):
        subject = "foreign tourists having picnic under full bloom cherry blossom trees"
        bg = "Ueno Park Tokyo in spring, pink sakura petals falling, blue sky, traditional lanterns"
    elif any(w in combined for w in ["festival", "matsuri"]):
        subject = "foreign tourists in colorful yukata watching traditional Japanese festival parade"
        bg = "lively summer matsuri with paper lanterns, food stalls, fireworks in sky"
    elif any(w in combined for w in ["tea", "matcha", "ceremony"]):
        subject = "foreign tourist experiencing traditional Japanese tea ceremony with kimono master"
        bg = "serene tatami room with shoji screens, bamboo garden visible outside, tea utensils"
    elif any(w in combined for w in ["shop", "market", "buy", "konbini", "convenience", "store"]):
        subject = "foreign tourist looking amazed inside brightly-lit Japanese convenience store"
        bg = "perfectly organized konbini shelves, colorful products, friendly staff"
    elif any(w in combined for w in ["manner", "etiquette", "rule", "guide", "tip", "must", "never", "rude"]):
        subject = "foreign tourist carefully following local customs, bowing politely to Japanese locals"
        bg = "bustling Shibuya scramble crossing at dusk, massive neon billboards, crowd crossing"
    elif any(w in combined for w in ["clean", "tidy", "organize", "minimalism"]):
        subject = "amazed foreign tourist on spotless Japanese street looking at pristine environment"
        bg = "ultra-clean Tokyo residential street, no litter, orderly bicycles, vending machines"
    elif any(w in combined for w in ["apartment", "house", "living", "home"]):
        subject = "foreign person entering traditional Japanese apartment, removing shoes at genkan"
        bg = "modern Japanese apartment entrance with shoe cabinet, wooden floor, sliding doors"
    elif any(w in combined for w in ["friend", "social", "meet", "group"]):
        subject = "diverse group of foreign and Japanese friends laughing together at izakaya table"
        bg = "cozy Japanese izakaya with wooden tables, sake bottles, warm lighting, food plates"
    else:
        subject = "excited foreign tourists exploring beautiful traditional Japanese street"
        bg = "photogenic Kyoto alley with stone lanterns, wooden machiya houses, cherry blossoms"

    return (
        f"Cinematic wide-angle travel photograph. {subject}, positioned on the RIGHT side of the frame. "
        f"{bg} fills the background. "
        "Vivid, saturated colors. Dramatic golden hour or blue hour lighting. "
        "Shallow depth of field with bokeh. Professional travel photography style. "
        "The left portion is slightly darker — ideal for text overlay. "
        "Photorealistic, hyperdetailed, 16:9 landscape format. "
        "No text, no words, no letters, no watermarks, no logos."
    )


def _generate_pollinations(title: str, topic: str, output_path: Path, prompt: str | None = None) -> Path | None:
    """Generate background with Pollinations.ai (completely free, no API key)."""
    try:
        prompt = prompt or _build_prompt(title, topic)
        encoded = urllib.parse.quote(prompt)
        # Use non-deterministic seed so each generation creates a fresh image
        seed = random.randint(0, 2**31 - 1)
        
        # Free tier allows 1 image / 45s per IP (HTTP 402 FREE_LIMIT otherwise),
        # so try exactly one model per call; retrying other models back-to-back
        # only burns time and always hits the limit.
        model = POLLINATIONS_MODEL
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={W}&height={H}&model={model}&nologo=true&seed={seed}"
        )
        logger.info(f"Generating image with Pollinations.ai ({model}) for: {title[:50]}")
        r = requests.get(url, timeout=120)
        r.raise_for_status()

        # Verify we got image data
        if len(r.content) < 1000:
            raise ValueError(f"Response too small ({len(r.content)} bytes)")

        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        img = img.resize((W, H), Image.LANCZOS)
        img.save(str(output_path), "JPEG", quality=95)
        logger.info(f"Pollinations.ai ({model}) background saved: {output_path}")
        return output_path

    except Exception as e:
        logger.warning(f"Pollinations.ai image generation failed: {e}")
        return None


def _generate_gemini(title: str, topic: str, output_path: Path, prompt: str | None = None) -> Path | None:
    """Generate background with Gemini (requires paid plan for image generation)."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        prompt = prompt or _build_prompt(title, topic)
        logger.info(f"Generating image with Gemini for: {title[:50]}")

        # Try newest image-capable models first
        for model in ["gemini-3.1-flash-image-preview", "gemini-2.5-flash-image"]:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                    ),
                )
                for part in response.candidates[0].content.parts:
                    if getattr(part, "inline_data", None):
                        image_bytes = base64.b64decode(part.inline_data.data)
                        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                        img = img.resize((W, H), Image.LANCZOS)
                        img.save(str(output_path), "JPEG", quality=95)
                        logger.info(f"Gemini ({model}) background saved: {output_path}")
                        return output_path
            except Exception as model_err:
                logger.debug(f"Gemini model {model} failed: {model_err}")
                continue

        logger.warning("Gemini returned no image from any model.")
        return None

    except Exception as e:
        logger.warning(f"Gemini image generation failed: {e}")
        return None


def _generate_openai(title: str, topic: str, output_path: Path, prompt: str | None = None) -> Path | None:
    """Generate background with DALL-E 3 (paid, fallback)."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt = prompt or _build_prompt(title, topic)
        logger.info(f"Generating image with DALL-E 3 for: {title[:50]}")

        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1792x1024",
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url
        r = requests.get(image_url, timeout=60)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        img = img.resize((W, H), Image.LANCZOS)
        img.save(str(output_path), "JPEG", quality=95)
        logger.info(f"DALL-E 3 background saved: {output_path}")
        return output_path

    except Exception as e:
        logger.warning(f"DALL-E 3 image generation failed: {e}")
        return None


def generate_bg_image(title: str, topic: str, output_path: Path) -> Path | None:
    """
    Generate a thumbnail background image.
      1. Pollinations.ai (free, no key) — one model, one attempt
      2. None → caller uses the existing programmatic background

    HuggingFace FLUX.1-schnell was removed (HTTP 410, deprecated on hf-inference).
    _generate_openai / _generate_gemini are kept but no longer in the chain.
    """
    return _generate_pollinations(title, topic, output_path)


def generate_facts_bg_image(title: str, topic: str, output_path: Path) -> Path | None:
    """Generate an AI background for Facts & Wonders thumbnails using science/nature prompts.
    Same policy as generate_bg_image: one Pollinations attempt, else None (programmatic fallback).
    """
    prompt = _build_facts_prompt(title, topic)
    return _generate_pollinations(title, topic, output_path, prompt=prompt)
