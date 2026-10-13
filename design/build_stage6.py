#!/usr/bin/env python3
"""Stage 6 of the Graphite design, built on the stage 5 image. Pictures only; no program code.

  1. Bluetooth screen: the search animation (BT.STY).
  2. Shut-down animation: nine frames (END.STY).
  3. List icons: file-type icons of the folder view in two states, numbered marks,
     and the 113 remaining coloured icons turned into neutral tiles (COMMON.STY).
  4. Screensaver clock: large digits, colon, AM/PM and background; also the medium digits (COMMON.STY).
  5. Key-lock animation, battery notices, hearing notice (COMMON.STY).

usage: build_stage6.py [OUT_DIR]      (default: ../x91_dump/stage6)
"""
import collections
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
RED = s4.RED
stroke = s4.stroke


def rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, t):
    """Colour between a (t=0) and b (t=1)."""
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(rgb(a), rgb(b)))


def text(x, y, s, size, weight, fill, anchor="middle", spacing=0):
    return ('<text x="%g" y="%g" font-family="Ubuntu" font-weight="%d" font-size="%g" letter-spacing="%g" fill="%s" '
            'text-anchor="%s">%s</text>' % (x, y, weight, size, spacing, fill, anchor, s))


def arc(cx, cy, r, a0, a1, color, width):
    """Arc from angle a0 to a1 in degrees, clockwise, 0 = up."""
    p = lambda a: (cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a)))
    (x0, y0), (x1, y1) = p(a0), p(a1)
    return '<path d="M%.2f %.2fA%g %g 0 %d 1 %.2f %.2f" %s/>' % (x0, y0, r, r, 1 if (a1 - a0) % 360 > 180 else 0, x1, y1,
                                                             stroke(color, width))


# ------------------------------------------------------------------ Bluetooth and shut-down

def bt_spinner(frame):
    """Search animation, 48 x 48, six frames: an accent arc going round the Bluetooth mark."""
    a = frame * 60
    return s1.svg(48, 48, ['<circle cx="24" cy="24" r="20" %s/>' % stroke(T["line"], 2.4),
                           arc(24, 24, 20, a, a + 100, T["accent"], 2.4),
                           xd.icon("bluetooth", 13, 13, 22, T["text"], 2.0)])


def end_frame(k):
    """Shut-down, 128 x 160, nine frames: the start-up picture going dark."""
    t = k / 8.0
    tile = mix(T["accent"], T["surface"], min(1, t * 1.6)) if t < 0.8 else mix(T["surface"], "#000000", (t - 0.8) / 0.2)
    glyph = mix(T["on_accent"], T["text2"], min(1, t * 1.6)) if t < 0.8 else mix(T["text2"], "#000000", (t - 0.8) / 0.2)
    word = mix(T["text"], "#000000", min(1, t * 1.15))
    parts = [xd.rect(46, 44, 36, 36, 10, tile), xd.icon("music", 53, 51, 22, glyph),
             text(64, 107, "X91", 17, 700, word, spacing=1.5)]
    if k < 8:
        parts.append(xd.rect(54, 116, 20, 2, 1, mix(T["line"], "#000000", t)))
        left = 9 * (1 - t)
        if left >= 1:
            parts.append(xd.rect(54, 116, left, 2, 1, mix(T["accent"], "#000000", t * 0.6)))
    return s1.svg(128, 160, parts)


# ------------------------------------------------------------------ list icons

FILE_ICON = ('<path d="M7 3.500h7l4 4V19a1.500 1.500 0 0 1-1.500 1.500h-9.500A1.500 1.500 0 0 1 5.500 19V5A1.500 1.500 0 0 1 7 3.500z'
             'M13.500 3.800V8h4" %s/>')
FILE_TYPES = ["file", "folder", "music", "video", "book", "picture"]      # order in which the firmware numbers them


def glyph14(name, color):
    if name == "file":
        return '<g transform="scale(%.4f)">%s</g>' % (14 / 24.0, FILE_ICON % stroke(color, 2.3))
    return xd.icon(name, 0, 0, 14, color, 2.3)


