#!/usr/bin/env python3
"""
Generate TikTok App Icon for AI Japan Culture.
Creates a professional 512x512px icon for TikTok Developer Center.
"""

import os
import sys
import io
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw, ImageFont
import requests

from src.utils import setup_logger, PROJECT_ROOT

logger = setup_logger("tiktok_icon_generator")

ICONS_DIR = PROJECT_ROOT / "output" / "app_icons"
ICONS_DIR.mkdir(parents=True, exist_ok=True)


def generate_tiktok_icon_with_ai() -> Path:
    """Generate TikTok app icon using AI image generation.
    
    Creates a 512x512px icon with Japan/AI theme for TikTok app.
    """
    try:
        # Try multiple AI services in order of preference
        
        # 1. Try Gemini API
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            logger.info("🎨 Generating with Gemini API...")
            result = _generate_with_gemini(gemini_key)
            if result:
                return result
        
        # 2. Try HuggingFace
        hf_token = os.getenv("HF_API_TOKEN")
        if hf_token:
            logger.info("🎨 Generating with HuggingFace...")
            result = _generate_with_huggingface(hf_token)
            if result:
                return result
        
        # 3. Fallback: Generate programmatically
        logger.info("🎨 Generating icon programmatically...")
        return _generate_programmatic_icon()
        
    except Exception as e:
        logger.error(f"Icon generation failed: {e}")
        logger.info("Using fallback programmatic generation...")
        return _generate_programmatic_icon()


def _generate_with_gemini(api_key: str) -> Path | None:
    """Generate icon using Google Gemini API."""
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=api_key)
        
        prompt = """Create a professional 512x512px app icon for TikTok.

Theme: AI learning Japanese culture
Style: Modern, clean, vibrant
Elements:
- TikTok's signature colors (black, white, vibrant pink/magenta)
- Subtle Japan elements: sakura petals, Mount Fuji silhouette, or torii gate
- AI/technology element: neural network lines or digital grid
- The character/mascot should look friendly and approachable
- Must work well as a small app icon

The icon should be:
- Square format (512x512px)
- Colorful but professional
- Highly recognizable even at small sizes
- Appeal to both AI enthusiasts and Japan culture lovers

Generate a single, finished app icon image ready for use."""
        
        model = genai.GenerativeModel('gemini-pro-vision')
        logger.info("⏳ Sending request to Gemini...")
        
        # Gemini doesn't generate images via this API
        # This is a placeholder for the correct approach
        logger.warning("Gemini image generation in pro-vision not available. Trying alternative.")
        return None
        
    except Exception as e:
        logger.warning(f"Gemini generation failed: {e}")
        return None


def _generate_with_huggingface(hf_token: str) -> Path | None:
    """Generate icon using HuggingFace Inference API."""
    try:
        api_url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1"
        
        headers = {"Authorization": f"Bearer {hf_token}"}
        
        payload = {
            "inputs": """Professional TikTok app icon 512x512px. 
            Theme: AI learning Japanese culture. 
            Style: Modern, clean, vibrant. 
            Elements: TikTok signature magenta colors, Japan (sakura petals, Mount Fuji), AI (neural networks, digital).
            The icon should be highly recognizable, colorful but professional, friendly mascot character.""",
            "parameters": {
                "height": 512,
                "width": 512,
                "num_inference_steps": 50,
                "guidance_scale": 7.5
            }
        }
        
        logger.info("⏳ Sending request to HuggingFace...")
        response = requests.post(api_url, headers=headers, json=payload, timeout=120)
        
        if response.status_code == 200:
            # Save image
            image_data = response.content
            output_path = ICONS_DIR / "tiktok_icon_ai_512x512.png"
            
            with open(output_path, "wb") as f:
                f.write(image_data)
            
            logger.info(f"✅ Icon generated: {output_path}")
            return output_path
        else:
            logger.warning(f"HuggingFace error: {response.status_code} {response.text}")
            return None
            
    except Exception as e:
        logger.warning(f"HuggingFace generation failed: {e}")
        return None


