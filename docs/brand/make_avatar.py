"""XAHOO profile photo (Telegram / app). Usage: python make_avatar.py <output-folder>. Font: Inter (SIL OFL)."""
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import math, random, sys
OUT = sys.argv[1]
W = 2048; C = W // 2
AMBER, AMBER_HI, AMBER_LO = (245, 165, 36), (255, 206, 92), (214, 128, 20)
bg = Image.new("RGB", (W, W)); px = bg.load()
for y in range(W):
    for x in range(W):
        t = min(1.0, math.hypot(x - C, y - C * 0.92) / (W * 0.62)) ** 1.4
        px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip((26, 34, 47), (5, 7, 10)))
img = bg.convert("RGBA")
grid = Image.new("RGBA", (W, W), (0, 0, 0, 0)); g = ImageDraw.Draw(grid)
for i in range(0, W, W // 16):
    g.line([(i, 0), (i, W)], fill=(80, 100, 130, 20), width=3); g.line([(0, i), (W, i)], fill=(80, 100, 130, 20), width=3)
img = Image.alpha_composite(img, grid)
# candlesticks: behind the X only, low opacity, clear of the wordmark
cs = Image.new("RGBA", (W, W), (0, 0, 0, 0)); d = ImageDraw.Draw(cs)
random.seed(7); price = 0.0; x0, step = int(W * 0.17), int(W * 0.066)
base_y, scale = W * 0.42, W * 0.045
for i in range(11):
    o = price; c = o + random.uniform(-1.1, 1.3) + (0.25 if i > 5 else -0.15)
    h = max(o, c) + random.uniform(0.2, 0.7); l = min(o, c) - random.uniform(0.2, 0.7); price = c
    col = (47, 210, 122, 48) if c >= o else (255, 92, 92, 48)
    cx = x0 + i * step; to_y = lambda v: base_y - v * scale
    d.line([(cx, to_y(h)), (cx, to_y(l))], fill=col, width=8)
    d.rectangle([cx - 24, to_y(max(o, c)), cx + 24, to_y(min(o, c)) + 6], fill=col)
img = Image.alpha_composite(img, cs)
ring = Image.new("RGBA", (W, W), (0, 0, 0, 0)); rd = ImageDraw.Draw(ring); R = int(W * 0.445)
rd.arc([C - R, C - R, C + R, C + R], start=-62, end=242, fill=AMBER + (150,), width=14)
img = Image.alpha_composite(img, ring)
cx, cy, s = C, int(W * 0.40), int(W * 0.16)
def x_mask(width):
    m = Image.new("L", (W, W), 0); md = ImageDraw.Draw(m)
    for (a, b) in (((cx - s, cy - s), (cx + s, cy + s)), ((cx + s, cy - s), (cx - s, cy + s))):
        md.line([a, b], fill=255, width=width)
        for p in (a, b): md.ellipse([p[0] - width // 2, p[1] - width // 2, p[0] + width // 2, p[1] + width // 2], fill=255)
    return m
glow = Image.new("RGBA", (W, W), AMBER + (0,))
glow.putalpha(x_mask(170).filter(ImageFilter.GaussianBlur(70)).point(lambda v: int(v * 0.55)))
img = Image.alpha_composite(img, glow)
grad = Image.new("RGBA", (W, W)); gp = grad.load()
for y in range(cy - s - 120, cy + s + 120):
    t = min(1, max(0, (y - (cy - s)) / (2 * s)))
    col = tuple(int(a + (b - a) * t) for a, b in zip(AMBER_HI, AMBER_LO))
    for x in range(cx - s - 120, cx + s + 120): gp[x, y] = col + (255,)
grad.putalpha(x_mask(124)); img = Image.alpha_composite(img, grad)
f1 = ImageFont.truetype("/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf", int(W * 0.105))
f2 = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Bold.otf", int(W * 0.036))
td = ImageDraw.Draw(img)
def spaced(text, font, y, fill, track):
    ws = [td.textlength(ch, font=font) for ch in text]; x = C - (sum(ws) + track * (len(text) - 1)) / 2
    for ch, w in zip(text, ws): td.text((x, y), ch, font=font, fill=fill); x += w + track
spaced("XAHOO", f1, int(W * 0.645), AMBER + (255,), int(W * 0.022))
spaced("GOLD · SILVER", f2, int(W * 0.775), (160, 172, 190, 255), int(W * 0.012))
final = img.convert("RGB")
for size in (1024, 640):
    final.resize((size, size), Image.LANCZOS).save(f"{OUT}/xahoo-avatar-{size}.png", optimize=True)
prev = final.resize((640, 640), Image.LANCZOS).convert("RGBA")
mask = Image.new("L", (640, 640), 0); ImageDraw.Draw(mask).ellipse([0, 0, 639, 639], fill=255)
out = Image.new("RGBA", (640, 640), (255, 255, 255, 255)); out.paste(prev, (0, 0), mask)
out.convert("RGB").save(f"{OUT}/avatar_circle_preview.png")

print("ok")
