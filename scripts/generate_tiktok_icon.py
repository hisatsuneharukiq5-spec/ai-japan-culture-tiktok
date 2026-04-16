#!/usr/bin/env python3
"""Generate TikTok App Icon for AI Japan Culture."""

import sys
from pathlib import Path
from PIL import Image, ImageDraw
import math

# Setup paths
OUTPUT_DIR = Path(__file__).parent.parent / "output" / "app_icons"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_tiktok_icon_simple():
    """Generate a TikTok app icon with magenta gradient and music notes."""
    
    size = 1024
    icon = Image.new("RGB", (size, size), color=(0, 0, 0))
    draw = ImageDraw.Draw(icon)
    
    # TikTok gradient: magenta to black
    for i in range(size):
        ratio = i / size
        r = int(229 * (1 - ratio))
        g = int(39 * (1 - ratio))
        b = int(141 * (1 - ratio))
        draw.rectangle([(0, i), (size, i + 1)], fill=(r, g, b))
    
    # White circle in center (TikTok style)
    circle_size = 400
    draw.ellipse(
        [(size // 2 - circle_size // 2, size // 2 - circle_size // 2),
         (size // 2 + circle_size // 2, size // 2 + circle_size // 2)],
        fill=(255, 255, 255)
    )
    
    # Magenta music notes inside
    note_x = size // 2
    note_y = size // 2
    
    # Left note
    draw.ellipse([(note_x - 120, note_y - 40), (note_x - 80, note_y + 40)],
                 fill=(229, 39, 141))
    draw.rectangle([(note_x - 90, note_y - 160), (note_x - 70, note_y - 40)],
                   fill=(229, 39, 141))
    
    # Right note
    draw.ellipse([(note_x + 80, note_y + 40), (note_x + 120, note_y + 120)],
                 fill=(229, 39, 141))
    draw.rectangle([(note_x + 90, note_y - 80), (note_x + 110, note_y + 40)],
                   fill=(229, 39, 141))
    
    # Connecting beam
    draw.line([(note_x - 70, note_y - 40), (note_x + 90, note_y - 80)],
              fill=(229, 39, 141), width=16)
    
    # Save
    output_path = OUTPUT_DIR / "tiktok_icon_1024x1024.png"
    icon.save(output_path, "PNG")
    
    return output_path


def generate_tiktok_icon_with_japan():
    """Generate TikTok icon with Japan-themed elements."""
    
    size = 1024
    icon = Image.new("RGB", (size, size), color=(0, 0, 0))
    draw = ImageDraw.Draw(icon, "RGBA")
    
    # TikTok gradient: magenta to navy
    for i in range(size):
        ratio = i / size
        r = int(229 * (1 - ratio * 0.5))
        g = int(39 * (1 - ratio * 0.8))
        b = int(141 + 114 * ratio)
        draw.rectangle([(0, i), (size, i + 1)], fill=(r, g, b))
    
    # Large white background circle
    circle_size = 640
    draw.ellipse(
        [(size // 2 - circle_size // 2, size // 2 - circle_size // 2),
         (size // 2 + circle_size // 2, size // 2 + circle_size // 2)],
        fill=(255, 255, 255, 240)
    )
    
    # Music notes (TikTok signature)
    note_x = size // 3
    note_y = size // 2 + 60
    
    # Left note
    draw.ellipse([(note_x - 80, note_y + 80), (note_x - 20, note_y + 140)],
                 fill=(229, 39, 141))
    draw.rectangle([(note_x - 40, note_y - 120), (note_x - 10, note_y + 80)],
                   fill=(229, 39, 141), width=6)
    
    # Right note
    draw.ellipse([(note_x + 120, note_y + 120), (note_x + 180, note_y + 180)],
                 fill=(229, 39, 141))
    draw.rectangle([(note_x + 140, note_y - 80), (note_x + 170, note_y + 120)],
                   fill=(229, 39, 141), width=6)
    
    # Connecting beam
    draw.line([(note_x - 10, note_y - 120), (note_x + 140, note_y - 80)],
              fill=(229, 39, 141), width=12)
    
    # Mount Fuji (Japan element) on the right
    fuji_x = size - 360
    fuji_y = size - 300
    fuji_color = (255, 100, 100)
    
    # Fuji triangle
    draw.polygon([(fuji_x + 120, fuji_y + 200), 
                  (fuji_x + 240, fuji_y),
                  (fuji_x + 360, fuji_y + 200)],
                 fill=fuji_color)
    
    # Snow cap
    draw.polygon([(fuji_x + 200, fuji_y + 80),
                  (fuji_x + 240, fuji_y),
                  (fuji_x + 280, fuji_y + 80)],
                 fill=(255, 255, 255))
    
    # Sakura flowers (cherry blossoms)
    sakura_color = (255, 150, 200)
    for sx, sy in [(size // 4, size // 4), (size - 200, size // 3)]:
        # 5-petal flower
        for i in range(5):
            angle = (i * 72) * math.pi / 180
            px = int(sx + 60 * math.cos(angle))
            py = int(sy + 60 * math.sin(angle))
            draw.ellipse([(px - 20, py - 20), (px + 20, py + 20)],
                        fill=sakura_color)
        # Center
        draw.ellipse([(sx - 16, sy - 16), (sx + 16, sy + 16)],
                    fill=(255, 50, 100))
    
    # Save
    output_path = OUTPUT_DIR / "tiktok_icon_japan_1024x1024.png"
    icon.save(output_path, "PNG")
    
    return output_path


def main():
    """Generate all TikTok app icons."""
    print("\n" + "=" * 70)
    print("🎨 TIKTOK APP ICON GENERATOR")
    print("=" * 70)
    
    print("\n1️⃣ Generating TikTok icon (simple)...")
    icon1 = generate_tiktok_icon_simple()
    print(f"   ✅ {icon1.name}")
    
    print("\n2️⃣ Generating TikTok icon (Japan-themed)...")
    icon2 = generate_tiktok_icon_with_japan()
    print(f"   ✅ {icon2.name}")
    
    print("\n" + "=" * 70)
    print("✅ ICON GENERATION COMPLETE")
    print("=" * 70)
    
    print(f"\n📁 Icons saved to:")
    print(f"   {OUTPUT_DIR}")
    
    print(f"\n📝 Files created:")
    print(f"   • {icon1.name}")
    print(f"   • {icon2.name}")
    
    print(f"\n📐 Specifications (both icons):")
    print(f"   • Size: 1024x1024 pixels")
    print(f"   • Format: PNG (transparent background support)")
    print(f"   • Colors: TikTok brand magenta/pink + Japan themes")
    
    print(f"\n💡 Upload to TikTok Developer Center:")
    print(f"   → https://developer.tiktok.com/")
    print(f"   → Select your app → Settings")
    print(f"   → Upload icon.png (1024x1024)")
    
    print(f"\n🎯 Which icon to use?")
    print(f"   • Simple: Clean, professional, traditional TikTok look")
    print(f"   • Japan-themed: Shows your content focus (Japan culture)")
    print(f"\n   Recommendation: Use Japan-themed for better branding!")


if __name__ == "__main__":
    main()
