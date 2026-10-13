#!/usr/bin/env python3
"""Stage 4 of the Graphite design, built on the stage 3 image: the small shared pictures.

Pictures in COMMON.STY only; every picture keeps its size and place, nothing else changes.
  1. Status icons (file types, battery, Bluetooth) redrawn as line icons.
  2. Lists: radio marks at the end of a row, scrollbar, and the remaining blue row backgrounds.
  3. Charging pictures and the large battery marks.
  4. Leftover green and blue details (check marks, small folders) turned neutral.

usage: build_stage4.py [OUT_DIR]      (default: ../x91_dump/stage4)
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
import build_stage3 as s3  # noqa: E402

T = s1.T
RED = "#ff4d4d"


def stroke(color, width):
    return 'fill="none" stroke="%s" stroke-width="%g" stroke-linecap="round" stroke-linejoin="round"' % (color, width)


def status_icon(name, color):
    """File-type mark, 20 x 16."""
    if name == "lock":
        return s1.svg(20, 16, ['<rect x="5.5" y="7" width="9" height="7" rx="1.8" fill="%s"/>' % color,
                               '<path d="M7.3 7V5.4a2.700 2.700 0 0 1 5.400 0V7" %s/>' % stroke(color, 1.3)])
    return s1.svg(20, 16, [xd.icon(name, 3, 1, 14, color, 1.6 if name == "settings" else 2.2)])


def battery(level, low=False):
    """Status-bar battery, 20 x 13; level 0 to 4."""
    c = RED if low else T["text"]
    parts = ['<rect x="1.600" y="2.600" width="14.800" height="7.800" rx="2.200" %s/>' % stroke(RED if low else T["text2"], 1.2),
             xd.rect(17.4, 5, 1.6, 3, 0.8, RED if low else T["text2"])]
    if low:
        parts.append(xd.rect(3.5, 4.5, 2, 4, 0.6, c))
    for i in range(0 if low else level):
        parts.append(xd.rect(3.5 + i * 2.9, 4.5, 2.2, 4, 0.6, c))
    return s1.svg(20, 13, parts)


def charge_picture(level, bolt=False):
    """Charging animation, 50 x 34; level 0 to 4."""
    parts = ['<rect x="7" y="8" width="33" height="18" rx="5" %s/>' % stroke(T["text2"], 1.6),
             xd.rect(42, 13.5, 2.6, 7, 1.3, T["text2"])]
    for i in range(level):
        parts.append(xd.rect(10.5 + i * 6.7, 11.5, 5.2, 11, 1.6, T["accent"]))
    if bolt:
        parts.append('<path d="M25.500 9.500l-6 8.500h4.500l-1.500 6.500 6-8.500h-4.500z" fill="%s" stroke="%s" stroke-width="1.400" '
                     'stroke-linejoin="round"/>' % (T["text"], T["bg"]))
    return s1.svg(50, 34, parts)


def big_battery(low):
    """Battery mark, 20 x 20."""
    c = RED if low else T["accent"]
    return s1.svg(20, 20, ['<rect x="1.700" y="5.700" width="14.600" height="8.600" rx="2.400" %s/>' % stroke(T["text2"], 1.2),
                           xd.rect(17.3, 8.3, 1.6, 3.4, 0.8, T["text2"]),
                           xd.rect(3.6, 7.6, 2.2 if low else 10.8, 4.8, 0.9, c)])


def tail(active):
    """Mark at the end of a list row, 16 x 24. On the selected row it also has to continue the row panel."""
    if not active:
        return s1.svg(16, 24, ['<circle cx="7" cy="12" r="4" %s/>' % stroke(T["line"], 1.4)])
    return s1.svg(16, 24, [xd.rect(-20, 1.5, 34, 21, 6.5, T["surface"]),
                           '<circle cx="7" cy="12" r="4" %s/>' % stroke(T["accent"], 1.4),
                           '<circle cx="7" cy="12" r="1.900" fill="%s"/>' % T["accent"]])


def bar(h, color):
    return s1.svg(3, h, [xd.rect(1, 0, 1, h, 0, color)])


def neutral(data):
    """Turn the stock green into white and the stock blue into black, keeping each pixel's brightness."""
    out = bytearray(len(data))
    for i in range(0, len(data), 2):
        v = data[i] | data[i + 1] << 8
        r, g, b = (v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31
        hi, lo = max(r, g, b), min(r, g, b)
        if hi - lo > 40:
            if g == hi:                                   # green: keep as a grey of the same strength
                y = min(255, hi + 30)
                r, g, b = y, y, y
            else:                                         # blue backgrounds
                r, g, b = 0, 0, 0
        struct.pack_into("<H", out, i, (r >> 3) << 11 | (g >> 2) << 5 | b >> 3)
    return bytes(out)


def picture_bytes(sty, index):
    po = struct.unpack_from("<I", sty, 0x10)[0]
    off, ln, typ, w, h = struct.unpack_from("<IIHHH", sty, po + index * 16)
    return bytes(sty[off:off + ln]), w, h


def edit_common(lfi, work):
    com = bytearray(lfi.get("COMMON.STY"))
    n = 0

    def put(index, svg_text, w, h, name):
        nonlocal n
        s1.set_picture(com, index, s1.render_565(svg_text, w, h, work, name), w, h)
        n += 1

    for index, name, color in ((174, "folder", T["text"]), (175, "folder", T["accent"]), (176, "lock", T["text"]),
                               (178, "music", T["text"]), (179, "picture", T["text"]), (180, "radio", T["text"]),
                               (181, "mic", T["text"]), (182, "settings", T["text"]), (183, "video", T["text"]),
                               (184, "video", T["accent"])):
        put(index, status_icon(name, color), 20, 16, "status-%d-%s" % (index, name))
    for first in (188, 194):                               # two identical sets of six in the stock file
        for level in range(5):
            put(first + level, battery(level), 20, 13, "battery-%d" % level)
        put(first + 5, battery(0, low=True), 20, 13, "battery-low")
    for index, color in ((200, T["text"]), (202, T["accent"])):
        put(index, s1.svg(9, 13, [xd.icon("bluetooth", -2, 0, 13, color, 2.3)]), 9, 13, "bt-%d" % index)
    for level in range(5):
        put(206 + level, charge_picture(level), 50, 34, "charge-%d" % level)
    put(211, charge_picture(4, bolt=True), 50, 34, "charge-bolt")
    put(345, big_battery(False), 20, 20, "battery-big")
    put(346, big_battery(True), 20, 20, "battery-big-low")
    put(290, tail(False), 16, 24, "tail")
    put(291, tail(True), 16, 24, "tail-active")
    for index in range(295, 300):                          # the other "selected row" pictures, blue in the stock file
        put(index, s3.row_picture(125), 125, 24, "row-125")
    for index, h in ((310, 144), (311, 120), (312, 96), (313, 96)):
        put(index, bar(h, T["line"]), 3, h, "scroll-track-%d" % h)
    put(314, bar(79, T["text2"]), 3, 79, "scroll-thumb")
    put(315, bar(79, T["line"]), 3, 79, "scroll-thumb-off")
    for index in list(range(268, 279)) + list(range(283, 290)):
        data, w, h = picture_bytes(com, index)
        s1.set_picture(com, index, neutral(data), w, h)
        n += 1
    lfi.put("COMMON.STY", bytes(com))
    return n


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage4")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE3") or os.path.join(ROOT, "x91_dump", "stage3", "x91_lfi_stage3.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 3 image does not pass its checksums")
    print("shared pictures replaced: %d" % edit_common(lfi, work))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage4.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    names = [n for n in lfi.entries if lfi.get(n) != stock[lfi.entries[n][1]:lfi.entries[n][1] + lfi.entries[n][2]]]
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files that differ from the stock firmware:", ", ".join(sorted(names)))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