def _generate_programmatic_icon() -> Path:
    """Generate icon programmatically using PIL.
    
    Creates a professional-looking TikTok app icon with:
    - TikTok's signature magenta/pink colors
    - Japan cultural elements (sakura, Mount Fuji)
    - AI technology elements
    """
    import math
    
    size = 512
    icon = Image.new("RGB", (size, size), color=(255, 255, 255))
    draw = ImageDraw.Draw(icon, "RGBA")
    
    # Create gradient background
    for i in range(size):
        ratio = i / size
        r = int(magenta_start[0] * (1 - ratio) + 0 * ratio)
        g = int(magenta_start[1] * (1 - ratio) + 0 * ratio)
        b = int(magenta_start[2] * (1 - ratio) + 0 * ratio)
        draw.rectangle([(0, i), (size, i+1)], fill=(r, g, b))
    
    # Draw music note (TikTok symbol)
    # Left note head
    music_note_x = size // 4
    music_note_y = size // 3
    draw.ellipse(
        [(music_note_x - 30, music_note_y + 80), (music_note_x + 30, music_note_y + 140)],
        fill=(255, 255, 255)
    )
    # Stem
    draw.rectangle(
        [(music_note_x + 25, music_note_y - 40), (music_note_x + 35, music_note_y + 80)],
        fill=(255, 255, 255)
    )
    # Double beam
    draw.polygon(
        [(music_note_x + 35, music_note_y), (music_note_x + 120, music_note_y - 30),
         (music_note_x + 120, music_note_y - 10), (music_note_x + 35, music_note_y + 20)],
        fill=(255, 255, 255)
    )
    draw.polygon(
        [(music_note_x + 35, music_note_y + 30), (music_note_x + 100, music_note_y),
         (music_note_x + 100, music_note_y + 20), (music_note_x + 35, music_note_y + 50)],
        fill=(255, 255, 255)
    )
    
    # Draw Mount Fuji silhouette (small, in corner)
    fuji_x = size - 150
    fuji_y = size - 100
    draw.polygon(
        [(fuji_x + 50, fuji_y + 80), (fuji_x + 100, fuji_y), (fuji_x + 150, fuji_y + 80)],
        fill=(255, 200, 100, 150)  # Light silhouette with transparency
    )
    
    # Draw sakura flowers (3 petals)
    sakura_positions = [
        (size * 0.75, size * 0.25),
        (size * 0.85, size * 0.35),
        (size * 0.70, size * 0.45)
    ]
    
    for sx, sy in sakura_positions:
        # 5-petal flower
        for i in range(5):
            angle = (i * 72) * 3.14159 / 180
            px = sx + 25 * math.cos(angle)
            py = sy + 25 * math.sin(angle)
            draw.ellipse([(px - 8, py - 8), (px + 8, py + 8)], fill=(255, 182, 193, 200))
        
        # Center
        draw.ellipse([(sx - 5, sy - 5), (sx + 5, sy + 5)], fill=(255, 100, 100))
    
    # Draw neural network dots (AI element)
    for angle in range(0, 360, 45):
        rad = angle * math.pi / 180
        x = size // 2 + 120 * math.cos(rad)
        y = size // 2 + 120 * math.sin(rad)
        draw.ellipse([(x - 6, y - 6), (x + 6, y + 6)], fill=(255, 255, 255))
    
    # Center circle
    draw.ellipse(
        [(size // 2 - 10, size // 2 - 10), (size // 2 + 10, size // 2 + 10)],
        fill=(255, 100, 150)
    )
    
    # Save icon
    output_path = ICONS_DIR / "tiktok_icon_512x512.png"
    icon.save(output_path, "PNG")
    
    logger.info(f"✅ Programmatic icon created: {output_path}")
    return output_path


def generate_tiktok_icon_simple() -> Path:
    """Generate a simpler TikTok app icon (faster, reliable)."""
    
    size = 512
    icon = Image.new("RGB", (size, size), color=(0, 0, 0))
    draw = ImageDraw.Draw(icon)
    
    # TikTok gradient: magenta to black
    for i in range(size):
        ratio = i / size
        r = int(229 * (1 - ratio))
        g = int(39 * (1 - ratio))
        b = int(141 * (1 - ratio))
        draw.rectangle([(0, i), (size, i+1)], fill=(r, g, b))
    
    # White circle in center (TikTok style)
    circle_size = 200
    draw.ellipse(
        [(size // 2 - circle_size // 2, size // 2 - circle_size // 2),
         (size // 2 + circle_size // 2, size // 2 + circle_size // 2)],
        fill=(255, 255, 255)
    )
    
    # Magenta music notes inside
    note_x = size // 2
    note_y = size // 2
    
    # Left note
    draw.ellipse([(note_x - 60, note_y - 20), (note_x - 40, note_y + 20)], 
                fill=(229, 39, 141))
    draw.rectangle([(note_x - 45, note_y - 80), (note_x - 35, note_y - 20)], 
                  fill=(229, 39, 141))
    
    # Right note
    draw.ellipse([(note_x + 40, note_y + 20), (note_x + 60, note_y + 60)], 
                fill=(229, 39, 141))
    draw.rectangle([(note_x + 45, note_y - 40), (note_x + 55, note_y + 20)], 
                  fill=(229, 39, 141))
    
    # Connecting beam
    draw.line([(note_x - 35, note_y - 20), (note_x + 45, note_y - 40)], 
             fill=(229, 39, 141), width=8)
    
    # Save
    output_path = ICONS_DIR / "tiktok_icon_simple_512x512.png"
    icon.save(output_path, "PNG")
    
    logger.info(f"✅ Simple icon created: {output_path}")
    return output_path


def main():
    """Generate TikTok app icons."""
    print("\n" + "=" * 70)
    print("🎨 TIKTOK APP ICON GENERATOR")
    print("=" * 70)
    
    # Generate both versions
    print("\n1️⃣ Generating AI-powered icon...")
    ai_icon = generate_tiktok_icon_with_ai()
    print(f"   📍 {ai_icon}")
    
    print("\n2️⃣ Generating simple icon...")
    simple_icon = generate_tiktok_icon_simple()
    print(f"   📍 {simple_icon}")
    
    print("\n" + "=" * 70)
    print("✅ ICON GENERATION COMPLETE")
    print("=" * 70)
    print(f"\n📁 Icons saved to: {ICONS_DIR}")
    print(f"\n📝 For TikTok Developer Center:")
    print(f"   • Recommended: {ai_icon.name}")
    print(f"   • Fallback: {simple_icon.name}")
    print(f"\n📐 Specifications:")
    print(f"   • Size: 512x512 pixels")
    print(f"   • Format: PNG")
    print(f"   • Total: 2 icon variations")
    print("\n💡 Upload the icon at:")
    print("   https://developer.tiktok.com/app/{YOUR_APP_ID}/settings")


if __name__ == "__main__":
    main()
