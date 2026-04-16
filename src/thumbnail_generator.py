import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

from src.utils import setup_logger, PROJECT_ROOT

logger = setup_logger("thumbnail_generator")

THUMBNAIL_DIR = PROJECT_ROOT / "output" / "thumbnails"
W, H = 1280, 720

FONT_PATHS = [
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/verdanab.ttf",
]
KANJI_FONT_PATHS = [
    "C:/Windows/Fonts/NotoSansJP-VF.ttf",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
]

# ---------------------------------------------------------------------------
# 6 distinct color schemes:
# bg/bg2 = background gradient start/end
# t1/t2/t3 = text line colors (headline / body / accent)
# el/el2 = main element (circle/diagonal) dark/bright
# ring = circle ring accent
# badge = number badge color
# glow = background glow tint
# ---------------------------------------------------------------------------
SCHEMES = [
    # 0: Navy + Gold (classic Japan)
    dict(name="navy",
         bg=(8, 10, 28), bg2=(16, 18, 52),
         glow=(30, 40, 120),
         t1=(255, 215, 0), t2=(255, 255, 255), t3=(255, 88, 55),
         el=(185, 0, 36), el2=(220, 38, 60), ring=(255, 255, 255),
         badge=(255, 215, 0), badge_txt=(20, 20, 20)),
    # 1: Forest + Lime
    dict(name="forest",
         bg=(4, 18, 8), bg2=(8, 32, 14),
         glow=(20, 100, 40),
         t1=(55, 235, 110), t2=(255, 255, 255), t3=(255, 168, 0),
         el=(0, 125, 52), el2=(18, 168, 70), ring=(55, 235, 110),
         badge=(55, 235, 110), badge_txt=(5, 40, 15)),
    # 2: Purple + Cyan
    dict(name="purple",
         bg=(14, 6, 30), bg2=(24, 10, 55),
         glow=(70, 20, 140),
         t1=(0, 210, 255), t2=(255, 255, 255), t3=(200, 80, 255),
         el=(105, 0, 190), el2=(145, 28, 225), ring=(0, 210, 255),
         badge=(0, 210, 255), badge_txt=(10, 5, 40)),
    # 3: Volcanic + Orange
    dict(name="volcanic",
         bg=(18, 6, 4), bg2=(32, 10, 5),
         glow=(120, 45, 10),
         t1=(255, 162, 0), t2=(255, 245, 200), t3=(255, 55, 0),
         el=(192, 40, 0), el2=(228, 72, 8), ring=(255, 162, 0),
         badge=(255, 162, 0), badge_txt=(30, 8, 0)),
    # 4: Ocean Teal + Gold
    dict(name="teal",
         bg=(4, 16, 22), bg2=(6, 28, 38),
         glow=(10, 80, 100),
         t1=(0, 218, 202), t2=(255, 255, 255), t3=(255, 198, 0),
         el=(0, 122, 142), el2=(0, 165, 185), ring=(0, 218, 202),
         badge=(0, 218, 202), badge_txt=(4, 30, 38)),
    # 5: Crimson + Pink
    dict(name="crimson",
         bg=(22, 5, 14), bg2=(38, 8, 24),
         glow=(130, 20, 70),
         t1=(255, 105, 185), t2=(255, 240, 255), t3=(255, 218, 0),
         el=(175, 0, 80), el2=(210, 30, 100), ring=(255, 105, 185),
         badge=(255, 105, 185), badge_txt=(35, 5, 20)),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _get_kanji_font(size: int):
    for path in KANJI_FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return None


def _outline_text(draw, pos, text, font, fill, outline=(0, 0, 0), ow=5):
    x, y = pos
    for dx in range(-ow, ow + 1):
        for dy in range(-ow, ow + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def _blend(c1, c2, t):
    """Linear interpolation between two RGB tuples."""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _pick_scheme(title: str) -> dict:
    """Deterministic scheme selection from title hash."""
    return SCHEMES[hash(title) % len(SCHEMES)]


def _pick_template(title: str, topic: str) -> str:
    combined = (title + " " + topic).lower()
    if any(w in combined for w in ["rule", "tip", "mistake", "guide", "must", "things", "ways", "reason"]):
        return "rules"
    if any(w in combined for w in ["surprise", "shock", "secret", "never knew", "actually", "hidden", "truth", "reveal", "unbelievable"]):
        return "shock"
    return "culture"


def _get_thumbnail_lines(title: str) -> tuple:
    """Return (badge_number_or_None, [line1, line2, line3])."""
    num_match = re.search(r'\b(\d+)\b', title)
    badge = num_match.group(1) if num_match else None

    text = title.split(":", 1)[1].strip() if ":" in title else title
    text = re.sub(r'\b\d+\b\s*', '', text).strip()

    words = text.upper().split()
    lines, cur = [], ""
    for word in words:
        test = (cur + " " + word).strip()
        # Only break to next line if we still have room for more lines (< 2 filled)
        if cur and len(test) > 13 and len(lines) < 2:
            lines.append(cur)
            cur = word
        else:
            # 3rd line: keep accumulating all remaining words
            cur = test
    if cur:
        lines.append(cur)

    return badge, lines[:3]


def _draw_bg(draw, sc: dict):
    """Draw background: gradient + corner glow."""
    bg, bg2, glow_color = sc["bg"], sc["bg2"], sc["glow"]
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)], fill=_blend(bg, bg2, t))
    # Subtle glow in top-left corner
    for r in range(280, 0, -4):
        t = (280 - r) / 280
        color = _blend(glow_color, bg, 0.7 + t * 0.3)
        draw.ellipse([-r + 60, -r + 60, r + 60, r + 60], fill=color)


