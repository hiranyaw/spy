from PIL import Image, ImageDraw
S = 16  # draw at 1024px (64 * 16), then shrink for smooth edges
im = Image.new("RGBA", (64 * S, 64 * S), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rounded_rectangle([0, 0, 64 * S - 1, 64 * S - 1], radius=14 * S, fill="#0b0f19")
d.rounded_rectangle([2 * S, 2 * S, 62 * S, 62 * S], radius=12 * S, outline="#26304a", width=2 * S)

def bez(p0, p1, p2, p3, n=60):
    return [tuple((1-t)**3*a + 3*(1-t)**2*t*b + 3*(1-t)*t**2*c + t**3*e for a, b, c, e in zip(p0, p1, p2, p3))
            for t in (i / n for i in range(n + 1))]

def stroke(segs, color, w=4.5):
    pts = []
    for s in segs:
        pts += bez(*s)
    pts = [(x * S, y * S) for x, y in pts]
    r = w * S / 2
    dense = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dense += [(x0 + (x1 - x0) * k / 8, y0 + (y1 - y0) * k / 8) for k in range(8)]
    for x, y in dense + [pts[-1]]:  # round brush: smooth edges, no joint spikes
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)

stroke([((10, 44), (22, 42), (28, 34), (32, 30)), ((32, 30), (36, 26), (44, 18), (54, 16))], "#4fc3f7")  # 9 EMA
stroke([((10, 22), (22, 26), (28, 30), (32, 30)), ((32, 30), (36, 30), (46, 38), (54, 38))], "#ffa726")  # 21 EMA
d.ellipse([24 * S, 22 * S, 40 * S, 38 * S], fill="#0b0f19")
d.ellipse([26 * S, 24 * S, 38 * S, 36 * S], fill="#00e676")

big = im.resize((256, 256), Image.LANCZOS)
big.save(r"C:\Users\Hiranya\spy\hsm_icon.png")
big.save(r"C:\Users\Hiranya\spy\hsm_icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ok")
