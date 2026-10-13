#!/usr/bin/env python3
"""Stage 8 of the Graphite design, built on the stage 7 image. Pictures only (COMMON.STY).

  1. Screensaver clock digits redrawn for the way the firmware really draws them.
     The display driver (DRV_UI.DRV, function 38 at 0x118a7a) first restores the background under a digit
     and then copies only those pixels of the digit picture whose 16-bit value is greater than 0xb5b6;
     everything else is treated as transparent. In practice a pixel needs red >= 184 of 255 to be drawn,
     so soft edges and dim colours disappear. The digits are therefore drawn solid, in bright colours only:
       time digits 158 to 167 (13 x 20), colon 170, AM/PM 168 and 169, date digits 147 to 156, dash 157.
  2. Battery notice: the firmware draws its own battery mark (pictures 248 and 322) on top of the notice
     panel (247 and 321). The panels lose the battery drawn into them in stage 6; the two marks are restyled.

usage: build_stage8.py [OUT_DIR]      (default: ../x91_dump/stage8)
"""
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import x91_design as xd  # noqa: E402
import x91_modify as xm  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage2 as s2  # noqa: E402
import build_stage4 as s4  # noqa: E402
import build_stage6 as s6  # noqa: E402

T = s1.T
KEY = 0xb5b6                              # the driver draws a pixel only if its value is greater than this
SOFT = (198, 200, 204)                    # the dimmest grey used; still above the key
DATE = (204, 208, 214)


def v565(c):
    return (c[0] >> 3) << 11 | (c[1] >> 2) << 5 | c[2] >> 3


def drawn(c):
    return v565(c) > KEY


def coverage(svg_text, w, h, work, name):
    """Render white-on-black artwork and return how much of each pixel is covered, 0 to 255."""
    data = s1.render_565(svg_text, w, h, work, name)
    return [((data[i] | data[i + 1] << 8) >> 5 & 63) * 255 // 63 for i in range(0, len(data), 2)]


def solid(cov, color, soft=None, full=0.70, part=0.36):
    """Covered pixels in the bright colour, half-covered ones in the soft grey (if given), the rest black."""
    out = []
    for c in cov:
        if c >= full * 255:
            out.append(v565(color))
        elif c >= part * 255:
            out.append(v565(soft or color))
        else:
            out.append(0)
    return struct.pack("<%dH" % len(out), *out)


def white_text(x, y, s, size, weight):
    return s6.text(x, y, s, size, weight, "#ffffff")


def white_svg(w, h, parts):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
            '<rect width="%d" height="%d" fill="#000000"/>%s</svg>' % (w, h, w, h, w, h, "".join(parts)))


def date_digit(ch):
    """Small digits as plain pixel shapes, the same ones as in the text font."""
    px = [0] * (9 * 11)
    if ch == "-":
        for x in range(2, 7):
            px[6 * 9 + x] = v565(DATE)
    else:
        width, top, pattern = s2.HAND[ch]
        for j, line in enumerate(pattern):
            for i, c in enumerate(line):
                if c == "#":
                    px[(j + 2) * 9 + i + 2] = v565(DATE)
    return struct.pack("<%dH" % len(px), *px)


def battery_mark(low):
    """The battery the firmware puts on the notice panel, 31 x 19."""
    c = s4.RED if low else T["accent"]
    return s1.svg(31, 19, ['<rect x="1.200" y="1.200" width="25.600" height="16.600" rx="4.500" %s/>' % s4.stroke(T["text2"], 1.6),
                           xd.rect(28, 6, 2.2, 7, 1.1, T["text2"]),
                           xd.rect(4.2, 4.2, 4.5 if low else 19.6, 10.6, 2, c)])


def notice_panel():
    return s1.svg(108, 100, ['<rect x="1" y="1" width="106" height="98" rx="10" %s/>' % s4.stroke(T["line"], 1.4)])


def edit_common(lfi, work):
    com = bytearray(lfi.get("COMMON.STY"))
    text_c, accent_c = s6.rgb(T["text"]), s6.rgb(T["accent"])
    if not (drawn(text_c) and drawn(SOFT) and drawn(DATE)):
        sys.exit("a clock colour would not be drawn by the firmware")
    for k in range(10):
        cov = coverage(white_svg(13, 20, [white_text(6.5, 17, str(k), 20, 500)]), 13, 20, work, "time-%d" % k)
        s1.set_picture(com, 158 + k, solid(cov, text_c, SOFT), 13, 20)
        s1.set_picture(com, 147 + k, date_digit(str(k)), 9, 11)
    s1.set_picture(com, 157, date_digit("-"), 9, 11)
    dots = accent_c if drawn(accent_c) else text_c            # an accent the firmware would not draw falls back to white
    cov = coverage(white_svg(13, 20, [xd.rect(5, 6, 3, 3, 0.4, "#ffffff"), xd.rect(5, 13, 3, 3, 0.4, "#ffffff")]), 13, 20, work, "time-colon")
    s1.set_picture(com, 170, solid(cov, dots), 13, 20)
    for index, word in ((168, "AM"), (169, "PM")):
        cov = coverage(white_svg(28, 20, [white_text(14, 17, word, 11.5, 700)]), 28, 20, work, "time-%s" % word.lower())
        s1.set_picture(com, index, solid(cov, DATE, full=0.5, part=0.5), 28, 20)
    put = lambda index, svg_text, w, h, name: s1.set_picture(com, index, s1.render_565(svg_text, w, h, work, name), w, h)
    put(247, notice_panel(), 108, 100, "notice-panel")
    put(321, notice_panel(), 108, 100, "notice-panel")
    put(248, battery_mark(False), 31, 19, "notice-battery")
    put(322, battery_mark(True), 31, 19, "notice-battery-low")
    # every pixel of the clock pictures is either black or bright enough to be drawn
    po = struct.unpack_from("<I", com, 0x10)[0]
    for index in list(range(147, 171)):
        off, ln = struct.unpack_from("<II", com, po + index * 16)
        vals = struct.unpack_from("<%dH" % (ln // 2), com, off)
        if any(0 < v <= KEY for v in vals):
            sys.exit("picture %d has pixels the firmware would drop" % index)
    lfi.put("COMMON.STY", bytes(com))


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage8")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE7") or os.path.join(ROOT, "x91_dump", "stage7", "x91_lfi_stage7.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 7 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    edit_common(lfi, work)
    print("clock digits redrawn for the driver's colour key; battery notice fixed")
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage8.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    names = [n for n in lfi.entries if lfi.get(n) != stock[lfi.entries[n][1]:lfi.entries[n][1] + lfi.entries[n][2]]]
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
