#!/usr/bin/env python3
"""Stage 7 of the Graphite design, built on the stage 6 image.

  1. Screensaver clock: the firmware draws it by code (time and date at the top, one full-screen
     background picture, a timer that only redraws when the minute changes). This stage
       - replaces the background (picture 171 of COMMON.STY) with a night meadow,
       - adds an animation below the clock: a pink jelly blob hopping in the grass, 12 frames.
         The frames reuse the first 12 pictures of the unused "demo" screensaver (221 to 232),
         declared smaller (56 x 80). Program code: the start of the shared clock routine is rewritten
         to draw the next frame on every timer tick (patches/clock_sprite.S), and the timer runs
         every 200 ms instead of 500 ms. The same change goes into the seven programs one can be in
         when the screensaver starts: main menu, Music, Folder, Bluetooth, eBook, Settings, Tools.
       - restyles the small date digits.
  2. Folder view icons moved down by one pixel so they line up with the text.
  3. Bluetooth search animation: three arcs turning 20 degrees per frame instead of one arc turning 60.

usage: build_stage7.py [OUT_DIR]      (default: ../x91_dump/stage7)
"""
import hashlib
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import ap_dis  # noqa: E402
import x91_design as xd  # noqa: E402
import x91_modify as xm  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage4 as s4  # noqa: E402
import build_stage6 as s6  # noqa: E402

T = s1.T
stroke = s4.stroke

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


def meadow():
    """Background without the blob: black sky, a band of grass with a few flowers in the accent colour."""
    px = [[C["sky"]] * ART_W for _ in range(ART_H)]
    accent = s6.rgb(T["accent"])
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
        px[y][x] = s6.rgb(T["line"])
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


# ------------------------------------------------------------------ pictures

def resize_picture(sty, index, w, h):
    """Declare a picture smaller than it was; its data keeps its place, the rest of its old space stays unused."""
    po = struct.unpack_from("<I", sty, 0x10)[0]
    off, ln, typ, pw, ph = struct.unpack_from("<IIHHH", sty, po + index * 16)
    if w * h * 2 > ln:
        sys.exit("picture %d: no room for %dx%d" % (index, w, h))
    struct.pack_into("<IIHHH", sty, po + index * 16, off, w * h * 2, typ, w, h)


def bt_spinner(frame):
    parts = ['<circle cx="24" cy="24" r="20" %s/>' % stroke(T["line"], 2.4)]
    for k in range(3):
        a = frame * 20 + k * 120
        parts.append(s6.arc(24, 24, 20, a, a + 55, T["accent"], 2.4))
    parts.append(xd.icon("bluetooth", 13, 13, 22, T["text"], 2.0))
    return s1.svg(48, 48, parts)


def edit_pictures(lfi, work):
    com = bytearray(lfi.get("COMMON.STY"))
    frames = animation()
    x0, y0, w, h = RECT
    for k, px in enumerate(frames):
        resize_picture(com, 221 + k, w * 2, h * 2)
        s1.set_picture(com, 221 + k, to_565(px, x0, y0, w, h), w * 2, h * 2)
    s1.set_picture(com, 171, to_565(frames[0], 0, 0, ART_W, ART_H), 128, 160)
    put = lambda index, svg_text, pw, ph, name: s1.set_picture(com, index, s1.render_565(svg_text, pw, ph, work, name), pw, ph)
    date = s6.mix(T["text"], T["text2"], 0.45)
    for k in range(10):
        put(147 + k, s1.svg(9, 11, [s6.text(4.5, 10, str(k), 11.5, 500, date)]), 9, 11, "date-%d" % k)
    put(157, s1.svg(9, 11, [xd.rect(2, 5.3, 5, 1.4, 0.7, date)]), 9, 11, "date-dash")
    down = lambda g: '<g transform="translate(0 1)">%s</g>' % g
    for k, name in enumerate(s6.FILE_TYPES):
        put(113 + k, s1.svg(14, 14, [down(s6.glyph14(name, T["text2"]))]), 14, 14, "list-%s" % name)
        put(119 + k, s1.svg(14, 14, [s6.panel_under(1, 5), down(s6.glyph14(name, T["accent"]))]), 14, 14, "list-%s-on" % name)
    lfi.put("COMMON.STY", bytes(com))
    bt = bytearray(lfi.get("BT.STY"))
    for frame in range(6):
        s1.set_picture(bt, 1 + frame, s1.render_565(bt_spinner(frame), 48, 48, work, "bt-search-%d" % frame), 48, 48)
    lfi.put("BT.STY", bytes(bt))
    return frames


