#!/usr/bin/env python3
"""Stage 2 of the Graphite design: a new typeface in the firmware's 16-row bitmap font.

UNICODE.FON holds 65536 glyphs of 33 bytes: 16 rows of one byte (width up to 8) or two bytes
(width 9 to 16), most significant bit left, and the advance width in the last byte. This replaces
the Latin, Greek and Cyrillic glyphs with a system font rendered to one bit, and leaves the rest.

usage: build_stage2.py [BASE_IMAGE] [OUT_DIR]
       defaults: ../x91_dump/stage1/x91_lfi_stage1.bin and ../x91_dump/stage2
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import cairo  # noqa: E402
import x91_modify as xm  # noqa: E402

FAMILY, SIZE, BASELINE = "Ubuntu", 12, 13      # caps then sit on rows 4 to 12, as in the stock font
RANGES = [(0x21, 0x7E), (0xA1, 0xFF), (0x100, 0x17F), (0x384, 0x3CE), (0x400, 0x45F),
          (0x2010, 0x2026), (0x20AC, 0x20AC), (0x2122, 0x2122)]
G = 33

# Glyphs drawn by hand where the automatic one-bit rendering reads badly at this size:
# the lowercase f came out looking like a capital F, S looked like 5, and the digits were uneven.
# Capitals and digits occupy rows 5 to 12, ascenders start at row 4.
# Each entry: advance width, first row, rows as text ("#" = lit), starting at column 1.
HAND = {
    "f": (5, 4, ["..##", ".#..", ".#..", "###.", ".#..", ".#..", ".#..", ".#..", ".#.."]),
    "t": (5, 5, [".#..", ".#..", "###.", ".#..", ".#..", ".#..", ".#..", "..##"]),
    "S": (7, 5, [".###.", "#...#", "#....", ".###.", "....#", "....#", "#...#", ".###."]),
    # the automatic M, N, O and Q came out with a doubled right-hand stroke (seen on the player as a "boot" on the M)
    "M": (9, 5, ["#.....#", "##...##", "#.#.#.#", "#..#..#", "#.....#", "#.....#", "#.....#", "#.....#"]),
    "N": (8, 5, ["#....#", "##...#", "#.#..#", "#.#..#", "#..#.#", "#..#.#", "#...##", "#....#"]),
    "O": (9, 5, [".#####.", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", ".#####."]),
    "Q": (9, 5, [".#####.", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", ".#####.", "....#..", ".....##"]),
    "0": (7, 5, [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."]),
    "1": (7, 5, ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."]),
    "2": (7, 5, [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#....", "#####"]),
    "3": (7, 5, [".###.", "#...#", "....#", "..##.", "....#", "....#", "#...#", ".###."]),
    "4": (7, 5, ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#.", "...#."]),
    "5": (7, 5, ["#####", "#....", "#....", "####.", "....#", "....#", "#...#", ".###."]),
    "6": (7, 5, [".###.", "#...#", "#....", "####.", "#...#", "#...#", "#...#", ".###."]),
    "7": (7, 5, ["#####", "....#", "...#.", "...#.", "..#..", "..#..", ".#...", ".#..."]),
    "8": (7, 5, [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", "#...#", ".###."]),
    "9": (7, 5, [".###.", "#...#", "#...#", "#...#", ".####", "....#", "#...#", ".###."]),
}


def hand_glyph(ch):
    width, top, pattern = HAND[ch]
    rows = [0] * 16
    for i, line in enumerate(pattern):
        for x, c in enumerate(line):
            if c == "#":
                rows[top + i] |= 0x8000 >> (x + 1)
    return width, rows


def tidy(rows):
    """Remove the single stray pixel that one-bit hinting leaves above or below a round stroke."""
    used = [y for y in range(16) if rows[y]]
    if len(used) < 4:
        return rows
    for edge, inner in ((used[0], used[0] + 1), (used[-1], used[-1] - 1)):
        bits = rows[edge]
        if bin(bits).count("1") == 1 and (rows[inner] & (bits << 1)) and (rows[inner] & (bits >> 1)) and (rows[inner] & bits):
            rows[edge] = 0
    return rows


def rasterise(ch):
    """One glyph as (width, rows) with rows as 16 integers, bit 15 = leftmost column; None if it does not fit."""
    if ch in HAND:
        return hand_glyph(ch)
    s = cairo.ImageSurface(cairo.FORMAT_RGB24, 24, 16)
    c = cairo.Context(s)
    fo = cairo.FontOptions()
    fo.set_antialias(cairo.ANTIALIAS_NONE)
    fo.set_hint_style(cairo.HINT_STYLE_FULL)
    fo.set_hint_metrics(cairo.HINT_METRICS_ON)
    c.set_font_options(fo)
    c.select_font_face(FAMILY, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    c.set_font_size(SIZE)
    ext = c.text_extents(ch)
    pen = max(0, -int(round(ext.x_bearing)))
    c.set_source_rgb(1, 1, 1)
    c.move_to(pen, BASELINE)
    c.show_text(ch)
    s.flush()
    d, stride = bytes(s.get_data()), s.get_stride()
    rows, right = [], -1
    for y in range(16):
        bits = 0
        for x in range(16):
            if d[y * stride + x * 4 + 1] > 127:
                bits |= 0x8000 >> x
                right = max(right, x)
        if any(d[y * stride + x * 4 + 1] > 127 for x in range(16, 24)):
            return None                         # wider than the format allows
        rows.append(bits)
    if right < 0:
        return None
    rows = tidy(rows)
    width = max(int(round(ext.x_advance)) + pen, right + 2)   # keep at least one empty column after the ink
    if width > 16:
        return None
    return width, rows


def encode(width, rows):
    g = bytearray(G)
    for y, bits in enumerate(rows):
        if width <= 8:
            g[y] = bits >> 8
        else:
            g[2 * y], g[2 * y + 1] = bits >> 8, bits & 0xFF
    g[32] = width
    return bytes(g)


def new_font(lfi):
    """Replace the glyphs in the image's UNICODE.FON; returns (replaced, kept as stock, wider than 8)."""
    font = bytearray(lfi.get("UNICODE.FON"))
    if len(font) < 65536 * G:
        sys.exit("unexpected font file size")
    done, skipped, wide = 0, [], 0
    for lo, hi in RANGES:
        for cp in range(lo, hi + 1):
            if not any(font[cp * G:cp * G + 32]):
                continue                        # the stock font has no glyph here; leave it empty
            r = rasterise(chr(cp))
            if r is None:
                skipped.append(cp)
                continue
            font[cp * G:(cp + 1) * G] = encode(*r)
            done += 1
            wide += r[0] > 8
    lfi.put("UNICODE.FON", bytes(font))
    return done, skipped, wide


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage1", "x91_lfi_stage1.bin")
    out = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(ROOT, "x91_dump", "stage2")
    os.makedirs(out, exist_ok=True)
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the base image does not pass its checksums")
    done, skipped, wide = new_font(lfi)
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage2.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    names = [n for n in lfi.entries if lfi.get(n) != stock[lfi.entries[n][1]:lfi.entries[n][1] + lfi.entries[n][2]]]
    print("glyphs replaced: %d (of which %d are wider than 8 pixels); kept as stock: %d" % (done, wide, len(skipped)))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files that differ from the stock firmware:", ", ".join(sorted(names)))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
