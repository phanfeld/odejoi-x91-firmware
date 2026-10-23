"""The screensaver clock.

The firmware draws the clock by code: time and date at the top, one full-screen background picture (COMMON.STY 171)
and a timer that redraws when the minute changes. The display driver's keyed draw (DRV_UI.DRV function 38) restores
the background under a digit and copies only the digit picture's pixels whose value is above a key.

  - Background: a night meadow; below the clock a pink jelly blob hops in the grass, 12 frames in the first 12
    pictures of the unused "demo" screensaver (221 to 232), declared 56 x 80. The start of the shared clock routine
    is rewritten (patches/clock_sprite.S) to draw the next frame on every timer tick, and the timer runs every 200 ms
    instead of 500 ms, in the seven programs one can be in when the screensaver starts.
  - The key becomes 0 (every pixel that is not black is drawn) in every program that has the routine, so any accent
    shows; the digits are drawn solid all the same (time 158 to 167, colon 170 in the accent, date 147 to 157 and
    AM/PM 168, 169 in the second text colour).
"""
import hashlib
import struct

from . import base
from .base import T, ap_dis, fail, rgb, svg, xd
from .typeface import HAND

# ------------------------------------------------------------------ the animation (pixel art, 2 x 2 screen pixels each)

ART_W, ART_H = 64, 80                     # the whole screen in art pixels
GROUND = 73                               # last row the blob stands on
RECT = (18, 36, 28, 40)                   # the animated part in art pixels: x, y, w, h  -> screen 36, 72, 56 x 80
FRAMES = [                                # height above ground, width factor, height factor, eyes
    (0, 1.00, 1.00, "open"), (0, 1.00, 1.00, "open"), (0, 1.00, 1.00, "shut"), (0, 1.14, 0.84, "open"),
    (3, 0.90, 1.14, "open"), (9, 0.94, 1.08, "open"), (12, 1.00, 1.00, "open"), (9, 0.96, 1.05, "open"),
    (3, 0.92, 1.12, "open"), (0, 1.18, 0.78, "shut"), (1, 0.95, 1.06, "open"), (0, 1.06, 0.94, "open"),
]
C = dict(sky=(0, 0, 0), g1=(13, 62, 30), g2=(26, 110, 50), g3=(52, 170, 82), g4=(126, 224, 138), shadow=(8, 40, 20),
         body=(255, 150, 180), light=(255, 198, 214), white=(255, 255, 255), shade=(232, 106, 146),
         line=(138, 47, 82), eye=(52, 14, 30))
FIRST_FRAME, BACKGROUND = 221, 171

# ------------------------------------------------------------------ the clock routine

PROGRAMS = ["MAINMENU.AP", "MUSIC.AP", "BROWSER.AP", "BT.AP", "EBOOK.AP", "SETTING.AP", "TOOLS.AP"]
CLOCK_BANK, TIMER_BANK = 0x18ce1a00, 0x18cc1a00
LO, HI = 0x034, 0x0c6
STOCK_REGION = "1b641267ec1c5875"
TIMER_SITES = (0x066, 0x34a)                                   # mov.w r1, #500
TIMER_OLD, TIMER_NEW = bytes.fromhex("4ff4fa71"), bytes.fromhex("4ff0c801")   # -> mov.w r1, #200
OLD_KEY, NEW_KEY = 0xb5b6, 0
KEY_OFFSETS = (0x8a, 0xa6)                       # in the stock routine, and in clock_sprite.S's