# ------------------------------------------------------------------ program patch

PROGRAMS = ["MAINMENU.AP", "MUSIC.AP", "BROWSER.AP", "BT.AP", "EBOOK.AP", "SETTING.AP", "TOOLS.AP"]
CLOCK_BANK, TIMER_BANK = 0x18ce1a00, 0x18cc1a00
LO, HI = 0x034, 0x0c6
STOCK_REGION = "1b641267ec1c5875"
TIMER_SITES = (0x066, 0x34a)                                   # mov.w r1, #500
TIMER_OLD, TIMER_NEW = bytes.fromhex("4ff4fa71"), bytes.fromhex("4ff0c801")   # -> mov.w r1, #200


def disassemble(data, path):
    tmp = path + ".bin"
    open(tmp, "wb").write(data)
    r = subprocess.run(["arm-none-eabi-objdump", "-D", "-b", "binary", "-marm", "-Mforce-thumb",
                        "--adjust-vma=%#x" % CLOCK_BANK, tmp], capture_output=True, text=True)
    os.remove(tmp)
    open(path, "w").write(r.stdout)
    return path


def patch_clock(lfi, work):
    src = os.path.join(HERE, "patches", "clock_sprite.S")
    obj, raw = os.path.join(work, "clock_patch.o"), os.path.join(work, "clock_patch.bin")
    for cmd in (["arm-none-eabi-as", "-o", obj, src], ["arm-none-eabi-objcopy", "-O", "binary", obj, raw]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit("could not assemble the clock patch: " + r.stderr[-300:])
    built = open(raw, "rb").read()[LO:HI]
    os.remove(raw)
    done = []
    for name in PROGRAMS:
        ap = bytearray(lfi.get(name))
        segs, _ = ap_dis.segments(ap)
        base, tbase = ap_dis.find(segs, CLOCK_BANK), ap_dis.find(segs, TIMER_BANK)
        if base is None or tbase is None:
            sys.exit("%s: the screensaver code is not where expected" % name)
        bank = bytes(ap[base:base + 0x458])
        if hashlib.sha256(bank[LO:HI]).hexdigest()[:16] != STOCK_REGION:
            sys.exit("%s: the clock routine is not the expected one" % name)
        last_minute = struct.unpack_from("<I", bank, 0x3ec)[0]
        demo_index = struct.unpack_from("<I", ap, tbase + 0x194)[0]
        if demo_index != last_minute - 4 or bank[0x14a:0x14c] != bytes.fromhex("47e1"):
            sys.exit("%s: the variables the patch relies on are laid out differently" % name)
        new_bank = bank[:LO] + built + bank[HI:]
        old_dis = disassemble(bank, os.path.join(work, "clock_%s_old.dis" % name[:-3]))
        new_dis = disassemble(new_bank, os.path.join(work, "clock_%s_new.dis" % name[:-3]))
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "patches", "check_clock_patch.py"), old_dis, new_dis],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit("%s: the clock patch failed its side-by-side check:\n%s%s" % (name, r.stdout[-600:], r.stderr[-300:]))
        ap[base + LO:base + HI] = built
        for site in TIMER_SITES:
            s5_patch(ap, tbase + site, TIMER_OLD, TIMER_NEW, name + " timer")
        lfi.put(name, bytes(ap))
        done.append("%s (%s)" % (name, r.stdout.strip()))
    return done


def s5_patch(buf, offset, old, new, what):
    if bytes(buf[offset:offset + len(old)]) != old:
        sys.exit("%s: unexpected bytes at %#x, not patching" % (what, offset))
    buf[offset:offset + len(new)] = new


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage7")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE6") or os.path.join(ROOT, "x91_dump", "stage6", "x91_lfi_stage6.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 6 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    edit_pictures(lfi, work)
    print("pictures: meadow background, %d animation frames, date digits, folder icons, Bluetooth search" % len(FRAMES))
    for line in patch_clock(lfi, work):
        print("clock routine patched in", line)
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage7.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    names = [n for n in lfi.entries if lfi.get(n) != stock[lfi.entries[n][1]:lfi.entries[n][1] + lfi.entries[n][2]]]
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  files that differ from the stock firmware:", ", ".join(sorted(names)))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
