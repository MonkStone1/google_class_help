"""Build-time tool: generate assets/GoogleClassHelp.ico.

Draws a simple brand icon (green rounded square with a white mortarboard)
with Pillow and saves it as a multi-size Windows .ico. Best-effort: if
Pillow is missing, build.bat simply skips the icon option.

Usage: python tools/make_icon.py
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow not installed - skipping icon generation.")
    sys.exit(0)

ASSET = Path(__file__).resolve().parent.parent / "assets" / "GoogleClassHelp.ico"

SIZE = 256
GREEN = (24, 128, 56, 255)        # Google Classroom green
WHITE = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)


def build() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), TRANSPARENT)
    draw = ImageDraw.Draw(img)

    # Rounded green square
    draw.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=48, fill=GREEN)

    # Mortarboard: a diamond, then the cap base and a tassel below
    cx = SIZE // 2
    top, mid = 56, 128
    half = 78
    draw.polygon(
        [(cx - half, mid), (cx, top), (cx + half, mid), (cx, mid + 34)],
        fill=WHITE,
    )
    # Cap base (a band under the board)
    draw.polygon(
        [(cx - 44, mid + 34), (cx + 44, mid + 34), (cx + 44, mid + 64), (cx - 44, mid + 64)],
        fill=WHITE,
    )
    # Tassel
    draw.line([(cx + 58, mid + 6), (cx + 58, mid + 56)], fill=WHITE, width=10)
    draw.ellipse([cx + 50, mid + 56, cx + 66, mid + 74], fill=WHITE)
    return img


def main() -> None:
    ASSET.parent.mkdir(parents=True, exist_ok=True)
    icon = build()
    icon.save(ASSET, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"OK: icon written to {ASSET}")


if __name__ == "__main__":
    main()