def _draw_japan_circle(draw, cx, cy, r, sc: dict, with_kanji=True):
    """Draw the Japan-flag red circle with scheme ring color."""
    # Glow
    for gr in range(r + 45, r, -3):
        color = _blend(sc["el"], sc["bg"], (gr - r) / 45)
        draw.ellipse([cx - gr, cy - gr, cx + gr, cy + gr], fill=color)
    # Main circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=sc["el"])
    # Highlight
    draw.ellipse([cx - r + 18, cy - r + 18, cx + 8, cy + 8], fill=sc["el2"])
    # Double ring
    for offset in [10, 20]:
        draw.ellipse(
            [cx - r - offset, cy - r - offset, cx + r + offset, cy + r + offset],
            outline=sc["ring"], width=2,
        )
    # Kanji
    if with_kanji:
        fn_k = _get_kanji_font(108)
        if fn_k:
            draw.text((cx - 75, cy - 75), "日本", font=fn_k, fill=(255, 255, 255))


def _draw_text_block(draw, lines, sc, text_x, y_start, font_sizes, max_width):
    """Draw stacked text lines and return y after last line."""
    colors = [sc["t1"], sc["t2"], sc["t3"]]
    y = y_start
    for i, line in enumerate(lines):
        if not line:
            continue
        font = _get_font(font_sizes[min(i, len(font_sizes) - 1)])
        color = colors[min(i, len(colors) - 1)]
        # Shrink font if text too wide
        while font_sizes[min(i, len(font_sizes) - 1)] > 40:
            bb = draw.textbbox((0, 0), line, font=font)
            if bb[2] - bb[0] <= max_width:
                break
            font = _get_font(font.size - 6)
        _outline_text(draw, (text_x, y), line, font, color, (0, 0, 0), 6)
        bb = draw.textbbox((0, 0), line, font=font)
        y += (bb[3] - bb[1]) + 10
    return y


def _draw_branding(draw, sc, text_x, y):
    """Separator bar + AI JAPAN label."""
    draw.rectangle([text_x, y + 14, text_x + 500, y + 20], fill=sc["t1"])
    fn_sm = _get_font(36)
    _outline_text(draw, (text_x, y + 28), "AI JAPAN", fn_sm, (195, 195, 195), (0, 0, 0), 3)


def _draw_branding_label(draw, accent_color, text_x, y, label):
    """Separator bar + arbitrary branding label."""
    draw.rectangle([text_x, y + 14, text_x + 500, y + 20], fill=accent_color)
    fn_sm = _get_font(36)
    _outline_text(draw, (text_x, y + 28), label, fn_sm, (225, 225, 225), (0, 0, 0), 3)


