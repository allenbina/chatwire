"""Generate PWA icon PNGs from the chatwire favicon spec.

Favicon design (from web/static/favicon.svg):
  - Rounded-rect background: #bd93f9 (Dracula purple)
  - Lowercase "c", bold, dark: #282a36
  - Corner radius = 7/32 of total size (matching SVG rx="7" on 32px viewBox)
  - Font: Lato-Bold (closest available to Inter/system-ui on this host)

Also generates a maskable variant (icon-512-maskable.png):
  - Full-bleed solid background (no rounded corners) so Android adaptive icon
    masks (circle, squircle, etc.) can safely crop without showing transparent
    edges.
  - Glyph is scaled to ~55 % of canvas height, centred within the inner 60 %
    safe zone (Android spec: radius = 40 % of icon size).

Run: python3 scripts/gen_pwa_icons.py
"""

import os
from PIL import Image, ImageDraw, ImageFont

BG_COLOR   = (0xBD, 0x93, 0xF9, 0xFF)  # #bd93f9
TEXT_COLOR = (0x28, 0x2A, 0x36, 0xFF)  # #282a36
FONT_PATH  = "/usr/share/fonts/truetype/lato/Lato-Bold.ttf"
OUT_DIR    = os.path.join(os.path.dirname(__file__), "../web/frontend/public/icons")

SIZES = [192, 512]


def rounded_rect_mask(size: int, radius: int) -> Image.Image:
    """Return an 'L' image with a white rounded rectangle mask.

    Compatible with Pillow < 8.2 (which lacks rounded_rectangle).
    Technique: fill two overlapping rectangles + four corner ellipses.
    """
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    s = size - 1
    r = radius
    # Horizontal and vertical bands
    draw.rectangle([(r, 0), (s - r, s)], fill=255)
    draw.rectangle([(0, r), (s, s - r)], fill=255)
    # Four corner quarter-circles
    draw.ellipse([(0,       0),       (2 * r,     2 * r)],     fill=255)
    draw.ellipse([(s - 2*r, 0),       (s,         2 * r)],     fill=255)
    draw.ellipse([(0,       s - 2*r), (2 * r,     s)],         fill=255)
    draw.ellipse([(s - 2*r, s - 2*r), (s,         s)],         fill=255)
    return mask


def _draw_glyph(img: Image.Image, font_scale: float) -> None:
    """Draw the centred "c" glyph onto img in-place."""
    size = img.size[0]
    draw = ImageDraw.Draw(img)
    font_size = round(font_scale * size)
    font = ImageFont.truetype(FONT_PATH, font_size)

    try:
        # Pillow ≥ 8.2
        bbox = draw.textbbox((0, 0), "c", font=font)
        glyph_w = bbox[2] - bbox[0]
        glyph_h = bbox[3] - bbox[1]
        x = (size - glyph_w) / 2 - bbox[0]
        y = (size - glyph_h) / 2 - bbox[1]
    except AttributeError:
        # Pillow < 8.2 fallback
        glyph_w, glyph_h = draw.textsize("c", font=font)
        x = (size - glyph_w) / 2
        y = (size - glyph_h) / 2 + round(0.08 * size)

    draw.text((x, y), "c", font=font, fill=TEXT_COLOR)


def generate_icon(size: int) -> Image.Image:
    """Regular icon: rounded-rect background, glyph at ~68.75 % canvas height."""
    radius = round(7 / 32 * size)

    # Background layer (solid colour, will be composited through rounded mask)
    bg = Image.new("RGBA", (size, size), BG_COLOR)

    # Apply rounded corners via mask
    mask = rounded_rect_mask(size, radius)
    bg.putalpha(mask)

    # Draw text on a separate overlay so we can composite cleanly
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # Scale font so the "c" glyph fills ~68 % of the canvas height (matching
    # the SVG font-size=22 on a 32px canvas: 22/32 ≈ 0.6875).
    _draw_glyph(overlay, font_scale=0.6875)

    return Image.alpha_composite(bg, overlay)


def generate_maskable_icon(size: int) -> Image.Image:
    """Maskable icon: full-bleed background, glyph within Android safe zone.

    Android adaptive icons apply a circular or squircle mask at runtime.
    The safe zone is a circle of radius = 40 % of the icon side; content
    outside it may be cropped.  We use a full opaque square background
    (no transparent corners) and scale the glyph to ~55 % of canvas height
    so it sits comfortably within the inner 60 % safe-zone circle.
    """
    img = Image.new("RGBA", (size, size), BG_COLOR)
    _draw_glyph(img, font_scale=0.55)
    return img


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # Regular icons
    for size in SIZES:
        icon = generate_icon(size)
        out_path = os.path.join(OUT_DIR, f"icon-{size}.png")
        icon.save(out_path, "PNG", optimize=True)
        print(f"  wrote {out_path}  ({size}×{size})")

    # Maskable variant (512 only — Android uses the largest available)
    maskable = generate_maskable_icon(512)
    out_path = os.path.join(OUT_DIR, "icon-512-maskable.png")
    maskable.save(out_path, "PNG", optimize=True)
    print(f"  wrote {out_path}  (512×512, maskable)")


if __name__ == "__main__":
    main()
