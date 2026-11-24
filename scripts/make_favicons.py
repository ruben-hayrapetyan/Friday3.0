"""The site's icons for browsers and search results, made from the app icon (site/images/icon.png).

23 Nov: Google showed Friday's icon small and blurry inside a white ring, where Canva's filled its circle. The app icon
is a macOS one: a rounded square inside a transparent margin, which Google fills with white and shrinks into its
circle. These are cut to the icon's edges and its navy fills the whole square, so the ring and the F fill the circle
Google crops to; at the sizes Google asks for (multiples of 48), with a favicon.ico for those that look for one.

    uv run --with pillow python scripts/make_favicons.py
"""

from pathlib import Path

from PIL import Image

IMAGES = Path(__file__).resolve().parent.parent / "site" / "images"
SIZES = (48, 96, 192, 512)


def full_bleed(icon: Image.Image) -> Image.Image:
    """The icon cut to its rounded square, the corners filled with its own background color."""
    icon = icon.convert("RGBA")
    box = icon.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    square = icon.crop(box)
    w, h = square.size
    background = square.getpixel((w // 2, max(1, h // 16)))  # inside the square, above the ring
    out = Image.new("RGBA", (w, h), (*background[:3], 255))
    out.alpha_composite(square)
    return out


def main() -> None:
    made = full_bleed(Image.open(IMAGES / "icon.png"))
    for size in SIZES:
        made.resize((size, size), Image.Resampling.LANCZOS).save(IMAGES / f"icon-{size}.png", optimize=True)
    made.resize((180, 180), Image.Resampling.LANCZOS).save(IMAGES / "icon-180.png", optimize=True)
    made.save(IMAGES.parent / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"made icon-{'/'.join(map(str, SIZES))}.png, icon-180.png and favicon.ico in {IMAGES.parent}")


if __name__ == "__main__":
    main()