def panel_under(hx, hy):
    """The piece of the selected-row panel that lies under an icon drawn at (hx, hy) within the row."""
    return '<g transform="translate(%d %d)">%s</g>' % (-hx, -hy, xd.rect(1, 1.5, 122, 21, 6.5, T["surface"]))


def number_mark(n, active):
    """Numbered mark, 14 x 13."""
    if active:
        return s1.svg(14, 13, [panel_under(0, 4), '<circle cx="7" cy="6.500" r="6" fill="%s"/>' % T["accent"],
                               text(7, 10, str(n), 9.5, 700, T["on_accent"])])
    return s1.svg(14, 13, ['<circle cx="7" cy="6.500" r="5.500" %s/>' % stroke(T["text2"], 1.1),
                           text(7, 10, str(n), 9.5, 500, T["text"])])


def neutral_tile(data):
    """A coloured icon tile with a white glyph becomes a dark tile with a light glyph."""
    px = [data[i] | data[i + 1] << 8 for i in range(0, len(data), 2)]
    to_rgb = lambda v: ((v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31)
    cols = [to_rgb(v) for v in px]
    counts = collections.Counter(c for c in cols if max(c) > 60 and max(c) - min(c) > 40)
    if not counts:
        return data
    tile = counts.most_common(1)[0][0]
    lo = min(range(3), key=lambda i: tile[i])
    hi = max(range(3), key=lambda i: tile[i])
    tn, wn = rgb(T["raised"]), rgb(T["text"])
    out = bytearray(len(data))
    for k, c in enumerate(cols):
        if c[lo] > tile[lo] + 12:                                   # some white mixed in: part of the glyph
            a = min(1.0, (c[lo] - tile[lo]) / max(1, 255 - tile[lo]))
            b = 1.0
        else:                                                       # tile or its rounded edge
            a = 0.0
            b = min(1.0, c[hi] / max(1, tile[hi]))
        r, g, bl = (int(b * (tn[i] + a * (wn[i] - tn[i]))) for i in range(3))
        struct.pack_into("<H", out, k * 2, (r >> 3) << 11 | (g >> 2) << 5 | bl >> 3)
    return bytes(out)


# ------------------------------------------------------------------ clock, lock, notices

def digit(ch, w, h, size, weight, baseline):
    return s1.svg(w, h, [text(w / 2.0, baseline, ch, size, weight, T["text"])])


def colon(w, h, y1, y2, r):
    return s1.svg(w, h, ['<circle cx="%g" cy="%g" r="%g" fill="%s"/>' % (w / 2.0, y, r, T["accent"]) for y in (y1, y2)])


def clock_background():
    return s1.svg(128, 160, [xd.rect(54, 114, 20, 2, 1, T["line"]), xd.rect(54, 114, 9, 2, 1, T["accent"])])


def padlock(frame):
    """Key lock, 36 x 44, five frames from open to closed."""
    d = [7, 5, 3, 1, 0][frame]
    color = T["accent"] if frame == 4 else T["text"]
    top = 9 - d
    right_end = 21 - d * 1.3 if d else 21
    shackle = ('<path d="M11.500 21V%g a6.500 6.500 0 0 1 13 0V%g" %s/>' % (top + 6.5, right_end, stroke(color, 2.4)))
    return s1.svg(36, 44, [shackle, xd.rect(6, 21, 24, 18, 4.5, color),
                           '<circle cx="18" cy="29" r="2.300" fill="%s"/>' % T["bg"],
                           xd.rect(17.1, 29, 1.8, 5, 0.9, T["bg"])])


def battery_notice(low):
    """Notice behind "Charged." / "Low battery...", 108 x 100; the firmware writes the text into the lower half."""
    c = RED if low else T["accent"]
    return s1.svg(108, 100, ['<rect x="1" y="1" width="106" height="98" rx="10" %s/>' % stroke(T["line"], 1.4),
                             '<rect x="35" y="17" width="34" height="20" rx="5.500" %s/>' % stroke(T["text2"], 1.8),
                             xd.rect(70.5, 23, 3, 8, 1.5, T["text2"]),
                             xd.rect(39, 21, 6 if low else 26, 12, 2.5, c)])


def hearing_notice():
    """Shown by the firmware as a full-screen notice about loud listening; the stock picture has Chinese text."""
    return s1.svg(128, 160, ['<rect x="10" y="26" width="108" height="108" rx="14" %s/>' % stroke(T["line"], 1.4),
                             xd.icon("speaker", 40, 44, 48, T["accent"], 1.8),
                             text(64, 112, "High volume", 12, 500, T["text"]),
                             text(64, 126, "can harm hearing", 10.5, 400, T["text2"])])


# ------------------------------------------------------------------ build

def edit_common(lfi, work):
    com = bytearray(lfi.get("COMMON.STY"))
    n = 0

    def put(index, svg_text, w, h, name):
        nonlocal n
        s1.set_picture(com, index, s1.render_565(svg_text, w, h, work, name), w, h)
        n += 1

    for index in range(113):                                # generic coloured icons
        data, w, h = s4.picture_bytes(com, index)
        s1.set_picture(com, index, neutral_tile(data), w, h)
        n += 1
    for k, name in enumerate(FILE_TYPES):                   # folder view: normal and selected
        put(113 + k, s1.svg(14, 14, [glyph14(name, T["text2"])]), 14, 14, "list-%s" % name)
        put(119 + k, s1.svg(14, 14, [panel_under(1, 5), glyph14(name, T["accent"])]), 14, 14, "list-%s-on" % name)
    for k in range(6):
        put(251 + k, number_mark(k + 1, True), 14, 13, "mark-%d-on" % (k + 1))
        put(257 + k, number_mark(k + 1, False), 14, 13, "mark-%d" % (k + 1))

    for k in range(10):                                     # screensaver clock and medium digits
        put(366 + k, digit(str(k), 18, 28, 29, 300, 25), 18, 28, "clock-%d" % k)
        put(158 + k, digit(str(k), 13, 20, 20, 400, 17), 13, 20, "digit-%d" % k)
    put(377, colon(8, 23, 7, 17, 2), 8, 23, "clock-colon")
    put(170, colon(13, 20, 7, 14, 1.6), 13, 20, "digit-colon")
    put(168, s1.svg(28, 20, [text(14, 17, "AM", 12, 500, T["text2"])]), 28, 20, "clock-am")
    put(169, s1.svg(28, 20, [text(14, 17, "PM", 12, 500, T["text2"])]), 28, 20, "clock-pm")
    put(187, clock_background(), 128, 160, "clock-background")

    for frame in range(5):
        put(316 + frame, padlock(frame), 36, 44, "lock-%d" % frame)
    put(247, battery_notice(False), 108, 100, "notice-charged")
    put(321, battery_notice(True), 108, 100, "notice-low")
    put(416, hearing_notice(), 128, 160, "notice-hearing")
    lfi.put("COMMON.STY", bytes(com))
    return n


def edit_bluetooth(lfi, work):
    sty = bytearray(lfi.get("BT.STY"))
    for frame in range(6):
        s1.set_picture(sty, 1 + frame, s1.render_565(bt_spinner(frame), 48, 48, work, "bt-search-%d" % frame), 48, 48)
    lfi.put("BT.STY", bytes(sty))
    return 6


def edit_shutdown(lfi, work):
    sty = bytearray(lfi.get("END.STY"))
    for k in range(9):
        s1.set_picture(sty, k, s1.render_565(end_frame(k), 128, 160, work, "end-%d" % k), 128, 160)
    lfi.put("END.STY", bytes(sty))
    return 9


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage6")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE5") or os.path.join(ROOT, "x91_dump", "stage5", "x91_lfi_stage5.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 5 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    print("shared pictures replaced: %d" % edit_common(lfi, work))
    print("Bluetooth search frames: %d" % edit_bluetooth(lfi, work))
    print("shut-down frames: %d" % edit_shutdown(lfi, work))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage6.bin")
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
