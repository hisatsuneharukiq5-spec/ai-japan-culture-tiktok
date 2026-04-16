#!/usr/bin/env python3
"""Generate thumbnails using Pexels real photos as backgrounds."""

import os
import sys
import requests
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import urllib.parse

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from src.utils import setup_logger

logger = setup_logger("pexels_thumbnail_generator")

W, H = 1280, 720
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

def get_pexels_photo(search_query: str, output_path: Path) -> Path | None:
    """Download a relevant photo from Pexels."""
    if not PEXELS_API_KEY:
        logger.warning("PEXELS_API_KEY not set")
        return None
    
    try:
        headers = {"Authorization": PEXELS_API_KEY}
        url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(search_query)}&per_page=5&orientation=landscape"
        
        logger.info(f"Searching Pexels for: {search_query}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        if not data.get("photos"):
            logger.warning(f"No photos found for: {search_query}")
            return None
        
        # Get the first high-quality photo
        photo = data["photos"][0]
        image_url = photo["src"]["large2x"]  # High quality
        
        logger.info(f"Downloading photo from: {image_url}")
        img_response = requests.get(image_url, timeout=60)
        img_response.raise_for_status()
        
        # Open and resize
        img = Image.open(io.BytesIO(img_response.content)).convert("RGB")
        img = img.resize((W, H), Image.LANCZOS)
        img.save(str(output_path), "JPEG", quality=95)
        
        logger.info(f"Pexels photo saved: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Pexels photo download failed: {e}")
        return None


def get_search_query(title: str, topic: str) -> str:
    """Generate Pexels search query based on video content."""
    combined = (title + " " + topic).lower()
    
    if any(w in combined for w in ["hanami", "sakura", "cherry", "blossom"]):
        return "cherry blossom japan tourists spring"
    elif any(w in combined for w in ["temple", "shrine", "torii", "kyoto"]):
        return "fushimi inari shrine torii gate kyoto tourists"
    elif any(w in combined for w in ["tea", "matcha", "ceremony"]):
        return "japanese tea ceremony matcha traditional"
    elif any(w in combined for w in ["convenience", "konbini", "store"]):
        return "japanese convenience store interior bright"
    elif any(w in combined for w in ["clean", "street", "tidy"]):
        return "clean tokyo street japan urban"
    elif any(w in combined for w in ["friend", "social", "meet"]):
        return "japanese friends izakaya restaurant laughing"
    elif any(w in combined for w in ["tipping", "rude", "manner", "etiquette"]):
        return "japan tourist shibuya crossing tokyo"
    elif any(w in combined for w in ["apartment", "house", "home"]):
        return "japanese apartment interior modern minimalist"
    elif any(w in combined for w in ["ramen", "food", "sushi"]):
        return "japanese ramen shop interior steam"
    elif any(w in combined for w in ["train", "station", "subway"]):
        return "tokyo station japan trains crowded"
    elif any(w in combined for w in ["work", "office", "business"]):
        return "tokyo office workers business district"
    elif any(w in combined for w in ["festival", "matsuri"]):
        return "japanese festival lanterns matsuri night"
    else:
        return "japan traditional street kyoto tourists"


def add_text_overlay(img_path: Path, title: str, output_path: Path) -> Path:
    """Add text overlay to Pexels photo."""
    img = Image.open(img_path).convert("RGBA")
    
    # Dark gradient overlay on left for text readability
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    fade_w = int(W * 0.65)
    for x in range(fade_w):
        t = x / fade_w
        alpha = int(200 * (1 - t ** 0.5))
        ov_draw.line([(x, 0), (x, H)], fill=(0, 0, 0, alpha))
    
    # Bottom gradient
    for y in range(H - 100, H):
        t = (y - (H - 100)) / 100
        alpha = int(180 * t)
        ov_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    
    img = Image.alpha_composite(img, overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    
    # Load fonts
    font_paths = [
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    
    title_font = None
    for fp in font_paths:
        try:
            title_font = ImageFont.truetype(fp, 90)
            break
        except:
            continue
    
    if not title_font:
        title_font = ImageFont.load_default()
    
    # Split title into lines
    words = title.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=title_font)
        if bbox[2] - bbox[0] < 700:  # Max width
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(" ".join(current_line))
    
    # Draw text with outline
    y_pos = 150
    for line in lines:
        # Outline
        for dx in [-4, -2, 0, 2, 4]:
            for dy in [-4, -2, 0, 2, 4]:
                if dx != 0 or dy != 0:
                    draw.text((60 + dx, y_pos + dy), line, font=title_font, fill=(0, 0, 0))
        # Main text
        draw.text((60, y_pos), line, font=title_font, fill=(255, 215, 0))  # Gold
        y_pos += 100
    
    img.save(str(output_path), "JPEG", quality=95)
    logger.info(f"Text overlay added: {output_path}")
    return output_path


def generate_pexels_thumbnail(title: str, topic: str, output_filename: str) -> Path:
    """Generate thumbnail using Pexels photo + text overlay."""
    thumb_dir = ROOT / "output" / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = thumb_dir / output_filename
    bg_path = thumb_dir / f"_bg_{output_filename}"
    
    # Get search query
    search_query = get_search_query(title, topic)
    
    # Download Pexels photo
    photo_path = get_pexels_photo(search_query, bg_path)
    
    if not photo_path:
        raise ValueError(f"Failed to download Pexels photo for: {search_query}")
    
    # Add text overlay
    result = add_text_overlay(photo_path, title, output_path)
    
    return result


if __name__ == "__main__":
    # Test
    result = generate_pexels_thumbnail(
        "Hanami — Why Japan Goes Crazy for Cherry Blossoms",
        "Cherry blossom viewing tradition, hanami culture, sakura season",
        "hanami_pexels_test.jpg"
    )
    print(f"Generated: {result}")
