"""The site's icons for browsers and search results, made from the app icon (site/images/icon.png).

23 Nov: Google showed Friday's icon small and blurry inside a white ring, where Canva's filled its circle. The app icon
is a macOS one: a rounded square inside a transparent margin, which Google fills with white and shrinks into its
circle. These are cut to the icon's edges and its navy fills the whole square, so the ring and the F fill the circle
Google crops to; at the sizes Google asks for (multiples of 48), with a favicon.ico for those that look for one.

25 Nov, the user ("friday scheduler still looks bad on google"): at the size Google shows it, the ring around the F
read as a circle inside Google's circle and the F was small. The user's choice: for the small icons (the favicon and
48/96/192, what browsers and search use) the app's own F alone, filling the navy, no ring; the home-screen icon
(180) and 512 stay the app icon.

    uv run --with pillow --with numpy python scripts/make_favicons.py
"""

from pathlib import Path

import numpy as np
from PIL import Image

IMAGES = Path(__file__).resolve().parent.parent / "site" / "images"
SMALL = (48, 96, 192)  # the bold F
F_HEIGHT = 0.62  # of the square: inside Google's circle crop, corners and all


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


def bold_f(icon: Image.Image) -> Image.Image:
    """The app icon's F alone (the white inside the ring, near the middle), on the icon's navy, as tall as F_HEIGHT."""
    a = np.asarray(icon).astype(int)
    h, w = a.shape[:2]
    light = a[..., :3].min(axis=2)
    yy, xx = np.mgrid[0:h, 0:w]
    near = (light > 200) & (np.hypot(yy - h / 2, xx - w / 2) < 0.28 * w)  # the ring lies further out
    ys, xs = np.nonzero(near)
    glyph = icon.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    navy = tuple(int(c) for c in a[h // 2, int(w * 0.08)][:3])
    out = Image.new("RGBA", (w, h), (*navy, 255))
    gh = round(h * F_HEIGHT)
    glyph = glyph.resize((round(glyph.width * gh / glyph.height), gh), Image.Resampling.LANCZOS)
    g = np.asarray(glyph).astype(float)[..., :3].min(axis=2)
    alpha = np.clip((g - max(navy)) / (255 - max(navy)), 0, 1)  # its own soft edge, not a hard cut
    mask = Image.fromarray((alpha * 255).astype(np.uint8))
    out.paste(Image.new("RGBA", glyph.size, (255, 255, 255, 255)), ((w - glyph.width) // 2, (h - gh) // 2), mask)
    return out


def main() -> None:
    made = full_bleed(Image.open(IMAGES / "icon.png"))
    small = bold_f(made)
    for size in SMALL:
        small.resize((size, size), Image.Resampling.LANCZOS).save(IMAGES / f"icon-{size}.png", optimize=True)
    made.resize((512, 512), Image.Resampling.LANCZOS).save(IMAGES / "icon-512.png", optimize=True)
    made.resize((180, 180), Image.Resampling.LANCZOS).save(IMAGES / "icon-180.png", optimize=True)
    small.save(IMAGES.parent / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"made icon-{'/'.join(map(str, SMALL))}.png and favicon.ico (the F), icon-180/512.png (the app icon)")


if __name__ == "__main__":
    main()
