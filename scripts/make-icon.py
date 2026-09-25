#!/usr/bin/env python3
"""Compose AppIcon.icns from a transparent 1024px Earth render.

Usage: make-icon.py <earth-1024.png> <out.icns>

Draws the render on a macOS-style rounded square with a deep-space gradient,
then builds the iconset with sips/iconutil.
"""
import os, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter

src, out = sys.argv[1], sys.argv[2]
S = 1024
earth = Image.open(src).convert("RGBA")

# Trim transparent margins so the globe fills the tile consistently.
bbox = earth.getbbox()
if bbox:
    earth = earth.crop(bbox)
target = int(S * 0.56)
scale = target / max(earth.size)
earth = earth.resize((max(1, int(earth.width * scale)), max(1, int(earth.height * scale))), Image.LANCZOS)

# macOS icon grid: the tile occupies ~82% of the canvas.
tile = int(S * 0.82)
radius = int(tile * 0.225)
off = (S - tile) // 2

# Vertical space gradient.
grad = Image.new("RGBA", (tile, tile))
px = grad.load()
top, bot = (12, 20, 48), (2, 4, 14)
for y in range(tile):
    t = y / (tile - 1)
    c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    for x in range(tile):
        px[x, y] = (*c, 255)

# Faint star field.
import random
random.seed(7)
sd = ImageDraw.Draw(grad)
for _ in range(140):
    x, y = random.randrange(tile), random.randrange(tile)
    r = random.choice([1, 1, 1, 2])
    a = random.randint(90, 220)
    sd.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, a))

mask = Image.new("L", (tile, tile), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, tile - 1, tile - 1), radius=radius, fill=255)

canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
# Soft drop shadow.
shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
sm = Image.new("L", (S, S), 0)
ImageDraw.Draw(sm).rounded_rectangle((off, off + 18, off + tile - 1, off + tile - 1 + 18), radius=radius, fill=110)
shadow.putalpha(sm.filter(ImageFilter.GaussianBlur(28)))
canvas = Image.alpha_composite(canvas, shadow)
canvas.paste(grad, (off, off), mask)

ex = (S - earth.width) // 2
ey = (S - earth.height) // 2
canvas.alpha_composite(earth, (ex, ey))

with tempfile.TemporaryDirectory() as td:
    iconset = os.path.join(td, "AppIcon.iconset")
    os.mkdir(iconset)
    base = os.path.join(td, "base.png")
    canvas.save(base)
    for pt in (16, 32, 128, 256, 512):
        for scale_ in (1, 2):
            pxs = pt * scale_
            name = f"icon_{pt}x{pt}{'@2x' if scale_ == 2 else ''}.png"
            canvas.resize((pxs, pxs), Image.LANCZOS).save(os.path.join(iconset, name))
    subprocess.check_call(["iconutil", "-c", "icns", iconset, "-o", out])
print(f"wrote {out}")
