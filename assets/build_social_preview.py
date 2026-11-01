"""GitHub social preview for axiom-discovery-kit. 1280x640 PNG, Axiom letterhead (DESIGN.md).

Numbers and terminal lines are copied from eval/RESULTS.md and the call-1 extraction
(synthetic call; terminal text is condensed from extraction.md, the quotes are verbatim).
Run: python3 assets/build_social_preview.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "social-preview.png")
W, H, S = 1280, 640, 2
STONE, INK, NAVY, BRASS, GREY = (242, 238, 230), (18, 19, 22), (21, 32, 58), (140, 115, 80), (98, 98, 96)
CINZEL = os.path.expanduser("~/axiom/Axiom-deploy/assets/fonts/Cinzel.ttf")
BASK = "/System/Library/Fonts/Supplemental/Baskerville.ttc"
MONO = "/System/Library/Fonts/SFNSMono.ttf"


def cinzel(px, wt):
    f = ImageFont.truetype(CINZEL, px * S)
    f.set_variation_by_axes([wt])
    return f


def bask(px, style):
    for i in range(8):
        try:
            f = ImageFont.truetype(BASK, px * S, index=i)
        except OSError:
            break
        if f.getname()[1] == style:
            return f
    raise SystemExit(f"no Baskerville {style}")


img = Image.new("RGB", (W * S, H * S), STONE)
d = ImageDraw.Draw(img)
M = 64 * S
R = W * S - M


def tracked(x, y, text, f, fill, track):
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + track
    return x


def tracked_len(text, f, track):
    return sum(d.textlength(c, font=f) + track for c in text) - track


def wrap(text, f, width):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if d.textlength(test, font=f) <= width:
            cur = test
        else:
            lines.append(cur); cur = w_
    lines.append(cur)
    return lines


# letterhead
tracked(M, 46 * S, "AXIOM", cinzel(36, 800), INK, 0.28 * 36 * S)
f_chrome = cinzel(13, 600)
t = "OPEN SOURCE  ·  MIT LICENSE"
tracked(R - tracked_len(t, f_chrome, 2.8 * S), 62 * S, t, f_chrome, GREY, 2.8 * S)
y = 104 * S
d.rectangle([M, y, R, y + 3 * S], fill=INK)
d.rectangle([M, y + 8 * S, R, y + 9 * S], fill=INK)

# left column
LX, LW = M, 540 * S
y = 146 * S
d.text((LX, y), "axiom-discovery-kit", font=bask(44, "SemiBold"), fill=INK)
y += 64 * S
for line in wrap("Discovery calls recorded, transcribed and summarized on our own Mac, "
                 "then turned into a process map with a candidate quote to check for each item.", bask(23, "Regular"), LW):
    d.text((LX, y), line, font=bask(23, "Regular"), fill=INK); y += 33 * S
y += 16 * S
d.rectangle([LX, y, LX + 56 * S, y + 2 * S], fill=BRASS)
y += 22 * S
f_lab, f_val = cinzel(12, 700), bask(21, "Regular")
for lab, val in [("WORD ERROR", "1.0–4.5% clean or noisy · 13.6% cross-talk"),
                 ("CHECKLIST", "87–100% keyword hits, clean or noisy"),
                 ("LIMIT", "no speaker names; owners checked by hand")]:
    tracked(LX, y + 7 * S, lab, f_lab, BRASS, 2.4 * S)
    d.text((LX + 138 * S, y), val, font=f_val, fill=INK)
    y += 36 * S
y += 8 * S
d.text((LX, y), "Eval: 3 synthetic calls, local models only.", font=bask(18, "Italic"), fill=GREY)
left_bottom = y // S + 26

# terminal panel (real reader output on synthetic call 1)
PX0, PX1 = 640 * S, R
top = 150 * S
fm, fmt = ImageFont.truetype(MONO, 14 * S), ImageFont.truetype(MONO, 12 * S)
raw = [
    ("$ python3 meetily_reader.py --meeting <id>", (120, 124, 132)),
    ("Items: 34. Candidate quote: 31. Flagged: 3.", (226, 178, 92)),
    ("", None),
    ("Pain: Answering service guesses on urgency,", (232, 232, 228)),
    ("leading to missed real emergencies ...", (232, 232, 228)),
    ("> candidate quote, verify [02:09] \"Last", (150, 190, 160)),
    ("month they woke him up twice for a thermostat", (150, 190, 160)),
    ("battery, and they missed a real one where a", (150, 190, 160)),
    ("family had no heat with a newborn.\"", (150, 190, 160)),
    ("", None),
    ("Candidate agent task: Dispatcher reads", (232, 232, 228)),
    ("messages and calls customers back", (232, 232, 228)),
    ("> candidate quote, verify [01:04] \"...calls", (150, 190, 160)),
    ("each person back, and enters the job in", (150, 190, 160)),
    ("Service Titan by hand.\"", (150, 190, 160)),
]
bar, lh = 30 * S, 21 * S
bot = top + bar + 16 * S + lh * len(raw) + 14 * S
d.rounded_rectangle([PX0, top, PX1, bot], radius=12 * S, fill=(18, 19, 22), outline=(60, 62, 66), width=2 * S)
for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
    cx = PX0 + (20 + i * 18) * S; cy = top + bar // 2
    d.ellipse([cx - 5 * S, cy - 5 * S, cx + 5 * S, cy + 5 * S], fill=c)
lab = "extraction — synthetic call (fake data)"
d.text(((PX0 + PX1) / 2 - d.textlength(lab, font=fmt) / 2, top + 8 * S), lab, font=fmt, fill=(120, 124, 132))
d.line([PX0, top + bar, PX1, top + bar], fill=(60, 62, 66), width=1 * S)
ty = top + bar + 14 * S
maxw = 0
for s_, col in raw:
    if col:
        d.text((PX0 + 20 * S, ty), s_, font=fm, fill=col)
        maxw = max(maxw, d.textlength(s_, font=fm))
    ty += lh
assert PX0 + 20 * S + maxw < PX1 - 10 * S, "terminal text overflows panel"
panel_bottom = bot // S

# footer
fy = (H - 64) * S
d.rectangle([M, fy, R, fy + 1 * S], fill=BRASS)
d.text((M, fy + 16 * S), "Built on Meetily (MIT) by Zackriya Solutions. Not affiliated.", font=bask(17, "Italic"), fill=NAVY)
ft = "OBSERVED, NOT INFERRED"
tracked(R - tracked_len(ft, f_chrome, 2.8 * S), fy + 20 * S, ft, f_chrome, GREY, 2.8 * S)

print("left bottom", left_bottom, "panel bottom", panel_bottom, "footer", fy // S)
assert max(left_bottom, panel_bottom) < fy // S - 8, "overflow into footer"
out = img.resize((W, H), Image.LANCZOS)
out.save(OUT, optimize=True)
print(OUT, os.path.getsize(OUT), out.size)