# ---------------------------------------------------------------------------
# Template 1: RULES — number badge + text + Japan circle
# ---------------------------------------------------------------------------
def _thumbnail_rules(title: str, sc: dict, output_path: Path) -> None:
    img = Image.new("RGB", (W, H), sc["bg"])
    draw = ImageDraw.Draw(img)
    _draw_bg(draw, sc)

    # Right: Japan circle
    _draw_japan_circle(draw, cx=990, cy=358, r=245, sc=sc)

    badge, lines = _get_thumbnail_lines(title)

    if badge:
        # Large badge circle (left)
        bx, by, br = 148, 195, 128
        # Outer dark ring
        draw.ellipse([bx - br - 6, by - br - 6, bx + br + 6, by + br + 6], fill=sc["bg"])
        draw.ellipse([bx - br, by - br, bx + br, by + br], fill=sc["badge"])
        # Inner highlight
        draw.ellipse([bx - br + 10, by - br + 10, bx, by], fill=_blend(sc["badge"], (255, 255, 255), 0.25))
        fn_num = _get_font(185)
        bb = draw.textbbox((0, 0), badge, font=fn_num)
        nw, nh = bb[2] - bb[0], bb[3] - bb[1]
        _outline_text(draw, (bx - nw // 2, by - nh // 2 - 12), badge,
                      fn_num, sc["badge_txt"], (0, 0, 0), 2)
        text_x = 300
    else:
        text_x = 50

    y_end = _draw_text_block(draw, lines, sc, text_x, 62, [108, 86, 66], 590)
    _draw_branding(draw, sc, text_x, y_end)

    # Bottom bar
    draw.rectangle([0, H - 14, W, H], fill=sc["el"])
    img.save(str(output_path), "JPEG", quality=95)
    logger.info(f"Thumbnail [rules/{sc['name']}] saved: {output_path}")


# ---------------------------------------------------------------------------
# Template 2: SHOCK — diagonal + exclamation + bold text
# ---------------------------------------------------------------------------
def _thumbnail_shock(title: str, sc: dict, output_path: Path) -> None:
    img = Image.new("RGB", (W, H), sc["bg"])
    draw = ImageDraw.Draw(img)
    _draw_bg(draw, sc)

    # Diagonal band (right half)
    draw.polygon([(640, 0), (W, 0), (W, H), (430, H)], fill=sc["el"])
    draw.polygon([(710, 0), (W, 0), (W, int(H * 0.6))], fill=sc["el2"])
    draw.polygon([(800, 0), (W, 0), (W, int(H * 0.25))], fill=_blend(sc["el2"], (255, 255, 255), 0.15))

    # Bright "!" on the diagonal
    fn_ex = _get_font(305)
    _outline_text(draw, (985, -30), "!", fn_ex, sc["t1"], (0, 0, 0), 10)

    # Kanji bottom-right
    fn_k = _get_kanji_font(76)
    if fn_k:
        _outline_text(draw, (880, 545), "日本", fn_k, (255, 255, 255), (0, 0, 0), 3)

    # Left: bold text
    _, lines = _get_thumbnail_lines(title)
    y_end = _draw_text_block(draw, lines, sc, 48, 55, [106, 85, 65], 560)
    _draw_branding(draw, sc, 48, y_end)

    draw.rectangle([0, H - 14, W, H], fill=sc["el"])
    img.save(str(output_path), "JPEG", quality=95)
    logger.info(f"Thumbnail [shock/{sc['name']}] saved: {output_path}")


# ---------------------------------------------------------------------------
# Template 3: CULTURE — solid accent panel + Japan circle + divider
# ---------------------------------------------------------------------------
def _thumbnail_culture(title: str, sc: dict, output_path: Path) -> None:
    img = Image.new("RGB", (W, H), sc["bg"])
    draw = ImageDraw.Draw(img)
    _draw_bg(draw, sc)

    # Right panel: slightly lighter tint behind circle
    for x in range(645, W):
        t = (x - 645) / (W - 645)
        color = _blend(sc["bg2"], _blend(sc["el"], sc["bg"], 0.85), t * 0.4)
        draw.line([(x, 0), (x, H)], fill=color)

    # Japan circle
    _draw_japan_circle(draw, cx=968, cy=358, r=255, sc=sc)

    # Vertical divider (colored, not just grey)
    for x_off in range(4):
        alpha = _blend(sc["t1"], sc["bg"], 0.6)
        draw.rectangle([648 + x_off, 24, 649 + x_off, H - 24], fill=alpha)

    # Left: text
    _, lines = _get_thumbnail_lines(title)
    y_end = _draw_text_block(draw, lines, sc, 44, 62, [100, 80, 62], 580)
    _draw_branding(draw, sc, 44, y_end)

    draw.rectangle([0, H - 14, W, H], fill=sc["el"])
    img.save(str(output_path), "JPEG", quality=95)
    logger.info(f"Thumbnail [culture/{sc['name']}] saved: {output_path}")


# ---------------------------------------------------------------------------
# Template 4: AI PHOTO — DALL-E 3 background + text overlay
# ---------------------------------------------------------------------------
def _thumbnail_ai_photo(title: str, bg_path: Path, output_path: Path) -> None:
    """Overlay bold text on a DALL-E-generated background photo."""
    img = Image.open(bg_path).convert("RGBA")

    # --- Left-side gradient overlay for text readability ---
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    fade_w = int(W * 0.65)
    for x in range(fade_w):
        t = x / fade_w
        # Strong darkening on the left, fade to transparent
        alpha = int(195 * (1 - t ** 0.55))
        ov_draw.line([(x, 0), (x, H)], fill=(0, 0, 0, alpha))
    # Subtle bottom gradient for branding
    for y in range(H - 80, H):
        t = (y - (H - 80)) / 80
        alpha = int(160 * t)
        ov_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))

    img = Image.alpha_composite(img, overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    badge, lines = _get_thumbnail_lines(title)
    text_x = 48

    # Number badge (if present)
    if badge:
        bx, by, br = 148, 195, 118
        # Semi-transparent backing circle
        circ = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cd = ImageDraw.Draw(circ)
        cd.ellipse([bx - br, by - br, bx + br, by + br], fill=(255, 215, 0, 230))
        cd.ellipse([bx - br + 10, by - br + 10, bx + 5, by + 5],
                   fill=(255, 235, 80, 200))
        img = Image.alpha_composite(img.convert("RGBA"), circ).convert("RGB")
        draw = ImageDraw.Draw(img)
        fn_num = _get_font(180)
        bb = draw.textbbox((0, 0), badge, font=fn_num)
        nw, nh = bb[2] - bb[0], bb[3] - bb[1]
        _outline_text(draw, (bx - nw // 2, by - nh // 2 - 10), badge,
                      fn_num, (20, 20, 20), (0, 0, 0), 2)
        text_x = 295

    # Text lines — classic YouTube colors (yellow / white / orange)
    ai_sc = dict(t1=(255, 215, 0), t2=(255, 255, 255), t3=(255, 110, 40))
    y_end = _draw_text_block(draw, lines, ai_sc, text_x, 62, [110, 88, 68], 620)

    # Separator + "AI JAPAN" branding
    draw.rectangle([text_x, y_end + 14, text_x + 480, y_end + 20], fill=(255, 215, 0))
    fn_sm = _get_font(36)
    _outline_text(draw, (text_x, y_end + 28), "AI JAPAN", fn_sm,
                  (220, 220, 220), (0, 0, 0), 3)

    # Thin red bottom accent bar
    draw.rectangle([0, H - 10, W, H], fill=(196, 0, 38))

    img.save(str(output_path), "JPEG", quality=95)
    logger.info(f"Thumbnail [ai_photo] saved: {output_path}")


def _thumbnail_obscura_ai_photo(title: str, bg_path: Path, output_path: Path) -> None:
    """Overlay Obscura-style text on an AI-generated background photo."""
    img = Image.open(bg_path).convert("RGBA")

    # Dark-grade the background to match viral mystery/true-crime look.
    base_rgb = img.convert("RGB")
    base_rgb = ImageEnhance.Color(base_rgb).enhance(0.55)      # desaturate
    base_rgb = ImageEnhance.Contrast(base_rgb).enhance(1.18)   # stronger contrast
    base_rgb = ImageEnhance.Brightness(base_rgb).enhance(0.66) # darker exposure
    img = base_rgb.convert("RGBA")

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    fade_w = int(W * 0.78)
    for x in range(fade_w):
        t = x / fade_w
        alpha = int(238 * (1 - t ** 0.72))
        ov_draw.line([(x, 0), (x, H)], fill=(10, 0, 0, alpha))
    for y in range(H - 140, H):
        t = (y - (H - 140)) / 140
        alpha = int(210 * t)
        ov_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))

    # Subtle center vignette to avoid bright hotspots.
    for r in range(540, 280, -8):
        t = (r - 280) / 260
        a = int(70 * t)
        ov_draw.ellipse([W // 2 - r, H // 2 - r, W // 2 + r, H // 2 + r], outline=(0, 0, 0, a), width=8)

    img = Image.alpha_composite(img, overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    obscura_sc = dict(t1=(245, 237, 214), t2=(234, 228, 215), t3=(214, 184, 110))
    _, lines = _get_thumbnail_lines(title)
    headline_lines = lines[:2] if lines else ["TRUE CRIME MYSTERY"]
    y_end = _draw_text_block(draw, headline_lines, obscura_sc, 60, 36, [124, 108], 1150)

    fn_sub = _get_font(66)
    _outline_text(draw, (315, y_end + 8), "A TRUE CRIME MYSTERY", fn_sub, obscura_sc["t3"], (0, 0, 0), 5)

    fn_tag = _get_font(62)
    _outline_text(draw, (40, H - 96), "A TRUE STORY OF TRAGEDY", fn_tag, obscura_sc["t2"], (0, 0, 0), 4)

    draw.rectangle([0, H - 12, W, H], fill=(64, 44, 28))

    img.save(str(output_path), "JPEG", quality=95)
    logger.info(f"Thumbnail [obscura/ai_photo] saved: {output_path}")


def _thumbnail_obscura(title: str, output_path: Path) -> None:
    """Create a high-contrast mystery thumbnail for Obscura Files."""
    img = Image.new("RGB", (W, H), (13, 14, 16))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)], fill=_blend((16, 18, 24), (42, 44, 38), t))

    draw.polygon([(740, 0), (W, 0), (W, H), (560, H)], fill=(44, 48, 52))
    draw.polygon([(880, 0), (W, 0), (W, int(H * 0.48))], fill=(66, 70, 74))

    draw.rectangle([0, 500, W, H], fill=(22, 24, 21))
    for x in range(0, W, 32):
        draw.line([(x, 500), (x + 24, H)], fill=(34, 36, 32), width=2)

    for r in range(0, 220, 10):
        alpha_col = _blend((170, 176, 170), (52, 54, 50), r / 220)
        draw.ellipse([630 - r, 430 - r // 2, 1220 + r, 690 + r // 2], outline=alpha_col, width=3)

    obscura_sc = dict(t1=(245, 237, 214), t2=(234, 228, 215), t3=(214, 184, 110))
    _, lines = _get_thumbnail_lines(title)
    headline_lines = lines[:2] if lines else ["TRUE CRIME MYSTERY"]
    y_end = _draw_text_block(draw, headline_lines, obscura_sc, 60, 34, [126, 108], 1140)

    fn_sub = _get_font(66)
    _outline_text(draw, (315, y_end + 6), "A TRUE CRIME MYSTERY", fn_sub, obscura_sc["t3"], (0, 0, 0), 5)

    fn_tag = _get_font(62)
    _outline_text(draw, (40, H - 96), "A TRUE STORY OF TRAGEDY", fn_tag, obscura_sc["t2"], (0, 0, 0), 4)

    draw.rectangle([0, H - 12, W, H], fill=(64, 44, 28))
    img.save(str(output_path), "JPEG", quality=95)
    logger.info(f"Thumbnail [obscura] saved: {output_path}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def create_thumbnail(
    title: str,
    topic: str,
    output_filename: str = "latest_thumbnail.jpg",
) -> Path:
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = THUMBNAIL_DIR / output_filename

    # --- Try AI photo background first ---
    from src.image_generator import generate_bg_image
    bg_path = THUMBNAIL_DIR / f"_bg_{output_filename}"
    bg = generate_bg_image(title, topic, bg_path)
    if bg:
        _thumbnail_ai_photo(title, bg, output_path)
        return output_path

    # --- Fallback: programmatic geometric design ---
    template = _pick_template(title, topic)
    sc = _pick_scheme(title)
    logger.info(f"Thumbnail [{template}/{sc['name']}] for \"{title}\"")

    if template == "rules":
        _thumbnail_rules(title, sc, output_path)
    elif template == "shock":
        _thumbnail_shock(title, sc, output_path)
    else:
        _thumbnail_culture(title, sc, output_path)

    return output_path


def create_obscura_thumbnail(
    title: str,
    topic: str,
    output_filename: str = "latest_obscura_thumbnail.jpg",
) -> Path:
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = THUMBNAIL_DIR / output_filename

    from src.image_generator import generate_bg_image

    bg_path = THUMBNAIL_DIR / f"_obscura_bg_{output_filename}"
    bg_prompt_topic = (
        f"abandoned farmhouse at dusk, true crime mystery atmosphere, "
        f"stormy overcast sky, dead trees framing scene, low fog on ground, vintage realism, "
        f"desaturated teal-gray grade, cinematic documentary lighting, subtle film grain, "
        f"ominous but realistic mood, no people close-up, no cartoon, no text, {topic}"
    ).strip()
    bg = generate_bg_image(title, bg_prompt_topic, bg_path)
    if bg:
        _thumbnail_obscura_ai_photo(title, bg, output_path)
        return output_path

    _thumbnail_obscura(title, output_path)
    return output_path


def upload_thumbnail(video_id: str, thumbnail_path: Path) -> bool:
    from src.youtube_uploader import YouTubeUploader
    uploader = YouTubeUploader()
    uploader.youtube.thumbnails().set(
        videoId=video_id,
        media_body=str(thumbnail_path),
    ).execute()
    logger.info(f"Thumbnail uploaded to video: {video_id}")
    return True