def meadow():
    """Background without the blob: black sky, a band of grass with a few flowers in the accent colour."""
    px = [[C["sky"]] * ART_W for _ in range(ART_H)]
    accent = rgb(T["accent"])
    for x in range(ART_W):
        k = (x * 7 + (x * x) % 5 + (x // 3) % 4) % 9
        blade = (2, 1, 3, 1, 2, 0, 1, 2, 1)[k]
        for y in range(GROUND + 1, ART_H):
            px[y][x] = C["g1"] if (x + y) % 5 else C["g2"]
        px[GROUND + 1][x] = C["g2"]
        for i in range(blade):
            px[GROUND - i][x] = C["g4"] if i == blade - 1 and blade > 1 else C["g3"]
    for x in (5, 12, 52, 59):
        px[GROUND - 4][x] = accent
        px[GROUND - 3][x] = C["g3"]
        px[GROUND - 2][x] = C["g3"]
    for x, y in ((9, 33), (55, 40), (50, 62), (14, 58)):          # a few faint stars
        px[y][x] = rgb(T["line"])
    return px


def draw_blob(px, height, wide, tall, eyes):
    cx, rx, ry = 32.0, 10.0 * wide, 8.0 * tall
    bottom = GROUND - height
    cy = bottom + 1 - ry
    inside = set()
    for y in range(int(cy - ry) - 1, bottom + 1):
        for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
            dx, dy = (x + 0.5 - cx) / rx, (y + 0.5 - cy) / ry
            if (dy <= 0 and dx * dx + dy * dy <= 1) or (dy > 0 and abs(dx) ** 2.8 + abs(dy) ** 2.8 <= 1):
                inside.add((x, y))
    top = min(y for x, y in inside)
    inside |= {(31, top - 1), (32, top - 1), (31, top - 2)}        # the little tip on top
    half = int(rx * (1 - height / 18.0))
    for x in range(32 - half, 32 + half):                          # shadow on the grass
        px[GROUND + 1][x] = C["shadow"]
    for x, y in inside:
        dx, dy = (x + 0.5 - cx) / rx, (y + 0.5 - cy) / ry
        edge = any((x + i, y + j) not in inside for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if edge:
            c = C["line"]
        elif (dx + 0.42) ** 2 + (dy + 0.5) ** 2 < 0.07:
            c = C["light"]
        elif dy > 0.5 or dx > 0.62:
            c = C["shade"]
        else:
            c = C["body"]
        px[y][x] = c
    gy = int(round(cy - 0.5 * ry))
    px[gy][26] = C["white"]
    px[gy][27] = C["white"]
    ey = int(round(cy)) - 1
    for ex in (27, 35):
        if eyes == "open":
            for x, y in ((ex, ey - 1), (ex + 1, ey - 1), (ex, ey), (ex + 1, ey)):
                px[y][x] = C["eye"]
            px[ey - 1][ex] = C["white"]
        else:
            px[ey][ex], px[ey][ex + 1] = C["eye"], C["eye"]
    for x, y in ((30, ey + 2), (31, ey + 3), (32, ey + 3), (33, ey + 2)):
        px[y][x] = C["line"]


def to_565(px, x0, y0, w, h):
    """Art pixels to screen pixels (each doubled), as picture data."""
    out = []
    for y in range(y0, y0 + h):
        row = []
        for x in range(x0, x0 + w):
            r, g, b = px[y][x]
            v = (r >> 3) << 11 | (g >> 2) << 5 | b >> 3
            row += [v, v]
        out += row + row
    return struct.pack("<%dH" % len(out), *out)


def animation():
    frames = []
    for height, wide, tall, eyes in FRAMES:
        px = meadow()
        draw_blob(px, height, wide, tall, eyes)
        frames.append(px)
    return frames


# ------------------------------------------------------------------ digits

def white_svg(w, h, parts):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
            '<rect width="%d" height="%d" fill="#000000"/>%s</svg>' % (w, h, w, h, w, h, "".join(parts)))


def white_text(x, y, s, size, weight):
    return base.text(x, y, s, size, weight, "#ffffff")


def coverage(svg_text, w, h, work, name):
    """Render white-on-black artwork and return how much of each pixel is covered, 0 to 255."""
    data = base.render_565(svg_text, w, h, work, name)
    return [((data[i] | data[i + 1] << 8) >> 5 & 63) * 255 // 63 for i in range(0, len(data), 2)]


def solid(cov, color, soft=None, full=0.70, part=0.36):
    """Covered pixels in the colour, half-covered ones in the soft grey (if given), the rest black."""
    out = []
    for c in cov:
        if c >= full * 255:
            out.append(base.c565(color))
        elif c >= part * 255:
            out.append(base.c565(soft or color))
        else:
            out.append(0)
    return struct.pack("<%dH" % len(out), *out)


SOFT = (198, 200, 204)                           # the time digits' half-covered pixels


def date_digit(ch, color):
    """Small digits as plain pixel shapes, the same ones as in the text font; "-" is the dash."""
    px = [0] * (9 * 11)
    if ch == "-":
        for x in range(2, 7):
            px[6 * 9 + x] = base.c565(color)
    else:
        _, _, pattern = HAND[ch]
        for j, line in enumerate(pattern):
            for i, c in enumerate(line):
                if c == "#":
                    px[(j + 2) * 9 + i + 2] = base.c565(color)
    return struct.pack("<%dH" % len(px), *px)


def large_digit(ch):
    return svg(18, 28, [base.text(9, 25, ch, 29, 300, T["text"])])


def large_colon():
    return svg(8, 23, ['<circle cx="%g" cy="%g" r="%g" fill="%s"/>' % (4, y, 2, T["accent"]) for y in (7, 17)])


def clock_background():
    return svg(128, 160, [xd.rect(54, 114, 20, 2, 1, T["line"]), xd.rect(54, 114, 9, 2, 1, T["accent"])])


def pictures(b, work):
    com = b.get("COMMON.STY")
    put = base.Pictures(com, work)
    frames = animation()
    x0, y0, w, h = RECT
    for k, px in enumerate(frames):
        base.resize_picture(com, FIRST_FRAME + k, w * 2, h * 2)
        put.raw(FIRST_FRAME + k, to_565(px, x0, y0, w, h), w * 2, h * 2)
    put.raw(BACKGROUND, to_565(frames[0], 0, 0, ART_W, ART_H), 128, 160)
    put.svg(187, clock_background(), 128, 160, "clock-background")
    for k in range(10):
        put.svg(366 + k, large_digit(str(k)), 18, 28, "clock-%d" % k)
        cov = coverage(white_svg(13, 20, [white_text(6.5, 17, str(k), 20, 500)]), 13, 20, work, "time-%d" % k)
        put.raw(158 + k, solid(cov, rgb(T["text"]), SOFT), 13, 20)
    put.svg(377, large_colon(), 8, 23, "clock-colon")
    cov = coverage(white_svg(13, 20, [xd.rect(5, 6, 3, 3, 0.4, "#ffffff"), xd.rect(5, 13, 3, 3, 0.4, "#ffffff")]),
                   13, 20, work, "time-colon")
    put.raw(170, solid(cov, rgb(T["accent"])), 13, 20)
    dim = rgb(T["text2"])
    for k in range(10):
        put.raw(147 + k, date_digit(str(k), dim), 9, 11)
    put.raw(157, date_digit("-", dim), 9, 11)
    for index, word in ((168, "AM"), (169, "PM")):
        cov = coverage(white_svg(28, 20, [white_text(14, 17, word, 11.5, 700)]), 28, 20, work, "clock-%s" % word.lower())
        put.raw(index, solid(cov, dim, full=0.5, part=0.5), 28, 20)
    b.put("COMMON.STY", com)
    return len(frames)


def movw(reg, value):
    return struct.pack("<HH", 0xf240 | (value >> 11 & 1) << 10 | value >> 12, (value >> 8 & 7) << 12 | reg << 8 | value & 0xff)


def clock_routine(b, work):
    """clock_sprite.S over the start of the shared clock routine, and the 200 ms timer, in PROGRAMS."""
    built = base.assemble("clock_sprite", work)[LO:HI]
    done = []
    for name in PROGRAMS:
        ap = b.get(name)
        segs, _ = ap_dis.segments(ap)
        at, tat = ap_dis.find(segs, CLOCK_BANK), ap_dis.find(segs, TIMER_BANK)
        if at is None or tat is None:
            fail("%s: the screensaver code is not where expected" % name)
        bank = bytes(ap[at:at + 0x458])
        if hashlib.sha256(bank[LO:HI]).hexdigest()[:16] != STOCK_REGION:
            fail("%s: the clock routine is not the expected one" % name)
        last_minute = struct.unpack_from("<I", bank, 0x3ec)[0]
        demo_index = struct.unpack_from("<I", ap, tat + 0x194)[0]
        if demo_index != last_minute - 4 or bank[0x14a:0x14c] != bytes.fromhex("47e1"):
            fail("%s: the variables the clock patch relies on are laid out differently" % name)
        result = base.check("check_clock_patch.py", bank, bank[:LO] + built + bank[HI:], CLOCK_BANK, work,
                            "clock_" + name[:-3])
        ap[at + LO:at + HI] = built
        for site in TIMER_SITES:
            base.patch_bytes(ap, tat + site, TIMER_OLD, TIMER_NEW, name + " screensaver timer")
        b.put(name, ap)
        done.append("%s (%s)" % (name[:-3], result))
    return done


def clock_key(b):
    """The keyed draw's key 0xb5b6 -> 0 in every program with the clock routine."""
    done = []
    for name in b.programs():
        ap = b.get(name)
        segs, _ = ap_dis.segments(ap)
        bank = [(off, ln) for kind, addr, off, ln in segs if addr == CLOCK_BANK]
        if not bank:
            continue
        off, ln = bank[0]
        code = bytes(ap[off:off + ln])
        at = [i for i in range(0, ln - 3, 2) if code[i:i + 4] == movw(0, OLD_KEY)]
        if not at:
            continue
        if len(at) != 1 or at[0] not in KEY_OFFSETS or ap.count(movw(0, OLD_KEY)) != 1:
            fail("%s: the screensaver clock's key is not where expected" % name)
        ap[off + at[0]:off + at[0] + 4] = movw(0, NEW_KEY)
        b.put(name, ap)
        done.append(name[:-3])
    return done


def build(b):
    work = b.folder("screensaver")
    frames = pictures(b, work)
    patched = clock_routine(b, work)
    keyed = clock_key(b)
    b.note("screensaver: meadow with %d animation frames; clock routine in %s; key %#x -> %#x in %d programs",
           frames, ", ".join(patched), OLD_KEY, NEW_KEY, len(keyed))
