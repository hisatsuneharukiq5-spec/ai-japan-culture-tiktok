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


def _generate_pollinations(title: str, topic: str, output_path: Path) -> Path | None:
    """Generate background with Pollinations.ai (completely free, no API key)."""
    try:
        prompt = _build_prompt(title, topic)
        encoded = urllib.parse.quote(prompt)
        # Use non-deterministic seed so each generation creates a fresh image
        seed = random.randint(0, 2**31 - 1)
        
        # Try multiple models for better success rate
        models = ["flux-realism", "flux", "flux-pro"]
        
        for model in models:
            try:
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
            except Exception as model_err:
                logger.debug(f"Pollinations.ai model {model} failed: {model_err}")
                continue
                
        raise ValueError("All Pollinations.ai models failed")
        
    except Exception as e:
        logger.warning(f"Pollinations.ai image generation failed: {e}")
        return None


def _generate_huggingface(title: str, topic: str, output_path: Path) -> Path | None:
    """Generate background with HuggingFace Inference API (free with free HF account)."""
    api_key = os.getenv("HF_API_TOKEN", "")
    if not api_key or api_key.startswith("your_"):
        return None

    try:
        prompt = _build_prompt(title, topic)
        logger.info(f"Generating image with HuggingFace FLUX.1 for: {title[:50]}")
        r = requests.post(
            "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"inputs": prompt},
            timeout=120,
        )
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        img = img.resize((W, H), Image.LANCZOS)
        img.save(str(output_path), "JPEG", quality=95)
        logger.info(f"HuggingFace background saved: {output_path}")
        return output_path
    except Exception as e:
        logger.warning(f"HuggingFace image generation failed: {e}")
        return None


def _generate_gemini(title: str, topic: str, output_path: Path) -> Path | None:
    """Generate background with Gemini (requires paid plan for image generation)."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        prompt = _build_prompt(title, topic)
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


def _generate_openai(title: str, topic: str, output_path: Path) -> Path | None:
    """Generate background with DALL-E 3 (paid, fallback)."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt = _build_prompt(title, topic)
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
    Priority:
      1. Pollinations.ai   (free, no key needed — set HF_API_TOKEN=skip to skip)
      2. HuggingFace FLUX  (free with free HF account — set HF_API_TOKEN in .env)
      3. DALL-E 3          (paid, set OPENAI_API_KEY)
      4. Gemini            (paid plan required, set GEMINI_API_KEY)
      5. None              → programmatic thumbnail fallback
    """
    result = _generate_pollinations(title, topic, output_path)
    if result:
        return result

    result = _generate_huggingface(title, topic, output_path)
    if result:
        return result

    result = _generate_openai(title, topic, output_path)
    if result:
        return result

    result = _generate_gemini(title, topic, output_path)
    if result:
        return result

    return None
