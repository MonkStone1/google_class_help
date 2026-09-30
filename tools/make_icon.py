"""Build-time tool: generate the application icon and the site favicons.

Draws a simple brand icon (green rounded square with a white mortarboard)
with Pillow and saves it as:

* ``assets/GoogleClassHelp.ico`` - multi-size Windows icon for the Nuitka
  build (``build.bat`` passes it to ``--windows-icon-from-ico``);
* ``frontend/public/favicon.ico`` + PNG/SVG variants - the browser tab icon.
  These live in ``frontend/public`` so Vite copies them into ``frontend/dist``
  and they end up in the Docker image; the icon is therefore versioned with
  the sources instead of being generated only at release time.

Best-effort: if Pillow is missing, the script exits 0 and the caller carries
on - ``build.bat`` then skips the Nuitka icon option and the site simply falls
back to no favicon.

Usage: python tools/make_icon.py
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow not installed - skipping icon generation.")
    sys.exit(0)

ROOT = Path(__file__).resolve().parent.parent
ASSET = ROOT / "assets" / "GoogleClassHelp.ico"
PUBLIC_DIR = ROOT / "frontend" / "public"

SIZE = 256
GREEN = (24, 128, 56, 255)        # Google Classroom green
WHITE = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)

# Sizes embedded in the .ico. Windows picks the best fit for the shell/taskbar;
# 16 keeps the mortarboard legible, 256 covers high-DPI Explorer views.
ICO_SIZES = [
    (16, 16),
    (24, 24),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
]


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


def _svg() -> str:
    """The same mark as inline SVG, for the modern `<link rel=icon>` path.

    Vector keeps the tab icon crisp on HiDPI displays and needs no extra file
    sizes; it is written by hand rather than exported so the tool still has a
    single source of truth for the geometry (the numbers below mirror build()).
    """
    cx = SIZE // 2
    top, mid = 56, 128
    half = 78
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img"'
        ' aria-label="Google Class Help">'
        f'<rect x="8" y="8" width="240" height="240" rx="48" fill="#188038"/>'
        f'<polygon points="{cx - half},{mid} {cx},{top} {cx + half},{mid} {cx},{mid + 34}"'
        ' fill="#fff"/>'
        f'<polygon points="{cx - 44},{mid + 34} {cx + 44},{mid + 34} {cx + 44},{mid + 64}'
        f' {cx - 44},{mid + 64}" fill="#fff"/>'
        f'<line x1="{cx + 58}" y1="{mid + 6}" x2="{cx + 58}" y2="{mid + 56}"'
        ' stroke="#fff" stroke-width="10"/>'
        f'<circle cx="{cx + 58}" cy="{mid + 65}" r="8" fill="#fff"/>'
        "</svg>\n"
    )


def write_web_icons(icon: Image.Image) -> None:
    """Write the favicon set served by the SPA and the legal pages."""
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    (PUBLIC_DIR / "favicon.svg").write_text(_svg(), encoding="utf-8")
    icon.save(PUBLIC_DIR / "favicon.ico", sizes=ICO_SIZES)
    # PNG fallback for browsers that ignore the SVG, plus the iOS home-screen
    # icon (180x180 is what iOS expects for apple-touch-icon).
    # ``Image.Resampling.LANCZOS`` rather than the old ``Image.LANCZOS`` alias:
    # Pillow 10+ keeps the flat name only as a deprecated runtime leftover and
    # no longer declares it in the type stubs, so the checker rejects it.
    icon.resize((32, 32), Image.Resampling.LANCZOS).save(
        PUBLIC_DIR / "favicon-32x32.png"
    )
    icon.resize((180, 180), Image.Resampling.LANCZOS).save(
        PUBLIC_DIR / "apple-touch-icon.png"
    )


def main() -> None:
    ASSET.parent.mkdir(parents=True, exist_ok=True)
    icon = build()
    icon.save(ASSET, sizes=ICO_SIZES)
    print(f"OK: icon written to {ASSET}")
    write_web_icons(icon)
    print(f"OK: favicons written to {PUBLIC_DIR}")


if __name__ == "__main__":
    main()
