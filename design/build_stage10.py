#!/usr/bin/env python3
"""Stage 10 of the Graphite design, built on the stage 9 image. Pictures and one layout field in COMMON.STY.

  1. Volume pop-up. The firmware shows it as a full-screen page: background picture, speaker icon and the
     number at y=40, and a 106-pixel bar with a knob at y=80 (slider record 5 of COMMON.STY).
       - new background: a rounded panel like the battery notice, stored in picture 233 (one of the unused
         demo pictures); the slider record's background field is pointed at it (it was the shared black 185)
       - speaker and mute icons, track, fill, knob and the piece that restores the track behind the knob
  2. Correction: stage 4 replaced the brightness slider's sun icon (pictures 345 and 346) with a battery.
     They are suns again.

usage: build_stage10.py [OUT_DIR]      (default: ../x91_dump/stage10)
"""
import hashlib
import math
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
import build_stage4 as s4  # noqa: E402

T = s1.T
stroke = s4.stroke
VOLUME_SLIDER, PANEL_PICTURE = 5, 233


def solid(w, h, rows):
    """A picture given as one colour (or None for black) per row."""
    out = []
    for c in rows:
        v = 0
        if c:
            r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
            v = (r >> 3) << 11 | (g >> 2) << 5 | b >> 3
        out += [v] * w
    return struct.pack("<%dH" % len(out), *out)


def speaker(muted):
    """18 x 16."""
    c = T["text2"] if muted else T["text"]
    parts = ['<path d="M2.500 6.200h2.600L8.600 3.300v9.400L5.100 9.800H2.500z" fill="%s" stroke="%s" stroke-width="1.200" '
             'stroke-linejoin="round"/>' % (c, c)]
    if muted:
        parts.append('<path d="M11.500 5.800l4 4.400M15.500 5.800l-4 4.400" %s/>' % stroke(T["text"], 1.5))
    else:
        parts.append('<path d="M11.300 5.600a3.400 3.400 0 0 1 0 4.800M13.600 3.600a6.200 6.200 0 0 1 0 8.800" %s/>' % stroke(c, 1.4))
    return s1.svg(18, 16, parts)


def sun():
    """Brightness icon, 20 x 20."""
    rays = []
    for k in range(8):
        a = math.radians(k * 45)
        rays.append("M%.2f %.2fL%.2f %.2f" % (10 + 6.2 * math.cos(a), 10 + 6.2 * math.sin(a), 10 + 8.4 * math.cos(a), 10 + 8.4 * math.sin(a)))
    return s1.svg(20, 20, ['<circle cx="10" cy="10" r="3.600" %s/>' % stroke(T["text"], 1.6),
                           '<path d="%s" %s/>' % ("".join(rays), stroke(T["text"], 1.6))])


def panel():
    return s1.svg(128, 160, ['<rect x="4.700" y="16.700" width="118.600" height="86.600" rx="12" %s/>' % stroke(T["line"], 1.4)])


def knob():
    return s1.svg(8, 8, ['<circle cx="4" cy="4" r="3.600" fill="%s"/>' % T["text"]])


def edit_common(lfi, work):
    com = bytearray(lfi.get("COMMON.STY"))
    put = lambda index, svg_text, w, h, name: s1.set_picture(com, index, s1.render_565(svg_text, w, h, work, name), w, h)
    put(406, speaker(False), 18, 16, "volume-speaker")
    put(384, speaker(True), 18, 16, "volume-mute")
    put(359, knob(), 8, 8, "volume-knob")
    s1.set_picture(com, 360, solid(8, 8, [None, None, None, T["line"], T["line"], None, None, None]), 8, 8)   # track without the knob
    s1.set_picture(com, 333, solid(106, 2, [T["line"]] * 2), 106, 2)     # track
    s1.set_picture(com, 353, solid(1, 2, [T["accent"]] * 2), 1, 2)       # filled part
    s1.set_picture(com, 354, solid(1, 2, [T["line"]] * 2), 1, 2)         # open part
    s1.set_picture(com, 358, solid(1, 2, [T["line"]] * 2), 1, 2)
    put(PANEL_PICTURE, panel(), 128, 160, "volume-panel")
    put(345, sun(), 20, 20, "brightness")
    put(346, sun(), 20, 20, "brightness")
    # slider record: four addresses, then background picture, x, y, icon picture, x, y, ...
    style = struct.unpack_from("<I", com, 8)[0]
    begin = struct.unpack_from("<I", com, style + 8)[0]
    table, count = struct.unpack_from("<II", com, begin + 9 * 8)
    rec = table + VOLUME_SLIDER * 48
    back, bx, by, icon, ix, iy = struct.unpack_from("<6H", com, rec + 16)
    if count <= VOLUME_SLIDER or (back, bx, by, icon, ix, iy) != (0x8000 | 185, 0, 0, 0x8000 | 406, 45, 40):
        sys.exit("COMMON.STY: the volume slider record is not the expected one")
    struct.pack_into("<H", com, rec + 16, 0x8000 | PANEL_PICTURE)
    lfi.put("COMMON.STY", bytes(com))


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage10")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE9") or os.path.join(ROOT, "x91_dump", "stage9", "x91_lfi_stage9.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 9 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    edit_common(lfi, work)
    print("volume pop-up restyled; brightness icon restored")
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage10.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
